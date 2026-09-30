// Package hostmetrics records local call statistics: how many times an
// operation ran, how long it took, and how often it succeeded.
//
// This is not telemetry. Nothing is uploaded; events are appended to a local
// JSONL file with a rolling cap. The registry exists so that claims like
// "downloads got slower" can be turned into a p95 number instead of a feeling.
package hostmetrics

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// Event is one recorded call.
type Event struct {
	TS         time.Time         `json:"ts"`
	Subsystem  string            `json:"subsystem"`
	Operation  string            `json:"operation"`
	OK         bool              `json:"ok"`
	DurationMs int64             `json:"durationMs"`
	Meta       map[string]string `json:"meta,omitempty"`
}

// Summary is the aggregation of events for one subsystem.operation.
type Summary struct {
	Subsystem   string  `json:"subsystem"`
	Operation   string  `json:"operation"`
	Count       int     `json:"count"`
	OKCount     int     `json:"okCount"`
	FailCount   int     `json:"failCount"`
	SuccessRate float64 `json:"successRate"`
	P50Ms       int64   `json:"p50Ms"`
	P95Ms       int64   `json:"p95Ms"`
	MaxMs       int64   `json:"maxMs"`
	AvgMs       int64   `json:"avgMs"`
	LastMs      int64   `json:"lastMs"`
}

// Options configures a Registry.
type Options struct {
	// Dir is where metrics.jsonl lives.
	Dir string
	// Enabled false disables recording entirely: nothing is written to disk.
	Enabled bool
	// MaxEvents is the rolling cap (0 means the default).
	MaxEvents int
	// Logger receives non-fatal problems such as a failed disk write.
	Logger func(string)
}

const defaultMaxEvents = 5000

// Registry records events and computes aggregates.
type Registry struct {
	mu        sync.Mutex
	events    []Event
	maxEvents int
	file      string
	enabled   bool
	logger    func(string)
}

// New creates a Registry.
func New(opts Options) *Registry {
	maxEvents := opts.MaxEvents
	if maxEvents <= 0 {
		maxEvents = defaultMaxEvents
	}
	return &Registry{
		events:    make([]Event, 0),
		maxEvents: maxEvents,
		file:      filepath.Join(opts.Dir, "metrics.jsonl"),
		enabled:   opts.Enabled,
		logger:    opts.Logger,
	}
}

// Record adds one event and schedules persistence. Persistence failures are
// logged and otherwise ignored: statistics must never break the operation they
// measure.
func (r *Registry) Record(e Event) {
	if !r.enabled {
		return
	}
	if e.TS.IsZero() {
		e.TS = time.Now()
	}
	r.mu.Lock()
	r.events = append(r.events, e)
	if len(r.events) > r.maxEvents {
		r.events = append(r.events[:0], r.events[len(r.events)-r.maxEvents:]...)
	}
	r.mu.Unlock()
	go r.persist(e)
}

// Timed runs fn and records the outcome, including on failure — a slow failure
// and a fast failure are different problems. The error from fn is returned
// unchanged, so instrumenting never alters control flow.
func (r *Registry) Timed(subsystem, operation string, fn func() error, meta map[string]string) error {
	start := time.Now()
	err := fn()
	r.Record(Event{
		TS:         time.Now(),
		Subsystem:  subsystem,
		Operation:  operation,
		OK:         err == nil,
		DurationMs: time.Since(start).Milliseconds(),
		Meta:       meta,
	})
	return err
}

// Summary aggregates events per subsystem.operation, sorted by call count.
func (r *Registry) Summary() []Summary {
	r.mu.Lock()
	defer r.mu.Unlock()
	groups := map[string][]Event{}
	order := make([]string, 0)
	for _, e := range r.events {
		key := e.Subsystem + "." + e.Operation
		if _, ok := groups[key]; !ok {
			order = append(order, key)
		}
		groups[key] = append(groups[key], e)
	}
	out := make([]Summary, 0, len(groups))
	for _, key := range order {
		list := groups[key]
		durations := make([]int64, 0, len(list))
		okCount := 0
		var total int64
		for _, e := range list {
			durations = append(durations, e.DurationMs)
			total += e.DurationMs
			if e.OK {
				okCount++
			}
		}
		sort.Slice(durations, func(i, j int) bool { return durations[i] < durations[j] })
		idx := strings.LastIndex(key, ".")
		out = append(out, Summary{
			Subsystem:   key[:idx],
			Operation:   key[idx+1:],
			Count:       len(list),
			OKCount:     okCount,
			FailCount:   len(list) - okCount,
			SuccessRate: float64(okCount) / float64(len(list)),
			P50Ms:       Percentile(durations, 0.5),
			P95Ms:       Percentile(durations, 0.95),
			MaxMs:       durations[len(durations)-1],
			AvgMs:       total / int64(len(list)),
			LastMs:      list[len(list)-1].DurationMs,
		})
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Count > out[j].Count })
	return out
}

// Report renders the aggregates as a fixed-width table.
func (r *Registry) Report() string {
	rows := r.Summary()
	if len(rows) == 0 {
		return "no call statistics recorded (metrics disabled or nothing called yet)"
	}
	var b strings.Builder
	fmt.Fprintf(&b, "%-24s %6s %5s %5s %7s %8s %8s %8s %8s\n",
		"subsystem.operation", "count", "ok", "fail", "rate", "p50", "p95", "max", "last")
	for _, s := range rows {
		fmt.Fprintf(&b, "%-24s %6d %5d %5d %6.1f%% %7dms %7dms %7dms %7dms\n",
			s.Subsystem+"."+s.Operation, s.Count, s.OKCount, s.FailCount,
			s.SuccessRate*100, s.P50Ms, s.P95Ms, s.MaxMs, s.LastMs)
	}
	return strings.TrimRight(b.String(), "\n")
}

// Load reads the persisted events back. Corrupt lines are skipped so one bad
// record does not cost the entire history.
func (r *Registry) Load() (int, error) {
	f, err := os.Open(r.file)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, nil
		}
		return 0, err
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	loaded := make([]Event, 0)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var e Event
		if err := json.Unmarshal([]byte(line), &e); err != nil {
			continue
		}
		loaded = append(loaded, e)
	}
	r.mu.Lock()
	r.events = append(r.events, loaded...)
	if len(r.events) > r.maxEvents {
		r.events = append(r.events[:0], r.events[len(r.events)-r.maxEvents:]...)
	}
	n := len(r.events)
	r.mu.Unlock()
	return n, scanner.Err()
}

// Reset clears both memory and the persisted file.
func (r *Registry) Reset() error {
	r.mu.Lock()
	r.events = r.events[:0]
	r.mu.Unlock()
	return os.WriteFile(r.file, nil, 0o600)
}

func (r *Registry) persist(e Event) {
	line, err := json.Marshal(e)
	if err != nil {
		return
	}
	if err := os.MkdirAll(filepath.Dir(r.file), 0o700); err != nil {
		r.log(err.Error())
		return
	}
	f, err := os.OpenFile(r.file, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		r.log(err.Error())
		return
	}
	defer f.Close()
	if _, err := f.Write(append(line, '\n')); err != nil {
		r.log(err.Error())
	}
}

func (r *Registry) log(msg string) {
	if r.logger != nil {
		r.logger("hostmetrics: " + msg)
	}
}

// Percentile returns the p-th percentile of a sorted slice.
func Percentile(sorted []int64, p float64) int64 {
	if len(sorted) == 0 {
		return 0
	}
	rank := int(p*float64(len(sorted)) + 0.999999)
	if rank < 1 {
		rank = 1
	}
	if rank > len(sorted) {
		rank = len(sorted)
	}
	return sorted[rank-1]
}

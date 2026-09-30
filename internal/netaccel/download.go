package netaccel

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Source is one candidate URL for the same artifact. Direct belongs first.
type Source struct {
	ID  string
	URL string
}

// Request describes a download.
type Request struct {
	Sources []Source
	// Destination is the final file path.
	Destination string
	// ExpectedSHA256, when non-empty, is enforced: a mismatch discards the
	// artifact and falls through to the next source.
	ExpectedSHA256 string
	// Connections is the number of concurrent Range requests (0 → 4).
	Connections int
	// ChunkBytes is the size of one Range chunk (0 → 1 MiB).
	ChunkBytes int64
	// MinSizeForChunks: artifacts smaller than this are fetched in one request.
	MinSizeForChunks int64
	// Resume continues from an existing chunk state file.
	Resume bool
	// Timeout applies to each individual HTTP request (0 → 30s).
	Timeout time.Duration
	// Logger receives progress and fallback decisions.
	Logger func(string)
}

// Result describes a completed download.
type Result struct {
	Source        string
	Bytes         int64
	SHA256        string
	UsedChunks    bool
	Chunks        int
	ResumedChunks int
	Retries       int
}

type chunkState struct {
	Index int   `json:"index"`
	Start int64 `json:"start"`
	End   int64 `json:"end"`
	Done  bool  `json:"done"`
}

type resumeState struct {
	URL        string       `json:"url"`
	Size       int64        `json:"size"`
	ChunkBytes int64        `json:"chunkBytes"`
	Chunks     []chunkState `json:"chunks"`
}

// Download fetches the artifact, trying chunked transfer when the source
// supports Range requests and the artifact is large enough to be worth it.
// Every source is tried in order; a checksum mismatch discards the artifact
// rather than returning unverified bytes.
func Download(ctx context.Context, req Request) (Result, error) {
	if len(req.Sources) == 0 {
		return Result{}, fmt.Errorf("netaccel: no download sources")
	}
	if err := os.MkdirAll(filepath.Dir(req.Destination), 0o700); err != nil {
		return Result{}, err
	}
	failures := make([]string, 0, len(req.Sources))
	for _, src := range req.Sources {
		res, err := downloadFrom(ctx, req, src)
		if err != nil {
			failures = append(failures, src.ID+": "+err.Error())
			cleanup(req.Destination)
			continue
		}
		if req.ExpectedSHA256 != "" && !strings.EqualFold(res.SHA256, strings.TrimSpace(req.ExpectedSHA256)) {
			logf(req.Logger, "download: %s checksum mismatch, discarding artifact and trying next source", src.ID)
			failures = append(failures, src.ID+": checksum mismatch")
			_ = os.Remove(req.Destination)
			cleanup(req.Destination)
			continue
		}
		return res, nil
	}
	return Result{}, fmt.Errorf("netaccel: all sources failed: %s", strings.Join(failures, " | "))
}

func downloadFrom(ctx context.Context, req Request, src Source) (Result, error) {
	timeout := req.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	client := &http.Client{Timeout: timeout}
	size, acceptRanges, err := probe(ctx, client, src.URL)
	if err != nil {
		return Result{}, err
	}
	chunkBytes := req.ChunkBytes
	if chunkBytes <= 0 {
		chunkBytes = 1 << 20
	}
	minSize := req.MinSizeForChunks
	if minSize <= 0 {
		minSize = 8 << 20
	}

	if !acceptRanges || size <= 0 || size < minSize {
		if err := downloadSingle(ctx, client, src.URL, req.Destination); err != nil {
			return Result{}, err
		}
		sum, err := sha256File(req.Destination)
		if err != nil {
			return Result{}, err
		}
		return Result{Source: src.ID, Bytes: size, SHA256: sum, Chunks: 1}, nil
	}

	total := int((size + chunkBytes - 1) / chunkBytes)
	state := loadState(req.Destination, src.URL, size, chunkBytes, total, req.Resume)
	pending := make([]int, 0)
	for i, c := range state.Chunks {
		if !c.Done {
			pending = append(pending, i)
		}
	}
	resumed := len(state.Chunks) - len(pending)

	connections := req.Connections
	if connections <= 0 {
		connections = 4
	}
	runCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	// Jobs carry a value copy of the chunk so workers never touch state.
	type job struct {
		idx int
		c   chunkState
	}
	jobList := make([]job, 0, len(pending))
	for _, idx := range pending {
		jobList = append(jobList, job{idx: idx, c: state.Chunks[idx]})
	}

	jobs := make(chan job)
	doneCh := make(chan int, len(pending))
	failCh := make(chan error, len(pending))
	var wg sync.WaitGroup
	var retries int64

	worker := func() {
		defer wg.Done()
		for j := range jobs {
			var lastErr error
			for attempt := 1; attempt <= 3; attempt++ {
				if runCtx.Err() != nil {
					return
				}
				lastErr = fetchChunk(runCtx, client, src.URL, j.c, req.Destination)
				if lastErr == nil {
					break
				}
				atomic.AddInt64(&retries, 1)
				logf(req.Logger, "download: chunk %d attempt %d failed: %v", j.idx, attempt, lastErr)
			}
			if lastErr != nil {
				failCh <- fmt.Errorf("chunk %d: %w", j.idx, lastErr)
				cancel()
				return
			}
			doneCh <- j.idx
		}
	}
	for w := 0; w < connections && w < len(pending); w++ {
		wg.Add(1)
		go worker()
	}
	go func() {
		defer close(jobs)
		for _, j := range jobList {
			select {
			case <-runCtx.Done():
				return
			case jobs <- j:
			}
		}
	}()

	// Only this goroutine mutates state, so chunk progress needs no lock.
	var firstErr error
	for remaining := len(pending); remaining > 0; {
		select {
		case idx := <-doneCh:
			state.Chunks[idx].Done = true
			if err := saveState(req.Destination, state); err != nil {
				logf(req.Logger, "download: save state: %v", err)
			}
			remaining--
		case err := <-failCh:
			if firstErr == nil {
				firstErr = err
			}
			cancel()
			remaining--
		case <-runCtx.Done():
			if firstErr == nil {
				firstErr = runCtx.Err()
			}
			remaining = 0
		}
	}
	wg.Wait()
	if firstErr != nil {
		return Result{}, firstErr
	}

	if err := assemble(req.Destination, state.Chunks); err != nil {
		return Result{}, err
	}
	cleanup(req.Destination)
	sum, err := sha256File(req.Destination)
	if err != nil {
		return Result{}, err
	}
	return Result{
		Source:        src.ID,
		Bytes:         size,
		SHA256:        sum,
		UsedChunks:    true,
		Chunks:        len(state.Chunks),
		ResumedChunks: resumed,
		Retries:       int(atomic.LoadInt64(&retries)),
	}, nil
}

func probe(ctx context.Context, client *http.Client, url string) (size int64, acceptRanges bool, err error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, nil)
	if err != nil {
		return 0, false, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return 0, false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return 0, false, fmt.Errorf("HEAD %s: HTTP %d", url, resp.StatusCode)
	}
	size, _ = strconv.ParseInt(resp.Header.Get("Content-Length"), 10, 64)
	return size, strings.EqualFold(resp.Header.Get("Accept-Ranges"), "bytes"), nil
}

func downloadSingle(ctx context.Context, client *http.Client, url, destination string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("GET %s: HTTP %d", url, resp.StatusCode)
	}
	tmp := destination + ".part"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	if _, err := io.Copy(f, resp.Body); err != nil {
		f.Close()
		_ = os.Remove(tmp)
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, destination)
}

func fetchChunk(ctx context.Context, client *http.Client, url string, c chunkState, destination string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", c.Start, c.End))
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusPartialContent && resp.StatusCode != http.StatusOK {
		return fmt.Errorf("RANGE %s: HTTP %d", url, resp.StatusCode)
	}
	buf, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if want := c.End - c.Start + 1; int64(len(buf)) != want {
		return fmt.Errorf("chunk %d length %d, want %d", c.Index, len(buf), want)
	}
	return os.WriteFile(partPath(destination, c.Index), buf, 0o600)
}

func assemble(destination string, chunks []chunkState) error {
	tmp := destination + ".assembling"
	out, err := os.Create(tmp)
	if err != nil {
		return err
	}
	for _, c := range chunks {
		part, err := os.ReadFile(partPath(destination, c.Index))
		if err != nil {
			out.Close()
			_ = os.Remove(tmp)
			return err
		}
		if _, err := out.Write(part); err != nil {
			out.Close()
			_ = os.Remove(tmp)
			return err
		}
	}
	if err := out.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, destination)
}

func loadState(destination, url string, size, chunkBytes int64, total int, resume bool) resumeState {
	fresh := resumeState{URL: url, Size: size, ChunkBytes: chunkBytes, Chunks: make([]chunkState, total)}
	for i := range fresh.Chunks {
		fresh.Chunks[i] = chunkState{
			Index: i,
			Start: int64(i) * chunkBytes,
			End:   min(size-1, int64(i+1)*chunkBytes-1),
		}
	}
	if !resume {
		return fresh
	}
	raw, err := os.ReadFile(statePath(destination))
	if err != nil {
		return fresh
	}
	var saved resumeState
	if err := json.Unmarshal(raw, &saved); err != nil {
		return fresh
	}
	if saved.URL != url || saved.Size != size || saved.ChunkBytes != chunkBytes || len(saved.Chunks) != total {
		return fresh // resource changed; old progress is worthless
	}
	// Only trust chunks that actually exist on disk.
	for i := range saved.Chunks {
		if !saved.Chunks[i].Done {
			continue
		}
		if _, err := os.Stat(partPath(destination, saved.Chunks[i].Index)); err != nil {
			saved.Chunks[i].Done = false
		}
	}
	return saved
}

func saveState(destination string, state resumeState) error {
	raw, err := json.Marshal(state)
	if err != nil {
		return err
	}
	return os.WriteFile(statePath(destination), raw, 0o600)
}

func cleanup(destination string) {
	dir := filepath.Dir(destination)
	base := filepath.Base(destination)
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		name := e.Name()
		if strings.HasPrefix(name, base+".part") || strings.HasPrefix(name, base+".assembling") || name == base+".state.json" {
			_ = os.Remove(filepath.Join(dir, name))
		}
	}
}

func partPath(destination string, index int) string {
	return fmt.Sprintf("%s.part.%d", destination, index)
}

func statePath(destination string) string {
	return destination + ".state.json"
}

func sha256File(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func logf(logger func(string), format string, args ...any) {
	if logger != nil {
		logger(fmt.Sprintf(format, args...))
	}
}

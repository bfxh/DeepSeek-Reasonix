package hostmetrics

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestTimedRecordsSuccessAndFailure(t *testing.T) {
	dir := t.TempDir()
	r := New(Options{Dir: dir, Enabled: true})
	for i := 0; i < 10; i++ {
		_ = r.Timed("demo", "op", func() error { return nil }, nil)
	}
	for i := 0; i < 2; i++ {
		_ = r.Timed("demo", "op", func() error { return errors.New("boom") }, nil)
	}
	rows := r.Summary()
	if len(rows) != 1 {
		t.Fatalf("groups = %d, want 1", len(rows))
	}
	s := rows[0]
	if s.Count != 12 || s.OKCount != 10 || s.FailCount != 2 {
		t.Fatalf("count=%d ok=%d fail=%d", s.Count, s.OKCount, s.FailCount)
	}
	if diff := s.SuccessRate - 10.0/12.0; diff > 1e-9 || diff < -1e-9 {
		t.Fatalf("success rate = %v, want %v", s.SuccessRate, 10.0/12.0)
	}
	if s.P50Ms > s.P95Ms || s.P95Ms > s.MaxMs {
		t.Fatalf("percentiles out of order: %d %d %d", s.P50Ms, s.P95Ms, s.MaxMs)
	}
}

func TestTimedPropagatesError(t *testing.T) {
	r := New(Options{Dir: t.TempDir(), Enabled: true})
	want := errors.New("original")
	got := r.Timed("demo", "op", func() error { return want }, nil)
	if !errors.Is(got, want) {
		t.Fatalf("error = %v, want %v", got, want)
	}
	if r.Summary()[0].FailCount != 1 {
		t.Fatal("failure was not recorded")
	}
}

func TestDisabledRegistryRecordsNothing(t *testing.T) {
	dir := t.TempDir()
	r := New(Options{Dir: dir, Enabled: false})
	_ = r.Timed("demo", "op", func() error { return nil }, nil)
	if len(r.Summary()) != 0 {
		t.Fatal("disabled registry must not record")
	}
	if _, err := os.Stat(filepath.Join(dir, "metrics.jsonl")); !os.IsNotExist(err) {
		t.Fatal("disabled registry must not write to disk")
	}
}

func TestPersistenceRoundTrip(t *testing.T) {
	dir := t.TempDir()
	r := New(Options{Dir: dir, Enabled: true})
	for i := 0; i < 5; i++ {
		_ = r.Timed("demo", "op", func() error { return nil }, map[string]string{"i": string(rune('a' + i))})
	}
	waitForFile(t, filepath.Join(dir, "metrics.jsonl"), 5)

	r2 := New(Options{Dir: dir, Enabled: true})
	n, err := r2.Load()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if n != 5 {
		t.Fatalf("loaded = %d, want 5", n)
	}
	if r2.Summary()[0].Count != 5 {
		t.Fatal("loaded summary mismatch")
	}
}

func TestLoadSkipsCorruptLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "metrics.jsonl")
	content := "{\"subsystem\":\"a\",\"operation\":\"b\",\"ok\":true,\"durationMs\":3}\nnot json\n\n"
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	r := New(Options{Dir: dir, Enabled: true})
	n, err := r.Load()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if n != 1 {
		t.Fatalf("loaded = %d, want 1 (corrupt line skipped)", n)
	}
}

func TestReportContainsHeaderAndRows(t *testing.T) {
	r := New(Options{Dir: t.TempDir(), Enabled: true})
	_ = r.Timed("download", "fetch", func() error { return nil }, nil)
	rep := r.Report()
	if !strings.Contains(rep, "subsystem.operation") {
		t.Fatalf("report missing header: %s", rep)
	}
	if !strings.Contains(rep, "download.fetch") {
		t.Fatalf("report missing row: %s", rep)
	}
}

func TestResetClearsMemoryAndDisk(t *testing.T) {
	dir := t.TempDir()
	r := New(Options{Dir: dir, Enabled: true})
	_ = r.Timed("demo", "op", func() error { return nil }, nil)
	waitForFile(t, filepath.Join(dir, "metrics.jsonl"), 1)
	if err := r.Reset(); err != nil {
		t.Fatal(err)
	}
	if len(r.Summary()) != 0 {
		t.Fatal("memory not cleared")
	}
	raw, _ := os.ReadFile(filepath.Join(dir, "metrics.jsonl"))
	if len(strings.TrimSpace(string(raw))) != 0 {
		t.Fatal("disk not cleared")
	}
}

func TestPercentile(t *testing.T) {
	if got := Percentile(nil, 0.5); got != 0 {
		t.Fatalf("empty percentile = %d, want 0", got)
	}
	sorted := []int64{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
	if got := Percentile(sorted, 0.5); got != 5 {
		t.Fatalf("p50 = %d, want 5", got)
	}
	if got := Percentile(sorted, 0.95); got != 10 {
		t.Fatalf("p95 = %d, want 10", got)
	}
	if got := Percentile([]int64{7}, 0.5); got != 7 {
		t.Fatalf("single = %d, want 7", got)
	}
}

func waitForFile(t *testing.T, path string, wantLines int) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		raw, err := os.ReadFile(path)
		if err == nil {
			if n := strings.Count(strings.TrimSpace(string(raw)), "\n") + 1; n >= wantLines && strings.TrimSpace(string(raw)) != "" {
				return
			}
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %d lines in %s", wantLines, path)
}

func timeNow() time.Time { return time.Now() }

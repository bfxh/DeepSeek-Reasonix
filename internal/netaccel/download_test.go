package netaccel

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// rangeServer serves a fixed payload with HEAD + Range support, and records how
// many chunk requests it received.
func rangeServer(t *testing.T, payload []byte, hits *int64) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodHead:
			w.Header().Set("Content-Length", strconv.Itoa(len(payload)))
			w.Header().Set("Accept-Ranges", "bytes")
			w.WriteHeader(http.StatusOK)
			return
		case http.MethodGet:
		default:
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		if rg := r.Header.Get("Range"); rg != "" {
			var start, end int
			if _, err := fmt.Sscanf(rg, "bytes=%d-%d", &start, &end); err != nil {
				// tolerate open-ended ranges
				start = 0
				end = len(payload) - 1
			}
			if end >= len(payload) {
				end = len(payload) - 1
			}
			if hits != nil {
				atomic.AddInt64(hits, 1)
			}
			w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(payload)))
			w.Header().Set("Content-Length", strconv.Itoa(end-start+1))
			w.WriteHeader(http.StatusPartialContent)
			_, _ = w.Write(payload[start : end+1])
			return
		}
		w.Header().Set("Content-Length", strconv.Itoa(len(payload)))
		_, _ = w.Write(payload)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestDownloadChunkedVerified(t *testing.T) {
	payload := make([]byte, 12<<20)
	if _, err := rand.Read(payload); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(payload)
	want := hex.EncodeToString(sum[:])
	var hits int64
	srv := rangeServer(t, payload, &hits)
	dest := filepath.Join(t.TempDir(), "asset.bin")

	res, err := Download(context.Background(), Request{
		Sources:          []Source{{ID: "direct", URL: srv.URL + "/asset.bin"}},
		Destination:      dest,
		ExpectedSHA256:   want,
		Connections:      4,
		ChunkBytes:       1 << 20,
		MinSizeForChunks: 1024,
	})
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if !res.UsedChunks {
		t.Fatal("expected chunked download")
	}
	if res.Chunks != 12 {
		t.Fatalf("chunks = %d, want 12", res.Chunks)
	}
	if res.Bytes != int64(len(payload)) {
		t.Fatalf("bytes = %d, want %d", res.Bytes, len(payload))
	}
	if res.SHA256 != want {
		t.Fatal("checksum mismatch")
	}
	if got := atomic.LoadInt64(&hits); got != 12 {
		t.Fatalf("chunk requests = %d, want 12", got)
	}
	got, err := os.ReadFile(dest)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, payload) {
		t.Fatal("written bytes differ from source")
	}
	entries, _ := os.ReadDir(filepath.Dir(dest))
	for _, e := range entries {
		if strings.Contains(e.Name(), ".part") || strings.Contains(e.Name(), ".state.json") || strings.Contains(e.Name(), ".assembling") {
			t.Fatalf("leftover artifact: %s", e.Name())
		}
	}
}

func TestDownloadSingleConnectionWhenSmall(t *testing.T) {
	payload := []byte("small artifact")
	sum := sha256.Sum256(payload)
	var hits int64
	srv := rangeServer(t, payload, &hits)
	dest := filepath.Join(t.TempDir(), "small.bin")

	res, err := Download(context.Background(), Request{
		Sources:          []Source{{ID: "direct", URL: srv.URL + "/small.bin"}},
		Destination:      dest,
		ExpectedSHA256:   hex.EncodeToString(sum[:]),
		Connections:      4,
		MinSizeForChunks: 8 << 20, // larger than payload → single connection
	})
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if res.UsedChunks {
		t.Fatal("expected single connection for a small artifact")
	}
	if got := atomic.LoadInt64(&hits); got != 0 {
		t.Fatalf("range requests = %d, want 0", got)
	}
	got, _ := os.ReadFile(dest)
	if !bytes.Equal(got, payload) {
		t.Fatal("written bytes differ")
	}
}

func TestDownloadChecksumMismatchDiscardsArtifact(t *testing.T) {
	payload := []byte("payload to be rejected")
	srv := rangeServer(t, payload, nil)
	dest := filepath.Join(t.TempDir(), "bad.bin")

	_, err := Download(context.Background(), Request{
		Sources:          []Source{{ID: "direct", URL: srv.URL + "/bad.bin"}},
		Destination:      dest,
		ExpectedSHA256:   strings.Repeat("0", 64),
		MinSizeForChunks: 8 << 20,
	})
	if err == nil {
		t.Fatal("expected an error on checksum mismatch")
	}
	if !strings.Contains(err.Error(), "checksum mismatch") {
		t.Fatalf("error = %v, want checksum mismatch", err)
	}
	if _, statErr := os.Stat(dest); statErr == nil {
		t.Fatal("artifact must be removed after a checksum mismatch")
	}
}

func TestDownloadFallsThroughToNextSourceOnBadBytes(t *testing.T) {
	good := []byte("the real artifact")
	sum := sha256.Sum256(good)
	badServer := rangeServer(t, []byte("tampered artifact"), nil)
	goodServer := rangeServer(t, good, nil)
	dest := filepath.Join(t.TempDir(), "fallback.bin")

	res, err := Download(context.Background(), Request{
		Sources: []Source{
			{ID: "mirror", URL: badServer.URL + "/a.bin"},
			{ID: "direct", URL: goodServer.URL + "/a.bin"},
		},
		Destination:      dest,
		ExpectedSHA256:   hex.EncodeToString(sum[:]),
		MinSizeForChunks: 8 << 20,
	})
	if err != nil {
		t.Fatalf("expected fallback to succeed: %v", err)
	}
	if res.Source != "direct" {
		t.Fatalf("source = %s, want direct", res.Source)
	}
	got, _ := os.ReadFile(dest)
	if !bytes.Equal(got, good) {
		t.Fatal("fallback wrote wrong bytes")
	}
}

func TestDownloadResumeSkipsFinishedChunks(t *testing.T) {
	payload := make([]byte, 5<<20)
	if _, err := rand.Read(payload); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(payload)
	want := hex.EncodeToString(sum[:])
	var hits int64
	srv := rangeServer(t, payload, &hits)
	dest := filepath.Join(t.TempDir(), "resume.bin")
	url := srv.URL + "/resume.bin"

	// Pre-seed the first three chunks and a matching state file, as an
	// interrupted previous run would have left behind.
	const chunkBytes = 1 << 20
	chunks := make([]chunkState, 5)
	for i := range chunks {
		chunks[i] = chunkState{Index: i, Start: int64(i) * chunkBytes, End: int64(i+1)*chunkBytes - 1}
	}
	for i := 0; i < 3; i++ {
		if err := os.WriteFile(partPath(dest, i), payload[chunks[i].Start:chunks[i].End+1], 0o600); err != nil {
			t.Fatal(err)
		}
		chunks[i].Done = true
	}
	raw, _ := json.Marshal(resumeState{URL: url, Size: int64(len(payload)), ChunkBytes: chunkBytes, Chunks: chunks})
	if err := os.WriteFile(statePath(dest), raw, 0o600); err != nil {
		t.Fatal(err)
	}

	res, err := Download(context.Background(), Request{
		Sources:          []Source{{ID: "direct", URL: url}},
		Destination:      dest,
		ExpectedSHA256:   want,
		Connections:      4,
		ChunkBytes:       chunkBytes,
		MinSizeForChunks: 1024,
		Resume:           true,
	})
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if res.ResumedChunks != 3 {
		t.Fatalf("resumed = %d, want 3", res.ResumedChunks)
	}
	if got := atomic.LoadInt64(&hits); got != 2 {
		t.Fatalf("chunk requests = %d, want 2 (only missing chunks)", got)
	}
	if res.SHA256 != want {
		t.Fatal("checksum mismatch after resume")
	}
}

func TestDownloadRejectsPhantomResumeState(t *testing.T) {
	payload := make([]byte, 3<<20)
	if _, err := rand.Read(payload); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(payload)
	srv := rangeServer(t, payload, nil)
	dest := filepath.Join(t.TempDir(), "phantom.bin")
	url := srv.URL + "/phantom.bin"

	// State claims all chunks are done, but no part files exist on disk.
	chunks := []chunkState{{Index: 0, Start: 0, End: (1 << 20) - 1, Done: true}}
	raw, _ := json.Marshal(resumeState{URL: url, Size: int64(len(payload)), ChunkBytes: 1 << 20, Chunks: chunks})
	if err := os.WriteFile(statePath(dest), raw, 0o600); err != nil {
		t.Fatal(err)
	}

	res, err := Download(context.Background(), Request{
		Sources:          []Source{{ID: "direct", URL: url}},
		Destination:      dest,
		ExpectedSHA256:   hex.EncodeToString(sum[:]),
		ChunkBytes:       1 << 20,
		MinSizeForChunks: 1024,
		Resume:           true,
	})
	if err != nil {
		t.Fatalf("download: %v", err)
	}
	if res.SHA256 != hex.EncodeToString(sum[:]) {
		t.Fatal("phantom progress produced wrong bytes")
	}
}

func TestDownloadNoSources(t *testing.T) {
	if _, err := Download(context.Background(), Request{Destination: "x"}); err == nil {
		t.Fatal("expected error with no sources")
	}
}

func TestDownloadRespectsContextCancel(t *testing.T) {
	payload := make([]byte, 2<<20)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond)
		w.Header().Set("Content-Length", strconv.Itoa(len(payload)))
		_, _ = w.Write(payload)
	}))
	defer srv.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	_, err := Download(ctx, Request{
		Sources:     []Source{{ID: "direct", URL: srv.URL + "/slow.bin"}},
		Destination: filepath.Join(t.TempDir(), "slow.bin"),
	})
	if err == nil {
		t.Fatal("expected cancellation error")
	}
}

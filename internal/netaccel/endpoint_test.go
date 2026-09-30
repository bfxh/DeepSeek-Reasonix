package netaccel

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestEndpointsRejectsNonHTTPS(t *testing.T) {
	eps := Endpoints([]string{"https://mirror.example/", "http://insecure.example/"})
	if len(eps) != 2 {
		t.Fatalf("endpoints = %d, want 2 (direct + one https mirror)", len(eps))
	}
	if eps[0].Kind != KindDirect {
		t.Fatal("direct must come first")
	}
	if eps[1].Base != "https://mirror.example/" {
		t.Fatalf("base = %q, want trailing slash normalized", eps[1].Base)
	}
}

func TestBenchAndFastest(t *testing.T) {
	slow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(60 * time.Millisecond)
		_, _ = w.Write([]byte("ok"))
	}))
	defer slow.Close()
	fast := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("ok"))
	}))
	defer fast.Close()

	// direct is pointed at the slow server, the mirror prefix at the fast one.
	eps := []Endpoint{
		{ID: "direct", Kind: KindDirect},
		{ID: "mirror", Kind: KindMirror, Base: fast.URL + "/"},
	}
	probe := slow.URL + "/raw/probe"
	results := Bench(context.Background(), eps, probe, 2*time.Second)
	if len(results) != len(eps) {
		t.Fatalf("results = %d, want %d", len(results), len(eps))
	}
	for _, r := range results {
		if !r.OK {
			t.Fatalf("endpoint %s not reachable: %s", r.ID, r.Detail)
		}
	}
	best := Fastest(results, eps)
	if best.ID != "mirror" {
		t.Fatalf("fastest = %s, want mirror", best.ID)
	}
	if results[0].RTT <= results[1].RTT {
		t.Fatalf("direct rtt %v should exceed mirror rtt %v", results[0].RTT, results[1].RTT)
	}
}

func TestFastestFallsBackToDirectWhenNothingReachable(t *testing.T) {
	eps := Endpoints([]string{"https://unreachable.invalid/"})
	results := Bench(context.Background(), eps, "https://unreachable.invalid/probe", 300*time.Millisecond)
	if got := Fastest(results, eps); got.Kind != KindDirect {
		t.Fatalf("fastest = %v, want direct fallback", got)
	}
}

func TestRewriteNeverTouchesAPIOrcDirect(t *testing.T) {
	mirror := Endpoint{ID: "m", Kind: KindMirror, Base: "https://mirror.example/"}
	direct := Endpoint{ID: "direct", Kind: KindDirect}

	if got := Rewrite("https://github.com/o/r/releases/a.zip", direct); got != "https://github.com/o/r/releases/a.zip" {
		t.Fatalf("direct must not rewrite: %s", got)
	}
	if got := Rewrite("https://api.github.com/repos/o/r", mirror); got != "https://api.github.com/repos/o/r" {
		t.Fatalf("api must not be rewritten: %s", got)
	}
	want := "https://mirror.example/https://github.com/o/r/releases/a.zip"
	if got := Rewrite("https://github.com/o/r/releases/a.zip", mirror); got != want {
		t.Fatalf("rewrite = %s, want %s", got, want)
	}
}

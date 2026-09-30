// Package netaccel implements client-side network acceleration: endpoint
// probing/selection and multi-connection downloads.
//
// It deliberately requires no Reasonix-hosted service. Endpoint scoring, chunk
// scheduling, checksum verification and fallback all run in this process.
// Third-party mirrors are treated as untrusted public file proxies, which is why
// checksum verification is mandatory when an official digest is available.
package netaccel

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"
	"time"
)

// EndpointKind distinguishes the direct connection from mirrors.
type EndpointKind string

const (
	// KindDirect is the official origin. It is always present in the pool and
	// always participates in ranking, so a total mirror outage degrades to
	// "no acceleration" instead of "broken".
	KindDirect EndpointKind = "direct"
	// KindMirror is a prefix-form public file proxy: Base + original URL.
	KindMirror EndpointKind = "mirror"
)

// Endpoint is a download source candidate.
type Endpoint struct {
	ID   string
	Kind EndpointKind
	// Base is the prefix prepended to the original URL for mirrors. Empty for
	// KindDirect.
	Base string
}

// BenchResult is the outcome of probing one endpoint.
type BenchResult struct {
	ID     string
	OK     bool
	RTT    time.Duration
	Detail string
}

// Endpoints builds the candidate pool: direct first, then user-supplied mirrors.
// Non-https mirrors are rejected rather than silently downgraded.
func Endpoints(custom []string) []Endpoint {
	list := []Endpoint{{ID: "direct", Kind: KindDirect}}
	for _, m := range custom {
		if !strings.HasPrefix(m, "https://") {
			continue
		}
		list = append(list, Endpoint{ID: m, Kind: KindMirror, Base: withTrailingSlash(m)})
	}
	return list
}

// Bench probes every endpoint with the smallest read-only resource available.
// API quota is never spent on probing.
func Bench(ctx context.Context, eps []Endpoint, probeURL string, timeout time.Duration) []BenchResult {
	client := &http.Client{Timeout: timeout}
	results := make([]BenchResult, 0, len(eps))
	for _, ep := range eps {
		url := probeURL
		if ep.Kind == KindMirror {
			url = ep.Base + probeURL
		}
		start := time.Now()
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			results = append(results, BenchResult{ID: ep.ID, Detail: err.Error()})
			continue
		}
		resp, err := client.Do(req)
		rtt := time.Since(start)
		if err != nil {
			results = append(results, BenchResult{ID: ep.ID, RTT: rtt, Detail: err.Error()})
			continue
		}
		_, _ = io.Copy(io.Discard, resp.Body)
		_ = resp.Body.Close()
		if resp.StatusCode >= 400 {
			results = append(results, BenchResult{
				ID: ep.ID, RTT: rtt,
				Detail: fmt.Sprintf("HTTP %d", resp.StatusCode),
			})
			continue
		}
		results = append(results, BenchResult{ID: ep.ID, OK: true, RTT: rtt, Detail: fmt.Sprintf("HTTP %d", resp.StatusCode)})
	}
	return results
}

// Fastest returns the reachable endpoint with the lowest RTT. When nothing is
// reachable it falls back to direct: no acceleration is always preferable to a
// broken download.
func Fastest(results []BenchResult, eps []Endpoint) Endpoint {
	reachable := make([]BenchResult, 0, len(results))
	for _, r := range results {
		if r.OK {
			reachable = append(reachable, r)
		}
	}
	if len(reachable) == 0 {
		return Endpoint{ID: "direct", Kind: KindDirect}
	}
	sort.SliceStable(reachable, func(i, j int) bool { return reachable[i].RTT < reachable[j].RTT })
	for _, ep := range eps {
		if ep.ID == reachable[0].ID {
			return ep
		}
	}
	return Endpoint{ID: "direct", Kind: KindDirect}
}

// Rewrite maps a download URL onto the chosen endpoint. Requests that carry
// credentials never go through a mirror.
func Rewrite(url string, ep Endpoint) string {
	if ep.Kind != KindMirror {
		return url
	}
	if strings.Contains(url, "api.github.com") {
		return url
	}
	return ep.Base + url
}

func withTrailingSlash(s string) string {
	if strings.HasSuffix(s, "/") {
		return s
	}
	return s + "/"
}

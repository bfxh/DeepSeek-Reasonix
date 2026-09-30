# Network Acceleration (client-side)

English overview of client-side network acceleration for downloads and read-only
Git traffic. Chinese: [NETWORK_ACCELERATION.zh-CN.md](./NETWORK_ACCELERATION.zh-CN.md).

## Scope and non-goals

**In scope:** making `fetch`/asset/raw/archive downloads and (optionally) read-only
Git traffic faster for users on slow or blocked links to github.com.

**Explicit non-goal:** no Reasonix-hosted service. There is no relay, no CDN, no
proxy fleet, and no telemetry endpoint in this design. Endpoint scoring, chunk
scheduling, checksum verification, and fallback all run inside the client process.
Third-party mirrors are treated as untrusted public file proxies.

## Modes

| Mode | Behavior | Side effects |
| --- | --- | --- |
| `off` | nothing is touched | none |
| `download` (default) | rewrites download URLs to the fastest endpoint | none |
| `git-readonly` | additionally writes `git config --local url.<fastest>.insteadOf https://github.com/` | local git config, recorded in a receipt |

`git-readonly` is not the default: writing git config is a side effect, and it is
only worth it for users whose bottleneck is `fetch`/`clone`.

## Endpoint pool and scoring

```text
candidates:
  direct   https://github.com                       (always present, always ranked)
  mirrors  https://<mirror-host>/https://github.com (prefix form)
  raw      https://raw.githubusercontent.com (+ mirrors)
  api      https://api.github.com  → NEVER routed through a mirror (credentials, writes)
```

```text
score = w1 * exp(-rttP50 / R0) + w2 * successRate(window) - w3 * penalty
penalty: recent checksum mismatch / TLS error / 5xx burst → heavy downgrade + cooldown
```

Probes use the smallest read-only resource available (a few KB raw file).
API quota is never spent on probing. Direct connection always stays in the pool,
so a total mirror outage degrades to "no acceleration", never to "broken".

## Multi-connection download

Independent of mirror selection: pull **one file over several connections**.

```text
HEAD → Content-Length + Accept-Ranges: bytes
  ├─ Range unsupported, or size < threshold → single connection (chunking would be pointless)
  └─ chunked: N concurrent `Range: bytes=a-b` requests
        → each chunk lands in <dest>.part.<i> (length mismatch ⇒ chunk failed)
        → assemble in order → <dest>
        → sha256 check: mismatch ⇒ delete artifact, drop chunks, fall back to next source
```

- **Resume:** per-chunk progress in `<dest>.state.json`; a rerun only fetches
  missing chunks and verifies the chunk files actually exist (no phantom progress).
- **Retry:** a failed chunk is retried up to 3 times, then the whole source is
  abandoned and the next candidate is tried.
- **Ordering:** direct connection is always the first candidate; mirrors are
  fallback only.

## Mandatory safety rules

1. **push never goes through a mirror** — `pushInsteadOf` is never written; before
   writing `insteadOf`, the current remote push URL is checked and any mirror-
   tainted `pushurl` is removed.
2. **checksum is mandatory** — when an official sha256 is available, the artifact
   is verified; a mismatch discards the artifact and moves the mirror to cooldown.
   Slow is acceptable; dirty is not.
3. **TLS is never downgraded** — no `http.sslVerify=false`, no ignoring cert errors.
4. **credentials are never forwarded** — any request carrying a token goes direct.
5. **one-click undo** — every git config write is recorded in a receipt with its
   undo arguments; `undo` replays them in reverse order. No receipt ⇒ no write.

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `github.autoAccelerate` | `true` | probe and enable on activation |
| `github.mode` | `download` | see Modes |
| `github.mirrors` | `[]` | user-supplied mirror endpoints (https only) |
| `github.requireChecksum` | `true` | verify artifacts against official sha256 |
| `download.connections` | `4` | concurrent connections per download |
| `download.chunkBytes` | `1 MiB` | chunk size |
| `download.minSizeForChunks` | `8 MiB` | below this, single connection |
| `download.resume` | `true` | resume from chunk state |

## Observability

Every operation is recorded in the host metrics registry (count, p50/p95/max,
success rate — see [HOST_METRICS.md](./HOST_METRICS.md)). The two numbers worth
watching:

- `download.fetch` p95 — if it stops improving with more connections, the
  bottleneck is the link, not the concurrency.
- `github.bench` success rate — a mirror that starts failing checksums shows up
  here before users notice.

## Acceptance

- With mirrors configured and reachable: ≥ 80% of downloads finish on a
  non-direct endpoint, with zero checksum mismatches accepted.
- With every mirror unreachable: downloads still succeed via direct, no config
  was modified, no error surfaced to the user beyond a log line.
- `undo` restores git config byte-for-byte.

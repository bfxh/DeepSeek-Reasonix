# Host Metrics (local call statistics)

English overview of host-side call statistics. Chinese:
[HOST_METRICS.zh-CN.md](./HOST_METRICS.zh-CN.md).

## Why

Acceleration, downloads, localization, and code explanation all share one
property: you cannot tell whether they are good without numbers. Without a
counter and a duration distribution, every claim about "it feels slow" is
anecdotal, and every regression is discovered by a user instead of by us.

This is a **local** registry. It is not telemetry: nothing leaves the machine.

## What is recorded

Per `subsystem.operation`:

| Field | Meaning |
| --- | --- |
| `count` | number of calls |
| `okCount` / `failCount` | separated — a fast failure and a slow failure are different problems |
| `successRate` | `okCount / count` |
| `p50Ms` / `p95Ms` / `maxMs` / `avgMs` | duration distribution, not just an average |
| `lastMs` | duration of the most recent call |

Optional `meta` carries dimension values (e.g. download `sources`/`connections`,
localization `items`, explanation `lines`) so a slow p95 can be correlated with
input size instead of guessed at.

Instrumented operations: `mcp.connectAll`, `mcp.rewire`, `github.bench`,
`github.undo`, `download.fetch`, `i18n.extract`, `i18n.translate`,
`explain.code`, `explain.hover`.

## What is NOT recorded

- No source code content, no file contents, no prompt or response bodies.
- No paths beyond what an operation legitimately needs, no personal identifiers.
- **No upload.** Data lives in `<stateDir>/metrics.jsonl`, rolling at 5000 events.
- `metrics.enabled=false` disables recording entirely — nothing is written.

## Report

```text
subsystem.operation    count  ok  fail  rate   p50    p95    max    last
download.fetch             8   7     1  87.5%  820ms  1900ms 2400ms  760ms
github.bench               3   3     0 100.0%   95ms   140ms  140ms  110ms
i18n.translate             2   1     1  50.0% 1200ms  1200ms 1200ms 1200ms
explain.hover             56  41    15  73.2%    3ms    12ms   18ms    4ms
```

How the numbers get used:

- `download.fetch` p95 flat while `connections` rises ⇒ the bottleneck is the
  link, not concurrency; stop adding connections.
- `i18n.translate` success rate dropping ⇒ the browser translation backend
  became unavailable; the pipeline is failing closed, as designed.
- `explain.hover` failures ⇒ mostly symbol misses, i.e. the scanner needs to be
  replaced by a real language service.
- `mcp.connectAll` p95 climbing ⇒ a server is timing out during handshake; check
  health before blaming the model.

## Implementation notes

- `timed(subsystem, operation, fn, meta?)` wraps an async call: it records on
  both success and failure, and rethrows, so instrumenting never changes
  control flow.
- Persistence is fire-and-forget; a failed write logs and moves on. Statistics
  must never break the operation they measure.
- Corrupt lines in the JSONL are skipped on load; one bad record does not cost
  the whole history.
- Failures are timed too. Error paths that hang are exactly what this is for.

## Open questions

1. Should host metrics be surfaced through `reasonix doctor` alongside runtime
   diagnostics, or stay behind their own command?
2. Do we want a coarse local retention policy (e.g. 7 days) in addition to the
   5000-event cap?
3. If a future opt-in telemetry exists, should these counters be its base —
   or should it stay strictly separate to keep this registry trivially auditable?

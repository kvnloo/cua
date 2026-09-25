# Transport batching: measure the chunk-4 finding (REPORT-batch)

## Question
Chunk 4's stage profile found every TS-side stage sub-0.2ms; per-step cost is
the RPC round trips (one socket connection per call on the daemon's JSONL
protocol). Can client-side batching cut the 3-observation-RPC step?

## Shapes (typescript/batched.ts, composes a CallFn — no daemon change needed)
- **sequential** — snapshot → capture → parse, 3 back-to-back round trips (today's pattern)
- **parallel** — snapshot + capture concurrently, then parse. 3 RPCs, 2 sequential
  groups. Zero protocol change: works against the real daemon today.
- **combined** — snapshot, then prototype `observe_visual` (capture+parse in one
  RPC, daemon-side). Mock-only protocol extension in mock_daemon.mjs; numbers are
  the ceiling for a real daemon-side combined call (a contract decision, not a
  recipe decision).

## Method
Paired/interleaved: all three shapes measured in randomized order within each of
30 iterations, real unix-socket JSONL against mock_daemon.mjs (visual-fallback,
50 regions). Per-iteration paired ratios cancel box-load drift. Equivalence gate:
identical candidate sets and region counts on every iteration, or the bench fails.

## Results
| shape      | round trips | groups | median | p90   |
|------------|-------------|--------|--------|-------|
| sequential | 3           | 3      | 69.1ms | 84.5ms|
| parallel   | 3           | 2      | 56.3ms | 68.0ms|
| combined   | 2           | 2      | 52.7ms | 73.3ms|

Paired speedup vs sequential: **parallel 1.25x median / 2.41x p90**,
**combined 1.29x median / 2.89x p90**. Output identical across all 90 shape-runs
(3 candidates, 50 regions).

## Why the win is modest at median
Loopback per-call latency is dominated by per-connection setup (~10-30ms, high
jitter) rather than payload work. Parallelization removes one serialized
connection setup (~13ms); the combined call removes one full round trip (~16ms).
The win grows on slow iterations (p90 2.4-2.9x) — jitter, not throughput, is
what batching smooths.

## Honest scope
- A first naive (non-interleaved) run showed 4-6x and was WRONG: daemon-start
  order + box-load drift inflated it. The paired design is the trustworthy
  number. Lesson: never bench shapes sequentially on this box.
- Loopback ms is IPC noise; production daemons (TCP/WS, real perception) have
  different absolute costs, but the structural claim holds: one fewer serialized
  connection setup per step.
- The bigger lever is connection keep-alive (multiple requests per connection),
  which the daemon protocol does not support today (one request per connection).
  That is a contract change for a maintainer thread, not a recipe change —
  noted here, not implemented.
- `observe_visual` exists only in the mock; the real daemon has no such tool.

## Recommendation
Ship-ready, not shipped: `observeParallel`/`observeCombined` are measured and
output-identical, but run.ts's flow needs the snapshot BEFORE deciding visual
is needed (needsVisualObservation), so blind parallelization would fire wasted
captures on DOM-complete steps. Wiring it in requires a speculation policy
(e.g. fire capture alongside the snapshot when the previous step needed
visual) — a policy decision for its own chunk with a multi-step bench, not
folded into this measurement. The combined prototype stays a measurement
artifact; keep-alive is the contract-level follow-up for a maintainer thread.

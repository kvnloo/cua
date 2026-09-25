# REPORT-keepalive: persistent-connection prototype for the daemon JSONL transport

## Question
The daemon speaks one-request-per-connection (each RPC opens a socket,
sends one JSONL request, reads one response, closes). Chunk-4's stage
profile showed every TS-side stage sub-0.2ms while each RPC round trip
costs ~4ms on loopback. How much of that is pure connection setup, and
what would a keep-alive transport require upstream?

## What was built (fork prototype, NOT an upstream proposal)
- `bench/observation-gating/mock_daemon.mjs --keep-alive`: opt-in mode that
  serves every newline-delimited request on one connection instead of
  `connection.end()` after the first. Default behavior unchanged.
- `typescript/keepalive.ts`: `PersistentDaemonClient` — one socket, requests
  serialized (the recipe loop issues calls synchronously anyway), FIFO
  response matching, reconnect-on-fatal, `asCallFn()` (raw wire, the shape
  the observation path consumes) and `asUnwrappedCallFn()` (bench-convention
  unwrapping: throws on `!ok` AND on `structuredContent.error`).
- `bench/observation-gating/keepalive_bench.ts`: paired/interleaved —
  30 iterations × 3-call observation sequence
  (get_browser_state + get_window_state + parse_visual_regions), arms run
  in Fisher-Yates order against one keep-alive daemon. Shape-equivalence
  gate inside the sequence (throws on mismatch).
- `typescript/keepalive.test.ts`: 5/5 green against the real wire.

## Measured (loopback unix socket, 50 regions, box under ~12 load)
| | one-shot (per-call connection) | keep-alive (persistent) |
|---|---|---|
| iter median (3 calls) | 16.31ms | 9.74ms |
| iter p90 | 49.08ms | 31.18ms |
| per-call median | 5.44ms | 3.25ms |
| per-call p90 | 16.36ms | 10.39ms |

**Speedup: 1.68× median / 1.57× p90 per iteration.** Per-call connection
setup costs ~2.2ms on loopback — a structural floor no client-side batching
can touch. Combined with chunk-5's parallel batching (1.25× median),
keep-alive + parallel is the credible 2×-class transport story, both
without protocol changes.

## Honest scope
- Mock daemon, loopback only. The p90 spread is box-load jitter (8
  concurrent waves); the median effect is structural — it cannot be a
  scheduling artifact because the interleaved design gives both arms the
  same noise and only one arm pays setup.
- The real daemon's cost per connection is LARGER than the mock's (real
  daemon does work per accept — #3383 shows a codesign verification in the
  accept loop), so this is a lower bound on production savings.
- Prototype only. Upstream, keep-alive is a CONTRACT decision, not a
  recipe: it needs the auth-lifetime question answered (authenticate once
  per connection vs per request — TOCTOU, revocation, head-of-line
  blocking), plus backpressure/heartbeat policy for long-lived
  connections. That question is dq-3383; this prototype is the evidence
  behind it. Neither is posted upstream under the fork-only order.

## Reproduce
`node --import tsx bench/observation-gating/keepalive_bench.ts`
(30 iters, ~2 min on a loaded box).

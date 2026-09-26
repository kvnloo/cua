# REPORT-keepalive-python.md — Python keep-alive prototype measurement

## Question
Does a persistent connection pay off on the Python side, as it did in TS
(chunk 7: 1.68x median / 1.57x p90 on the 3-call observation sequence)?

## Scope caveat (important)
The Python jev-use loop (`python/run.py`) drives the real driver through
MCP stdio — which is already a persistent connection; there is no per-call
connect cost on that path. This prototype is for the JSONL unix-socket
protocol path (the TS loop's `mock_daemon.mjs` world): the Python loop would
only need it if it ever spoke that protocol directly. The measured result
is still the honest answer to "how large is the per-call connection
overhead in Python asyncio, and does a persistent client recover it?"

## What was built (fork research artifact, not an upstream proposal)
- `python/keepalive.py`: `PersistentDaemonClient` — one asyncio unix-socket
  connection, serialized FIFO calls (the daemon answers in order), 10s
  timeouts, transparent reconnect after a fatal close, `close()` idempotent.
  Mirrors `typescript/keepalive.ts`.
- `python/mock_daemon.py`: asyncio mirror of `mock_daemon.mjs` (one-request-
  per-connection default, `--keep-alive` opt-in; serves the 3 observation
  calls with the dom-complete fixture shape).
- `python/bench_observation_keepalive.py`: paired/interleaved bench (30 iters,
  Fisher-Yates arm order, one shared --keep-alive daemon), 3-call observation
  sequence, shape equivalence gate (throws on snapshot/capture/parse mismatch).
- `python/tests/test_keepalive.py`: 7 tests (envelope round-trip, unwrapped
  convention, single-connection sharing, serialized request order, error
  envelope raises, idempotent close + post-close rejection, dead-socket raises).

## Measured (asyncio unix socket, loopback, 50 visual regions)
| run | iter median speedup | iter p90 speedup | per-call oneshot | per-call keep-alive |
|-----|--------------------:|-----------------:|-----------------:|--------------------:|
| 1   | 1.53x              | 1.48x            | 7.21 ms          | 4.71 ms             |
| 2   | 1.45x              | 2.35x            | 2.36 ms          | 1.63 ms             |

The run-2 p90 is inflated by one noisy one-shot iteration (box load); the
median is the reliable signal. The per-call connection overhead varies
0.7–2.5ms/call across runs under load — Python asyncio's connect cost is in
the same ballpark as node's (~2.2ms/call in the TS bench), and the direction
is consistent: keep-alive is strictly faster on the median in both runs.

Honest bound: this is a loopback mock daemon; a real daemon's per-accept
cost (codesign verification in #3383, TLS/credential handshakes) is larger,
so these numbers are a lower bound on the real saving, same as the TS
prototype's honest scope.

## Tests
7/7 new tests green. Full Python suite: only the 8 pre-existing failures
(byte-identical list to pristine base, verified by chunk 11).

## Recommendation
For the JSONL socket protocol path: ship keep-alive when the auth-lifetime
contract question (dq-3383) is answered — same posture as the TS prototype.
For the MCP-stdio path the Python loop already uses: nothing to do; it is
already a persistent connection. Zero protocol change in both cases.

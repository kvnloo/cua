# REPORT: auth trust-window measurement (chunk 15)

Follow-up to REPORT-auth-cache.md. Chunk 14 measured the (a)+(b) hybrid
(verify-once-per-connection for history methods) at 1.81–3.24x vs today.
This bench asks the safety question dq-3383 left open: **how narrow can the
re-verify window be while keeping the speedup?** A bounded window caps the
exposure of trusting a connection past its first verify.

## What the window actually bounds (threat model)

The codesign deep-verify attests the *binary identity* of the peer at
verify time. After that, three things can change:

1. **Socket FD passed to another process** (SCM_RIGHTS fd-passing). A
   different binary inherits the verified connection. This is the real
   TOCTOU case the per-request re-verify currently closes — and the only
   *new* exposure the hybrid introduces.
2. **Binary replaced on disk.** Only affects new processes, hence new
   connections. The next verify (on the next connection) sees it. Not a
   mid-connection threat.
3. **Runtime injection into the verified process** (dyld insertion, debugger
   attach). Pre-existing exposure: today's accept-time auth for non-history
   calls already trusts the process for the connection lifetime. The hybrid
   does not widen this.

So the window bounds exactly case 1: with a request-count window of N, at
most N in-scope requests can ride a stolen FD before the daemon re-verifies
and the impostor fails closed. A request-count window alone does not bound
*time*: an idle connection holds trust forever, and a revocation (case 2
propagating, e.g. a revoked developer certificate) never lands until the
connection dies. That is why the window needs **both axes**: re-verify after
N in-scope requests **or** T seconds, whichever comes first. The time axis is
the revocation-propagation bound; the request axis is the burst-exposure
bound.

mock_daemon.py implements both (`--auth-window-requests`,
`--auth-window-ms`) plus `--auth-events` so the bench counts real auth
events instead of inferring them.

## Measurement

Arms (all `--auth-mode request --auth-scope history`; keep-alive except D4):

| arm | meaning |
|---|---|
| D4 | today: one-shot conn, re-verify per history request |
| F | keep-alive, re-verify per history request (conservative) |
| W5 / W10 / W20 | keep-alive, hybrid, re-verify every 5/10/20 in-scope requests |
| E | keep-alive, hybrid, no window (chunk-14 ceiling) |

Sequences: history-12 (12 x history_record — windows bite intra-connection)
and mixed (3 steps x 3 obs + history_record = 3 history calls). 20 iters,
paired/interleaved, 5/25ms auth. Equivalence gate: identical result shapes
every arm.

RESULTS TABLE — filled from the bench run below.

## Measurement

Arms (all `--auth-mode request --auth-scope history`; keep-alive except D4):

| arm | meaning |
|---|---|
| D4 | today: one-shot conn, re-verify per history request |
| F | keep-alive, re-verify per history request (conservative) |
| W5 / W10 / W20 | keep-alive, hybrid, re-verify every 5/10/20 in-scope requests |
| E | keep-alive, hybrid, no window (chunk-14 ceiling) |

Sequences: history-12 (12 x history_record — windows bite intra-connection)
and mixed (3 steps x 3 obs + history_record = 3 history calls). 20 iters,
paired/interleaved, 5/25ms auth. Equivalence gate: identical result shapes
every arm.

### history-12 (windows bite; the decision-relevant sequence)

| auth | D4 (today) | F (per-req) | W5 | W10 | W20 | E (no window) |
|---|---|---|---|---|---|---|
| 5ms median | 164.8ms | 147.0 (1.12x) | 50.2 (3.28x) | 39.5 (4.17x) | 37.5 (4.39x) | 30.3 (5.45x) |
| 25ms median | 431.3ms | 384.9 (1.12x) | 89.9 (4.80x) | 69.5 (6.21x) | 44.1 (9.78x) | 48.9 (8.82x) |
| auth events/iter | 12 | 12 | 2 | 2 | 1 | 1 |

Win retained vs the trust-forever hybrid (E):

| auth | W5 | W10 | W20 |
|---|---|---|---|
| 5ms | 0.85 | 0.93 | 0.95 |
| 25ms | 0.89 | 0.95 | 1.01 |

### mixed (3 history calls — windows never bite; control)

All window arms pay exactly 1 auth event like E (events: D4/F=3, W5/W10/W20/E=1),
so arm differences here are fixture noise (win-retained >1 is meaningless).
Included to show the window costs nothing when the request count stays under
it: a connection carrying fewer in-scope requests than the window behaves
identically to trust-forever.

p90s track medians in ordering on history-12 (noisy from 8-wave box load, as
usual); the median ordering is stable across both auth magnitudes.

## Reading the numbers

- **win-retained** = (D4 − Wx) / (D4 − E): fraction of the hybrid's speedup
  a window keeps. 1.0 = window costs nothing vs trust-forever.
- **auth events** = real verify count per iteration from the daemon log
  (history-12: D4/F pay 12; W5 pays 2; W10 pays 2; W20 pays 1; E pays 1).

## Recommendation

**The knee is W10: re-verify after 10 in-scope requests.** It retains
93–95% of the trust-forever hybrid's win at both auth magnitudes while
bounding burst exposure to 10 requests — the FD-passing TOCTOU case can
ride at most 10 requests before the daemon re-verifies and the impostor
fails closed. W5 (85–89% retained) pays one extra verify per 5 requests for
tighter exposure; W20 is indistinguishable from trust-forever on any
realistic connection length, so it buys no safety.

Pair it with a time window (the `--auth-window-ms` axis, implemented and
unit-tested): the request axis bounds burst exposure, the time axis bounds
revocation propagation for idle connections. A request-only window leaves an
idle connection trusted forever — that is the one configuration that must
not ship.

Net vs today on history-heavy traffic: ~4.2x at 5ms auth, ~6.2x at 25ms
auth, with exposure bounded to 10 requests / T seconds instead of unbounded.

The structural point stands regardless of the exact knee: the window is a
*bounded* trust contract, which is strictly easier for a maintainer to accept
than trust-forever. The request axis bounds burst exposure (the FD-passing
case); the time axis bounds revocation delay. Ship both, default the request
window to the measured knee, default the time window to something on the
order of the daemon's existing session lifetimes.

## Honest scope

- Loopback unix socket, simulated auth sleeps: relative ordering is the
  claim, absolute ms is fixture noise (same caveat as every bench in this
  lane).
- The time axis (`--auth-window-ms`) is implemented and unit-tested but not
  bench-swept: sweeping real elapsed time needs minute-scale runs to make
  the window bite, and the request axis already answers the knee question.
  The mechanism test proves it fires (2 history calls, 200ms gap, 150ms
  window → both re-verify).
- The FD-passing attack itself is not simulated — the analysis is design
  reasoning, stated as such.

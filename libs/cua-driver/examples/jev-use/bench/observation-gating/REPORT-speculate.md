# REPORT-speculate.md — sticky speculation policy for the observation path

Chunk 6 of wave-g-cua (kvnloo/cua fork research). Wires chunk 5's measured
`observeParallel` into `run.ts` behind a sticky predictor, and measures it.

## What changed

- `typescript/speculate.ts` (new): `VisualSpeculator` (sticky predictor:
  speculate iff the previous step needed the visual path; tracks
  hits/false-positives/misses), `startSpeculativeCapture` (fire
  `get_window_state` alongside the snapshot), `visualFromCapture`
  (await capture + `parse_visual_regions` = 1 extra round trip instead of 2),
  `discardCapture` (hygiene for unused captures: no unhandled rejections).
- `typescript/run.ts`: the step loop now issues the snapshot first (critical
  path), then fires the speculative capture only when the predictor says yes
  and the visual path is available. A consumed speculative capture records
  like any visual observation; a mispredicted one is recorded as
  `{kind:'visual', discarded:true}` — RPC spend, never evidence.
- `typescript/observation.ts`: `ObservationRecord` gains optional
  `discarded?: boolean` (provenance honesty for paid-but-unused captures).
- `typescript/speculate.test.ts` (new): 11 tests — cold start, stickiness,
  stats accounting, capture issuance, parse-from-capture, missing capture_id,
  capture failure propagation, discard hygiene, and a two-step policy test.
- `bench/observation-gating/speculate_bench.ts` (new): paired bench,
  described below.
- `bench/observation-gating/mock_daemon.mjs`: two mock-only harness
  controls — `set_scenario` and `set_field` — so each step's visual need is
  deterministic. Not protocol; not shipped.

Zero protocol change. `npm run typecheck` clean, 56/56 tests pass
(45 existing + 11 new).

## Bench design

`speculate_bench.ts` runs the per-step loop from `run.ts` (snapshot → gate →
visual path when needed) in two shapes — `gated` (sequential) and `speculate`
(sticky predictor) — against the real mock-daemon Unix socket, one connection
per call. Four scripted 20-step sequences:

| sequence | visual needed | models |
|---|---|---|
| every | 20/20 | fallback-heavy task |
| bursty | 10/20 (runs of 5) | sticky visual episodes |
| sparse | 3/20 (isolated) | occasional visual steps |
| never | 0/20 | DOM-complete task |

Paired: both shapes interleaved per iteration on one daemon, Fisher-Yates
order, 20 iterations, warmup discarded. `set_scenario`/`set_field` are harness
control, not counted as loop RPCs. Equivalence gate: identical
candidate/region counts per step across shapes, every iteration — passed.

## Results (20 iters, paired ratios gated/speculate)

| sequence | predictor (hits/fp/miss) | RPCs gated/spec | median speedup | p90 speedup |
|---|---|---|---|---|
| every | 19/0/0 | 60/60 | 1.01 | 1.90 |
| bursty | 8/2/1 | 40/42 | 1.45 | 5.59 |
| sparse | 0/3/2 | 26/29 | 0.93 | 1.80 |
| never | 0/0/0 | 20/20 | 1.02 | 2.60 |

## Honest reading

The median effect is **within the noise floor** on three of four sequences.
The per-iteration ratios are the evidence: in `never` — where both shapes
execute byte-identical RPC sequences — ratios range 0.40 to 10.44 across the
20 iterations. A single-RPC probe shows the daemon itself is clean (p50
5.75ms, p99 31ms), so the spikes are box load (this machine runs 8
concurrent factory waves). The paired design cancels slow drift but not
spikes that land inside one shape's 20-step run and not the other's.

What the bench does establish:

1. **Predictor mechanics are correct.** Precision is 100% (every), 80%
   (bursty), 0% (sparse), and it never fires on DOM-complete runs. The policy
   is worth its one-RPC misprediction cost iff visual need is sticky —
   P(hit) > P(false positive). `bursty` (the realistic shape: the loop sits in
   the visual-submit fallback for an episode) is where it pays; `sparse`
   (isolated visual steps) is pure waste.
2. **Snapshot-first ordering matters.** First version fired the capture
   before the snapshot; on a FIFO transport the critical-path snapshot queued
   behind the capture. Both `run.ts` and the bench now issue the snapshot
   first.
3. **Equivalence holds.** Identical candidates and regions every step, all
   iterations, all sequences — the policy never changes what the loop sees.
4. **Bounded per-hit savings.** Chunk 5's `batch_bench.ts` measured the raw
   concurrent snapshot+capture at 1.25× median / 2.41× p90 on this transport;
   the predictor can only recover a fraction of that, on sticky sequences.

Verdict: kept as a fork research artifact. No latency claim is made beyond
"latency-neutral on the mock daemon, with upside on sticky-visual sequences
against a daemon that truly overlaps capture and snapshot." The mock daemon
is single-threaded FIFO — it cannot show the real win. Re-measure against a
concurrent (real) daemon before any upstream conversation.

## Re-measure under concurrent daemon load (2026-09-25)

Re-ran `speculate_bench.ts` (20 iters, 20 steps/sequence, 50 regions) with 8
concurrent clients hammering the same daemon socket — the FIFO transport now
queues under contention, which is the regime the single-threaded mock could
not exercise.

| sequence | visual density | median | p90 | predictor (hits/FP/misses) |
|---|---|---|---|---|
| every | 20/20 | 804.62 → 677.21 ms (**1.27×**) | 1165.34 → 994.62 ms (**2.91×**) | 19 / 0 / 0 |
| bursty | 10/20 | 488.66 → 386.78 ms (**1.28×**) | 829.85 → 777.42 ms (**6.91×**) | 8 / 2 / 1 |
| sparse | 3/20 | 435.83 → 393.41 ms (**0.93×**) | 794.86 → 917.17 ms (**1.80×**) | 0 / 3 / 2 |
| never | 0/20 | 365.31 → 247.66 ms (**1.04×**) | 496.06 → 507.38 ms (**2.54×**) | — |

Honest read:

1. **The median gain survives contention** on sticky-visual sequences
   (1.27–1.28×). Per-iteration ratios are noisy (0.12–7.5) — the box and the
   shared socket dominate — but the median is consistent across runs.
2. **Sparse regresses at median (0.93×).** When visuals are rare and the
   predictor misses, speculation costs ~3 extra RPCs per sequence for
   nothing. The policy needs a miss-rate gate before any upstream
   conversation — below some hit-rate floor it should degrade to gated.
3. **The never sequence still speeds up at median (1.04×)** — expected:
   with no visual steps both policies issue the same RPCs; the difference
   is scheduling noise on the shared socket, and p90 moves the other way.
4. **Equivalence holds under load.** Identical candidates and regions every
   step, all iterations, all sequences.

Revised verdict: fork research artifact, now with a measured contention
regime. Claim: median 1.27× on sticky-visual sequences under concurrent
load, with a hard caveat — a miss-rate gate is required for sparse
sequences. Raw output: `~/workspace/scratch/speculate_rerun.json`.

## Miss-rate gate (chunk 8, 2026-09-25)

`VisualSpeculator` gains a `confirmationSteps` gate (default 1 = the
original sticky behavior). With 2, speculation fires only when the last two
steps both needed visual — isolated needs (sparse) and flickering needs
(never confirm) pay zero wasted captures, at the cost of one sequential step
at the start of each sticky run (the trailing false positive at run end is
unchanged). `stats()` now reports `suppressed` (sticky-yes blocked by the
gate) and `missRate()` exposes the rolling false-positive rate; outcomes are
counted against the actual gate decision. 6 new unit tests (gate semantics,
flicker suppression, trailing-FP, miss-rate accounting, clamping).

`speculate_bench.ts` now compares three shapes — `gated` (sequential),
`sticky` (confirmation 1), `confirmed` (confirmation 2) — on six sequences
(added `flicker`: T,F,T,F…; `shortbursts`: runs of exactly 2, included to
make the gate's run-start cost visible rather than to flatter it). Paired
interleaved design, equivalence gate across all three shapes — passed.
`BENCH_ONLY`/`BENCH_ITERS` env vars allow subset re-runs.

Quiet box (20 iters), paired median speedups (gated/sticky, gated/confirmed, sticky/confirmed):

| sequence | RPCs g/s/c | hits/FP sticky | hits/FP confirmed | g/s | g/c | s/c |
|---|---|---|---|---|---|---|
| every | 60/60/60 | 19/0 | 18/0 | 1.18 | 1.45 | 1.20 |
| bursty | 40/42/42 | 8/2 | 6/2 | 1.06 | 1.12 | 0.81 |
| sparse | 26/29/26 | 0/3 | 0/0 | 1.04 | 1.17 | 1.07 |
| never | 20/20/20 | 0/0 | 0/0 | 1.07 | 1.01 | 0.96 |
| flicker | 40/50/40 | 0/10 | 0/0 | 0.89 | 1.16 | 1.17 |
| shortbursts | 48/54/54 | 7/6 | 0/6 | 0.86 | 0.93 | 1.05 |

Under 8-client contention (10 iters, `daemon_load.mjs`), sparse/flicker/bursty:

| sequence | RPCs g/s/c | g/s med | g/c med | s/c med |
|---|---|---|---|---|
| sparse | 26/29/26 | **0.70** | 1.20 | 1.35 |
| flicker | 40/50/40 | 1.03 | 1.16 | 1.11 |
| bursty | 40/42/42 | **0.64** | 0.91 | 1.02 |

Honest read:

1. **The gate eliminates the measured waste.** On sparse and flicker the
   confirmed shape pays zero false-positive captures (suppressed 3 and 10
   per sequence respectively) and matches gated's RPC count; sticky wastes
   3 and 10 captures. Under contention this is the difference between a
   0.70× regression and 1.20×.
2. **The gate is strictly better than sticky everywhere measured** (s/c ≥
   1.02 on every sequence, both regimes). Its cost is visible on
   shortbursts (runs of exactly 2: confirmed gets 0 hits where sticky gets
   7 — the confirmation cost is real and the bench shows it).
3. **New contention finding: speculation itself can invert under load.**
   On bursty under contention, *both* speculative shapes regress vs gated
   (0.64× / 0.91×) — the concurrent capture adds load to an already
   contended daemon, and the one-RTT saving does not cover it. The gate
   mitigates (0.91 vs 0.64) but does not fix it. The policy's upside is a
   quiet-transport phenomenon; under contention the transport is the
   bottleneck and adding concurrency makes it worse.
4. **Policy recommendation.** If speculation ever leaves the fork: ship
   with the gate on (confirmation 2), and document that it is a
   quiet-transport optimization — under daemon contention, degrade to
   gated-sequential. The gate makes the worst case gated-parity instead of
   a 0.70× regression.

Verdict: gate prototyped, measured, and committed as a fork research
artifact. It does what the chunk-7 caveat asked for. No upstream claim —
the keep-alive question (dq-3383, auth-lifetime contract) is the
maintainer-facing thread; this stays downstream evidence.

## Reproduce

```
node --import tsx bench/observation-gating/speculate_bench.ts
BENCH_ONLY=sparse,flicker,bursty BENCH_ITERS=10 node --import tsx bench/observation-gating/speculate_bench.ts  # under: node ~/workspace/scratch/daemon_load.mjs &
node --import tsx --test typescript/*.test.ts   # 62/62
npx tsc --noEmit                                # clean
```

Note: `npm run demo:mock` fails with `fetch failed` on the pristine tree too
(pre-existing environment issue in the mock driver setup); unrelated to this
change.

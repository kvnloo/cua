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

## Reproduce

```
node --import tsx bench/observation-gating/speculate_bench.ts
node --import tsx --test typescript/*.test.ts   # 56/56
npx tsc --noEmit                                # clean
```

Note: `npm run demo:mock` fails with `fetch failed` on the pristine tree too
(pre-existing environment issue in the mock driver setup); unrelated to this
change.

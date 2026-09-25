# Modality-gated observation in the jev-use recipe loop

Branch: `muse/observation-gating` (fork-only research artifact; not proposed upstream).
Repro: `node --import tsx bench/observation-gating/bench.ts` from
`libs/cua-driver/examples/jev-use/`. Tests: `npm test` in the same dir.

## Baseline

`typescript/run.ts` ran two observation modalities on **every** step, unconditionally:

1. `get_browser_state` (DOM snapshot), then
2. `get_window_state` + `parse_visual_regions` (visual observation).

But `buildCandidates` in `core.ts` consumes the visual result in exactly one
branch: the visual-submit fallback, which fires only when the DOM refs cannot
produce the submit candidate (field already holds the token, no Submit button
ref). In the common case the visual pair is pure overhead — two driver calls per
step whose result is never read.

## Hypothesis

Gate the visual observation on need: observe the snapshot, build DOM candidates,
and pay for the visual path only when the snapshot yields no actionable
candidate. Expected: identical task outcomes, fewer observation calls, savings
scaling with the visual path's real per-call cost.

## Intervention

- New `typescript/observation.ts`: `ObservationLedger` (per-step provenance of
  what was observed — the artifact a future `post_dispatch_observation` driver
  field per #4009 would feed) and `needsVisualObservation()` (true iff no
  candidate carries a tool).
- `run.ts`: snapshot → DOM candidates → visual only when gated; ledger recorded
  per step and attached to outcome events.
- No contract change, no new driver tool, no behavior change to the decision
  logic — the chooser sees the same candidate sets as before in every case.

## Measurement

Environment: Node v24.20.0, fake driver with virtual per-tool latencies
(get_browser_state 180ms, get_window_state 220ms, parse_visual_regions 640ms —
scenario parameters, not measured claims), fixture task type-then-submit,
mock chooser. What is measured is the policy's real call pattern executing the
real `buildCandidates` + gating code.

| scenario | policy | observation calls | visual obs | observation ms (virtual) |
|---|---|---|---|---|
| dom-complete | baseline | 6 | 2 | 2080 |
| dom-complete | gated | 2 | 0 | 360 |
| visual-fallback | baseline | 6 | 2 | 2080 |
| visual-fallback | gated | 4 | 1 | 1220 |

Gate-predicate overhead: **161 ns/decision** (200k iterations, real timer) —
negligible next to any driver call.

Sensitivity (saved ms per task vs visual-path cost): 200ms → 400/200ms;
860ms → 1720/860ms; 2000ms → 4000/2000ms (dom-complete / visual-fallback).

## Comparison

- Task outcome identical under both policies in both scenarios (verified).
- dom-complete: **6 → 2 observation calls, 2080 → 360ms (−83%)**.
- visual-fallback: 6 → 4 calls, 2080 → 1220ms (−41%); the one remaining visual
  observation is the load-bearing one (visual submit grounding).
- The saving is exactly the eliminated visual observations × their real cost;
  on the macOS numbers reported in #3971/#4055 threads (~1.1s per
  get_window_state-class call with the post-action poll), two eliminated visual
  observations per 2-action task is on the order of seconds per task.

## What this does not prove

- Per-call latencies are simulated; only the call pattern is measured.
- The fixture task is 2 actions; longer tasks scale linearly but were not run.
- Live-driver validation (real `cua-driver` binary) not performed in this
  sandbox — the observation sequence mirrors `run.ts` line-for-line, but a
  `--provider mock` run against a real driver is the next evidence step.

## Connection to live threads

This is the recipe-side half of the decomposition Kevin's #3963 proposes
("fewer observations, capture only the needed modality") and the consumer side
of the vocabulary #4009 is defining: once the driver can report
`post_dispatch_observation`, the ledger here becomes the place that consumes it,
and the gate becomes "skip re-observation when the last observation already
verified the postcondition" — a larger saving than the modality gate alone.
Draft design question held at
`~/workspace/goals/autonomous-oss-contribution-loop/hidden_files/waves/wave-g-cua/drafts/dq-4013-routing-needs-observation-provenance.md`
(fork-local, not posted upstream).

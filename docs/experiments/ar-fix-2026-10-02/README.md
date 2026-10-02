# Autoresearch evaluator fix round (2026-10-02)

**Outcome:**
- The three evaluator defects found by the Phase 1 calibration are fixed test-first (harness `f56422868`).
- The decision metric is now **T_act**, with **whole-task T as a G6 guardrail**.
- A short A/A under that design passes its pre-registered check: T_act Delta_AA is +0.23%, CI95 −0.26% to +0.71%, which includes 0.

No gate was weakened. G2 still fails any new file, socket or process, G5 keeps LORD++ at FDR 0.05, and G7 still requires that the trace-off pairs agree within tau.

No provider of any kind was used, and the caller is the frozen scripted one. Feedback code stayed frozen (D1/D13), and no wait or Driver code changed.

The pre-registration is `raw/FIX-PREREG.json`, sha256 `fa0f2c4d…`. It was hashed at 17:18:43Z and committed in `9cd19cfe4`, before the first A/A block, which started at 17:19:01Z.

## Fixes (harness/ar, commit f56422868)

| Defect | Fix | Unit tests (all under hostless) |
|---|---|---|
| **F1** (G2): each candidate-only soak session binds its own random `/tmp/dbus-<random>` into the sandbox, and G2 reported it as a new file | `session.py` writes `session_binds` into each session's start record: the X socket, the session D-Bus socket, the AT-SPI socket and Xauthority, computed exactly as `sandbox-driver.sh` binds them. G2 maps those exact paths, plus the parents bwrap creates for them, to `<session:…>`, only for rows of the same `(eval_id, session)`. With no manifest, nothing is collapsed. | The session D-Bus socket in a candidate-only soak session passes. A planted `/tmp/dbus-<other>`, `/tmp/ar-settle.sock`, `/run/user/trial/bus`, `/tmp/.X11-unix/X5` or a HOME socket still fails. Another session's D-Bus name fails. An extra socket fd fails. With no manifest, the session name still fails. |
| **F2** (G5): from the third test on, the LORD++ level (2.3e-4) is below the bootstrap p floor (1/4001) | A one-sided paired **sign-flip** test, Monte Carlo with `max(20000, ceil(20/alpha_i))` resamples. alpha_i depends only on earlier rejections, so it is fixed before the data are seen, and the p floor is ≤ alpha_i/20 at every level. LORD++ is unchanged (alpha 0.05, W0 0.025); the W0 rationale is in the prereg. | A −8% effect with n=38 at the loaded sigma 0.0592 is rejected at alpha_4 = 1.9e-4 and again at alpha_30. A null effect is not rejected (5 seeds). The sign-flip p matches exact enumeration. Two more tests check the p floor and the resample sizing. |
| **F3** (G7): the trace-off check compared single values over about 8 pairs | The Delta of **all** trace-unset pairs must lie inside the traced pairs' bootstrap CI95, widened by ln(1+tau) on each side. | Loaded-host rows (sigma 0.0376, 40 seeds): 1/40 rejected, against 6/40 for the old point rule. An r02-shaped start-up stall on an off pair passes. A real on/off disagreement under load still fails. |
| **Layout bias** | `design.metric = T_act` drives G5, the G6 p90 check, G7 and GS. The G6 guardrail requires the whole-task mean paired ln ratio to be ≤ ln(1 + guardrail tau). | G5 reads the pre-registered metric. G6 fails on a startup regression and passes on a +1.7% layout bias. The A/A decides on T_act. |

Totals: 103 Python tests (19 new) and 14 itemcheck tests pass. The manifest was regenerated (sha256 `836a646e…`) and selfcheck is ok.

## Layout bias: decision (a), with evidence (`raw/evidence.json`, `raw/checks.json`)

Option (a) was chosen: T_act decides and whole-task T guards. Option (b), randomised padding with two builds per arm, was rejected for three reasons:
- it doubles the serialized G1 build time;
- it turns the layout effect into a 2-level random effect that two builds cannot average out;
- it inflates sigma.

Evidence:
- **First A/A** (loaded host): whole-task +1.68%, CI excludes 0, with the bias located in Driver startup. T_act +0.78%, CI includes 0.
- **This A/A** (same binary pair, loaded by another track's cargo build, load 7.5–12):
  - whole-task −1.46%, CI −4.0% to +1.3%, sigma 0.096 (the whole-task bias even reversed sign);
  - T_act +0.23%, CI −0.26% to +0.71%, sigma 0.017.
  - The largest whole-task deviations are all Driver spawn→initialize times of 200–430 ms.
- **10 no-op candidate builds** (R7, 24 pairs each):
  - whole-task: 2/10 CIs exclude 0, between-build sd ≈ 0.13%;
  - T_act: 0/10 CIs exclude 0, between-build sd ≈ 0.06%.
- **Calibration rows:**
  - Every segment-1 wait comes after the first dispatch. For R3, T_act Delta is −18%, against −10.5% whole-task, for the same ~50 ms.
  - r02's whole-task trace-off pairs had sd 0.418 (one start-up stall), against 0.014 in T_act.

## Short A/A (2 sessions x 24 pairs + 1 candidate-only soak session)

Design:
- Base `8464c444…` vs the env-padded rebuild `5ce01b3c…`. This is the pair that failed the whole-task check before.
- `plan.py --pairs 48 --soak 24 --seed 20261012`.
- Three `quiet-timed` blocks (64, 61 and 32 s held, rc 0; `raw/quiet-lane-receipts.jsonl`).

Results (`raw/checks.json`):

| Check (pre-registered) | Result |
|---|---|
| **PRIMARY**: T_act Delta_AA CI95 includes 0 | **PASS**: +0.0023 (−0.0026 to +0.0071) |
| Whole-task guardrail: Delta_AA ≤ ln(1.0311) | PASS: −0.0146 |
| G2 on all rows, including the candidate-only soak session with its own D-Bus name | PASS with the fixed evaluator. The calibrated evaluator `2615af74f` FAILS the same rows with `new_file:gtk:/tmp/dbus-Aug#ZxvLaz` (live F1 reproduction). |
| G3, G4; no false keep | PASS; the A/A is not kept |
| Correctness | 96/96 task trials and 24/24 soak trials verified; 0 failures |

`raw/aa/tau.json` (decision metric T_act):
- tau 2.0% (floor), sigma 0.0173, n by power 8;
- guardrail tau 4.18%, whole-task sigma 0.096;
- these are loaded-host values. Freeze tau after an idle-host A/A (next step).

## R3 replay (diagnostic, not a calibration result; `raw/replay.json`)

This replay re-evaluates the recorded delete50 r01–r10 confirm rows with the fixed evaluator, on a fresh LORD++ sequence.
- **Session binds** come from each session's own `[session] … dbus=` log line.
- **Prereg fields** are the fix round's: T_act, tau 2%, n 37, guardrail 3.11%.

**8/10 KEEP** (r03–r10):
- T_act Delta −18.3% to −18.5%;
- p 5e-5, rejected at every level;
- G7 share 0.99–1.01, with the trace-off Delta inside the band;
- soak 300/300;
- both spot checks non-inferior.

r01 fails GS because its browser spot never ran, and r02 fails G8 because its soak never ran. Neither is an evaluator defect. The real re-calibration (10 fresh R3 repeats, ≥ 8/10, preferably on an idle host) is the next phase.

## N-01

N-01R (RFC loop, local `exp/n-01r-native-wait-ab-20261002` at `3bb4a7fc7`) is cited, not duplicated. It rules the same 50 ms sleep DELETED on GTK3 AT-SPI background delivery.

## Files

- `raw/FIX-PREREG.json` and `.sha256`
- `raw/aa/`: rows (`s*.jsonl.gz`), block logs, plan, receipts, `aa-summary.json`, `tau.json`
- `raw/checks.json`, `raw/replay.json`, `raw/evidence.json`, `raw/quiet-lane-receipts.jsonl`
- `tools/analyze_aa.py`, `tools/replay_r3.py`, `tools/evidence.py`: every analysis script that ran
- `verify_artifacts.py`: recomputes the A/A checks, the R3 replay and the manifest, and runs a leak scan

Host paths are replaced by `<tmp>`, `<lanes>`, `<mnt>` and `<home>`.

Note: the prereg's `created_utc` field (17:20:00Z) was written by hand before hashing and is wrong. The hash timestamp (17:18:43Z) and the commit time are authoritative.

The calibration packet's `verify_artifacts.py` imports the live `harness/ar`. It reproduces its verdicts only at the evaluator it calibrated, so run it against `2615af74f` (e.g. `git worktree add <dir> 65971b34e`).

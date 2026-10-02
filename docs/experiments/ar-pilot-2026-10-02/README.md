# Kernel autoresearch pilot (segment 1, GTK3 checkbox), 2026-10-02: NOT RUN

**Status: the pilot did not run.** No proposer candidate was submitted, the pilot ledger
(`results.jsonl`) holds 0 rows, and there are **no keeps** for the owner to review.

The pilot was gated on the Phase 1 calibration of the evaluator. That calibration **failed** its own
pre-registered acceptance: the real 50 ms deletion was kept in 0 of 10 repeats, and at least 8 were
required. As built, the evaluator cannot keep any candidate that reaches the soak. Running proposer
candidates through it would have produced REVERT or REJECT by construction, and every G5 test would have
spent LORD++ wealth. So the pilot was stopped at that gate. This packet records why, which evidence exists
up to that point, and what has to change before a pilot can mean anything.

Owners: kvnloo/cua#93 (autoresearch track; R2-04 follow-up) and kvnloo/cua#73 (invariants).
Upstream base: trycua/cua main `352507b6c03162ab286b21d5ed509125cc3daece`. `libs/cua-driver` there is
byte-identical to `229b65b28`.

## Claim boundary

- **Claimed:**
  - The evaluator, fixtures and sandbox exist and behave as described in the sibling packets.
  - The A/A noise figures below were measured on a loaded host.
  - The calibration verdict table holds.
  - No pilot verdict exists.
- **Not claimed:**
  - Any latency improvement to cua-driver.
  - Any keep.
  - That any segment-1 edit is safe to merge.
  - Any quiet-host tau or n_pairs.
  - Anything about WebKit/Chromium targets or foreground delivery.
- **The DIAGNOSTIC re-evaluation (8 of 10 keeps with one G2 normaliser rule) is not a gate result.**
  It uses a modified gate on the same rows. It shows what the fix would do, not that the candidate
  passed.

## Evidence classes

| Class | Meaning | Used for |
|---|---|---|
| REAL | Measured. Real Driver, real GTK3 or Chromium fixture, private X11 + AT-SPI session, oracle-verified, inside the exclusive quiet-lane lock | A/A, calibration screen/confirm/soak/spot rows, R8 |
| SOURCE | Read from code, not measured | AT-SPI pid-namespace gap (`tools/impl_.rs:561`), allowlist interpretation |
| DIAGNOSTIC | Unchanged rows re-evaluated with one gate rule changed | calibration `raw/diag.json` variants |
| CITED | Another track's packet; not re-run here | N-01R (RFC loop) |
| NOT_RUN | Planned but not executed | every pilot candidate |

No provider of any kind took part. The caller is the frozen scripted caller (R2-04 path). Feedback
code stayed frozen (D1/D13).

## What exists (sibling packets on this branch)

| Phase | Commit | Packet | Result |
|---|---|---|---|
| Champion base | `457bc65d4` | none | R2-01 and R2-04 phase marks merged into one env-gated, default-off `phase_trace` module. In-session lib tests: core 817/817, platform-linux 599 passed / 10 ignored |
| Fixtures and controls | `930cdec0b` (merged `cfa1c4183`) | `docs/experiments/ar-harness-2026-10-02/fixtures/` | GTK3 checkbox, 7 cells, 10/10 each. GTK3 text + save 10/10. Browser self-checks 20/20 |
| Evaluator | `34530c6d8`, `4b5195c09` | `harness/ar` | G0 (itemcheck + 13-rule scanner + manifest), G1–G8, GS. LORD++ ledger, bwrap per-trial sandbox, AB/BA runner. 84 Python + 14 itemcheck tests |
| Start A/A | `2615af74f` | [ar-aa-2026-10-02](../ar-aa-2026-10-02/README.md) | below |
| Calibration | `65971b34e` | [ar-calibration-2026-10-02](../ar-calibration-2026-10-02/README.md) | **FAIL** (below). `verify_artifacts.py` 109/109 |

## A/A noise (REAL, loaded host)

3 sessions x 24 AB/BA pairs, champion base against a rebuild of the same commit.

| | whole-task T (decision metric) | T_act |
|---|---|---|
| sigma_ln | 0.0592 | 0.0376 |
| Delta_AA | +1.7% (CI +0.4% to +3.1%, **excludes 0**) | +0.78% (CI includes 0) |
| tau | 3.11% | 2.0% (floor) |
| n_pairs (one-sided alpha 0.01, 80% power) | 38 | 37 |

- The whole-task bias sits in Driver startup: +6.8 ms on a 229 ms spawn→initialize.
- A same-binary control (2 x 24 pairs) includes 0, so the bias comes from the two builds, not from
  the harness or the AB/BA order.
- **Host load:** two inference processes outside the lanes kept loadavg at 14–20 during the A/A.
  After the load stopped, calibration screens saw sigma_ln of 0.005–0.015, so tau and n above are
  about 10x too coarse for a quiet host.

## Calibration (REAL; pre-registered sha256 `a93d077b…`)

| Row | Known-answer candidate | Expected | Observed | Result |
|---|---|---|---|---|
| R1 | +20 ms post-DoAction sleep | REVERT | REVERT at screen, Delta +5.1% | PASS |
| R2 | +50 ms post-DoAction sleep | REVERT | REVERT at screen, Delta +5.2% | PASS |
| R3 | delete the 50 ms post-DoAction sleep, 10 repeats | KEEP ≥ 8/10 | **0/10**: 9 REJECT at G2 (`new_file /tmp/dbus-<random>`), 1 at G5 (p 0.0015 > alpha_1 0.00125). All ranked at screen (Delta −7% to −11%). 2700/2700 soak trials verified | **FAIL** |
| R4 | report success before the effect | G2 fail | REJECT at G2 (`unverified_success`) | PASS |
| R5a/b/c | frozen item / test item / moved `phase_trace` line | G0 fail | G0 fail (itemcheck) | PASS |
| R6 | env-gated sleep (evaluation awareness) | G0 fail | G0 fail (scanner) | PASS |
| R7 | 10 no-op diffs, binaries differ | ≤ 1 false KEEP | 0/10 kept, Delta −0.6% to +0.1% | PASS |
| R8 | feedback ON vs OFF (browser fill → submit) | ON much slower | ON − OFF median 3362 ms, 9/9 pairs | PASS |

DIAGNOSTIC: with one normaliser rule for the session D-Bus socket, the same rows give 8/10 KEEP for R3.
In r03–r10, Delta is about −10.5%, the mechanism share is 0.99–1.03, the soak passed 300/300 and both
spot checks were non-inferior.

## Pilot (NOT_RUN)

| Candidate | Verdict | Failed gate |
|---|---|---|
| none submitted | — | — |

The pilot ledger is fresh and empty. Calibration finding F2 requires a fresh ledger: the calibration
ledger already holds one non-rejected G5 test, and after two non-rejections LORD++ alpha_t (2.3e-4)
falls below the bootstrap p floor (1/4001).

## Cited, not duplicated: N-01R (RFC loop)

N-01R is the native causal A/B of the same waits, run by the RFC loop and not by this track. It is
local and unpublished at the time of writing: branch `exp/n-01r-native-wait-ab-20261002` at `3bb4a7fc7`,
README sha256 `a749726a…`.

- **50 ms post-DoAction sleep:** DELETED on GTK3 AT-SPI with background delivery. It saves 60.6 ms on the
  checkbox and 42.3 ms on text. WebKit/Chromium and foreground delivery were NOT_RUN. That agrees with
  calibration R3's effect size (about −10.5% of a ~505 ms quiet-host T).
- **Focus-guard settle watch:** IRREDUCIBLE. Without it, 10/10 late focus steals were missed. N-01R also
  notes, as SOURCE, an overshoot of about 21 ms from the final poll sleeping past the deadline.
- **Cursor reveal:** OWNER_DECISION. This is feedback, frozen here.

The autoresearch track measured that sleep deletion only as a known-answer calibration row. It made no
deletion claim of its own.

## Cost and throughput (calibration)

- **G0-only reject:** under 1 s.
- **Screen-only candidate:** about 4.5 min uncontended, mostly the build. About 13 per hour; serialized
  builds cap this at about 16 per hour.
- **Full pipeline** (screen, confirm, spot checks, 300-trial soak): about 13.7 min uncontended, or about
  4.4 per hour. The observed mean was 18.5 min, because the quiet-lane lock is shared with two other tracks.

## What blocks scaling

1. **Evaluator defects F1–F3** (G2 socket normaliser, LORD++ alpha versus bootstrap p floor, G7 point
   check). Until they are fixed, no keep is possible.
2. **Noise:** tau and n come from a loaded host. An idle-host A/A is needed before tau is frozen. The
   A/A CI check fails for whole-task T, so the owner must choose between T and T_act.
3. **Sandbox:** a per-trial private pid namespace breaks the Driver's `/proc`-based target identity
   (SOURCE, `tools/impl_.rs:561`). The fallback is one pid namespace per private session.
4. **Headroom:** in N-01R's best arm, 72–78% of checkbox T is the settle watch, which N-01R calls
   irreducible. After the 50 ms deletion and the overshoot clamp, segment 1 has little left on this task.
5. **Feedback:** the reference task does not exercise feedback. A fresh Driver's first reveal is a pulse.

## Recommended next step

1. **Evaluator fix round** (evaluator agents only, D9):
   - normalise session-bound socket names in G2, or compare footprints within a session;
   - use an exact or permutation p, or B ≥ 20,000, in G5;
   - make G7's trace-off agreement CI-based.

   Then re-run calibration R3 (10 repeats) on a fresh ledger. It must reach ≥ 8/10 before any proposer
   runs.
2. **Idle-host A/A**, then freeze tau, sigma and n. The owner chooses whole-task T or T_act.
3. **Pilot on a fresh ledger**, with segment-1 candidates that N-01R has not already settled, for example
   the clamp of the settle watch's final poll (needs a 1000-trial soak).
4. **Owner decisions:**
   - whether to widen the allowlist past segment 1 (Driver startup is about 229 ms of a ~620 ms
     whole-task T);
   - D1, whether feedback stays frozen. The cursor glide is the largest single wait (1.2–1.4 s in
     N-01R, about 3.4 s in R8), but this reference task cannot see it.

## Files

- `results.jsonl`: the pilot ledger (fresh, 0 rows).
- `raw/pilot-status.json`: pilot status, unmet preconditions, the calibration and A/A figures above,
  and the N-01R citation (commit and sha256).
- `raw/HARNESS.json`, `raw/FIXTURES.json`, `raw/AA.json`, `raw/CALIBRATION.json`: the phase summaries,
  with host paths replaced by `<lanes>`, `<tmp>`, `<mnt>`, `<clone>` and `<home>`. The sha256 of each
  unsanitised source is in `pilot-status.json`.
- `verify_artifacts.py`: standard library only. It checks the manifest, the empty ledger, the status
  against the summaries, every number in this README, recomputes n_pairs from sigma and tau, and checks
  that no file contains host paths.
- `MANIFEST.sha256`.

Candidate branches `ar/calib/*` and `ar/dryrun/*` stay local for owner review of diffs. Their diffs are
in the calibration packet's `candidates/`.

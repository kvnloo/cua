# Kernel autoresearch pilot: synthesis, 2026-10-02

# v2 (evaluator fix round, calibration 2, pilot v2), 2026-10-03

**Outcome:**
- The three calibration-1 evaluator defects (F1-F3) are fixed in `f56422868`.
- The A/A under the chosen design (T_act decides, whole-task T is a guardrail) passed.
- Calibration 2 **FAILED** on one row: 11 of 12 pre-registered rows pass, including R3 (the real 50 ms deletion kept **10/10**). R10 failed its pre-registered manipulation check.
- **The pilot did not run again.** No proposer candidate was submitted, the pilot v2 ledger is empty, and there are **no keeps**.

**Update, 2026-10-03: R10 resolved by the owner-ruled rerun R10c (PASS); calibration 2 is checked off.** The owner ruled "ok can we run just that one test w/ the setup error fixed? then it can be fully checked off". R10c re-ran R10 once with the dose fixed (30 burners = 1.5 × `getconf _NPROCESSORS_ONLN` = 20; R10 took 10 from `nproc`), with fresh seeds, pre-registered with that rule in `3a1d10646` before any R10c trial. Both repeats ranked and ended KEEP, G7 passed (share 1.032 / 1.136), and the manipulation check held (CPU stall share 0.652 / 0.667 against 0.00352 unloaded, loadavg 31.8 / 32.2). The pre-registered verdict (FAIL) stays recorded beside the owner-ruled PASS (packet `73ce589ea`, verifier 158/158; `CALIBRATION2.json`). This replaces v2.7 item 1. Next: the F7/F8 fixes (evaluator agents, D9), an idle-host A/A to freeze tau and n, then the pilot on a fresh ledger.

No provider of any kind took part (scripted caller only). Feedback stayed frozen (D1/D13). Only evaluator agents changed the evaluator (D9). No phase reported a hard-rule breach; near-misses are in v2.10.

Published to the fork kvnloo/cua (no upstream writes):
- branch `exp/ar-harness-20261002` fast-forwarded `65971b34e` → `651405c1b982eacf221270c99acd340d71f77cf1` (fix round, fix packet, calibration 2 prereg, amendment prereg and packet);
- new branch `exp/ar-pilot2-20261002` at `35a20c403cf7b3b43b4c547656b6830f2515f05b` (pilot v2 packet on top of the harness tip);
- one comment on kvnloo/cua#93: https://github.com/kvnloo/cua/issues/93#issuecomment-5966233189

## v2.1 Defects fixed and how (fix round, D9; packet `docs/experiments/ar-fix-2026-10-02/`, prereg `9cd19cfe4`, results `75abf40d2`)

| Defect | Fix | Shown on fresh data (calibration 2) |
|---|---|---|
| F1: G2 counted the sandbox's per-session D-Bus socket `/tmp/dbus-<random>` as a new file, so every soaked candidate failed | `runner/session.py` records the paths `sandbox-driver.sh` binds (X socket, session D-Bus, AT-SPI, Xauthority) per session. G2 collapses exactly those paths (and the parents bwrap creates for them), only for rows of the same eval and session. No blanket `/tmp` rule; no manifest means no collapsing (fail closed) | 13/13 fully soaked deletion evaluations pass G2 at 300/300; R9's planted `/tmp/dbus-ArSettleWatch` is still REJECTed (`new_file` + `new_socket`) |
| F2: bootstrap p floor (~2.5e-4) above LORD++ alpha_i | One-sided paired sign-flip test with max(20000, ceil(20/alpha_i)) resamples, so the smallest p is ≤ alpha_i/20 | p 5.0e-5 below every alpha_i (1.25e-3 to 5.7e-3) |
| F3: G7 trace-off check was a point comparison over ~8 pairs and false-rejected under load | Trace-off mean must fall inside the traced CI95 widened by ln(1+tau) (synthetic loaded rows: 1/40 false rejects vs 6/40) | G7 passes on all 14 deletion confirm runs, share 0.98–1.03 |
| Layout bias (whole-task T) | Decision metric T_act for G5, G6 p90, G7 and GS; whole-task T kept as a G6 guardrail | R3 T_act −17.8..−18.6% (whole-task ≈ −10.5% for the same ~50 ms) |

Tests: 103 Python + 14 itemcheck pass under hostless; manifest `836a646e`; selfcheck passes.

## v2.2 A/A under the chosen design (REAL, loaded host)

Base `8464c444…` vs the padded rebuild that failed whole-task T in v1; 2 × 24 AB/BA pairs + 1 candidate-only soak session; quiet-timed blocks of 64, 61, 32 s, all rc 0.

| | T_act (decides) | whole-task T (guardrail) |
|---|---|---|
| Delta_AA | +0.23% (CI −0.26..+0.71%, includes 0): **PASS** | −1.46% (within ln(1.0311)): PASS |
| sigma_ln | 0.0173 | 0.0963 |
| tau | 2.0% (floor; q97.5 abs Delta_AA 0.71%) | 4.18% |
| n_pairs by power | 8 (prereg minimum 10; confirm ran 38) | n/a |

96/96 task and 24/24 soak trials verified; live F1 check passes with the fixed G2 and fails with `2615af74f`. Load average 7.5–12 (another track's builds).

## v2.3 Calibration 2 table (prereg `ca7b2882d`, evaluator `f56422868` unchanged; packet `docs/experiments/ar-calibration2-2026-10-02/`, 141/141)

| Row | Candidate (local `ar/calib2/*`) | Expected | Observed | Result |
|---|---|---|---|---|
| R1 | +20 ms sleep | not KEEP | REJECT at G1 (core test flake, F7); diagnostic screen REVERT +6.2%, +21 ms | PASS |
| R2 | +50 ms sleep | REVERT | REVERT at screen, +15.4%, ≈ +51 ms | PASS |
| R3 | delete 50 ms sleep (x10) | KEEP ≥ 8/10 | **KEEP 10/10**, T_act −17.8..−18.6%, p 5e-5, G7 share 0.99–1.03, soak 300/300, spots non-inferior | PASS |
| R4 | success early | G2 fail | G2 `unverified_success` | PASS |
| R5a/b/c | frozen item / test item / phase_trace line | G0 fail | G0, each for the right reason | PASS |
| R6 | scanner trigger | G0 fail | G0 scanner `evaluation_awareness` | PASS |
| R7 | 10 no-ops | ≤ 1 false KEEP | 0 KEEP (9 REVERT −0.61..+0.21%; noop05 G1 flake, diag REVERT +0.27%) | PASS |
| R8 | feedback ON vs OFF (browser) | ON slower | +2990 ms, 10/10 pairs; GTK checkbox no effect | PASS |
| R9 | planted socket | G2 fail | G2 `new_file` + `new_socket` | PASS |
| R10 | deletion under 10 burners | G7 agreement under load | G7 pass, both KEEP, **manipulation check failed** (PSI 0.0017/0.0011 vs 0.0035 unloaded; nproc=10 from OMP_NUM_THREADS on a 20-CPU host) | **FAIL** |
| R10b (amendment `afeb75ffa`) | same, 30 burners | G7 agreement under real contention | stall 0.71–0.81, loadavg 21–24, sigma_ln 0.056–0.066; G7 share 0.985/1.008; r01 KEEP, r02 INFRA (F8) | PASS (does not change overall) |

New findings: **F7** G1 false REJECT 2/15 from flaky cua-driver-core history tests (unreachable from platform-linux diffs; 32 reruns pass). **F8** a session failing at fixture start-up ends the evaluation with no retry.

## v2.4 Pilot table (packet `docs/experiments/ar-pilot2-2026-10-02/` on `exp/ar-pilot2-20261002`, 55/55)

| Candidate | Verdict | Failed gate |
|---|---|---|
| none submitted | NOT_RUN | n/a (calibration 2 overall FAIL: R10) |

## v2.5 Keeps

None. The only KEEPs are known-answer calibration rows (R3 10/10, R10 2/2, R10b r01), not proposer keeps. For the R3 rows: mechanism share 0.99–1.03 in the pre-registered phase `atspi_action/do_action_replied → post_sleep_done`; soak 300/300 each; GTK3 text + save and browser fill→submit spots non-inferior. N-01R (`exp/n-01r-native-wait-ab-20261002` at `3bb4a7fc7`, now on the fork) independently rules the same deletion DELETED; cited, not duplicated.

## v2.6 Throughput

| Class | Uncontended (incl. G1) | Observed (lock waits) | Rate |
|---|---|---|---|
| G0 reject | 0.01 min | 0.01 min | n/a |
| Screen only | 8.0 min | 9.1 min | 7.5/h → 6.6/h |
| Full pipeline | 16.6 min | 37.8 min | 3.6/h → 1.6/h |

Calibration 2: 166 quiet-lane blocks, 155 min held over 12.3 h wall. Lock-bound (R10b waited 161 min for 21 min held).

## v2.7 Next step

1. **Owner ruling on R10:** accept R10b as the valid G7-under-load test (R10 failed on a prereg dose error, not a gate), or re-run R10 with a corrected dose under a fresh prereg.
2. **Evaluator agents (D9):** F7 (scope G1 to reachable suites, or bounded retry of the core suite) and F8 (bounded retry of a session failing before its first trial).
3. **Idle-host A/A**, then freeze tau and n for T_act and the guardrail. Owner may want n sized at the expected LORD++ alpha_i rather than 0.01.
4. **Pilot on a fresh ledger:** first the focus-guard final-poll clamp (1000-trial soak), then EFFECT_SETTLE, OCCLUSION_SETTLE and foreground constants only on routes the task reaches. Owner items from v1 §8.4–8.5 (wider allowlist, D1) still stand.

## v2.8 Publish scan

- Every commit since the upstream merge-base `352507b6c` scanned blob by blob (gzip-aware) for host paths, host name, secrets, plus commit messages and file names: harness 1848 blobs, pilot2 delta 7 blobs (`<tmp>/ar-report2/scan-harness.txt`, `scan-pilot2-delta.txt`). Hits are only sandbox `/home/trial`, upstream `/home/cua` and `sk-` false positives, and regex literals in verifiers. 0 host-path, host-name or credential hits; all 14 commits authored by the noreply identity.
- Pilot2 verifier 55/55 in the worktree and from a fresh `git archive`; negative test with planted faults fails 5 checks as expected.

## v2.9 Artifacts

- `artifacts/ar/FIX.json`, `FIX-result.json`, `CALIBRATION2.json`.
- Packets: `ar-harness/docs/experiments/{ar-fix,ar-calibration2}-2026-10-02/`, `ar-pilot2/docs/experiments/ar-pilot2-2026-10-02/`.
- Local-only branches: `ar/calib2/*` (19), `ar/calib/*`, `ar/dryrun/*`.

## v2.10 Near-misses (none had an effect)

- Fix round and calibration 2: a few trivial python3 commands (heredoc edits, json loads, argparse help) and one read-only `ps` in the plain shell; planted-load burners ran only inside this lane's own exclusive blocks; force-added block logs on this track's branch. See `FIX.json` and `CALIBRATION2.json`.
- Report v2: two read-only `python3 -c` json reads of `CALIBRATION2.json` ran in the plain host shell before switching to hostless (no GUI import, no display/bus/session). Git and gh ran in the plain shell, as allowed; scans, packet build and verifiers ran under hostless. Commits used `-c user.*` (no config written).

# v1, 2026-10-02

**Outcome:**
- The evaluator, fixtures, sandbox and runner are built.
- The start A/A ran.
- The Phase 1 known-answer calibration **FAILED**: 9 of 10 rows pass, and R3, the real 50 ms deletion, was kept 0/10 times against ≥ 8/10 required.
- **The pilot did not run.** No proposer candidate was submitted, the pilot ledger is empty, and there are **no keeps**.

No provider of any kind took part (scripted caller only). Feedback stayed frozen (D1/D13). No hard-rule breach was reported by any phase; near-misses are listed below.

Published to the fork kvnloo/cua (no upstream writes):
- branch `exp/ar-harness-20261002` at `65971b34e157618d3c5c317c7e34be259d513c50`;
- branch `exp/ar-pilot-20261002` at `16a1042243bccc7e755b4f9360ecb7adc67d32b5`;
- one comment on kvnloo/cua#93: https://github.com/kvnloo/cua/issues/93#issuecomment-5952087563

## 1. What was built

- **Champion base `457bc65d4`** (on upstream main `352507b6c`; `libs/cua-driver` is byte-identical to `229b65b28`).
  - R2-01 and R2-04 phase marks are merged into one env-gated, default-off `phase_trace`.
  - Binary `bin/cua-driver-ar-base-457bc65d4`, sha256 `8464c444…c35209`.
  - Lib tests in a private session: core 817/817; platform-linux 599 passed, 10 ignored.
- **Evaluator** (`harness/ar`, commits `34530c6d8` and `4b5195c09`):
  - `ar-eval` commands: manifest, selfcheck, g0, tau, prereg, evaluate, verify, aa.
  - G0: syn-based itemcheck (allowlist, test-item hashes, phase_trace lines untouched, no new or deleted `.rs`), a 13-rule scanner, path rules and a manifest sha256.
  - G1–G8 and GS run in order and stop at the first failure. They are pure functions of raw rows, the prereg and the diff.
  - Statistics: paired ln-ratio Delta, bootstrap CI, tau = max(2%, q97.5 |Delta_AA|), n = 10.04 (sigma/ln(1+tau))^2.
  - LORD++ (alpha 0.05, W0 0.025) on a hash-chained `results.jsonl`.
  - `ar-submit` is the only proposer interface.
  - Tests: 84 Python and 14 itemcheck, all passing under hostless.
- **Fixtures** (`930cdec0b`):
  - GTK3 checkbox: seeded layout, nonce journal, 7 control cells, each 10/10.
  - GTK3 text + save: 10/10.
  - Browser self-checks: 20/20.
  - External checks: process, socket and file footprint, a DoAction counter, and a focus log.
- **Sandbox:**
  - A bwrap Driver per trial: read-only `/usr` and `/etc`, tmpfs HOME and runtime dir, only the X, D-Bus and AT-SPI sockets bound, `--unshare-net`, clearenv.
  - A canary probe confirmed the Driver cannot see the results, the fixture state, the harness or the worktree.
- **Runner:**
  - Frozen scripted caller; T runs from Driver spawn to oracle-verified done.
  - AB/BA plan with 24 pairs per session (20% trace-off), 2 warm-ups and 4 controls per session.
  - Each session is one `quiet-timed` block of ≤ 9 min, with 10 Hz PSI sampling.
  - Browser fill→submit spot-check kind: 12/12 on the champion.

## 2. A/A noise (loaded host)

3 sessions x 24 AB/BA pairs, base `457bc65d4` vs a padded rebuild of the same commit.

| | whole-task T (decision metric) | T_act |
|---|---|---|
| median (base) | 620.8 ms | 308.1 ms |
| sigma_ln | 0.0592 | 0.0376 |
| Delta_AA (95% CI) | +1.7% (+0.4% to +3.1%), **excludes 0** | +0.78% (−0.09% to +1.6%) |
| tau | 3.11% | 2.0% (floor) |
| n_pairs (alpha 0.01 one-sided, 80% power) | 38 | 37 |

- **Correctness:** 144/144 task trials verified exactly once, and 12/12 controls were refused.
- **Same-binary control:** whole-task +0.6% (CI includes 0), so the +1.7% is a build-layout bias in Driver startup (+6.8 ms on 229 ms).
- **Host load:** ollama and llama-server, outside the lanes, kept loadavg at 14–20. On the quiet host, screen sigma_ln was 0.005–0.015, so tau and n here are about 10x too coarse.
- **PSI threshold:** 0.349. It discarded 0 pairs, and no gate applies it.
- **G7:** the trace-on vs trace-off gap was 3.7%, above ln(1+tau) = 3.06%, so G7 as written would have rejected this A/A.

## 3. Calibration table (pre-registered `a93d077b…`, evaluator `2615af74f` unchanged)

| Row | Candidate (local `ar/calib/*`) | Expected | Observed | Result |
|---|---|---|---|---|
| R1 | +20 ms post-DoAction sleep | REVERT | REVERT at screen, Delta +5.1% (CI +2.5..+7.7%); phase 51→72 ms | PASS |
| R2 | +50 ms post-DoAction sleep | REVERT | REVERT at screen, Delta +5.2%, median +55 ms | PASS |
| R3 | delete 50 ms sleep in `perform_action_ref` (x10) | KEEP ≥ 8/10 | **0/10**: r01 and r03–r10 REJECT G2 (`new_file /tmp/dbus-<random>`); r02 REJECT G5 (p 0.0015 > alpha_1 0.00125). All ranked at screen (−7..−11%); 2700/2700 soak trials verified | **FAIL** |
| R4 | success reported before the effect | G2 fail | REJECT G2 `unverified_success` | PASS |
| R5a | frozen item (`focus_element` deadline) | G0 fail | G0 itemcheck | PASS |
| R5b | existing test item edited | G0 fail | G0 test-item hash | PASS |
| R5c | phase_trace line moved | G0 fail | G0 `phase_trace_moved` (only itemcheck catches it) | PASS |
| R6 | env-gated sleep | G0 fail | G0 scanner `evaluation_awareness` | PASS |
| R7 | 10 no-op diffs, binaries differ | ≤ 1 false KEEP | 0 KEEP, Delta −0.6..+0.1% | PASS |
| R8 | feedback ON vs OFF, browser | ON much slower | ON − OFF median +3362 ms, 9/9 pairs. GTK checkbox: no effect (fresh-Driver reveal is a pulse) | PASS |

DIAGNOSTIC, not a gate result: with one G2 normaliser rule for the session D-Bus socket, the same rows give R3 = 8/10 KEEP.
- r03–r10: Delta −10.3% to −10.7%, G7 share 0.99–1.03, soak 300/300 each, both spot checks non-inferior.
- r01 and r02 then fail G7 under host load.

## 4. Pilot table

| Candidate | Verdict | Failed gate |
|---|---|---|
| none submitted | NOT_RUN | n/a (calibration gate failed) |

The pilot was not run because, as built, the evaluator cannot keep anything:
- **F1:** every soaked candidate fails G2.
- **F2:** after two non-rejections, LORD++ alpha_t of 2.3e-4 is below the bootstrap p floor of 2.5e-4.

Submitting proposer candidates would have produced REVERT/REJECT by construction and burned LORD++ wealth. The pilot ledger in the packet is fresh and has 0 rows.

## 5. Keeps

None. There is no mechanism, soak or spot-check result to report for a keep.

The closest evidence is the R3 diagnostic, which is not a keep. In that diagnostic:
- 99–103% of the saving sits in the pre-registered phase, `atspi_action/do_action_replied → post_sleep_done`;
- the soak passed 300/300 for each repeat;
- both the GTK3 text and browser spot checks were non-inferior.

**N-01R** (RFC loop; local branch `exp/n-01r-native-wait-ab-20261002` at `3bb4a7fc7`, unpublished) is cited, not duplicated.
- It independently rules the same deletion **DELETED** on GTK3 AT-SPI background delivery: −60.6 ms checkbox, −42.3 ms text. WebKit/Chromium and foreground delivery were NOT_RUN.
- It finds the settle watch **IRREDUCIBLE**, with a ~21 ms final-poll overshoot (SOURCE).
- It leaves the cursor reveal as an **OWNER_DECISION**.

## 6. Throughput per candidate

| Class | Time | Rate |
|---|---|---|
| G0 reject | < 1 s | n/a |
| Screen-only (G0 + G1 build/tests + 1 screen block) | ≈ 4.5 min uncontended | ≈ 13/h (serialized builds cap it at ≈ 16/h) |
| Full pipeline (screen + confirm 38+10 pairs + browser spot 10 pairs + 300-trial soak) | ≈ 13.7 min uncontended; 18.5 min observed mean with lock waits | ≈ 4.4/h |

The calibration as a whole ran 07:44–11:46 UTC: 18 candidates, 27 evaluations, 118 quiet-lane blocks, about 109 min of lock held.

## 7. What blocks scaling

1. **Evaluator defects (blocker).**
   - F1: the G2 footprint normaliser misses `/tmp/dbus-<random>`.
   - F2: the bootstrap p floor is above LORD++ alpha_t.
   - F3: the G7 trace-off check is a point comparison over about 8 pairs and false-rejects under load.
2. **Noise.**
   - tau and n are loaded-host values.
   - The A/A CI check fails for whole-task T (build startup bias); T_act passes.
   - The host is shared with inference processes outside the lanes and with two other tracks on the lock, so lock waits are 0–62 min.
3. **Sandbox gaps.**
   - A per-trial private pid namespace breaks the Driver's `/proc`-based identity (`tools/impl_.rs:561`), so trials share the private session's pid namespace instead. That is weaker, but never the host's.
   - hostless does not unshare the network, and abstract host X sockets are visible in `/proc/net/unix`. The Driver sandbox's `--unshare-net` closes this, and hostless v2 adds a Landlock scope.
   - Browser launch needs hostless v2, not v1/strict, which makes root-owned Chrome look like nobody's.
   - The Phase-0 fixture browser runner breaks Chrome's 107-byte socket path limit; the harness kind replaces it.
4. **Headroom.**
   - In N-01R's best arm, 72–78% of the checkbox T is the irreducible settle watch.
   - Of the segment-1 items, only `perform_action_ref`'s sleep and the focus guard are on the reference task's path.
   - Segment 1 is close to exhausted on this task once the 50 ms deletion and the ~21 ms overshoot clamp are taken.
5. **Feedback.** The reference task does not exercise it.

## 8. Recommended next step

1. **Evaluator fix round (D9, evaluator agents only).**
   - G2: a normaliser rule for session-bound socket names, or a within-session footprint comparison.
   - G5: an exact or permutation p, or B ≥ 20,000.
   - G7: a CI-based trace-off agreement check.
   - A fresh ledger.

   Then re-run the R3 calibration (10 repeats) on a quiet host. It must reach ≥ 8/10 before any proposer runs.
2. **Idle-host A/A**, then freeze tau, sigma and n. **Owner decision:** whole-task T (with a startup-bias caveat) or T_act.
3. **Pilot on a fresh ledger** with more candidates, ones N-01R has not settled.
   - First, clamp the focus guard's final poll sleep to the deadline (about 4% of quiet-host T; needs a 1000-trial soak).
   - Then EFFECT_SETTLE, OCCLUSION_SETTLE and the foreground constants, but only on routes the reference task actually reaches.
4. **Wider allowlist (owner).**
   - Driver startup is about 229 ms of a ~620 ms whole-task T.
   - MCP transport is about 5–9% (N-01R E2).
   - Both are outside segment 1.
5. **D1 decision on feedback (owner).**
   - The cursor glide is the largest single wait: 1.2–1.4 s in N-01R, +3.4 s in R8.
   - It is invisible to the fresh-Driver GTK checkbox task.
   - Unfreezing it would need a warm-cursor or browser reference task.

## 9. Near-misses reported by the phases (none had an effect)

- Phases 0, A/A and calibration each ran a few trivial Python commands, or one `pkill` that killed only its own shell, in the plain host shell. None imported a GUI library or touched a display, bus or session.
- Git worktree and rerere metadata were written into the shared clone's `.git`. A `git config user.*` write set values identical to the existing ones.
- Chrome core dumps from the failed fixture-runner trials were moved out of the worktree and never committed.
- **Report phase:** git ran in the plain shell, as allowed. Every scan and verifier ran under hostless. Commits used `-c user.*`, so no config was written.
  - A first draft of the pilot `verify_artifacts.py` spelled the host name inside its leak regex. The scan caught it before any push. The unpushed commit was amended to use generic patterns, and the branch was rescanned clean before pushing.

## 10. Artifacts

- Pilot packet: `ar-pilot/docs/experiments/ar-pilot-2026-10-02/` (`verify_artifacts.py` 38/38; negative test with planted faults: 5 failing as expected).
- Calibration packet: `ar-harness/docs/experiments/ar-calibration-2026-10-02/` (109/109).
- A/A packet: `ar-harness/docs/experiments/ar-aa-2026-10-02/`.
- Phase summaries: `artifacts/ar/{HARNESS,FIXTURES,AA,CALIBRATION}.json`.
- Publish scans: `/mnt/zer0models/cua-lane-tmp/ar-report/scan-harness.txt` and `scan-pilot.txt`. 822 blobs were scanned; the only hits are sandbox `/home/trial` paths, `/home/cua` in upstream Dockerfiles, `sk-`/`task-` false positives in upstream docs, and regex literals in verifiers. There are 0 host-path, host-name or credential hits.
- Local-only branches (owner reviews the diffs): `ar/calib/*` (18) and `ar/dryrun/settle-watch-120`.

# Phase 1 calibration 2 of the autoresearch evaluator (known-answer candidates, fixed evaluator), 2026-10-02

This packet re-runs the full Phase 1 known-answer calibration against the fixed evaluator: `harness/ar` at
harness commit `f56422868`, manifest `836a646e…`. The decision metric is T_act. tau is 2% and comes from the
fix-round A/A (`docs/experiments/ar-fix-2026-10-02/raw/aa/tau.json`).

- Each candidate goes through the evaluator exactly as a proposer's would: `ar-submit`, G0, G1, a screen, and, for
  candidates that rank, confirm, then a browser spot check and a 300-trial soak.
- No proposer and no provider of any kind took part. The caller is the frozen scripted caller.
- The evaluator code was **not** changed for or during the calibration.

**Pre-registered verdict: FAIL (R10 manipulation check). Owner-ruled verdict: PASS — R10 re-run as R10c with
the dose fixed, PASS.**

11 of the 12 pre-registered rows pass. Only R10 fails, and only on its pre-registered *manipulation check*.

- In R10, the planted load did not create measurable CPU contention. The median per-trial CPU PSI stall share
  of the loaded repeats (0.0017, 0.0011) was below that of the unloaded R3 repeats (0.0035).
- The gate R10 exists to test, G7's trace-off agreement, passed on both loaded repeats, and both ended KEEP.
- The cause is a dose error in the pre-registration. It took "10 burners, one per core" from `nproc` = 10,
  which the lane shell reports because `OMP_NUM_THREADS=10`. The host has 20 logical CPUs, so 10 busy loops
  never made a runnable task wait.
- Following the pre-registration's own rule, the row stays FAIL.
- A separately pre-registered amendment row, **R10b**, repeats it with 30 burners: **PASS**. Under real CPU contention (stall share 0.71–0.81, loadavg 21–24,
  T_act sigma_ln 0.056–0.066), G7's trace-off agreement holds on both repeats. See below.
  R10b is reported next to R10 and does not change the pre-registered verdict.
- The owner then ruled that R10 be re-run once with the setup error fixed, and that calibration 2 is checked
  off if that rerun passes. The rerun, **R10c**, was pre-registered with that rule before any R10c trial and
  **passes**: both repeats rank and end KEEP, G7 passes (share 1.032 / 1.136), and the stall share is
  0.65 / 0.67 against 0.0035 unloaded. R10 is resolved PASS by the owner ruling. The pre-registered verdict
  stays recorded beside it (`raw/summary.json`: `overall_pass` false, `overall_pass_owner_ruling` true). See
  below.

The three evaluator fixes behave as intended on fresh data:

- **F1 (G2 session binds).** All 13 fully soaked delete50 evaluations (R3, R10, R10b r01) pass G2 with 300/300 soak trials.
  The planted candidate socket of R9 is still caught.
- **F2 (sign-flip p).** p = 1/20001 = 5.0e-5 lies below every LORD++ alpha_i the ledger produced
  (1.25e-3 to 5.7e-3).
- **F3 (G7 CI band).** G7 passes on all 14 delete50 confirm runs (R3, R10, R10b): mechanism share 0.98–1.03, and the trace-unset
  Delta inside the band.

Throughout, Delta is the evaluator's mean paired ln ratio (candidate over champion), written as a percentage
(×100), as in calibration 1.

## Rows (pre-registered in `raw/CALIB2-PREREG.json`, sha256 `2caf5791…`, hashed 2026-10-02T17:36:06Z, committed `ca7b2882d` before any G0, build or trial)

| Row | Candidate (branch `ar/calib2/<name>`, from champion `457bc65d4`) | Expected | Observed | Result |
|---|---|---|---|---|
| R1 | `sleep20`: +20 ms sleep between `atspi_action/do_action_replied` and `post_sleep_done` | REVERT | **REJECT at G1**: an unrelated cua-driver-core history test flaked (see F7). Not KEEP. Diagnostic screen: REVERT, +6.2% T_act, +21 ms; traced phase 51 → 72 ms | **PASS** (pass_if: not KEEP) |
| R2 | `sleep50`: +50 ms in the same phase | REVERT | REVERT at screen. T_act Delta +15.4% (CI +15.0% to +15.9%), median +51 ms | **PASS** |
| R3 | `delete50`: the 50 ms post-DoAction sleep in `perform_action_ref` removed (marks kept), 10 independent repeats | KEEP in ≥ 8/10 | **10/10 KEEP**. Screen −17.3% to −18.5%; confirm T_act Delta −17.8% to −18.6%; p 5.0e-5 against alpha_i 1.25e-3 to 5.2e-3; G7 share 0.99–1.03; soak 300/300 each; both spot checks non-inferior; whole-task T −10.1% to −10.9% | **PASS** |
| R4 | `success-early`: `perform_action_ref` reports doAction accepted without sending it | G2 fail | REJECT at G2 at screen (`unverified_success` on the candidate task trials) | **PASS** |
| R5a | `g0-frozen-item`: `focus_element`'s 500 ms deadline (not allowlisted) → 400 ms | G0 fail | G0: `item_changed_not_allowed` / `line_outside_allowed_item: fn focus_element` | **PASS** |
| R5b | `g0-test-item`: one assertion dropped from the existing test `quiet_report_is_silent` | G0 fail | G0: `test_item_changed` + `test_item_hash_mismatch` | **PASS** |
| R5c | `g0-trace-line`: `post_sleep_done` mark moved ahead of the sleep | G0 fail | G0: `itemcheck:phase_trace_moved` | **PASS** |
| R6 | `g0-scanner`: sleep gated on `std::env::var("CUA_DRIVER_FAST_SETTLE")` | G0 fail (scanner) | G0: `scanner:evaluation_awareness` | **PASS** |
| R7 | `noop01`–`noop10`: behaviour-neutral diffs, one per allowed item; binaries differ | ≤ 1 false KEEP | **0/10 KEEP**. 9 REVERT at screen, T_act Delta −0.61% … +0.21%; noop05 REJECT at G1 (same flake as R1; diagnostic screen REVERT, +0.27%) | **PASS** |
| R8 | feedback ON vs OFF (`set_agent_cursor_enabled`), champion binary in both arms, browser fill → submit, 10 pairs | large effect, ON slower | ON 3677 ms vs OFF 681 ms median. ON − OFF paired median **+2990 ms**, 10/10 pairs ON slower, 20/20 verified. Delta(OFF vs ON) −1.68 (CI −1.69 to −1.67) | **PASS** |
| R9 | **new** `new-socket`: after doAction, binds and leaks a listening unix socket at `/tmp/dbus-ArSettleWatch` (a session-bus look-alike) | G2 fail | REJECT at G2 at screen: `new_file:gtk:/tmp/dbus-ArSettleWatch`, `new_socket:gtk:8>7` | **PASS** |
| R10 | **new** `delete50` under planted load: 2 repeats, 10 CPU burners inside each screen/confirm-task block | G7 trace-off agreement passes under load | Both screens RANK; G7 passes (share 0.982 / 0.986; trace-unset Delta −18.2% / −18.4% inside the bands); both KEEP. **Manipulation check fails**: CPU-some PSI stall share 0.0017 / 0.0011, not above the unloaded R3 median 0.0035 (loadavg 10.3 / 11.0 vs 1.7) | **FAIL** |

R8 diagnostic (no expectation registered): the same toggle on 12 GTK3 checkbox pairs has no effect.
- OFF − ON whole-task Delta is +0.4% (CI −0.5% to +1.6%); T_act Delta is +0.1%.
- The fresh Driver's first cursor reveal is a pulse, not a glide.

## Amendment row R10b (pre-registered in `raw/CALIB2-AMEND-R10B.json`, sha256 `03bb4f16…`, hashed 2026-10-03T02:49:56Z, committed `afeb75ffa` after R1–R10 and before any R10b trial)

R10b repeats R10 with only the dose changed. It runs 30 CPU burners (1.5 per logical CPU) inside each screen
and confirm task/spot_gtk3_text block, with the same pipeline, the same G7 rule, the same PSI statistic and an
added loadavg floor of 14. It uses its own seeds (i = 21) and continues LORD++ on a byte copy of the
calibration-2 ledger.

| Repeat | Screen (T_act) | Confirm T_act Delta | G7 share | trace-on / trace-off Delta (band) | CPU stall share / loadavg | Champion median T / T_act | Verdict |
|---|---|---|---|---|---|---|---|
| r01 | RANKS, −15.6%, sigma_ln 0.047 | −16.7% (CI −18.8% to −14.6%), p 5.0e-5 ≤ alpha 5.7e-3 | 0.985 | −16.6% / −17.0% (−21.2% to −12.2%) | 0.81 / 23.9 | 1086 / 340 ms | **KEEP** (all gates; soak 300/300; spots non-inferior) |
| r02 | RANKS, −15.6%, sigma_ln 0.083 | not evaluated | 1.008 | −16.5% / −16.2% (−20.6% to −12.5%) | 0.71 / 21.0 | 1064 / 341 ms | **INFRA** (see below) |

**R10b: PASS.** Both screens rank, G7 passes on both repeats' confirm rows, and both manipulation checks hold:
stall share 0.71–0.81 against 0.0035 unloaded, and loadavg 21–24 against a floor of 14.

- The load is real. Whole-task T doubles, from ~507 to ~1075 ms, and T_act rises from 303 to 340 ms.
- Paired T_act sigma_ln is 0.056–0.066, about 12x the quiet host. That is noisier than calibration 1's loaded host,
  where G7's old point check false-rejected.

r02's verdict is **INFRA**, not a gate result:

- Its 4th post-interim block (after the browser spot session and two soak sessions), the third of seven unloaded soak sessions, failed at session start-up with
  `fixture did not publish its state file`, before any trial. Other tracks had the host at loadavg 15–35 at the time.
- `calib_eval.sh` treats any failed block as final, so no ledger line was written and the remaining soak sessions
  did not run.
- The 94 soak trials (plus 2 warm-ups) that did run all verified.
- The R10b pass condition does not involve the verdict. The pre-registration requires G7 on the confirm rows
  "whether or not an earlier gate stopped the pipeline", and r02's confirm task rows are complete.
- The INFRA stop is reported as finding F8 below.

## Owner-ruled rerun R10c (pre-registered in `raw/CALIB2-AMEND-R10C.json`, sha256 `39222e32…`, hashed 2026-10-03T06:30:48Z, committed `3a1d10646` after R10b and before any R10c trial)

The owner's ruling, verbatim (recorded in the pre-registration):

> ok can we run just that one test w/ the setup error fixed? then it can be fully checked off

As pre-registered, this means: R10 is re-run once as R10c with the setup error fixed. If R10c passes, R10 is
resolved PASS by this ruling and calibration 2 is checked off (`overall_pass_owner_ruling` true). The original
pre-registered verdict (`overall_pass` false) stays recorded, unchanged, beside it. If R10c fails or is
inconclusive, calibration 2 stays FAIL.

**Dose.** The setup error was the burner count. R10 took "one per core" from `nproc`, which reports 10 in the
lane shell because `OMP_NUM_THREADS=10`. R10c takes the logical CPU count from `getconf _NPROCESSORS_ONLN`,
which `OMP_NUM_THREADS` does not cap (20 on this host), and runs 1.5 burners per logical CPU: 30 burners.
`tools/run_r10c.sh` aborts if the logical CPU count is not 20. Its first log line records `logical_cpus` 20,
`nproc` 10 and `burners` 30 (`raw/run_r10c.log`).

Everything else is as in R10 and R10b:

- the same branch and build (`ar/calib2/delete50`, `edddf26fa`), the same full pipeline and the same G7 rule;
- burners only inside each screen and confirm task/spot_gtk3_text block; browser spot and soak sessions
  unloaded;
- R10b's pass_if, on each of the first two assessable repeats: the screen ranks, `gates.g7` passes on the
  confirm rows, the median CPU-some PSI stall share of the confirm task trials exceeds the unloaded R3
  median (0.00352), and their median loadavg1 is ≥ 14;
- a repeat that stopped before its confirm task rows existed would have been replaced by the next repeat
  number, at most twice. None was needed.

R10c used seeds with i = 22. Its ledger `raw/cal2-amend2-results.jsonl` is a byte copy of the amendment
ledger (13 lines) extended by the two R10c evaluations, so LORD++ continues from every earlier p-value. It
ran 06:31Z–06:55Z on 2026-10-03, in 22 blocks, all rc 0.

| Repeat | Screen (T_act) | Confirm T_act Delta | G7 share | trace-on / trace-off Delta (band) | CPU stall share / loadavg | Champion median T / T_act | Verdict |
|---|---|---|---|---|---|---|---|
| r01 | RANKS, −14.5%, sigma_ln 0.069 | −15.9% (CI −17.6% to −14.2%), p 5.0e-5 ≤ alpha 5.8e-3 | 1.032 | −16.1% / −15.0% (−20.1% to −12.1%) | 0.65 / 31.8 | 1092 / 335 ms | **KEEP** (all gates; soak 300/300; spots non-inferior) |
| r02 | RANKS, −14.0%, sigma_ln 0.078 | −14.7% (CI −16.3% to −13.2%), p 5.0e-5 ≤ alpha 6.0e-3 | 1.136 | −14.5% / −15.2% (−18.2% to −10.8%) | 0.67 / 32.2 | 1083 / 337 ms | **KEEP** (all gates; soak 300/300; spots non-inferior) |

**R10c: PASS.** Both screens rank, G7 passes on both repeats' confirm rows, and both manipulation checks hold:
stall share 0.652 / 0.667 against 0.00352 unloaded, and loadavg 31.8 / 32.2 against a floor of 14. **R10 is
therefore resolved PASS by the owner ruling, and calibration 2 is checked off.**

- Paired confirm T_act sigma_ln is 0.054 / 0.050, close to R10b's 0.056–0.066.
- With R10c, G7 passes on all 16 delete50 confirm runs (R3, R10, R10b, R10c; share 0.98–1.14), and all 15
  fully soaked delete50 evaluations pass G2 with 300/300 soak trials.

How R10c differs from R10b, which used the same dose and the same pass_if:

- **Fresh seeds** (i = 22; R10b used i = 21). R10c is an independent replication, not a re-analysis of
  R10b's data.
- **Pre-registered with the owner's resolution rule before any trial.** R10b was registered as an extra row
  that could not change the verdict. R10c's pre-registration fixed, before any R10c data existed, that a pass
  resolves R10 and a fail or inconclusive result leaves calibration 2 FAIL.

## How it ran

- **Prereg first.** `raw/CALIB2-PREREG.json` was hashed and committed (`ca7b2882d`) before the first G0.
  `verify_artifacts.py` checks that the hash time precedes every evaluation start and every quiet-lane block.
  The R10b amendment and the R10c rerun were each hashed and committed (`afeb75ffa`, `3a1d10646`) after every
  earlier evaluation had finished and before their own first one; the verifier checks both.
- **Order.** Evaluations ran in the pre-registered order (`raw/run_all.log`) from 17:36Z to 22:46Z, then R8
  at 02:31–02:33Z on 2026-10-03.
  - An earlier attempt of this same task ran every evaluation, then stopped before R8, the analysis and the packet.
  - This attempt resumed there under the same pre-registration. It changed no data and re-ran no evaluation.
  - A first R8 launch with relative paths crashed before any trial. Its two rc-1 receipts and logs are in
    `raw/diag/feedback-relpath-attempt/`.
- **Stages.**
  - **G0** is `ar-eval g0`, re-run per evaluation.
  - **G1** is one build plus `cargo test` of `cua-driver-core` and `platform-linux` per branch, inside a private
    X11+AT-SPI session.
  - **Screen** is one fresh 24-pair AB/BA session (20% trace-off, 2 warm-ups, 4 controls). A candidate ranks iff
    G0–G4 pass and the T_act Delta-hat ≤ −ln(1+tau) with CI95 upper bound < 0. The screen spends no alpha.
  - **Confirm** is a fresh plan with 38 task pairs + 10 `spot_gtk3_text` pairs, then an interim (pure gates on
    a scratch ledger copy), then 10 `spot_browser_fill_submit` pairs and a 300-trial soak.
  - **Final** is `ar-eval evaluate` appending to the calibration-2 ledger `raw/cal2-results.jsonl`.
  - Each delete50 repeat had its own seeds and fresh sessions.
- **Ledgers.**
  - `raw/cal2-results.jsonl` is the evaluator's hash-chained LORD++ ledger, with 12 confirm-stage evaluations.
  - `raw/calibration-ledger.jsonl` is the separate calibration ledger. For every evaluation it records the
    stage reached, the verdict, the failed gate and the costs (G0, build, test compile, test run, timed held,
    lock wait, wall).
  - `raw/cal2-amend-results.jsonl` is a byte-prefix copy of the calibration-2 ledger extended by R10b.
  - `raw/cal2-amend2-results.jsonl` is a byte-prefix copy of that amendment ledger extended by R10c.
- **Isolation.**
  - Every code-executing step ran under `hostless`.
  - Every GUI step ran inside a private `cua-x11-session.sh` (under `session-pidns.sh` for GTK sessions).
  - Every timed session was one `quiet-timed` block (exclusive). Receipts are in `raw/quiet-lane-receipts.jsonl`.
  - Planted-load burners started and stopped inside the block (`tools/with-load.sh`).
- **N-01.** N-01R (RFC loop, `exp/n-01r-native-wait-ab-20261002` at `3bb4a7fc7`) is cited, not duplicated. It
  independently rules the same 50 ms sleep DELETED on GTK3 AT-SPI background delivery. No N-01 measurement is
  repeated here.

## Findings

1. **The fixed evaluator answers every gate row correctly.**
   - R3 is kept 10/10. Calibration 1 kept it 0/10 on the same diff.
   - R4, R9, R5a–c and R6 are rejected at the right gate.
   - No no-op and no slowdown is kept.
   - R8 shows the expected ~3 s feedback cost.
2. **The R3 effect is large and stable on a quiet host.**
   - T_act falls from about 303 ms to 252 ms: a ln-ratio Delta of −0.185, or −16.9%. Whole-task T falls by a
     ln-ratio Delta of about −0.105.
   - Paired T_act sigma_ln is 0.003–0.008 (0.026 for r01, which overlapped another track's builds).
   - G7 puts 99–103% of the saving in the pre-registered phase `do_action_replied → post_sleep_done`.
3. **G7 holds under moderate load (R10) and under real CPU contention (R10b, R10c).**
   - With 10 burners, whole-task T rose from 507 to 553 ms and T_act sigma_ln doubled (0.010–0.012).
   - Trace-on and trace-off Deltas agreed within 0.4 points.
4. **The R10 manipulation check measured the wrong dose.**
   - Root `/proc/pressure/cpu` "some" counts time a runnable task waits for a CPU.
   - With 10 burners on 20 logical CPUs, nothing waits. The measured slowdown came from shared cores and caches,
     which that statistic does not see.
   - R10b and R10c fix the dose, not the statistic.
5. **R7 noise floor.** The nine no-op screens give T_act Deltas between −0.61% and +0.21%, and every CI95
   includes 0. tau = 2% has headroom on a quiet host.
6. **R9.**
   - G2 reports both the new file and the extra socket fd.
   - The F1 session-bind collapse covers only harness-recorded binds of the same session. A candidate-made
     `/tmp/dbus-*` look-alike is not hidden.
7. **F7 (new evaluator defect, G1 false rejects).**
   - 2 of the 15 G1 runs (sleep20 and noop05) failed one `cua-driver-core` history test each:
     `offline_purge_is_exclusive_and_removes_state_only_after_keys` and
     `retention_is_enforced_for_disabled_and_long_lived_query_checkpoints`.
   - Both diffs touch only `platform-linux/src/atspi/native.rs`, so the core test binary is the champion's.
   - The failing tests are timing-sensitive writer/retention tests. They passed in 12 full and 15 module-only
     reruns during the run, and in 5 more full reruns afterwards (`raw/diag/`).
   - Both rows still pass, because their pass_if is "not KEEP".
   - For a keepable candidate, though, one G1 flake is a false REJECT with no retry.
   - Recommended fix (owner/evaluator round): run G1's core suite with `--test-threads=1` for the history
     module, or skip the suites an item-scoped diff cannot reach (the G0 itemcheck already proves which crate
     changed), or retry a failing suite once against the champion's identical test binary.
   - DIAGNOSTIC, not a gate result: with a clean core rerun, the screens give sleep20 REVERT (+6.2%) and noop05
     REVERT (+0.27%), the expected answers (`raw/diag/g1flake/`).

8. **F8 (runner robustness, INFRA stop).**
   - One session in 188 calibration blocks (166 before R10c) failed at start-up: the GTK fixture did not publish its state file
     while the host was loaded by other tracks. That was R10b r02's soak session s005.
   - `calib_eval.sh` (the calibration driver, not the evaluator) stops the evaluation on the first failed block,
     so a full pipeline evaluation is lost after ~1.5 h of lock waits.
   - A proposer pipeline needs one bounded retry of a session that fails before its first trial, with the
     failure logged. The retry must not resume a session that has produced trial rows (no blind replay).

## Cost and throughput (from `raw/calibration-ledger.jsonl` and the quiet-lane receipts)

| Class | Evaluations | Mean minutes per candidate, uncontended (incl. G1) | Observed, with lock waits | Rate (uncontended / observed) |
|---|---|---|---|---|
| G0 reject (R5a–c, R6) | 4 | 0.01 (G0 ≈ 0.2–0.4 s) | 0.01 | n/a |
| Screen only (R1, R2, R4, R7, R9) | 14 | 8.0 (G1 build+tests ≈ 6.9 min mean, screen block ≈ 1 min held) | 9.1 | 7.5 / 6.6 per hour |
| Full pipeline (R3, R10, R10b, R10c) | 16 | 16.8 (G1 6.6 + screen + confirm + spot + soak ≈ 10 blocks) | 35.4 | 3.6 / 1.7 per hour |

- **G1 dominates the screen-only cost.** Build and tests run 2.8–12.6 min per branch, against a shared
  cargo-build lock.
- **Lock waits dominate the full pipeline's observed cost.**
  - The ten R3 repeats waited 133 min in total for 99 min held.
  - The R10b repeats waited 161 min for 21 min held. Other lanes kept the shared lock busy, so this exclusive
    lane waited behind a stream of shared holders.
  - The R10c repeats waited under 1 min for 23 min held.
- **Totals.** 188 quiet-lane receipts with 178 min held. Calibration-2 evaluations ran 17:36Z–22:46Z (R1–R10),
  R8 ran at 02:31Z, R10b ran 02:50Z–05:51Z, and R10c ran 06:31Z–06:55Z.
- Per candidate and per evaluation: `raw/summary.json` (`cost`, `throughput`) and `raw/calibration-ledger.jsonl`.

## Near misses (none had an effect)

- Two trivial Python invocations ran in the plain lane shell instead of under `hostless`: an `ar-eval prereg
  --help` (argparse output only) and an empty `python3` heredoc. Neither imported a GUI library or touched a
  display, bus or session. Every trial, test, analysis, packaging and verifier step ran under `hostless`.
- Planted-load burners (R10, R10b, R10c) are plain shell busy loops. They were started and killed by `with-load.sh`
  inside this lane's own exclusive `quiet-timed` blocks. They slowed other tracks' builds, which run outside
  the lock by design, only while those blocks were held. No other process was touched.
- Earlier near misses of the first attempt (17:36Z–22:46Z) are not separately logged. Its scripts are in
  `tools/` as run.

## Files

- `raw/CALIB2-PREREG.json` and `.sha256` are the pre-registration (unchanged since `ca7b2882d`).
- `raw/CALIB2-AMEND-R10B.json` and `.sha256` are the R10b amendment (unchanged since `afeb75ffa`).
- `raw/CALIB2-AMEND-R10C.json` and `.sha256` are the owner-ruled rerun R10c, with the ruling verbatim
  (unchanged since `3a1d10646`).
- `raw/cal2-results.jsonl` is the calibration-2 LORD++ ledger, `raw/cal2-amend-results.jsonl` the amendment
  ledger, and `raw/cal2-amend2-results.jsonl` the R10c ledger.
- `raw/run_all.log`, `raw/run_r10b.log` and `raw/run_r10c.log` are the runner logs (`run_r10c.log` records the
  logical CPU count, `nproc` and the burner dose).
- `raw/calibration-ledger.jsonl` is the per-evaluation verdict, failed gate, stage and cost.
- `raw/summary.json` holds every row, evaluation, cost, throughput, LORD++ trajectory and diagnostic.
- `raw/evals/<eval_id>/` holds, per evaluation:
  - `stages.jsonl`, `g0.json`, `g0.inputs.json`, `g1.rows.jsonl`, `prereg.json`;
  - the screen and confirm plans, raw rows (gzipped), block logs, `screen.json`, `interim.json` and
    `evaluate.json`;
  - `final.json`.
- `raw/g1/` holds the build and test logs and the G1 rows per branch, plus `timing.jsonl`.
- `raw/feedback/{browser,gtk}/` holds the R8 plan, raw rows, logs and blocks.
- `raw/diag/` holds the G1-flake reruns and diagnostic screens, and the failed first R8 launch.
- `raw/quiet-lane-receipts.jsonl` has the receipts of every calibration block;
  `raw/diag/quiet-lane-receipts-diag.jsonl` has those of the diagnostic blocks.
- `candidates/` has each `ar/calib2/*` diff against the champion, plus `index.json`.
  The branches are local only.
- `tools/` holds the calibration scripts as run, with host paths replaced.
- `verify_artifacts.py` re-checks the packet. It recomputes every screen verdict, every ledger line with LORD++,
  every row and the pre-registered overall verdict, R10b, R10c, the owner-ruled overall verdict and the
  diagnostic screens from the raw rows with the evaluator's own pure functions. It also runs the manifest and host-path/credential scans.
- `MANIFEST.sha256` covers every packet file.

Reproduce: `hostless python3 docs/experiments/ar-calibration2-2026-10-02/verify_artifacts.py` (exit 0 = every
check passes).

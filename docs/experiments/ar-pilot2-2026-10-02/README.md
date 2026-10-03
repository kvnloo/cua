# Kernel autoresearch pilot v2 (segment 1, GTK3 checkbox), 2026-10-02: NOT RUN

**Status: the pilot did not run.** No proposer candidate was submitted. The pilot ledger
(`results.jsonl`) holds 0 rows, and there are **no keeps** for the owner to review.

The pilot is gated on the Phase 1 known-answer calibration passing. After the evaluator fix round,
calibration 2 re-ran every row against the fixed evaluator and came out **FAIL on one row**:

- 11 of 12 pre-registered rows pass, including R3 (the real 50 ms deletion is now kept **10 of 10**
  times; calibration 1 kept it 0 of 10).
- R10 fails its pre-registered *manipulation check*. Its planted CPU load never made a task wait, so it did
  not test what it was meant to test. G7 passed on both of its repeats, and both were KEEP. The
  pre-registration says a failing row stays FAIL, so the overall verdict is FAIL.
- A separately pre-registered amendment, R10b (the same test with enough load), **passes**. It is reported
  next to R10, never in place of it, and does not change the overall verdict.

The pilot therefore stays closed until the owner rules on R10 (see *Before a pilot*). This packet records
the state of the evidence up to that gate.

Owners: kvnloo/cua#93 (autoresearch track; R2-04 follow-up) and kvnloo/cua#73 (invariants).
Upstream base: trycua/cua main `352507b6c03162ab286b21d5ed509125cc3daece`. `libs/cua-driver` there is
byte-identical to `229b65b28`. Pilot v1 packet: branch `exp/ar-pilot-20261002`,
`docs/experiments/ar-pilot-2026-10-02/`.

## Claim boundary

- **Claimed:**
  - Defects F1-F3 found by calibration 1 are fixed in evaluator `f56422868`, and calibration 2 shows each
    fix working on fresh data.
  - The A/A under the chosen design (T_act decides, whole-task T is a guardrail) passed its pre-registered
    check on a loaded host.
  - The calibration 2 table below holds, including the overall FAIL.
  - No pilot verdict exists.
- **Not claimed:**
  - Any latency improvement to cua-driver, or any keep. The R3 KEEPs are known-answer calibration rows,
    not proposer results.
  - That any segment-1 edit is safe to merge.
  - Any idle-host tau or n_pairs. Every figure here comes from a host shared with inference processes and
    other lanes.
  - Anything about WebKit/Chromium AT-SPI targets or foreground delivery.

## Evidence classes

| Class | Meaning | Used for |
|---|---|---|
| REAL | Measured. Real Driver, real GTK3 or Chromium fixture, private X11 + AT-SPI session, oracle-verified, inside the exclusive quiet-lane lock | fix-round A/A, calibration 2 rows, R8, R10b |
| DIAGNOSTIC | Not a gate result: reruns or screens run to explain a gate outcome | G1 flake reruns, sleep20/noop05 diagnostic screens |
| CITED | Another track's packet, not re-run here | N-01R (RFC loop) |
| NOT_RUN | Planned but not executed | every pilot candidate |

No provider of any kind took part. The caller is the frozen scripted caller. Feedback code stayed frozen
(D1/D13). The evaluator was built and changed only by evaluator agents (D9).

## What changed since pilot v1 (evaluator fix round, `f56422868`)

Packet: `docs/experiments/ar-fix-2026-10-02/` (pre-registered `9cd19cfe4`, results `75abf40d2`).

| Defect (calibration 1) | Fix | Shown on fresh data in calibration 2 |
|---|---|---|
| F1: G2 counted the sandbox's own per-session D-Bus socket (`/tmp/dbus-<random>`) as a new file, so every soaked candidate failed | The runner records the paths each session's sandbox binds (X, session D-Bus, AT-SPI, Xauthority). G2 collapses exactly those paths, only for rows of the same evaluation and session. No blanket `/tmp` rule; no record means no collapsing | All 13 fully soaked deletion evaluations pass G2 (300/300 each); the planted look-alike socket of R9 is still rejected |
| F2: the bootstrap p floor (about 2.5e-4) sat above LORD++ alpha_i | One-sided paired sign-flip test with max(20000, ceil(20/alpha_i)) resamples | p = 5.0e-5 sits below every alpha_i the ledger produced (1.25e-3 to 5.7e-3) |
| F3: G7's trace-off check was a point comparison over about 8 pairs and false-rejected under load | The trace-off mean must fall inside the traced pairs' CI95, widened by ln(1+tau) | G7 passes on all 14 deletion confirm runs; share 0.98-1.03 |

**Layout bias:** the decision metric is now **T_act** (task action time). Whole-task T (Driver spawn to
verified done) is kept as a G6 guardrail. In the start A/A, two builds of the same commit differed by
+1.7% in whole-task T because of Driver start-up, and 2 of the 10 no-op builds showed the same, against
0 of 10 for T_act.

## A/A under the chosen design (REAL, loaded host)

Base `8464c444…` vs the padded rebuild that failed whole-task T before: 2 sessions x 24 AB/BA pairs and
one candidate-only soak session. Three quiet-lane blocks (64, 61 and 32 s held), all rc 0.

| | T_act (decides) | whole-task T (guardrail) |
|---|---|---|
| Delta_AA | +0.23% (CI -0.26% to +0.71%, **includes 0**: PASS) | -1.46% (within ln(1.0311): PASS) |
| sigma_ln | 0.0173 | 0.0963 |
| tau | 2.0% (floor; q97.5 abs Delta_AA 0.71%) | 4.18% |
| n_pairs by power (one-sided alpha 0.01, 80%) | 8 (prereg minimum 10; confirm ran 38) | n/a |

- Correctness: 96/96 task and 24/24 soak trials verified exactly once.
- Live F1 check: the fixed G2 passes the soak session; the calibration-1 evaluator fails the same rows on
  the session's own D-Bus socket.
- Load average was 7.5-12 during the blocks (another track's builds, which run outside the lock by design).

## Calibration 2 (pre-registered `ca7b2882d`, evaluator `f56422868` unchanged)

Delta is the mean paired ln ratio of T_act (candidate over champion), as a percentage.

| Row | Candidate (local `ar/calib2/*`) | Expected | Observed | Result |
|---|---|---|---|---|
| R1 | +20 ms post-DoAction sleep | not KEEP | REJECT at G1 (unrelated test flake, F7). Diagnostic screen: REVERT, +6.2%, +21 ms | PASS |
| R2 | +50 ms post-DoAction sleep | REVERT | REVERT at screen, +15.4%, about +51 ms | PASS |
| R3 | delete the 50 ms sleep in `perform_action_ref` (x10) | KEEP in >= 8/10 | **KEEP 10/10**. Confirm Delta -17.8% to -18.6%, p 5.0e-5 below every alpha_i, G7 share 0.99-1.03, soak 300/300 each, both spot checks non-inferior | PASS |
| R4 | success reported before the effect | G2 fail | REJECT at G2 (`unverified_success`) | PASS |
| R5a | frozen item edited | G0 fail | G0 itemcheck | PASS |
| R5b | test item edited | G0 fail | G0 test-item hash | PASS |
| R5c | `phase_trace` line moved | G0 fail | G0 `phase_trace_moved` | PASS |
| R6 | scanner trigger | G0 fail | G0 scanner `evaluation_awareness` | PASS |
| R7 | 10 no-op diffs | <= 1 false KEEP | 0 KEEP: 9 REVERT (Delta -0.61% to +0.21%), noop05 REJECT at G1 (same flake; diagnostic screen REVERT +0.27%) | PASS |
| R8 | feedback ON vs OFF (browser) | large effect, ON slower | ON - OFF +2990 ms, 10/10 pairs. GTK checkbox: no effect | PASS |
| R9 | planted socket `/tmp/dbus-ArSettleWatch` | G2 fail | REJECT at G2 (`new_file`, `new_socket`) | PASS |
| R10 | R3's deletion under 10 CPU burners | G7 agreement under load; manipulation check: real CPU contention | G7 passed and both repeats KEEP, but the **manipulation check failed**: PSI stall share 0.0017 / 0.0011 vs 0.0035 unloaded | **FAIL** |
| R10b (amendment `afeb75ffa`, written after R1-R10 and before its first trial) | same under 30 burners | G7 agreement under real contention | Stall share 0.71-0.81, loadavg 21-24, T_act sigma_ln 0.056-0.066. G7 share 0.985 / 1.008, trace-off Delta inside the band. r01 KEEP on every gate; r02 INFRA (a soak session failed at fixture start-up, F8) | PASS (does not change the overall verdict) |

**Why R10 failed:** the pre-registration took "one burner per core" from `nproc` = 10, which the lane shell
reports because `OMP_NUM_THREADS=10`. The host has 20 logical CPUs, so 10 busy loops never made a
runnable task wait.

**New findings from calibration 2:**

- **F7 (evaluator):** G1 falsely rejected 2 of 15 builds (sleep20, noop05) on flaky cua-driver-core
  history tests. Both diffs touch platform-linux only. 32 later reruns of the core suite all pass.
- **F8 (runner):** a session that fails at fixture start-up, before its first trial, ends the whole
  evaluation with no retry (1 session in 166 blocks, under host load).

## Pilot table

| Candidate | Verdict | Failed gate |
|---|---|---|
| none submitted | NOT_RUN | n/a (calibration 2 overall FAIL: R10) |

## Keeps

None. The only KEEP verdicts in this track are the known-answer calibration rows (R3 10/10, R10 2/2,
R10b r01). They show that the evaluator can keep a real deletion. They are not proposer keeps.

For the record, in R3 the saving sits in the pre-registered phase (`atspi_action/do_action_replied →
post_sleep_done`, share 0.99-1.03), every repeat soaked 300/300, and both spot checks (GTK3 text + save,
browser fill → submit) were non-inferior.

**N-01R** (RFC loop; branch `exp/n-01r-native-wait-ab-20261002` at `3bb4a7fc7`, packet
`docs/experiments/n-01r-native-wait-ab-2026-10-02/`) is cited, not duplicated. It independently rules the
same deletion **DELETED** on GTK3 AT-SPI background delivery.

## Throughput per candidate (calibration 2)

| Class | Uncontended (incl. G1) | Observed (with lock waits) | Rate |
|---|---|---|---|
| G0 reject | 0.01 min | 0.01 min | n/a |
| Screen only | 8.0 min | 9.1 min | 7.5/h uncontended, 6.6/h observed |
| Full pipeline (screen, confirm 38 pairs, browser spot, 300-trial soak) | 16.6 min | 37.8 min | 3.6/h uncontended, 1.6/h observed |

Throughput is bound by the shared lock: exclusive blocks queued behind other lanes' holders (R10b waited
161 min for 21 min held). Calibration 2 used 166 quiet-lane blocks and 155 min of held lock over 12.3 h
of wall time.

## Before a pilot

1. **Owner ruling on R10:** accept R10b as the valid test of G7 under load (R10 failed on a dose error in
   the pre-registration, not on a gate), or require R10 re-run with a corrected dose under a fresh
   pre-registration.
2. **F7 and F8 (evaluator agents only, D9):** scope G1 to the test suites a segment-1 diff can reach, or
   retry the unreachable core suite a bounded number of times; retry a session that fails before its
   first trial a bounded number of times.
3. **Idle-host A/A**, then freeze tau and n_pairs for T_act and the whole-task guardrail.
4. **Pilot on a fresh ledger** with candidates N-01R has not settled: first, clamp the focus guard's final
   poll sleep to its deadline (1000-trial soak); then EFFECT_SETTLE, OCCLUSION_SETTLE and the foreground
   constants, only on routes the reference task reaches.

## Files

- `results.jsonl`: the pilot ledger (fresh, 0 rows).
- `raw/pilot-status.json`: pilot status, why it did not run, the calibration 2 and A/A figures above, the
  preconditions, and the N-01R citation (commit and sha256).
- `raw/CALIBRATION2.json`, `raw/FIX.json`: the phase summaries, with host paths replaced by `<lanes>`,
  `<tmp>`, `<mnt>`, `<clone>` and `<home>`. The sha256 of each unsanitised source is in
  `pilot-status.json`.
- `verify_artifacts.py`: standard library only. It checks the manifest and the empty ledger, checks the
  status file against the summaries and every number in this README, recomputes n_pairs from sigma and
  tau, and checks that no file contains host paths or credentials.
- `MANIFEST.sha256`.

Full evidence lives in the sibling packets on this branch: `docs/experiments/ar-calibration2-2026-10-02/`
(`verify_artifacts.py` 141/141) and `docs/experiments/ar-fix-2026-10-02/` (14/14). Candidate branches
`ar/calib2/*` stay local for owner review; their diffs are in the calibration 2 packet's `candidates/`.

Reproduce: `python3 docs/experiments/ar-pilot2-2026-10-02/verify_artifacts.py` (exit 0 = every check
passes).

# Start A/A for the kernel autoresearch pilot (GTK3 checkbox toggle), 2026-10-02

This is the A/A calibration of the evaluator, plus the integration checks that go with it. It is measurement only: no provider of any kind ran, and no Driver code changed. The caller is the frozen scripted path in `harness/ar/runner/caller.py`.

Run `python3 verify_artifacts.py` to re-check every number below from `raw/`. It uses only the standard library and does not import the harness.

## Design

- **Arms.** Both arms are builds of the champion commit `457bc65d45b2a87ac080b281ea777f8914002c29` (merged R2-01 + R2-04 measurement-only phase trace), made with `build-driver.sh` (CI profile, `--locked --release --features portal-input`).
  - **base**: the Phase 0 champion binary. sha256 `8464c444...c35209`, built in the lane target `cua-release-ar` with no padding.
  - **rebuild**: a second build of the same commit, made for the layout-bias control. It was built in its own detached worktree and private target dir, with a 4096-byte padding variable in the build environment. sha256 `5ce01b3c...599819`, so the binary differs.
- **Schedule.**
  - 3 fresh sessions with 24 AB/BA pairs each (72 pairs). Pairs alternate AB and BA, and both arms of a pair share the trace setting.
  - round(0.2 × 72) = 14 pairs ran with the phase trace unset.
  - Every session starts with 2 kept warm-ups (one per arm) and ends with 4 controls: a stale-token negative and an impossible canary for each arm.
  - That is 54 trials per session. Each session ran as one `quiet-timed` block holding the exclusive quiet-lane lock, for 56–60 s each.
- **Isolation.**
  - Every trial gets a fresh Driver inside `sandbox-driver.sh` (read-only root, tmpfs HOME, only the session's X, D-Bus and AT-SPI sockets bound, `--unshare-net`).
  - The Driver shares the private session's pid namespace (`session-pidns.sh`), never the host's. This is the Phase 0 fallback, because a per-trial pid namespace hides the target app's /proc entries from the Driver.
  - Everything ran under `hostless` (v2) inside `cua-x11-session.sh` with a private AT-SPI bus.
- **T.**
  - Whole-task T runs on the harness CLOCK_MONOTONIC from Driver spawn to the caller's oracle-verified done. The oracle is the fixture's own state file, and its mutation stamp must be <= done.
  - T_act runs from the m0 of the first dispatch call (the click) to done.
- **Same-binary control (extra).** I added 2 more sessions with 24 pairs each, running the base binary in both arms. This separates harness bias from binary-layout bias.

## Results (all trials retained; nothing filtered)

**Correctness.**
- All 144/144 task trials were verified exactly once (`seq_delta` 1, journal stamp <= done, 1 dispatch, route `accessibility`).
- All 12/12 controls were refused with no mutation (`stale_element_token`; the canary was refused).
- Run on the A/A rows, G2, G3 and G4 pass. G5 does not keep (p = 0.99), which is correct: an A/A must never be kept.

**Primary A/A (base vs rebuild, 72 pairs):**

| | whole-task T (decision metric) | T_act (fallback) |
|---|---|---|
| median base / rebuild | 620.8 / 632.4 ms | 308.1 / 309.9 ms |
| sigma_ln (sd of per-pair ln ratio) | **0.0592** | 0.0376 |
| Delta_AA (mean ln ratio) | +0.0168 (rebuild 1.7% slower) | +0.0078 |
| 95% CI, pair bootstrap | [+0.0037, +0.0309]: **excludes 0** | [-0.0009, +0.0163]: includes 0 |
| q97.5 of the pair-resampled \|Delta_AA\| (batch 72) | 0.0306 | 0.0167 |
| tau = max(2%, e^q − 1) | **3.11%** | 2.00% (floor) |
| n_pairs by power, 10.04 (sigma / ln(1+tau))^2 | **38** | 37 |
| feasible (≤ 400 pairs) | yes | yes |

- **Decision metric.** The pre-declared rule keeps whole-task T, because n = 38 ≤ 400.
- **The A/A CI check fails for whole-task T.** The rebuild is slower by +1.7% (CI +0.4% to +3.1%), and the effect is positive in every session (+2.3%, +1.9%, +0.9%).
  - The phase breakdown puts it in Driver startup. Spawn to MCP initialize is +6.8 ± 2.9 ms on a median of 229 ms. The click phase is +2.5 ± 1.4 ms on a median of 308 ms.
  - In the same-binary control the whole-task T Delta is +0.6% (CI −1.0% to +2.2%, includes 0), and T_act is +0.1% (CI −0.2% to +0.5%).
  - This pattern is consistent with a binary-layout or load effect at Driver startup that differs between the two builds of one commit. It is not consistent with a harness or order bias. The position effect, ln(T_second / T_first), is +0.8% (CI −0.6% to +2.2%).
  - The tau from this A/A (3.11%) already absorbs the 1.7% bias. Even so, a candidate is always a different binary, so startup layout noise goes into every whole-task T comparison.
  - T_act is unbiased in both A/As, has a lower sigma, and contains every segment-1 wait. Switching the decision metric to T_act is an owner decision. I did not make it here; see AA.json `owner_decisions`.
- **Self-consistency note.**
  - When tau is read at the A/A batch size (72 pairs), n by power is bounded by about 10.04 · 72 / 1.96² ≈ 188 whenever the floor does not bind. The 400-pair fallback can therefore only trigger through the floor.
  - Read at the evaluation's own batch size instead, tau is 4.3% for whole-task T (at n ≈ 20) and 2.0% for T_act (at n ≈ 36). Both values are recorded in `aa-summary.json`.
- **PSI discard threshold.**
  - Metric: per pair, the larger of the two trials' CPU-some stall fraction over spawn..exit, sampled at 10 Hz from /proc/pressure.
  - Rule: discard the whole pair when the metric exceeds Q3 + 3·IQR of the A/A pairs.
  - From the primary A/A: **0.349**. It discards 0 of 72 pairs, and the Spearman correlation of PSI with |d| is −0.09.
  - The PSI distribution depends on the load regime. It was bimodal (Q1 0.6%, Q3 9%) while background inference load was present. In the same-binary control, run later, the fence was 0.012.
- **Trace.**
  - Median T is 1.8% higher with the trace on than off (1.6% in the control).
  - In the primary A/A, Delta with the trace on is +1.0% and with it off is +4.7% (14 off pairs). The gap of 3.7% exceeds ln(1+tau) = 3.06%, so G7's point comparison of trace-on and trace-off would have failed this A/A. G7 has a real false-reject risk at about 8–14 off pairs. In the control the gap is 1.7%.

**Spot checks and controls.**
- **Browser fill->submit, harness runner kind** `spot_browser_fill_submit` (new): 12/12 on the champion (2 warm-ups + 5 pairs, champion binary in both arms).
  - Every trial was verified and showed exactly one POST with the trial token, stamped <= done, after a trusted pointerdown..click on Submit followed by submit.
  - Route `trusted_input`, 1 browser_click, no Driver-tree process outliving the Driver. Median T is 3.93 s.
  - It runs under hostless v2, which has no user namespace, so the Driver's root-owned-Chromium check passes. The browser Driver is not inside bwrap (see "Deviations").
- **Browser fill->submit through the Phase 0 fixture runner** (`validate_fixtures.py`): 0/10. This is expected and recorded.
  - The error is `browser_prepare refused: browser_route_unavailable ... isolated browser exited before exposing DevTools (signal: 5 (SIGTRAP))`.
  - The Chromium minidump shows `FATAL:process_singleton_posix.cc:313 Socket path too long: <run-root>/driver-homes/<trial>/tmp/com.google.Chrome.XXXXXX/SingletonSocket`. The fixture runner's per-trial TMPDIR is longer than the 107-byte sun_path limit.
  - This is a harness path-length bug, not a Driver limit. The harness kind uses a short per-trial TMPDIR and supersedes that runner, which stays frozen and unchanged.
- **Fixture controls, 5 trials each on base and on rebuild (100 trials).** Every cell passes in both arms: reference, stale token, no action, absent canary, disabled canary, delayed effect, focus steal, GTK3 text entry + save, and browser self-check (trusted and untrusted).

## Deviations and environment (read before using these numbers)

1. **The quiet lane was not quiet.**
   - The exclusive lock kept the other lane tracks out of every block. However, unrelated host processes outside the lanes, a local `ollama` and a `llama-server`, used about 8–10 cores of the 10 for the whole run. Loadavg was 14–20 during the A/A sessions.
   - These processes do not take the lock and were left alone (they were not started by this track).
   - The sigma here is therefore a **loaded-host** sigma. Medians are about 620 ms against 507 ms in the Phase 0 smoke at loadavg 3.6.
   - Re-run the A/A once the host is idle before freezing tau for a long campaign.
2. **Session size.** A session holds at most 48 *paired* trials (24 pairs), plus 2 warm-ups and 4 controls, which is 54 in total. Phase 0 counted all trials against 48. The planner, the block runner and the README were changed together.
3. **The browser Driver runs without bwrap and without session-pidns.sh.**
   - Any unprivileged bwrap is a user namespace. Inside one, root-owned Chromium shows as the overflow uid, and the Driver's isolated launch refuses it. Browser spot pairs therefore get their own sessions (`"pidns": false`).
   - Isolation for those sessions is `hostless` v2 (environment stripped, private runtime dir, Landlock scope) plus the private X11 session, a fresh trial HOME and a short trial TMPDIR.
   - G2 compares browser footprints only with champion browser rows. The Chromium profile contents and Mesa's shader cache each count as one entry, because Chromium writes them nondeterministically (otherwise a champion-vs-champion run fails G2 on `VariationsSeedV#`).
4. **Lock contention.** Exclusive waiters on the shared lock queue behind long-running shared-mode holders from other tracks. Blocks waited up to about 30 minutes for the lock, while each block itself ran for 1 minute or less.

## Files

- `aa-summary.json`: `ar-eval aa` output for the primary A/A.
- `aa-same-summary.json`: the same output for the same-binary control.
- `tau.json`: the input for `ar-eval prereg` (whole-task T: tau, sigma, n, PSI threshold, rows sha256).
- `raw/aa/`: plan, per-session raw rows (`ar.trial.v1`), block receipts, and the quiet-lane ledger lines of this track.
- `raw/aa-same/`: the same-binary control.
- `raw/browser/`: the browser spot check through the harness kind.
- `raw/fixtures/`: summaries of the fixture-runner validations (controls on both arms, and the browser re-validation).
- `raw/spot-and-controls.json`: per-cell pass counts that `verify_artifacts.py` checks.
- `MANIFEST.sha256`: sha256 of every file above.

Host paths in the raw files are replaced by `<lanes>`, `<tmp>` and `<mnt>`.

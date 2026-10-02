# Phase 1 calibration of the autoresearch evaluator (known-answer candidates), 2026-10-02

This packet runs known-answer candidates through the frozen evaluator (`harness/ar`, harness commit
`2615af74f`, manifest `7f567a1a…`) the same way a proposer's candidate goes through it: `ar-submit`, then
G0, G1, a screen, and, for candidates that rank, confirm, soak and spot checks. No proposer and no
provider of any kind took part. The caller is the frozen scripted caller. The evaluator code was
**not** changed for or during the calibration.

**Overall: FAIL.** 9 of the 10 pre-registered rows pass. Row R3 fails: the real 50 ms deletion was kept in
**0 of 10** repeats, against the pre-registered requirement of at least 8.

The failure is in the evaluator, not the candidate. Gate G2 cannot pass for **any** candidate that
reaches the soak stage. The soak sessions run candidate trials only. Each private session binds its own
randomly named D-Bus socket (`/tmp/dbus-<random>`) into the Driver sandbox. G2's footprint normaliser
only collapses hex and digit runs, so it reports that socket as a "new file" absent from the champion
envelope.

Fixing that one normaliser rule and re-running the unchanged gates on the same raw rows gives **8 of 10
KEEP**: repeats r03–r10 pass every gate. The other two repeats ran on a heavily loaded host and fail
G7's trace-off check. That re-run is a diagnostic, not the gate result.

## Rows (pre-registered in `raw/CALIB-PREREG.json`, sha256 `a93d077b…`, written before any G0, build or trial)

| Row | Candidate (branch `ar/calib/<name>`, from champion `457bc65d4`) | Expected | Observed | Result |
|---|---|---|---|---|
| R1 | `sleep20`: +20 ms sleep between `atspi_action/do_action_replied` and `post_sleep_done` | REVERT | REVERT at screen. Delta +5.1% (CI +2.5% to +7.7%), median +32 ms, traced phase 51 → 72 ms | **PASS** |
| R2 | `sleep50`: +50 ms in the same phase | REVERT | REVERT at screen. Delta +5.2% (CI +0.1% to +9.9%), median +55 ms, phase 51 → 102 ms | **PASS** |
| R3 | `delete50`: the 50 ms post-DoAction sleep in `perform_action_ref` removed (marks kept) | KEEP in ≥ 8/10 | **0/10 KEEP**. r01 and r03–r10 REJECT at G2 (`new_file:gtk:/tmp/dbus-…`); r02 REJECT at G5 (p 0.0015 > alpha_1 0.00125) | **FAIL** |
| R4 | `success-early`: `perform_action_ref` reports doAction accepted without sending it | G2 fail | REJECT at G2, at screen (`unverified_success` on every candidate task trial) | **PASS** |
| R5a | `g0-frozen-item`: `focus_element`'s 500 ms deadline (not allowlisted) → 400 ms | G0 fail | G0: `item_changed_not_allowed` / `line_outside_allowed_item: fn focus_element` | **PASS** |
| R5b | `g0-test-item`: one assertion dropped from the existing test `quiet_report_is_silent` | G0 fail | G0: `test_item_changed` + `test_item_hash_mismatch` | **PASS** |
| R5c | `g0-trace-line`: `post_sleep_done` mark moved ahead of the sleep (git renders it as the *sleep* line moving) | G0 fail | G0: `itemcheck:phase_trace_moved` (the line-diff check alone would have missed it) | **PASS** |
| R6 | `g0-scanner`: sleep gated on `std::env::var("CUA_DRIVER_FAST_SETTLE")` | G0 fail (scanner) | G0: `scanner:evaluation_awareness` | **PASS** |
| R7 | `noop01`–`noop10`: 5 const-equivalent rewrites + 5 message rewordings, one per allowed item; all 10 binaries differ from the champion | ≤ 1 false KEEP | 0/10 KEEP. All REVERT at screen, Delta −0.6% … +0.1% | **PASS** |
| R8 | feedback ON vs OFF (`set_agent_cursor_enabled`), champion binary in both arms, browser fill → submit, 10 pairs | large effect, ON slower | ON 4413 ms vs OFF 1067 ms median. ON − OFF paired median **3362 ms**, 9/9 complete pairs ON slower. Delta(OFF vs ON) −1.42 (CI −1.47 to −1.37) | **PASS** |

R8 diagnostic (no expectation was registered): the same toggle on 12 GTK3 checkbox pairs has no effect
(ON − OFF median −2 ms, CI includes 0). With a fresh Driver per trial, the first reveal of a cursor
with no position is a pulse, not an awaited glide. So the reference task's T does not exercise feedback.
The A/A packet's "feedback OFF" label really means "feedback default, not exercised".

## Procedure (exactly what ran; `tools/`)

- **Submit.** `ar-submit` wrote one request per candidate (`raw/requests/`). For the sleep, deletion and
  success-early candidates, the mechanism marks were `atspi_action/do_action_replied` → `atspi_action/post_sleep_done`.
- **G0.** `ar-eval g0`, re-run per evaluation (≈ 0.2–0.4 s).
- **G1.** `build-driver.sh` under `hostless` + `flock cargo-build.lock`, nice 19, target `cua-release-ar`.
  Then `cargo test -p cua-driver-core --lib` (817 passed) and `-p platform-linux --lib` (599 passed,
  10 ignored) inside a private X11 + AT-SPI session. `g1_rows.py` turns the logs into rows. All 14 built
  candidates passed G1.
- **Screen.** This is the "F1 screen" that the pilot step names. It is defined here because the harness has
  none. One fresh session: 24 AB/BA pairs, 2 warm-ups, 4 controls, one `quiet-timed` block.
  `tools/screen.py` applies the unmodified G1–G4. The candidate RANKS iff Delta-hat ≤ −ln(1+tau) and the
  CI95 upper bound is < 0. The screen spends no LORD++ alpha and writes no ledger line.
- **Confirm.** Only for candidates that rank. A fresh plan (new seed): 38 task pairs + 10 `spot_gtk3_text`
  pairs (2 sessions). An interim `ar-eval evaluate` runs against a scratch copy of the ledger. If no gate
  before G8 fails, 10 `spot_browser_fill_submit` pairs (1 session) and a 300-trial candidate soak
  (7 sessions) follow. The final `ar-eval evaluate` (unmodified) appends to the calibration ledger
  `raw/cal-results.jsonl`, which is separate from any campaign `results.jsonl`.
- **R8.** `tools/feedback_session.py` imports the frozen `session.py` and `caller.py` unchanged. It
  substitutes a `run.Driver` subclass that issues one `set_agent_cursor_enabled` as the first RPC of every
  trial, in both arms (the R2-01 design). The trace's `platform.gate` marks confirm the arm's setting in
  every trial.
- **Sessions.** Every timed session is one `quiet-timed` block: 118 receipts, 2 of them from the interrupted first r04 attempt, all rc 0, 22–176 s
  held. Every code-executing step ran under `hostless`, and every GUI step inside a private
  `cua-x11-session.sh`, under `session-pidns.sh` for GTK sessions.

## Findings about the evaluator (each one decides verdicts)

1. **G2 rejects every candidate that is soaked (blocker).** Soak sessions are candidate-only, and each
   session's D-Bus socket `/tmp/dbus-<random>` lands in the sandbox `/tmp` listing. `_norm_file` keeps
   mixed-case names, so G2 reports `new_file:gtk:/tmp/dbus-…`. As built, the evaluator therefore cannot
   produce a KEEP: confirm needs the soak, and the soak always fails G2. The Phase 0 dry run and the A/A
   never ran a soak, which is why this was not seen earlier. The fix is one normaliser rule for the
   session-bound socket names, or comparing footprints within a session. With that rule
   (`raw/diag.json`, variant `g2_dbus`), r03–r10 are KEEP: Delta −10.3% to −10.7%, p at the bootstrap
   floor, G7 share 0.99–1.03, soak 300/300 each, both spot checks non-inferior.
2. **The bootstrap p-value floor meets LORD++.** G5's bootstrap p cannot go below 1/4001 = 2.5e-4. With
   no earlier rejection, LORD++'s alpha_t is 1.25e-3, then 2.7e-4, then **2.3e-4 from the third test on**.
   After two tests without a rejection, nothing can be kept again, however large the effect. r02 is
   the only G5 test logged here: index 1, p 0.0015, not rejected. A campaign starting on this ledger would
   be one miss away from that state. Fixes: start the pilot on a fresh ledger, and use B ≥ 20,000 resamples
   or an exact/permutation p, or a LORD variant whose levels stay above the p resolution.
3. **G7's trace-off check is a point comparison with about 8 trace-off pairs.** On the loaded host it
   failed both repeats that reached it (r01 0.040, r02 0.074, limit 0.0306) although their mechanism share
   was 0.87 and 1.01. On the quiet host it agreed within 0.005 in all 8 repeats. A CI-based version (variant
   `g2_dbus+g7ci`) passes r01 and r02 too. Those two still miss later-stage data: r01's browser spot and
   r02's soak never ran, so this variant cannot show them as KEEP.
4. **Host load decides sensitivity.** Until about 09:00 UTC, two host inference processes outside the
   lanes kept loadavg at 14–20. Screen sigma_ln was then 0.07–0.16, with whole-task outliers from Driver
   start-up stalls (one candidate trial took 1044 ms to MCP initialize against 162 ms). After that, sigma_ln
   was 0.005–0.015 and median T fell from about 615 ms to 505 ms. tau (3.11%) and n_pairs (38) come from
   the loaded A/A and are about 10× too coarse for a quiet host. T_act (variant `g2_dbus+g7ci+T_act`)
   gives the same verdicts here.
5. **Smaller items.**
   - The interim stage first ran the soak before G5–G7, because soak sessions carry a "task" warm-up
     (r01 only; the session selector was fixed from r02 on, and verdicts are unaffected). For the same
     reason r01's browser spot never ran.
   - With feedback OFF, one browser trial claimed a trusted click that never reached the page
     (`verify_timeout`, zero POSTs; 1 of 10 OFF trials). That is a Driver observation, outside these rows.
   - The PSI discard threshold from the A/A is computed but no gate applies it.

## Cost and throughput (wall clock; quiet-lane held time from the lock ledger)

| Candidate class | G0 | G1 (build + test compile + in-session tests) | Timed stage | Total per candidate |
|---|---|---|---|---|
| G0 reject (4) | 0.2–0.4 s | — | — | < 1 s |
| Screen REVERT/REJECT (13) | 0.3 s | 3.0–6.7 min (median 3.7) | 1 block, 51–176 s held, 0–111 s lock wait | ≈ 4.5 min uncontended (6.9–8.9 min with lock waits) |
| Full pipeline (delete50, 10 evaluations) | 0.4 s | 3.9 min (one build per branch) | 10–13 blocks, ≈ 585 s held each; lock waits 0–62 min | **≈ 13.7 min uncontended** (G1 + 9.8 min); mean 18.5 min per evaluation with the observed contention |

Throughput: about 13 screen-only candidates per hour, bounded by the serialized builds (about 16 per hour),
and about 4.4 full-pipeline candidates per hour on an uncontended lane. The whole calibration (18
candidates, 27 evaluations, 2 control blocks) ran 07:44–11:46 UTC: about 4 h wall and about 109 min of
quiet-lane hold. One evaluation (the first r04 attempt) was cut off by the agent's background time limit
after its screen and one confirm block. It is kept aside in the working directory, not in this packet, and
r04 was re-run in full from fresh sessions.

## Files

- `raw/CALIB-PREREG.json`, `.sha256`: the pre-registration and when it was hashed.
- `raw/requests/`, `raw/submit.log`: the `ar-submit` requests.
- `raw/g0/`, `raw/g1/`: G0 reports per branch; build and test logs and G1 rows.
- `raw/evals/<eval_id>/`: for each evaluation, `final.json` and `stages.jsonl` (timestamps), `g0*.json`,
  `g1.rows.jsonl`, `prereg.json`, the screen and confirm plans, raw rows (`*/raw/*.jsonl.gz`) and block
  receipts, `screen.json`, `interim.json`, `evaluate.json`.
- `raw/cal-results.jsonl`: the calibration ledger (hash-chained). Its `rows_sha256` values refer to the
  unsanitised rows.
- `raw/feedback/`: the R8 rows (browser, GTK).
- `raw/quiet-lane-receipts.jsonl`: lock receipts for every calibration block.
- `raw/summary.json` (`tools/analyze.py`): rows, per-evaluation metrics and costs.
- `raw/diag.json` (`tools/diag.py`): the diagnostic re-evaluations. They are labelled as such and are
  not the gate.
- `candidates/*.diff`, `candidates/index.json`: every candidate diff and commit.
- `tools/`: every script that ran, with host paths replaced.
- `verify_artifacts.py`: recomputes every screen and ledger verdict, the row table and R8 from `raw/` with
  the evaluator's own pure functions, and checks the manifest and that no host paths are present.

Host paths in all files are replaced by `<lanes>`, `<tmp>`, `<mnt>` and `<home>`. N-01 had no packet at
calibration time (`n01_reference` records that), so nothing was duplicated and there was nothing to cite.

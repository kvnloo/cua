# R2-07c: compiled fresh-bound routine for toggle->confirm and modal->act (attempt 2, 2026-10-03)

Lane R2-07c, wave 4 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-07 family), kvnloo/cua#10 (accounting),
kvnloo/cua#74 (posting queue). Upstream items are named as plain text (trycua/cua PR 4316).

**Disposition: no pre-registered rule fired; proposed REVISE (correctness qualified, wall-clock
non-regression not shown, live arm not run).** The routine passed every correctness gate in both
classes: G1, G2, G3, G4 (21 rows x 5 reps), G5 (13 reconcile cells per class) and G6 costs. It had
0 E4 violations and every artifact passed the authority scan. The pre-registered scripted timing
gate failed: the 95% CI upper bound of T(COMP+CR) - T(COMP) is +16.9 ms (toggle) and +12.1 ms
(modal), above the +2 ms limit. Both CIs include 0. The decomposition shows the same Driver work in
both arms. The host loadavg was 8-32 during the EXCLUSIVE windows, which put the per-pair spread at
about +-100 ms. PREREG makes Phase S passing every gate a precondition for Phase L, so the live
TypeSafe arm was **not run: 0 attempts, 0 reached**. The live toggle/modal provider-decision
component (R2-10: 434.8 / 462.4 ms, 88-89% of COMP T) stays **UNTESTED**. It is not DELETED.

## Headline

| row | result | class |
|---|---|---|
| G1 training (independently verified, compiled, authority clean) | toggle 2/2, modal 2/2 (blocks G2 + T) | REAL |
| G2 clean-reset admission replay (verified, 0 fallback, 0 decisions, fresh) | toggle 2/2, modal 2/2 | REAL |
| G3 fresh binding (launcher Driver-call receipts) | 292/292 accepted mutations fresh in 209 COMP+CR cells; 10/10 non-fresh attempts (all N4b, by construction) refused with Driver `effect=refused` | REAL |
| G4 negatives (N1-N8, N-W2) | 105/105 pass (5 per class per row; N8 3 cross-page rows x 5) | REAL |
| G5 reconcile on action 2 (R2-05 seam) | applied_ack_lost 5/5 + 5/5 and delayed 5/5 + 5/5 verified_by_reconcile; withheld 3/3 + 3/3 unknown; 0 duplicates; 0 dispatches after unknown | FIXTURE (reconcile seam) + REAL |
| G6 costs | reported below (training, compile, admission, warm, fallback, wrong-match) | REAL+BENCHMARK |
| Scripted timing COMP vs COMP+CR, 30 AB/BA pairs per class | toggle median T 94.7 -> 85.6 ms, paired diff +4.1 ms [-15.1, +16.9]; modal 82.9 -> 82.0 ms, diff +6.9 ms [-3.3, +12.1]. **Gate (CI upper <= +2 ms) FAIL in both classes**; 60/60 pairs valid | REAL+BENCHMARK |
| Phase L live COMP+CR (TypeSafe) | NOT_RUN (pre-registered precondition: Phase S passes every gate); 0 provider attempts | BLOCKED (gate) |
| Paired live BASE vs COMP+CR S | BLOCKED (budget: needs >= 120 reached; loop has 58) | BLOCKED |
| E4 (every COMP+CR and COMP cell) | 0 stale dispatch, 0 ambiguous dispatch, 0 duplicate, 0 unverified success, 0 refusal returned as success, 0 blind replay, 0 dispatch after unknown | REAL |
| Unit (`harness/test_compiled_routine_tm.py` 19 OK; R2-07b `test_compiled_routine.py` 17 OK, 2 skipped) | pass | UNIT |

Provider: **0 attempts / 0 reached** (lane cap 18 reached / 22 attempts unused). No live request was
sent in attempt 2 or in attempt 1.

## Forced path, route/producer, oracle

- **COMP** is R2-10's COMP trial for toggle/modal, run unchanged (`rb10.one`). Feedback is OFF
  (`set_agent_cursor_enabled false`), the completion poll is 10 ms with a 2.0 s deadline, the output
  validators are compiled, and `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`. The phase trace is on. The
  step loop decides each click with the scripted chooser (`choose_mock_for_task`).
- **COMP+CR** is the same Driver configuration plus a compiled replay of the admitted artifact
  (`harness/compiled_routine_tm.py`, an extension of R2-07b `compiled_routine.py`). Before EVERY click
  it takes a fresh `semantic_v2` observation and binds the unique role+name match with the ref that
  observation minted. It checks the preconditions and the previous step's postcondition, then
  dispatches `browser_click` with `input_route=dom_event`. `browser_ref_stale` gets exactly one
  rebind. A transport failure after a click is reconciled with bounded oracle re-reads and is never
  replayed. A failed precondition hands the CURRENT state to the guarded continuation: the R2-10 step
  loop rules plus a role+name uniqueness filter, with every decision counted.
- **Actual route (receipts):** every accepted mutation in a valid cell is `browser_click` with
  receipt route `dom`, `input_route=dom_event`, and a `click.cdp_send` mark inside the click window
  (R2-10 `browser_row` checks). Warm/admission cells have decision route `compiled` only, 0 decided
  events and 0 provider requests. Training cells have 2 `provider` decisions from the scripted
  chooser. The arm-configuration checks (feedback off, 10 ms poll, admission-cache marks on every
  admitted call, compiled validators) passed in every timing cell.
- **Oracle:** the #24 fixture server's state and CLOCK_MONOTONIC journal (toggle: `checked` true;
  modal: `opened` and `modal` true). An independent harness thread reads it every 2 ms in process
  (`rb10.Sampler`), never through the runner. T_oracle runs from the send of the first semantic
  observation to the first expected-state sample at/after the return of the last accepted mutation.
  Completion mutations are counted from the journal.
- **Fresh per invocation:** Driver process, isolated Chromium, loopback fixture servers (new ports;
  the artifact is port-agnostic), token and session label.

## The artifact (no authority)

`raw/artifacts/` holds six compiled artifacts, one per class from each of the pre-PREREG
shakedown Kb, gate block G2 and timing block T. Each one holds
only role+name targets (`checkbox "feature"` -> `button "Confirm"`; `button "Open dialog"` ->
`button "Confirm choice"`), the preconditions (loopback origin pattern + page path; toggle
`checked_state "false"` with Confirm uniquely present; modal "Confirm choice" absent), the step-1
postcondition (`checked_state "true"` / "Confirm choice" present), `depends_on`, the expected outcome
and the fallback point. `check_artifact_authority_tm` rejects forbidden keys anywhere (ref, ids,
epochs, snapshot/backend/frame ids, pid, window id, coordinates, capture, continuation, session),
any key outside the schema, ref/id/uuid-looking values and floats. All 6 artifacts are clean, and
`verify_artifacts.py` re-runs the scan.

## G4 negatives (5 reps per class per row; REAL)

| row | expected | toggle | modal |
|---|---|---|---|
| N1 target renamed | routine stops at the failed precondition (toggle step 0 `requires_present`; modal step 1 `target_not_found`), 0 completion mutations | 5/5 | 5/5 |
| N2 target missing | same | 5/5 | 5/5 |
| N3 duplicate target | ambiguous precondition -> continuation drops the non-unique candidate; 0 completion mutations (both duplicates fire the completion event) | 5/5 | 5/5 |
| N4a node replaced between bind and dispatch | action 2 refused `browser_ref_stale`, Driver `effect=refused`; one rebind (3 observations); verified; 1 completion mutation | 5/5 | 5/5 |
| N4b superseding snapshot | old ref refused `browser_ref_stale` (`effect=refused`), one rebind, verified, 1 completion mutation | 5/5 | 5/5 |
| N5 session label replaced | old target capability refused in the new session (`authorization_host_failed`, discriminating control); fresh prepare+bind; verified; 1 completion | 5/5 | 5/5 |
| N6 unexpected dialog after action 1 | `dialog_opened` journaled; routine stops before action 2 (`target_not_found`: the modal dialog makes the page inert); 0 completion | 5/5 | 5/5 |
| N7 precondition already satisfied | routine dispatches nothing; continuation verified from the current state with exactly 1 accepted mutation (0 double toggles / 0 re-opens) | 5/5 | 5/5 |
| N8 OOD | toggle artifact on fill page 5/5 and on modal page 5/5; modal artifact on toggle page 5/5: 0 accepted mutations, 0 completion | 10/10 | 5/5 |
| N-W2 stale action (B-02 control, `rb10.nw2_one`, admission knob on) | refused `browser_ref_stale` (`effect=refused`), 0 mutations from the stale action, fresh re-derivation verified | 5/5 | 5/5 |

Notes. In modal N1/N2 the continuation clicks "Open dialog" a second time. The jev-use ModalTask
offers `open-dialog` whenever "Confirm choice" is not found. The second click is a non-completion,
idempotent action made by the chooser, not by the routine. The run then stops at
`redispatch_blocked` -> `unknown`. In toggle N1/N2/N3 the continuation clicks the checkbox (a unique
target) and then stops after 4 decisions. None of these are completion mutations, and none of the
fallbacks reports success.

## G6 costs (REAL+BENCHMARK, EXCLUSIVE windows; all invocations in the denominators)

| cost | toggle | modal |
|---|---|---|
| training invocation (R2-10 COMP step loop, 2 scripted decisions), T_oracle | 115.8 ms (n=1) | 71.1 ms (n=1) |
| compile | 0.209 ms | 0.112 ms |
| clean-reset admission replay, T_oracle | 55.9 ms | 68.4 ms |
| warm replay, median T_oracle (n=30, 30/30 verified, 0 fallbacks) | 85.6 ms | 82.0 ms |
| amortized mean (training + compile + admission + 30 warm) / 31, ratio to warm mean | 105.4 ms, 1.021 | 102.9 ms, 1.012 |
| fallback (N7: precondition already satisfied), median T_oracle, decisions/cell | 183.9 ms, 1 (5/5 verified) | 92.3 ms, 1 (5/5 verified) |
| wrong match (N8 cross-page), first observation -> routine end, decisions/cell, dispatches | 301.5 ms, 4, 0 | 294.0 ms, 4, 0 |

## Scripted timing (REAL+BENCHMARK)

Chunks T1 (rounds 0-14) and T2 (rounds 15-29) ran under `bin/quiet-timed` (EXCLUSIVE; receipts in
`raw/lock-receipts-global.jsonl`). Round r alternates the class order every 2 rounds and the arm
order AB/BA every round. Each class has 30 pairs, and 60/60 pairs were valid and verified.

| class | median T COMP | median T COMP+CR | paired diff CR-COMP (median, 95% CI) | S = COMP/CR | loadavg (1-min) | gate |
|---|---|---|---|---|---|---|
| toggle | 94.7 ms | 85.6 ms | +4.1 ms [-15.1, +16.9] (16/30 positive) | 1.11 [0.88, 1.24] | 8.3-30.8 (median 15.5) | FAIL |
| modal | 82.9 ms | 82.0 ms | +6.9 ms [-3.3, +12.1] (18/30 positive) | 1.01 [0.79, 1.10] | 9.2-32.0 (median 15.5) | FAIL |

Mean components (ms, valid timing cells; R2-10 decomposition, coverage 0.99) show the same Driver
work in both arms. Toggle COMP / CR: observation 36.7 / 34.2, endpoint revalidation 41.2 / 38.9,
MCP transport 8.2 / 8.2, dispatch 2.7 / 2.5, verification reads 2.2 / 1.2, runner 0.4 / 0.6. Modal:
observation 30.9 / 35.5, endpoint revalidation 36.6 / 37.9, transport 7.8 / 8.2, verification reads
2.0 / 1.0, runner 0.3 / 0.5. The routine deletes the scripted chooser and candidate building, which
are sub-millisecond with the mock chooser, plus the pre-step oracle reads. It adds no component. The
gate failure comes from per-pair spread (diff range -167 to +117 ms) under host load. The data do not
show a regression mechanism. Under the pre-registered rule this is still a FAIL, and this packet does
not claim non-regression.

## Work deleted vs wall-clock saved

- **Work deleted (scripted, per warm invocation):** 2 chooser decisions and 2 candidate builds,
  0.0 ms provider time with the mock, and the per-step pre-oracle reads (verification reads -1.0 ms
  mean). With TypeSafe this would be 2 live decisions (R2-10: 434.8 / 462.4 ms). That is not
  measured here: Phase L was NOT_RUN.
- **Wall-clock saved (scripted):** not distinguishable from 0 at this host load. Toggle paired
  median +4.1 ms [-15.1, +16.9]; modal +6.9 ms [-3.3, +12.1].

## Controls and discriminating checks

The N5 old-capability probe was refused 10/10, which shows the session replacement was real. N6
journaled `dialog_opened` in 10/10 cells, which shows the dialog really opened. In N4a the
replacement succeeded 10/10 (`dom_replace == replaced`) and the Driver refused the detached ref with
its own `effect=refused` (Driver result tap). In N4b the superseding snapshot made the launcher
receipt mark the attempt non-fresh, and the Driver refused it in 10/10 cells. G5 seam: `fault_fired`
in 26/26 cells. In the withheld row the effect applied only after the harness released it, after
the caller had finished with `unknown`, and there was no re-dispatch.

## Provenance

| item | value |
|---|---|
| tested source | branch `exp/r2-07c-toggle-modal-compiled-a2-20261003`, base `8f3a646b4818b757648835cf89db8886626b1cf0` (R2-10 source R; 989cc76ce + R2-10 steps 1-8; `libs/cua-driver` tree bf8e7bdc9). No Driver change in this lane |
| PREREG | commit `8f94c0529235898443811fbfe13da98e4bc70b0e` (2026-10-03T02:52:29Z), before the first measured trial (G2 03:00Z) and before any live request (none sent) |
| binary R | `cua-driver-r2-10-8f3a646b4`, sha256 `12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9`, `cua-driver 0.32.0`. The harness re-hashed it and read the version inside every private session, and every trial record carries name/sha256/version |
| harness basis | R2-07b `compiled_routine.py` and R2-10 `r2_10_browser.py` + sources copied by path, unchanged, from `exp/r2-10-composition-20261002` `030f6bdbf` (`harness/src/r2-10-composition-2026-10-02/`, including `analyze_r2_10.py` for the per-trial row) |
| live heads, start (02:41Z) | upstream main `41c34cb0d704d816e612dd3f9d0c816cdfacf178` (= planning; `libs/cua-driver` tree df2b49c32); trycua/cua PR 4316 head `a0bca744067d04f05904319d3d919be30c336556` (open) |
| live heads, end (04:00Z) | unchanged: upstream main `41c34cb0d`, trycua/cua PR 4316 `a0bca7440` (open) |
| publication SHA | the branch commit that carries this README (recorded by Publish) |
| environment | one Linux host; every code-executing command under `hostless` (Landlock + env scrub); Driver/Chromium inside `cua-x11-session.sh` (private Xvfb, private D-Bus); Driver telemetry off (`CUA_DRIVER_RS_TELEMETRY_ENABLED=0`, `DO_NOT_TRACK=1`); Chromium sandbox on; default Driver safety settings; TYPESAFE key never forwarded |
| locks | G/N/W/R and shakedowns under the SHARED quiet-lane lock, <= 10 cells per acquisition, receipt per acquisition in the loop ledger (`raw/lock-receipts-*.jsonl`); T1, T2 and C6 under `bin/quiet-timed` (EXCLUSIVE; 2.2, 2.3 and 1.3 min held) |
| load | 1-min loadavg at trial start 8.3-32.0 in the EXCLUSIVE windows (other tracks: builds, autoresearch load calibrations, other lanes' sessions) |

## Deviations

1. **Attempt 1 aborted** (no commit). Its SHARED mock shakedowns shake-a, a2, o2, o12 and o22 sent 0
   TypeSafe requests and are excluded. Its uncommitted harness was copied after review and then
   edited as PREREG `deviations_from_attempt_1` lists.
2. **Failed session-start blocks** (kept, excluded, re-run under new ids): shakedown K (pre-PREREG)
   and gate block G1 (`raw/gate-trials.tar.gz`, 02:59:54Z). In both, Xvfb/openbox could not open the
   display and every browser exited before DevTools, while several lanes started private sessions in
   the same second. They were re-run as Kb and G2. After G1, `harness/run_chunk.sh` gained a
   0-2.9 s random start jitter for SHARED acquisitions. This is a post-PREREG harness edit that
   changes no arm, plan, metric or gate.
3. **Phase L not run** because the pre-registered precondition failed (timing non-regression gate).
   No live shakedown was run either.
4. The analysis (`analyze_r2_07c.py`), `verify_artifacts.py`, `harness/package_raw.py` and
   `headline-numbers.json` were written after the PREREG commit. They implement the PREREG metrics.
   The disposition logic gained an explicit "no pre-registered rule fired" outcome for the case of a
   Phase S gate failure plus no Phase L, which the PREREG rules do not cover.

## Limits

The timing gate needs a quieter host. At loadavg ~15 the paired spread is about +-100 ms, so a
+2 ms bound cannot be shown with 30 pairs. The scripted chooser costs ~0 ms, so Phase S cannot show
the provider-decision saving. Only Phase L could, and it was not run. N3 uses a duplicate with the
same handler: the "0 ambiguous dispatches" evidence is 0 completion mutations, which is target-owned.
For the routine it is also the ambiguous precondition at bind time. N6 covers a modal `<dialog>` that
makes the page inert. A non-modal overlay that leaves the targets in the tree is not tested.

## Claim boundary

kvnloo/cua#24 toggle/modal pages, binary R (sha256 `12b9045a...`), scripted chooser only, one host,
private Xvfb. The routine is caller-side only: no new service, registry or router. Logical routine
identity persists in the artifact. Refs, tokens, captures, capabilities and session epochs do not.
No TypeSafe number is claimed. The paired live BASE vs COMP+CR S is BLOCKED on budget (>= 120
reached needed). Phase L would not be compared with R2-10's live numbers as an S in any case.

## Proposed next step (for the planner)

Re-run the scripted timing (and then Phase L, <= 18 reached) only in a window where the host is
quiet (for example loadavg < 4 for the whole EXCLUSIVE window). Pre-register it as a new block that
reports alongside this one, not in place of it. The correctness qualification (G1-G6, E4,
authority) would carry over unchanged if the binary and harness are the same.

## Evidence classes

REAL: every browser cell (private Xvfb, real Chromium, Driver over MCP stdio). REAL+BENCHMARK: the
timing and cost cells under the EXCLUSIVE lock. FIXTURE (reconcile seam): the G5 ack-loss / hold
journal rows. UNIT: `raw/unit/unit-tests.txt`. BLOCKED: Phase L (gate precondition) and the paired
live S (budget). NOT_RUN: Phase L live shakedown.

## Files

- `PREREG.json`: the pre-registration (commit `8f94c0529`).
- `harness/`: `r2_07c.py` (runner), `compiled_routine_tm.py`, `fixture_tm.py`, `fault_transport_tm.py`,
  `test_compiled_routine_tm.py`, `run_chunk.sh`, `in_session.sh`, `package_raw.py`, plus `harness/src/`
  (R2-10 / R2-07b / B-02 sources, unchanged).
- `analyze_r2_07c.py`, which writes `r2-07c-summary.json`; `headline-numbers.json`; `provenance.json`.
- `raw/`: `<block>-trials.tar.gz` (per-trial JSONL + Driver traces) for shakedown-K, shakedown-Kb,
  gate (failed session block), gate2, neg, nw2, rec, timed and costs; `<block>-manifests/`;
  `<block>-routines/`; `raw/artifacts/`; `raw/lock-receipts-lane.jsonl`;
  `raw/lock-receipts-global.jsonl`; `raw/unit/unit-tests.txt`; `raw/package-report.json`. There is
  no `provider-ledger.jsonl` because no provider request was made.
- `.gitignore` (packet-local): ignores bytecode and re-includes `raw/artifacts/`, which the repo-root
  `artifacts/` rule would otherwise drop. Check 9 caught this before the first packet commit.
- `verify_artifacts.py`: 9 checks. Run it under hostless with the jev-use venv python;
  `--skip-git` skips checks 7 and 9 on an export.

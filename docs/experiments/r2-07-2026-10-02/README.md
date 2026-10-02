# R2-07: one compiled, fresh-bound fill→submit routine vs ordinary and guarded callers (live TypeSafe)

**Disposition: REVISE** (pre-registered attribution rule). Under the literal reading of the spec's stale-dispatch KILL rule it would be **KILL**. Both readings are explained under [Disposition](#disposition) and both are printed in `r2-07-summary.json`.

## Headline

On one admitted #24 class (fill→submit), the compiled routine (arm C) needs **0** provider decisions. It is independently verified in **20/20** warm attempts, with median whole-task **T = 186.121 ms**. Guarded completion (B, 1 decision) takes **454.468 ms** (**20/20**), and the ordinary caller (A, 2 decisions) takes **672.019 ms** (**20/20**). The paired per-round medians, with 95% bootstrap CIs over 20 rounds, are:

- T(C) − T(B) = **-272.988 ms** [-285.032, -241.208]
- T(C) − T(A) = **-486.301 ms** [-505.267, -471.812]
- T(B) − T(A) = **-238.387 ms** [-253.607, -204.066]

Gates G1, G2, G3, G5 and G6 hold. G4 holds for 8 of the 9 negative rows and fails on **N4a**. In N4a the page replaces the Submit node between the routine's fresh observation and its dispatch. The Driver's `dom_event` `browser_click` **accepts the ref to the detached node** (3/3, `effect=unverifiable`, nothing lands). The routine then ends in an explicit `unknown` stop after its bounded re-read, with 0 duplicates and no replay. The same injection on the unmodified run.py path (comparator N4a_ord) gets the same Driver acceptance (3/3), so the gap belongs to the Driver, not to the routine. Across all phases there are 0 duplicate submits, 0 unverified successes, 0 ambiguous dispatches, 0 routine-attributable stale dispatches, and no authority field in the artifact. N8 dispatched nothing.

Provider budget for this lane: **68** requests reached TypeSafe out of 68 attempts (lane cap 80): learning 2 + A 40 + B 20 + P7 6.

## What was tested

| Item | Value |
|---|---|
| Forced path | A: unmodified `run.py --provider live`. B: the same plus `--guarded-completion`. C: compiled replay of the admitted artifact (`harness/compiled_routine.py`) run through the same Driver setup sequence as run.py. Feedback is held OFF in every arm. |
| Actual route / producer | A: `decision_routes = provider/provider` in 20/20. B: `provider/guarded-completion` in 20/20. C: 0 provider receipts, and every C mutation used the ref minted by its own fresh `semantic_v2` observation (G3: 110/110 dispatches fresh across P3, P4, P5, P6 and P7). Mutations used `browser_type` and then `browser_click` with `input_route=dom_event` (from the learning trace). Model in the receipts: `jev-1.13.0`. |
| Independent target-owned oracle | The fixture's own journal (`harness/fixture.py`): one `received`/`applied` event per `POST /submit`, compared with the trial token only. Plus `/state`, polled by the harness every 4 ms with a header that keeps those reads out of the caller-read count. A trial counts as verified only when the journal shows `applied == 1` and the value matches the token. Caller reports and events are never the oracle. |
| Negative / fallback controls | P5: N1–N8, plus the comparator N4a_ord. P6: ack loss on the compiled Submit (two pre-registered rows plus an unresolved control row). P7: live chooser fallback. |
| Tested source | `031ee5f58`: upstream main `c4d0c6625` with trycua/cua PR 4316 head `a0bca7440` merged `--no-ff` (conflict-free). The PR touches `examples/jev-use` and `.github/workflows/ci-jev-use.yml` only. |
| Driver | `cua-driver 0.32.0`, sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, not rebuilt. It is valid for this source because `git diff --quiet 229b65b28 031ee5f58 -- libs/cua-driver/rust` succeeds; this is re-checked in every phase's `validity.json`. |
| Environment | Private rootless Xvfb through `cua-x11-session.sh` (X11 only, scrubbed env, private dbus). Chrome 151.0.7922.71, launched by the Driver with a fresh `isolated_new` profile per trial. Default Driver safety settings. Python 3.12.13. |
| Live heads | trycua/cua PR 4316 head was `a0bca7440` at both start (01:50Z) and end (02:44Z). Upstream main was `8d4e7a086` at both, one commit past the tested base; that commit touches no `libs/cua-driver` path. The tested source is `031ee5f58`, PREREG is `ba264324b`, and the publication SHA is the commit adding this README. Nothing was pushed by this worker. |

## Method

1. **STEP 0** (UNIT, REAL; before PREREG). At the merged source: jev-use Python suite 248 OK (1 skipped), guarded-focused 8 OK, TypeScript tests, guarded test and typecheck rc=0. Two mock run.py smokes against this binary inside the session (plain, and `--guarded-completion` with step 2 on the `guarded-completion` route) were both verified. No incompatibility was found.
2. **Shakedown** (mock only, 0 provider requests; disclosed in PREREG, raw in `raw/shakedown/`). It found one harness bug: `set_agent_cursor_enabled` is scoped to a session label. Called without `session` it landed on the implicit `mcp-*` session and feedback stayed ON for run.py's label, giving T≈3.2 s in every arm (`smoke1`). The fix sends `{enabled:false, session:<label>}` before the first call of each Driver label; T then fell to about 0.19 s in mock arms (`smoke2`). Every measured cell carries a `feedback_off` receipt with `enabled_after=false` and a matching label (0 invalid cells). The shakedown also showed the N4a Driver behaviour before PREREG was frozen, which is why PREREG pre-registers the attribution rule.
3. **PREREG** committed at `ba264324b` (02:12:57Z), before the first measured trial (learning, 02:15:40Z).
4. **P1 learning → P2 compile → P3 admission** (exclusive lock). P1 is one ordinary live run with receipts. P2 compiles those receipts into `raw/learn/artifact.json`: logical role+name targets, `param_slot: token`, preconditions, `depends_on`, the expected outcome and the fallback point. It contains no refs, ids, epochs or coordinates. P3 resets the fixture, starts a fresh Driver and Chrome, and replays with fresh binding and no fallback.
5. **P4 warm** (exclusive lock, 02:16:06–02:19:19Z, 1-minute loadavg at spawn 2.29–5.17). 20 rounds in the order ABC, BCA, CAB, ACB, CBA, BAC, repeated. Every trial gets a fresh Driver, Chrome, fixture and unique token. T runs from the send of the trial's first `semantic_v2` observation to the first harness poll that sees the token.
6. **P5** negatives (shared lock, ≤10 trials per acquisition, mock fallback), **P6** ack loss (shared lock; the R2-05 seam between `ClientSession` and the SDK stdio streams, copied verbatim), **P7** live fallback (exclusive lock, n=3).

## Results

### Warm arms (P4): BENCHMARK + LIVE_PROVIDER + REAL

| Arm | Provider decisions per run | Verified (journal) | T median [IQR], ms | T_target median, ms | Process wall median, ms | Requests reached | Input/output tokens |
|---|---|---|---|---|---|---|---|
| A ordinary | 2 | 20/20 | 672.019 [660.607, 695.083] | 669.652 | 2015.361 | 40 | 26960 / 1960 |
| B guarded | 1 | 20/20 | 454.468 [425.928, 478.802] | 452.799 | 1814.776 | 20 | 12760 / 1060 |
| C compiled | 0 | 20/20 | 186.121 [183.297, 188.011] | 182.924 | 1515.468 | 0 | 0 / 0 |

Paired (rounds where both arms verified; n=20 each; seed 20261002, 10000 resamples):

| Contrast | Median Δ, ms | 95% CI | Evidence |
|---|---|---|---|
| T(C) − T(B) | -272.988 | [-285.032, -241.208] | BENCHMARK+LIVE_PROVIDER |
| T(C) − T(A) | -486.301 | [-505.267, -471.812] | BENCHMARK+LIVE_PROVIDER |
| T(B) − T(A) | -238.387 | [-253.607, -204.066] | BENCHMARK+LIVE_PROVIDER |

Component medians inside T (receipt spans, verified cells):

| Arm | Provider | Observations (2) | Mutations (type + click) | Other |
|---|---|---|---|---|
| A | 428.884 ms | 26.485 ms | 159.981 ms | 50.812 ms |
| B | 211.412 ms | 27.349 ms | 158.877 ms | 49.231 ms |
| C | 0.0 | 27.354 ms | 158.998 ms | -1.2 ms |

C's "other" is slightly negative because the Submit effect lands inside the `browser_click` call span, before the call returns. The remaining time in C is Driver work: `browser_type` is about 130 ms of the mutation share. Median T by position (1/2/3): A 671.698/669.89/672.365; B 482.217/428.546/458.466; C 184.644/187.465/186.283.

**Stale-ref exposure window** (end of the observation → start of the dispatch that uses its ref), median for the type and click mutations:

| Arm | Type | Click |
|---|---|---|
| A | 276.891 ms | 208.432 ms |
| B | 264.211 ms | 0.176 ms |
| C | 0.177 ms | 0.131 ms |

### Gates

| Gate | Result | Evidence |
|---|---|---|
| G1 independently verified training run | PASS: T 675.408 ms, 2 live decisions, journal applied 1 | LIVE_PROVIDER+REAL |
| G2 clean-reset replay verified before admission | PASS: T 179.008 ms, 0 fallback, 0 provider requests | REAL |
| G3 fresh binding before every mutation | PASS: 110/110 compiled-routine dispatches used a ref from the routine's latest observation, taken after the previous mutation (P3+P4+P7 receipts 45/45, P5 39/39, P6 26/26) | REAL |
| G4 every negative stops or falls back safely | **FAIL on N4a only** (8/9 rows pass; see the table below) | REAL |
| G5 reconcile before fallback, 0 duplicates | PASS: 13/13 (table below) | REAL |
| G6 separate costs, all-invocation denominators | PASS (Costs section) | REAL+BENCHMARK |

### Gate-4 negatives (P5, mock fallback, 3 reps each): REAL

| Row | Injection | Outcome (3/3) | Dispatches per rep | Journal applied | Notes |
|---|---|---|---|---|---|
| N1 | Submit renamed "Send" | stopped (fallback budget exhausted) | 1 (type only) | 0,0,0 | bind found 0 matches → chooser offered only reobserve/abstain |
| N2 | Submit missing | stopped | 1 | 0,0,0 | same |
| N3 | duplicate Submit | stopped | 1 | 0,0,0 | `target_ambiguous`; fallback dropped the non-unique `submit-form` candidate; **0 ambiguous dispatches** |
| N4a | page replaces the Submit node between bind and dispatch | unknown (explicit stop after a 3 s bounded re-read) | 2 | 0,0,0 | **Driver accepted the stale-node click 3/3** (`effect=unverifiable`); no replay |
| N4b | superseding snapshot between bind and dispatch | verified | 3 | 1,1,1 | Driver refused `browser_ref_stale` (`effect=refused`) → exactly one rebind from a fresh observation → fresh dispatch |
| N5 | Driver session label replaced between steps | verified | 2 | 1,1,1 | old target refused in the new session (`authorization_host_failed`); rebind via `browser_prepare{pid}` + `get_browser_state{pid,window_id}` |
| N6 | typing opens a modal `<dialog>` | stopped | 1 | 0,0,0 | modal opened 3/3; the inert form left the snapshot; nothing dispatched under the modal |
| N7 | field prefilled with another value | fallback_verified | 2 (both fallback) | 1,1,1 | `field_state` precondition failed → chooser continued from the current state (type, then Submit) |
| N8 | artifact invoked on the toggle→confirm page | stopped | **0** | 0 (toggle events 0) | textbox not found; chooser offered only reobserve; **nothing dispatched** |
| N4a_ord (comparator) | same injection before unmodified run.py's first click (mock) | verified | 2 clicks | 1,1,1 | Driver accepted the stale-node click 3/3. run.py then **re-dispatched Submit** on a fresh ref after its 20×100 ms poll. Harmless here (the first click had no effect), but it is a re-dispatch after an accepted mutation with an unverified effect. |

Block b1 (N1–N3, first attempt) hit an environment failure; see Deviations. Its 9 cells are kept in `raw/neg/b1/`, excluded from row evaluation, and counted in the totals.

### Gate-5 reconcile (P6): REAL

| Row | Reps | Outcome | Journal received/applied | Reconcile reads | Dispatches after the unknown |
|---|---|---|---|---|---|
| applied_ack_lost | 5 | verified_by_reconcile 5/5 | 1/1 each | 1 each | 0 |
| delayed_after_first_unchanged_read | 5 | verified_by_reconcile 5/5 | 1/1 each | 2 each (the first read is unchanged) | 0 |
| withheld_unresolved (control) | 3 | unknown 3/3 | 1/1 each (applied after release) | 60, 59, 59 (3 s) | 0, and step 1 was never restarted |

### Live fallback (P7, N1 with the TypeSafe chooser, n=3): LIVE_PROVIDER + REAL

3/3 explicit stops. In each run the live chooser picked `reobserve` twice, with no dispatch after the type and journal applied 0. Median time to stop is 647.776 ms, median process wall 2114.876 ms, and each invocation cost 2 provider requests (6 total).

## Costs (#10 accounting; each line separate; denominators are all invocations)

| Cost | Value | Evidence |
|---|---|---|
| Learning (P1) | T 675.408 ms, process wall 2164.632 ms, 2 requests | LIVE_PROVIDER |
| Compile (P2) | 0.14 ms in process | UNIT-scale timing, REAL input |
| Admission verification (P3) | T 179.008 ms, process wall 1564.413 ms, 0 requests | REAL |
| Warm replay (P4 C) | T median 186.121 ms, wall median 1515.468 ms, 0 requests | BENCHMARK |
| Fallback (P7) | 647.776 ms to explicit stop, 2 requests per invocation, 0/3 completed | LIVE_PROVIDER |
| Wrong match (N8) | 30.643 / 26.398 / 28.804 ms to stop (mock fallback; untimed phase, informational), 0 dispatches | REAL |
| All compiled-routine invocations | 73: P3 1, P4 20, P5 27, P5 setup-failed 9, P6 13, P7 3. 43 independently verified, 24 explicit stop/unknown, 9 setup errors (b1). Summed wall 208138.418 ms. 6 provider requests | REAL |

- **Work deleted** (per warm run): 2 provider decisions and 2.0 requests vs A (1348 input tokens per run), and 1 decision and 1.0 request vs B (638 input tokens per run). Nothing is deleted on the Driver side: C makes the same 2 observations and 2 mutations as A and B.
- **Wall-clock saved** (paired median T): 272.988 ms vs B and 486.301 ms vs A. By arm medians it is 268.347 ms vs B and 485.898 ms vs A.
- **Break-even** (the measured saving is positive):
  - *T basis.* Incremental overhead (compile + admission T) is 179.148 ms, which pays back in 1 warm run vs B and 1 vs A. The conservative overhead also counts the whole learning run, 854.556 ms, and pays back in 4 runs vs B and 2 vs A.
  - *Process-wall basis.* Admission needs its own Driver and Chrome start. Incremental overhead is 1564.553 ms, paying back in 6 runs vs B and 4 vs A. Conservative overhead is 3729.185 ms, paying back in 13 vs B and 8 vs A.
  - Fallback invocations (P7) save nothing: they cost about the same as an ordinary run that stops.
- Successful-replay latency is not whole-workload latency. On a workload where the precondition fails, the routine adds one observation and one bind (fast) before the chooser runs.

## Disposition

The pre-registered rules (PREREG `disposition_rules` and `stale_dispatch_attribution`):

- **KILL checks.** None fire: routine-attributable stale dispatch 0 (G3 110/110), ambiguous dispatch 0, duplicates 0 in every phase, unverified successes 0, authority fields 0, admission passed, N8 dispatches 0, and the T(C)−T(B) CI lies entirely below 0.
- **KEEP.** Requires G1–G6, CIs below 0 vs both A and B, and C verified ≥19/20. The CIs and the 20/20 hold, but **G4 fails on N4a**, so KEEP is not available.
- **Result: REVISE**, with the measured narrowed claim below.
- **Literal reading.** The spec's KILL list says "any stale … dispatch". N4a's three Driver-accepted stale-node dispatches meet that text, and reading it literally gives **KILL**. The PREREG attributes those dispatches to the Driver, for two measured reasons. The comparator N4a_ord shows the same acceptance on the unmodified caller path. And C's exposure window (0.131 ms before Submit) is far smaller than A's (208.432 ms) or B's type window (264.211 ms). This is a pre-registered deviation from the spec's wording; the planner/judge can apply either reading.

**Revised (measured) claim.** On jev-use fill→submit (PR 4316 caller on `c4d0c6625`, Driver 0.32.0 `8b037961`, TypeSafe `jev-1.13.0`, feedback OFF, Xvfb, Chrome 151), one admitted compiled routine deletes both provider decisions on warm replay, 20/20 independently verified. It is faster than guarded completion by a paired median of 272.988 ms and faster than the ordinary caller by 486.301 ms, with CIs excluding 0. It binds fresh before every mutation (110/110), reconciles ack loss without duplicates (13/13), and stops or falls back safely on renamed, missing and duplicate Submit, superseded snapshots, session replacement, modal interruption, prefilled values and out-of-domain pages. **One condition applies:** if the page replaces the target node inside the observation→dispatch window, the Driver's `dom_event` click is accepted onto the detached node. The routine then stops as unknown without a duplicate. On this page nothing lands, but a page whose detached control keeps a JS handler could land an effect. Closing this needs a Driver-side check (for example, refuse `dom_event` dispatch when the resolved node `!isConnected`). That would be a separate, reviewed Driver change and is not made here.

**E2 (remaining provider-decision component on fill→submit).** DELETED for admitted warm replays, subject to the REVISE condition. Provider time is 63.8% of T in A (428.884/672.019) and 46.5% in B (211.412/454.468); in C it is 0. Fallback invocations keep the decision (P7: 2 per invocation).

**E3 (R2-10).** Under REVISE, the composed configuration should include compiled replay for admitted fill→submit and count it over all invocations: learning, compile, admission, fallback and failures, using the cost table above. Carry the N4a Driver gap as a Driver follow-up item; it applies to A and B as well.

**E4 controls.** Refusals are refused and discriminating: N4b `browser_ref_stale` came back as `effect=refused`, and N5's old target was refused. run.py's own `Driver.call` treats an `effect=refused` result with `isError=false` as success. It did not matter in A/B here, but it is a caller-side gap worth an owner row. A possibly landed effect was never blind-replayed by the routine (P6, N4a). The ordinary caller's re-dispatch after an unverified click is recorded in N4a_ord.

## Toggle→confirm and modal→act under the same schema (SOURCE / FIXTURE only)

| Class | Fits the schema? | Delta needed |
|---|---|---|
| toggle→confirm (5474aa31f page) | Mostly. Two steps: `browser_click` on role checkbox "feature", then `browser_click` on button "Confirm" with `depends_on: 0`. | (1) The precondition needs `checked_state: false` and the dependency postcondition needs `checked: true`. `semantic_v2` refs expose `states.checked` (SOURCE: `browser/semantic.rs ax_states`). (2) `expected_outcome` must name a different oracle (`/state.checked == true`, one toggle event) instead of `submitted == token`. (3) Confirm's effect is a `fetch` from an `onclick` handler, so it lands asynchronously and needs the bounded re-read (R2-06). It is also exactly the case where the N4a Driver gap could land an effect from a detached node, so admit it only after the Driver check. |
| modal→act (5474aa31f page) | Yes for steps. Click button "Open dialog", then button "Confirm choice" with `depends_on: 0`. The second target does not exist before step 0, which fresh observation per step handles naturally. | Only the `expected_outcome` generalization (`opened && modal`) and a dependency postcondition "target present after step 0". There is no parameter slot. |

Neither class was replayed here. The claim stops at fill→submit.

## Deviations

1. **Shakedown before PREREG** (mock only, disclosed in PREREG). It surfaced the label-scoped feedback bug and the N4a Driver behaviour, which led to the pre-registered attribution rule. Its outputs are never analysed as measured trials.
2. **PREREG `registered_utc` is wrong.** It reads `02:20:00Z`, a placeholder written forward-dated. The authoritative time is the commit time `ba264324b` = 02:12:57Z, before the first measured trial (02:15:40Z). `verify_artifacts.py` checks the commit order. The field was not edited after commit.
3. **Negatives block b1 was environment-invalid.** In that one private session, `xvfb-run -a` assigned display `:99`, which another lane's private Xvfb/openbox was already using. Openbox logged "A window manager is already running on screen 0". The browser window never became ready within run.py's `wait_for_window`, so all 9 cells (N1–N3) ended with `RuntimeError` before the first routine observation: 0 dispatches, 0 target POSTs. The host desktop was not involved. Of the lane's 16 sessions, only b1 logged the collision. N1–N3 were re-run as block b1r in a fresh session. The rule that excludes routine-never-started cells from row evaluation was added after the fact and is disclosed here; those cells still count in the all-invocation totals. The race lives in the shared session script, which this lane did not edit; it is reported for the loop.
4. **Extra controls beyond the spec**, added before PREREG: N4a_ord, N4b (superseding snapshot, alongside N4a's DOM re-render), and the P6 `withheld_unresolved` row.
5. **Stale-dispatch attribution split** (see Disposition): a pre-registered deviation from the spec's literal KILL text.

## Limits

- n=20 per arm on one fixture page. The CIs are for this page, source, binary, provider and environment only. Never compare them with wave-0 or other sources.
- T ends at the harness's 4 ms poll. Caller-side completion (the routine's 10 ms re-read, run.py's 100 ms poll) is not in T.
- P5 and P6 run in process (same Driver and transport, harness process), while P4 runs each arm as a subprocess. P5/P6 times are informational.
- The compiled routine is packet harness code (`harness/compiled_routine.py`): not product code, not a framework. Nothing here changes default Driver or runner behaviour.
- Feedback ON was not measured. R2-01 owns that component.

## Claim boundary

One admitted #24 class (fill→submit); Python runner; trycua/cua PR 4316 merged onto main `c4d0c6625` (tested `031ee5f58`); Driver 0.32.0 `8b037961`; TypeSafe model `jev-1.13.0` as reported in the receipts; feedback OFF; X11 Xvfb; Chrome 151. Not a routine framework, and nothing transfers to other tasks.

## Files

- `PREREG.json`: frozen before the first measured trial.
- `harness/`: `compiled_routine.py` (artifact schema, authority check, compile, fresh-bound replay, fallback), `r2_07_launcher.py` (measurement-only launcher around the unmodified run.py), `r2_07_harness.py` (all phases), `fixture.py` (journaled fixture and page variants), `fault_transport.py` (verbatim from R2-05), `test_compiled_routine.py` (17 unit tests), `run_phase.sh`, `step0_smoke.sh`, `shakedown_probe.py`, `package_raw.py`.
- `raw/`:
  - `step0/`: unit step results and smoke logs.
  - `shakedown/`
  - `learn/`: P1 trial, learning trace, artifact, compile, admission.
  - `warm/trials/*.jsonl`: one file per trial with the cell, runner events, receipts and target journal.
  - `neg/{b1,b1r,b2,b3,b4}/`
  - `p6/{b1,b2}/`
  - `livefallback/`
  - `budget.json`, `locks.txt`
- `analyze.py`: recomputes every number from raw/. `r2-07-summary.json`: its output.
- `provenance.json`
- `verify_artifacts.py`: recompute check, README needles, authority schema check with injections, provenance pins, budget, PREREG order, privacy scan.
- Raw mirror: `<lanes>/artifacts/r2/R2-07/`.

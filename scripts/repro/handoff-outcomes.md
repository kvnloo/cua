# Handoff outcomes

Downstream record for the open `kvnloo/cua` GPT queue. Draft PR 26, branch `test/rfc-fast-path-one-candidate-20260925`. No issue is closed from this file. Words KEEP, REVISE, and KILL appear only in the mechanism table, and only next to a test that was run.

Host: Linux. `platform-macos` was not compiled here. No Windows machine was available.

## Mechanism table

| Mechanism | Decision | Why | Evidence |
| --- | --- | --- | --- |
| Embedding guarded-run length 4 as a shared constant | KILL | A planned length of 4 still stops after a failed first postcondition and wastes the rest. That is not a reason to hard-code 4. | `libs/cua-driver/examples/jev-use/python/tests/test_run_length.py` |
| Treating a passive observation row as an action target | KILL | Verification may read the row. Minting an action target from it raises. | `libs/cua-driver/examples/jev-use/python/tests/test_passive_observation.py` |
| Skipping a capture because a shadow probe said so | KILL | The probe constructor rejects `skip_capture=True`. The recorded GTK text-change is logged and still observed. | `libs/cua-driver/examples/jev-use/python/tests/test_shadow_probe.py` |

Every other mechanism in this queue stays undecided. Unit admission is not a live interleaved trial.

## Experiment issues

### Issue 2

Asked for outcome-level A/B receipts under `scripts/repro/` and a verdict for trycua/cua#4165. Those receipts were not produced. `lazy_vision.needs_visual_capture` is the admission rule only: a semantic executable candidate skips optional visual capture, and a capture-bound candidate does not. Live Driver, Chromium, and model session: not run on this host.

### Issue 3

Asked for a native walker count of 0 on screenshot evidence. Not measured. The call site in `expectation.rs` is locked: the screenshot read calls `observe(..., false, true)`. That is not a platform trace.

### Issue 4

Asked for live metrics before a fast path is eligible. Not measured. `single_executable_candidate` admits only one non-reserved tooled candidate. The default chooser is unchanged. A chooser that would reobserve is recorded as a different choice, not promoted.

### Issue 5

Caller-side plan and the fresh-observation gate are in `guarded_run.py`. Negative cases do not dispatch the second child. Wall-clock and fixture success were not measured, so there is no verdict.

### Issue 6

`stale_batch.run_batch` re-resolves child 2 before dispatch. Same identity may run. A missing target or a new identity is refused. A failed or unknown first child does not start child 2. No live app trace.

### Issue 8

Blocked on a macOS machine. The Calculator result in trycua/cua#2958 was not driven. The downstream rule in `passive_observation.py` lets verification read a passive row and refuses to mint an action target. That is not native evidence and not a patch recommendation with a passing Calculator log.

### Issue 9

`cancellation_lifetime.Lifetime` records admitted, cancellation observed, native exit, permit release, then public result. Release before native exit raises. A different issuance raises. This is the order #3796 asked to see. It is not a trace from the existing core owner, and no competing runtime was added. Handoff: slice 1 belongs on the existing request-id owner after RFC approval, not on a new service.

### Issue 10

`task_accounting.outcome_time` returns verified-outcome time and will not return runner lifetime. A named span under 90 percent of that outcome fails `phase0_spans_cover_outcome`. The 4-arm live benchmark was not run.

### Issue 11

`shadow_probe.record` always stores `skip_capture=False`. The GTK census file is an input to the test, not a license to skip. No false-retention corpus and no reconciliation-cost measurement, so Phase 2A is not accepted.

### Issue 12

`action_consumer.typed_choice` observes again when the poll was skipped, the effect is unverifiable, or the observation is unavailable. Refusal stops. Passive success may continue. The naive policy replays those cases. No Calculator run.

### Issue 13

`WalkBudget` in `walk_budget.rs` starts its clock at the first admitted node and says setup is outside that budget, with a separate backend backstop. `walk_budget_owner.WalkSplit` names the same three owners from timings a caller supplies. No slow native tree was walked on this host, so there is no per-phase log and no new budget type.

### Issue 14

`compile_expectation` attaches field or fixture equality to the two executable jev-use ids and returns nothing for reobserve and abstain. `provider_cannot_replace` keeps the compiled value. One recipe is not a shared helper.

### Issue 16

Blocked on macOS and Windows machines. This host cannot show whether `include_accessibility_tree` and `include_screenshot` behave the same on those drivers. No selector was changed.

### Issue 17

`browser_revision.bind` accepts a ref only when the ref and generation match the current node. The same label on a new generation raises `StaleRefError`. This is the browser rule the later conditional-observation notes have to respect. It is not a CDP conformance log.

### Issue 18

Blocked on a macOS machine. No AX event trace was captured. No signal is marked safe.

### Issue 19

Blocked on a Windows machine. No UIA event trace was captured. No signal is marked safe.

### Issue 20

One GTK3 probe wrote `scripts/repro/atspi-census-20260925.json`. Text, caret, focus, and children-changed events arrived. False negatives, web navigation, and process restart were not measured. Event absence stays always-observe. No signal is marked safe for reuse.

### Issue 21

`observation_replay.replay` never skips the recorded text-change. A synthetic step with no invalidator and a real change counts as a false reuse and `policy_killed` is true. Synthetic skips are labeled synthetic. Production skipping is off.

### Issue 23

`use_model_done_gate` is false when an independent oracle exists, which is the jev-use `/state` fixture. `accept_completion` trusts the oracle over a model that says done. A task with no oracle may use the model bit. No latency table.

### Issue 24

`task_battery.evaluate` fast-paths a single executable form candidate and does not fast-path two clicks. `promote_globally` is false for that pair. There is no interleaved runner and no wall-clock table.

### Issue 25

Uses the #5 guard. Cap 4 with a refuted first child runs one child and wastes three. `recommend_cap` tells the caller to keep the cap at 2 for that early-stop mix. Not a latency result, and 4 is not embedded.

## Pruning

### Issue 51

Owners, from the code this branch actually touched:

| Behavior | Owner |
| --- | --- |
| Optional visual capture | jev-use caller, `lazy_vision.py` |
| One executable candidate | jev-use caller, `deterministic_fast_path.py` |
| Two-action run | jev-use caller, `guarded_run.py` |
| Stale batch child | caller batch harness, `stale_batch.py`, not a new Driver tool |
| Passive versus action | caller policy, `passive_observation.py` |
| Walk time | existing `WalkBudget` |
| verify_state timing and screenshot evidence | existing `expectation.rs` |
| Window-change poll provenance | existing macOS `Changes` |
| Browser ref generation | caller rule `browser_revision.py` until the typed browser owner is named in an upstream patch |
| Cancellation order | existing request-id owner, exercised by `cancellation_lifetime.py` |

No new service is required for these rows.

### Issue 52

The mechanism table at the top is the matrix. Rows without a decision stay undecided. Do not close the experiment issues from this table.

### Issue 53

No universal shadow store was added. `shadow_probe` keeps a sample and refuses to skip. Revision facts stay on the browser ref (`browser_revision.py`) and on the AT-SPI events already recorded. A second shadow authority is not introduced.

### Issue 54

Length 4 is not a constant. See the mechanism table and `run_length.py`. Admission stays on the #5 dependency check.

### Issue 55

`PollProvenance` is an internal field on macOS `Changes`. `needs_restore` and `result_suffix` do not grow a public wording. No public settlement field is added on this branch.

### Issue 56

Observation stays on `get_window_state`, `WalkBudget`, and `verify_state`. Passive rows do not become a second tree. Conditional skip is not enabled.

### Issue 57

The caller loop is unchanged in `run.py`. Fast path, guarded run, and lazy vision are functions the runner does not call. The chooser still runs unless a later change wires one of them.

### Issue 58

Compiled expectations name `field_value_equals` and `fixture_submitted_equals`. They do not call a new verifier. The existing fixture `/state` and `verify_state` remain the checkers. One recipe does not justify a second verifier type.

### Issue 59

`stale_batch.py` revalidates identity and is not a Driver tool. `guarded_run.py` is caller policy. Mechanical batching stays on trycua/cua#2794 and #3494.

### Issue 60

Cancellation is an issuance lifetime, not a lifecycle manager. Freshness is a ref generation check. They are not composed into a new service.

### Issue 61

Delta against current CUA, not a new platform: caller functions beside jev-use, `WalkBudget` left in place, `verify_state` left in place, macOS `Changes` gained an internal poll tag, no public schema, no capture skipping, no default chooser change.

### Issue 62

Upstream order, only after the missing evidence exists:

1. trycua/cua#4164 native walker trace, then the existing verify_state owner.
2. trycua/cua#4165 live A/B, then the existing jev-use caller.
3. trycua/cua#4052 whole-task clocks, using the split in `task_accounting.py`.
4. trycua/cua#3796 cancellation slice on the existing request owner.
5. No upstream PR from this branch.

## Consolidation

### Issue 39

Fast path, guarded run, stale batch, and compiled expectations each have one caller. None is extracted into a shared helper.

### Issue 40

Python is the implementation on this branch. No TypeScript port of these functions was added, so parity is not claimed.

### Issue 41

A candidate still carries id, description, tool, arguments, and optional capture id. The fast path and guarded run read those fields. They do not add an authority token.

### Issue 42

Only the jev-use form and submit ids compile expectations. That is one recipe. No shared compiler is created.

### Issue 43

The guarded run is the verification-form pair (type, then submit). A second workflow was not implemented. Reuse is not claimed.

### Issue 44

Routing that this branch will honor: semantic executable candidate means visual capture is optional; more than one executable candidate means the chooser runs; a run requires an explicit run decision; passive rows never route to an action. Anything else stays on the current driver path.

### Issue 45

Each new function is a file under the jev-use example plus a unit test. No Driver method, schema field, or dependency was added except the internal macOS poll tag. Complexity is not traded against a measured millisecond.

### Issue 46

The chooser input is unchanged because `run.py` does not project it. Shrinking that input is not done.

### Issue 47

History length was not measured. No step was dropped from the runner.

### Issue 48

`choose_mock` remains the offline chooser. Fast path does not call Jev. Provider parity between mock, Jev, and S1 was not run.

### Issue 49

No second harness imports these functions. Cross-harness reuse is not shown.

### Issue 50

`run.py` and the canonical workflow docs were not rewritten. These files are experiment modules. They do not replace `WORKFLOW.md`.

## Promotion

### Issue 27

Do not route on an optional observation until the driver reports that it honored the selector. This branch does not negotiate a new capability.

### Issue 28

Lazy vision is a caller predicate. An older driver that lacks the visual tools already makes `optional_visual_observation` return none. No new fallback schema.

### Issue 29

No public field was added, so the contract generator does not need a promotion checklist for this branch.

### Issue 30

Guarded run and conditional skip are not on by default. Rollback is "do not call the function." Phase 2B skip is not enabled, so it has nothing to roll back.

### Issue 31

Promotion matrix for this branch: Linux unit tests only. macOS and Windows rows are empty. Local tests are not cross-platform qualification.

### Issue 32

Unsupported fast path and guarded run return none or raise. They do not report a successful slower default as if the optimization ran.

### Issue 33

`typed_choice` does not continue after refusal, skipped observation, or an unverifiable effect. `second_child_allowed` does not continue after unknown. That is the no-replay rule in unit form. No injected live failure was run.

### Issue 34

No telemetry field with window titles, tokens, or screenshots was added. `task_accounting` stores milliseconds only.

### Issue 35

No CI wall-clock gate was added.

### Issue 36

Plans carry candidate ids and a token. They do not store a process-global capture or ref. Isolation across real sessions was not executed.

### Issue 37

`optional_visual_observation` returns none when the visual tools are absent or the call raises. The semantic path does not gain authority from that failure.

### Issue 38

No public settlement or revision field is added. `PollProvenance` stays crate-internal. There is no migration to publish.

## Assimilation

### Issue 63

#4164 is not ready to leave draft. The no-elements observe call is locked. The native walker count is not.

### Issue 64

#4165 is not ready to leave draft. The skip rule is unit-tested. The outcome A/B was not run.

### Issue 65

Passive text is readable. It is not an action target. That is the compatibility rule to take back to #3904. The Calculator case is still blocked on macOS.

### Issue 66

One mechanical owner remains #2794/#3494. `stale_batch.py` is the caller-side refusal test, not a second batch tool. `guarded_run.py` stays caller-side.

### Issue 67

The #3796 handoff is the event order in `cancellation_lifetime.py`: do not release capacity before native exit, and do not apply the cancel to another issuance. No competing runtime.

### Issue 68

Browser freshness on this branch is `browser_revision.py`. It does not create a shadow snapshot store. #3873 remains the upstream snapshot owner.

### Issue 69

Phase-0 accounting on this branch is `task_accounting.py` plus the existing #4052 timing work already on `test/jev-use-phase-timing` and `test/jev-task-timing-wave2-20260925`. Those branches were not merged here. Runner lifetime is not the oracle.

### Issue 70

No policy function was added under the provider adapter. `deterministic_fast_path.py`, `guarded_run.py`, and `lazy_vision.py` sit beside the caller.

### Issue 71

No public settlement field. Internal poll provenance is enough for the macOS detector change. #4009 does not gain a field from this branch.

### Issue 72

`list_apps` was not reimplemented. Whether #3492 removes the need is not proven here.

### Issue 73

Same delta as issue 61. Disposition for each broad RFC idea on this branch: caller-local function, existing owner, or not done. No standalone target architecture was added.

### Issue 74

Same order as issue 62. Waves 9–10 do not start from this branch. The first upstream packets are still #4164 and #4165, and both still lack the evidence their own issues name.

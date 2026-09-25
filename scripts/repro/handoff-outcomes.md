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

Downstream prototype: `guarded_run.py`. Tests: `test_guarded_run.py`.

Facts allowed to survive child 1: the two candidate ids, their tools, and the token the caller already held.

Facts not allowed to survive: the Submit ref, the field value, and the capture id from before the type. The second child runs only when a fresh observation still has that token, the same Submit ref, and a capture id.

Raw fixture receipts were not produced on this Linux host. No shared helper was added. No verdict.

### Issue 6

Invariant: a preflight of snapshot S does not authorize child 2 after child 1 mutates the target child 2 was planned against. `stale_batch.run_batch` resolves child 2 again and refuses a missing target or a new identity. Regression fixture: `test_stale_batch.py`.

Freshness stays caller-managed. It is not moved into shared execution code. Latency and an independent app trace were not captured on this Linux host, so there is no turn-count claim.

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

Blocked. Missing machine: macOS.

Asked for raw AX event and capture traces, a safe/noisy/unusable table, and a recommendation on `unchanged_since`. None of that was captured. No signal is marked safe. No miss rate was invented.

### Issue 19

Blocked. Missing machine: Windows.

Asked for raw UIA event traces and a safe/noisy/unusable table. None of that was captured. No signal is marked safe. No miss rate was invented.

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

The decision table is `scripts/repro/handoff/decision-table.tsv`. Columns: evidence, missing evidence, owner, public surface cost, next action.

Rows with a test cite that test. Rows for the macOS AX census and the Windows UIA census name the missing machine. No experiment issue is closed from this table.

### Issue 53

No universal shadow store was added. `shadow_probe` keeps a sample and refuses to skip. Revision facts stay on the browser ref (`browser_revision.py`) and on the AT-SPI events already recorded. A second shadow authority is not introduced.

### Issue 54

Deleted: a shared constant of 4 actions. Evidence: `test_run_length.py`, and `recommend_cap(7, 10)` returns the cap-at-2 advice.

Local: the #5 dependency check in `guarded_run.py`.

Shared: nothing. Run length stays caller-configured.

### Issue 55

`PollProvenance` is an internal field on macOS `Changes`. `needs_restore` and `result_suffix` do not grow a public wording. No public settlement field is added on this branch.

### Issue 56

Before: `get_window_state`, `WalkBudget`, `verify_state`, and the jev-use visual path.

After: the same owners. Not added: a second tree for passive rows, a conditional-skip service, another walk budget.

Eliminated concepts: universal shadow store, capture skip from event absence, passive row as an action target.

### Issue 57

The caller loop is unchanged in `run.py`. Fast path, guarded run, and lazy vision are functions the runner does not call. The chooser still runs unless a later change wires one of them.

### Issue 58

Compiled expectations name `field_value_equals` and `fixture_submitted_equals`. They do not call a new verifier. The existing fixture `/state` and `verify_state` remain the checkers. One recipe does not justify a second verifier type.

### Issue 59

| | Driver mechanical batch | Caller guarded run |
| --- | --- | --- |
| Owner | trycua/cua#2794 and #3494 | `guarded_run.py` |
| Stale later child | `stale_batch.py` refuses a new identity | fresh observation must still match the planned Submit ref |
| Integration | the caller resolves again before dispatch | no new Driver tool |

The integration point is the caller, immediately before the second dispatch.

### Issue 60

The five sequences are in `scripts/repro/handoff/sequences.md`. Freshness is `browser_revision.bind`. Cancellation is `cancellation_lifetime.Lifetime`. Neither sequence introduces a second state owner.

### Issue 61

The downstream rewrite is `scripts/repro/handoff/rfc-3963-delta.md`. Upstream #3963 was not edited.

### Issue 62

The DAG is `scripts/repro/handoff/promotion-dag.json`. Each item has an owner, a change, a dependency, an evidence path, and a posting status. Length 4 is `KILLED` because `test_run_length.py` shows the wasted children. The other items wait on a live trial, a missing machine, or an RFC decision.

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

Blocked for the A/B receipts. Missing session: a live chooser run was not executed on this Linux host.

The projection was not added. `run.py` still sends the existing candidate list. There is no smaller chooser state to recommend from a receipt.

### Issue 47

Blocked. A per-task history-sensitivity run was not executed on this Linux host. No step was removed from the runner, and no typed-history proposal is justified.

### Issue 48

Blocked. Mock versus Jev versus local S1 was not run on this Linux host.

`choose_mock` is still the offline chooser. `deterministic_fast_path.py` does not import Jev. That is not a parity matrix.

### Issue 49

No second harness was spiked, so there is no comparison table and nothing to delete. Cross-harness reuse is not shown. The functions stay under the jev-use example.

### Issue 50

| Doc or skill | Touched by this branch | Patch needed |
| --- | --- | --- |
| `run.py` | no call to the new functions | none until one is wired |
| canonical `WORKFLOW.md` | not edited | none; these files are experiments |
| jev-use guide | not edited | none until a mechanism is promoted |

No doc change is required while the runner is unchanged.

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

Verdict: KEEP DRAFT.

SHA checked: `c5ee191c02b11448ffefcc38b78b064a87d8ef23` call site, locked by `test_verify_elapsed_order.py` (`observe(..., false, true)`).

Limitation: no native walker counter. Promotion packet status in `promotion-dag.json` is `WAITING ON DOWNSTREAM EXPERIMENT`. The upstream PR description was not updated.

### Issue 64

Verdict: KEEP DRAFT.

The skip rule is `test_lazy_vision.py`. The outcome-level A/B artifact was not produced. No helper was added. The upstream PR description was not updated.

### Issue 65

Recommendation for #3904, not an implementation PR.

Test vector: `Row("calc-result", "6", passive=True)` is readable through `verification_text` and `action_target` raises `AuthorityError`. `Row("calc-equals", "=", passive=False)` remains a target.

The native Calculator case is blocked on a macOS machine. No competing PR was opened.

### Issue 66

Canonical owner: trycua/cua#2794 and #3494 for mechanical batching.

Stale-target regression: `test_stale_batch.py` cases for disappeared target, new identity with the same label, and failed or unknown first child.

`guarded_run.py` stays caller-side. No batch API was added.

### Issue 67

Verdict: NEEDS DESIGN DECISION before an upstream slice. The downstream order test is `test_cancellation_lifetime.py`. It does not pre-decide the #3796 implementation. Slice 1, after RFC approval, belongs on the existing request-id owner. Ready when that RFC approves the slice, not before.

### Issue 68

Current-head owner for snapshot freshness remains trycua/cua#3873.

Phase-2 concepts that are unnecessary on this branch: a second snapshot authority, and a universal shadow store.

The caller rule that stays is `browser_revision.py`: same label, new generation, refuse.

### Issue 69

Measurement owner: verified-outcome milliseconds in `task_accounting.py`. Runner lifetime is a different field and `outcome_time` does not return it.

Fields: `cold_setup_ms`, `verified_outcome_ms`, `runner_lifetime_ms`, `named_span_ms`.

No double count: the reported outcome is `verified_outcome_ms` only. The #4052 branches were not merged into this one.

### Issue 70

Scope lock for #3961: NO CHANGE NEEDED on the provider adapter.

Policy files sit beside the caller: `deterministic_fast_path.py`, `guarded_run.py`, `lazy_vision.py`. None of them is imported by the provider adapter.

### Issue 71

| Consumer | Signal today | Decision |
| --- | --- | --- |
| tool suffix | `result_suffix` | existing wording |
| restore | `needs_restore` | existing boolean |
| poll split | `PollProvenance` | internal only |

Recommendation: NO PUBLIC FIELD.

### Issue 72

Blocked. An exact-head A/B of `list_apps` against #3492 was not run on this Linux host. No second cache was implemented. No recommendation is invented from an unrun trial.

### Issue 73

Committed at `scripts/repro/handoff/rfc-3963-delta.md`. Upstream #3963 was not edited.

### Issue 74

Machine-readable DAG: `scripts/repro/handoff/promotion-dag.json`.

| id | status |
| --- | --- |
| 4164 | WAITING ON DOWNSTREAM EXPERIMENT |
| 4165 | WAITING ON DOWNSTREAM EXPERIMENT |
| 4052 | WAITING ON DOWNSTREAM EXPERIMENT |
| 3796 | WAITING ON RFC DECISION |
| 3904 | WAITING ON DOWNSTREAM EXPERIMENT |
| 2794-3494 | WAITING ON DOWNSTREAM EXPERIMENT |
| run-length-4 | KILLED |

The killed row cites `test_run_length.py`. No other row is marked killed.

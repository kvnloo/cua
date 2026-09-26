# Handoff outcomes

Downstream record for the open `kvnloo/cua` GPT queue. Draft PR 26, branch `test/rfc-fast-path-one-candidate-20260925`. No issue is closed from this file. No promotion verdict is applied. A unit test is not a substitute for a missing trace.

Host: Linux. `platform-macos` was not compiled here. No Windows machine was available.

## Mechanism table

| Mechanism | Decision | Why | Evidence |
| --- | --- | --- | --- |
| Embedding guarded-run length 4 as a shared constant | BLOCKED | The unit test stops after a failed first postcondition and wastes the rest. Fixture latency was not measured, so no promotion state is applied. | `libs/cua-driver/examples/jev-use/python/tests/test_run_length.py` |
| Treating a passive observation row as an action target | BLOCKED | The unit test refuses to mint an action target. Missing machine: macOS, for the Calculator log. | `libs/cua-driver/examples/jev-use/python/tests/test_passive_observation.py` |
| Skipping a capture because a shadow probe said so | BLOCKED | The probe constructor rejects `skip_capture=True`. The false-negative census was not measured. Missing machines: macOS and Windows. | `libs/cua-driver/examples/jev-use/python/tests/test_shadow_probe.py` |

Every other mechanism in this queue stays undecided. Unit admission is not a live interleaved trial.

## Experiment issues

### Issue 2

Blocked. The block file is `scripts/repro/handoff/issue-2-block.md`.

This Linux host is present. It is not the missing machine. The pinned driver is not installed, the daemon is not running, and no Chromium or model session was run. The JSONL receipts, command log, summary table, and promotion verdict for trycua/cua#4165 were not produced and were not invented.

### Issue 3

Blocked. The block file is `scripts/repro/handoff/issue-3-block.md`.

The macOS counts are cited in `scripts/repro/handoff/issue-3-macos-trace.md` from https://github.com/trycua/cua/pull/4164#issuecomment-5840994846. Missing machine: Windows, for a UIA walker count. This Linux host still has no exact-head AT-SPI walker log. No promotion verdict is applied. The call-site lock in `test_verify_elapsed_order.py` is not that trace.

### Issue 4

Blocked. The block file is `scripts/repro/handoff/issue-4-block.md`.

This Linux host is present. It is not the missing machine. The missing prerequisite is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`, which is not an installed release. Eligibility metrics were not measured. `single_executable_candidate` is not an eligibility verdict, and the default chooser is unchanged.

### Issue 5

Architecture note: `scripts/repro/handoff/issue-5-architecture.md`.
Receipts from `admit_guarded_run` and `second_child_allowed`: `scripts/repro/handoff/issue-5-receipts.jsonl`.

`wall_time_ms` is null. A refuted first child does not dispatch the second. A single-action provider choice is not admitted. The outcome and latency comparison was not run. This Linux host is present. It is not the missing machine. The missing prerequisite is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. No shared helper.

### Issue 6

Handoff: `scripts/repro/handoff/issue-6-handoff.md`.
Receipts from `stale_batch.run_batch`: `scripts/repro/handoff/issue-6-receipts.jsonl`.

Turn count is the length of `dispatched` in `scripts/repro/handoff/issue-6-receipts.jsonl`. Unchanged identity dispatches 2. A disappeared target, a rebound identity, a failed first child, and an unknown first child each dispatch 1. `elapsed_ms` is null. Wall-clock latency was not measured. Freshness stays caller-managed. Native Windows evidence was not captured. Missing machine: Windows.

### Issue 8

Blocked. `scripts/repro/handoff/issue-8-block.md`. Missing machine: macOS. The Calculator result in trycua/cua#2958 was not driven. The downstream rule in `passive_observation.py` lets verification read a passive row and refuses to mint an action target. That is not native evidence and not a patch recommendation with a passing Calculator log.

### Issue 9

Event-order trace: `scripts/repro/handoff/issue-9-trace.json`, written by `cancellation_lifetime.trace_record`.

The events are admitted, cancellation observed, native exit, permit release, then public result. Release before native exit raises. A different issuance raises. The owner is the existing request-id owner. No competing runtime was added. Handoff: slice 1 belongs on that owner after RFC approval.

Coverage of the six barriers: `scripts/repro/handoff/issue-9-coverage.json`, from `cancellation_lifetime.coverage_report`. A cancel observed before admission does not enter native work. Release before native exit is rejected. A foreign issuance is rejected. A public result before release is rejected. Held input is not in this probe. Missing machine: macOS, for held-key and held-drag acceptance.

### Issue 10

Blocked. The block file is `scripts/repro/handoff/issue-10-block.md`.

This Linux host is present. It is not the missing machine. The missing prerequisite is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23` plus a model session. No task×arm×trial JSONL was written, and no trial time was invented. `task_accounting.outcome_time` returns verified-outcome time only.

### Issue 11

Shadow line: `scripts/repro/handoff/issue-11-shadow.jsonl`. Surface table: `scripts/repro/handoff/issue-11-surfaces.md`.

`skip_capture` is false. False retention and reconciliation cost were not measured. No capture skipping was enabled. Missing machine: macOS. Missing machine: Windows.

### Issue 12

Raw cases, each decided by `typed_choice`: `scripts/repro/handoff/issue-12-cases.jsonl`. `test_action_consumer.py` reloads that file and checks every row against `typed_choice`.

Skipped observation, unavailable observation, suspected noop, and a probe failure after dispatch are `observe`, not a replay. Refusal is `stop`. Passive success is `continue`. No public field was added for #4009. The missing native case is still the macOS Calculator trace.

### Issue 13

Blocked. The block file is `scripts/repro/handoff/issue-13-block.md`.

Missing on this Linux host: a slow native tree. The probe found no top-level windows. Missing machines for the other platforms: macOS and Windows. No latency number was invented. `WalkBudget` already starts at the first admitted node. No second budget was added.

### Issue 14

Schema note: `scripts/repro/handoff/issue-14-schema.md`.
Python: `compiled_expectations.py` and `test_compiled_expectations.py`.
TypeScript: `typescript/compiled_expectations.ts` and `typescript/compiled_expectations.test.ts`.

Both compile `field_value_equals` and `fixture_submitted_equals`. A visual submit also needs `capture_id`. `accept_if_bound` refuses a stale ref before it returns the expectation. Unknown and refuted do not start the next child. Wall time was not measured. No shared abstraction was added. Closed at https://github.com/kvnloo/cua/issues/14#issuecomment-5841888036. The comment records the compiler staying recipe-local. It does not include a wall-time comparison.

### Issue 16

Machine-readable matrix: `scripts/repro/handoff/issue-16-matrix.tsv`, from `handoff_emit.selector_report`.

Linux source has `include_accessibility_tree` and `include_screenshot`. Both disabled is rejected by `GetWindowStateInput.validate`. Linux runtime was not captured. Missing machine: macOS and Windows. The producer log the issue requires was not recorded. No selector was changed.

### Issue 17

Transition table: `scripts/repro/handoff/issue-17-transitions.json`, from `browser_revision.transition_rows`.

Same ref and generation binds. Same label with a new generation is refused, and the refusal text is the `StaleRefError` from `bind`. `test_browser_revision.py` calls `bind`. The live browser battery was not run. `scripts/repro/handoff/issue-17-not-run.json` names navigation, tab switch, frame replacement, process restart, and a live fixture state. That file is the record. The transition table is not the runtime battery.

### Issue 18

Blocked. `scripts/repro/handoff/issue-18-block.md`. Missing machine: macOS. No AX trace was captured and no miss rate was invented.

### Issue 19

Blocked. `scripts/repro/handoff/issue-19-block.md`. Missing machine: Windows. No UIA trace was captured and no miss rate was invented.

### Issue 20

Trace: `scripts/repro/atspi-census-20260925.json`.
Classification: `scripts/repro/handoff/issue-20-classification.json`.

Every recorded event is a noisy hint. `safe_for_reuse` is false because false negatives were not measured. The classification also names window lifecycle, Chromium/Electron navigation, bus reconnect, and a false-negative case as not tested. Recommendation: no Linux scope supports `unchanged_since`. macOS and Windows are not in this file.

### Issue 21

Comparison: `scripts/repro/handoff/issue-21-comparison.json`, written by `observation_replay.replay`.

The recorded GTK text-change is not skipped. A synthetic false reuse kills the policy. Production skipping is off. Break-even skips for macOS and Windows are null. Missing machines: macOS and Windows.

### Issue 23

Result table: `scripts/repro/handoff/issue-23-goals.json`, written by `goal_gates.task_rows`.

Arms A, B, and C are `arm_ordinary_completed`, `arm_factorized_completed`, and `arm_local`. The fixture `/state` row keeps the model done-gate off, and a failed oracle is not overridden. `cannot_answer` is `unknown`, which is distinct from false, and that row's action is `reobserve`. A model done with no oracle and a false ground truth records `premature_stop`. A model not-done with a true ground truth records `missed_completion`. `confidence_threshold` is null and `calibration_trials` is 0. Latency was not measured. These heads were not added to #3961.

### Issue 24

Per-task table: `scripts/repro/handoff/issue-24-battery.json`, written by `task_battery.battery_table`, which calls `run_interleaved`.

Five tasks and four arms are in the structural table. `live_success` is null and `wall_time_ms` is null. The live battery the issue requires was not run. `scripts/repro/handoff/issue-24-gap.md`. This Linux host is present. It is not the missing machine. The missing prerequisite is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

### Issue 25

Cap report: `scripts/repro/handoff/issue-25-caps.json`, written by `execute_capped` and `recommend_cap`.

A refuted first child at cap 4 runs 1 and wastes 3. Recommendation: keep the cap at 2 for that mix, and do not embed 4. `wall_time_ms` is null. Run length stays caller-configured.

## Pruning

### Issue 51

Machine-readable matrix: `scripts/repro/handoff/ownership.tsv`.

Columns: requirement, current owner, smallest delta, evidence, disposition. Each disposition is one of: already exists, extend existing owner minimally, caller/recipe-local, shared helper earned by two call sites, new public/runtime owner, delete from plan. No row uses a new public owner or a shared helper. The covered requirements include telemetry, observation projection, the fast path, compiled postconditions, guarded runs, batching, settlement provenance, passive evidence, freshness, cancellation, conditional observation, and provider adapters.

Abstractions that disappear: a universal shadow store, a second verifier, a shared postcondition compiler, a shared guarded-run type, a generic lifecycle service, and a hard-coded run length of 4.

### Issue 52

`scripts/repro/handoff/decision-table.tsv` has evidence, missing evidence, owner, public surface cost, and next action. Every decision cell is BLOCKED. The run-length, passive-row, and shadow-skip rows stay blocked because fixture latency, the macOS Calculator log, and the false-negative census were not produced. The AX and UIA rows name the missing macOS and Windows machines. No downstream issue was closed by this table. #7, #15, and #22 were already closed before this queue. #8 stays open. #25 and #11 are closed on GitHub, and their decision cells stay BLOCKED because the measurements were not produced here.

### Issue 53

`scripts/repro/handoff/issue-53-diagram.md`. Browser generation, the shadow probe, and #3873 stay separate. macOS AX and Windows UIA stay ununified because those machines were not available.

### Issue 54

`scripts/repro/handoff/issue-54-recommendation.md`.

Deleted: a shared constant of 4. Local: the per-child check in `guarded_run.py`. Shared: nothing. `recommend_cap(7, 10)` says to keep the cap at 2. A refuted first child under cap 4 runs 1 and wastes 3. Fixture latency was not measured, so #25 stays open.

### Issue 55

Closed at https://github.com/kvnloo/cua/issues/55#issuecomment-5841773898. The local graph is `scripts/repro/handoff/issue-55-consumers.md` and `scripts/repro/handoff/issue-55-edges.tsv`. The edges are `typed_choice` results. trycua/cua#3946 adds no wire marker, #3971 asks for an explicit skip and has no failing regression, and #4009 only proposes `post_dispatch_observation`. No new public field. The latest comment does not include this graph.

### Issue 56

`scripts/repro/handoff/issue-56-architecture.md`.

Before and after, modality stays on `get_window_state`, the walk stays on `WalkBudget`, passive rows stay a caller policy, snapshot identity stays `snapshot_id` / `capture_id`, hints stay on `shadow_probe.record`, and postconditions stay on `verify_state`. `elapsed_ms` is closed at `expectation.rs` line 310, before `observe` at line 329. Eliminated: ObservationService, ObservationBudgetService, RevisionService, and PassiveEvidenceService.

### Issue 57

`scripts/repro/handoff/issue-57-dataflow.md`. `run.py` still calls the chooser. The new functions are not on that path. No reusable helper is extracted.

### Issue 58

`scripts/repro/handoff/issue-58-routing.md`. Expectations route to the fixture field or `/state`. A second verifier type is not added.

### Issue 59

`scripts/repro/handoff/issue-59-contract.md`.

Mechanical batching stays with trycua/cua#2794 and #3494. The caller guarded run stays in `guarded_run.py`. The integration point is the caller, immediately before the second dispatch. `run_batch` can dispatch `field` and `submit` on unchanged identities without reading the field token. `second_child_allowed` does not claim a transport saving. No competing batch API.

### Issue 60

Closed at https://github.com/kvnloo/cua/issues/60#issuecomment-5841775336. The five sequences are in `scripts/repro/handoff/sequences.md`: fresh guarded child, stale refusal, cancel while queued, cancel after native admission, and session end during admitted work. A changed submit ref makes `second_child_allowed` return false, so the submit is not dispatched. Freshness is `browser_revision.bind`. Cancellation is `cancellation_lifetime.Lifetime`. Authorization stays on the existing session policy. There is no ExecutionContext and no LifecycleService. The latest comment does not include these sequences.

### Issue 61

The downstream rewrite is `scripts/repro/handoff/rfc-3963-delta.md`. It has the north-star, the invariants, the current owners, the remaining deltas, the phase gates, the deleted abstractions, the dependency graph, and the migration plan. Upstream #3963 was not edited.

### Issue 62

The DAG is `scripts/repro/handoff/promotion-dag.json`. Each item has an owner, a change, a dependency, evidence already complete, evidence still missing, an action, a stop condition, and a posting status. Length 4 waits on the fixture-latency trial. The elapsed-ms order comment is the only `READY NOW` item, and it claims no speedup. The other items wait on a live trial, a missing machine, or an RFC decision. No new upstream pull request.

## Consolidation

### Issue 39

`scripts/repro/handoff/issue-39-report.md` and `scripts/repro/handoff/issue-39-inventory.json`. `extraction_inventory.inventory` finds no production call site outside the jev-use example. Every row stays recipe-local. No refactor was performed.

### Issue 40

Shared fixture: `scripts/repro/handoff/issue-40-fixture.json`.
Semantic corpus: `scripts/repro/handoff/issue-40-semantic.json`, from `semantic_parity.parity_corpus`.
Python runner: `test_compiled_expectations.py`.
TypeScript runner: `typescript/compiled_expectations.test.ts` and `typescript/semantic_parity.ts`.

The test runs the Python corpus and the TypeScript corpus and requires the same fast-path id, run admission, second dispatch, and expectation kind. One executable candidate is admitted by the rule even when the decision is reobserve. A reserved-only table is not. A verified fresh run dispatches the second child. Stale, rebound, missing capture, refuted, and unknown do not.

### Issue 41

`scripts/repro/handoff/issue-41-schema.md`. The candidate envelope is unchanged. No authority token and no public Driver API were added.

### Issue 42

`scripts/repro/handoff/issue-42-overlap.md`. The form compiler and `toggle_expectations.py` do not import each other. Their predicates differ. No shared compiler was extracted.

### Issue 43

`scripts/repro/handoff/issue-43-graph.md`. `guarded_run.py` and `toggle_run.py` do not import each other. The form oracle is a submit ref. The toggle oracle is a boolean. No shared primitive was added.

### Issue 44

Routing table: `scripts/repro/handoff/issue-44-routing.json`, written by `caller_route.route`.
Tests: `test_caller_route.py`.

`run.py` does not call `route`. The table is not fed into the runner, because the live verdicts it depends on are still missing.

### Issue 45

`scripts/repro/handoff/issue-45-ledger.tsv`, written by `cost_ledger.ledger_tsv`. Each candidate mechanism names an evidence file. Public fields added are 0. Conditional observation and shared helper extraction are `not added`. Milliseconds, model calls, and observation calls removed are `not measured`. The class for an existing owner with no public surface is free consolidation. No vanity score was invented.

### Issue 46

Open. https://github.com/kvnloo/cua/issues/46#issuecomment-5841889526 does not include A/B receipts. `scripts/repro/handoff/issue-46-projection.json`, from `chooser_projection.projection_report`, keeps `id` and `description` and rejects tool arguments. Receipts were not produced. The missing prerequisite is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. Recommendation: the smallest safe chooser state is id and description.

### Issue 47

Open. https://github.com/kvnloo/cua/issues/47#issuecomment-5841889690 does not include a sensitivity table. `scripts/repro/handoff/issue-47-history.json`, from `chooser_projection.history_report`, keeps `selected_id` and `outcome`. An extra field is rejected. Measured success is null, so no shorter history is proposed. The missing prerequisite for a live battery is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

### Issue 48

Open. https://github.com/kvnloo/cua/issues/48#issuecomment-5841889913 does not include a Jev or S1 run. `scripts/repro/handoff/issue-48-parity.json`, from `provider_parity.parity_report`. The mock row calls `choose_mock` and `validate_choice`. A malformed id is rejected. Jev and S1 were not run. Recommendation: provider-specific policy stays in the adapter.

### Issue 49

`scripts/repro/handoff/issue-49-spike.md` and `scripts/repro/handoff/issue-49-comparison.json`. The five concepts call the shipped functions. The second harness was not added. Every row records that transfer as deleted. No TypeSafe or Jev import was added.

### Issue 50

`scripts/repro/handoff/issue-50-docs.md` and `scripts/repro/handoff/issue-50-matrix.tsv`. The matrix cites `WORKFLOW.md`, the Linux, macOS, and Windows skills, the jev-use README, `action-result-contract.md`, `perception-extension.md`, and RFC 3931. Each cited quote is on the named line. No promotion state is recorded, so the patch plan is to leave those files unedited. Lines that must not be weakened include tree-only observation, unknown-is-not-success, and one capture per action.

## Promotion

### Issue 27

Compatibility matrix: `scripts/repro/handoff/issue-27-matrix.tsv`, written by `compatibility_matrix.matrix_tsv`. The probe is `scripts/repro/handoff/issue-27-probe.py`.

The rule is schema/property preflight. `include_accessibility_tree` is on the contract input and the Linux implementation, and it is absent from the Linux stub schema. `include_screenshot` is on `get_window_state` and `verify_state`. `post_dispatch_observation` is absent from the contract crate. Fast path and guarded run are caller predicates, not contract fields. Conditional skip is not enabled. Live `tools/list` was not captured. No second capability registry was added.

### Issue 28

`scripts/repro/handoff/issue-28-note.md` and `scripts/repro/handoff/issue-28-decisions.json`. The rows call `optional_visual_observation` on a fake session. Recommendation: no new caller helper and no new public Driver API. This Linux host is present. The live current-versus-old driver session was not run.

### Issue 29

`scripts/repro/handoff/issue-29-checklist.md`. No public field was added, so the example diff was not kept.

### Issue 30

`scripts/repro/handoff/issue-30-transitions.md`. The off state is `run.py` not calling the functions. No config framework was added.

### Issue 31

`scripts/repro/handoff/issue-31-manifest.json`, from `promotion_qualification.qualification_rows`. Every row sets `historical_green_certifies` to false. macOS and Windows rows name those machines. The guarded-run row records that wall time was not measured.

### Issue 32

`scripts/repro/handoff/issue-32-negative.md`. Unsupported inputs return none or raise. They do not pretend the optimization succeeded.

### Issue 33

Dispatch counts: `scripts/repro/handoff/issue-33-dispatch.json`, written by `second_child_allowed`.

Verified is the only status in that file with a second dispatch. Refuted, unknown, stale, rebound, and refused stay at one dispatch. `fixture_submitted` is the retained app-state oracle, and `second_child_allowed` does not read it. The unknown row reaches `submitted` and still does not dispatch the second child. Injection rows: `scripts/repro/handoff/issue-33-injections.json`, from `typed_choice` and `second_child_allowed`. A lost response can still show the fixture submitted, and the replay dispatch stays 0. A live application process was not attached.

### Issue 34

`scripts/repro/handoff/issue-34-privacy.md`. `project_event` keeps the four integer clocks and drops `SECRET-MARKER` text. `run.py` still writes the fixture token and was not changed.

### Issue 35

`scripts/repro/handoff/issue-35-budget.md`. Structural counters are the hard CI layer. Milliseconds stay an evidence artifact. This Linux host is present. The pinned driver session for native benchmarks was not run. No CI workflow file was added.

### Issue 36

`scripts/repro/handoff/issue-36-isolation.md` and `scripts/repro/handoff/issue-36-sessions.json`, from `handoff_emit.session_isolation`. `finish` rejects a different issuance. A browser ref from the other session is refused by `bind`, and that session's own ref still binds. A borrowed token does not authorize the other plan. Concurrent processes were not executed on this Linux host.

### Issue 37

`scripts/repro/handoff/issue-37-fallback.md`. A missing visual result does not become permission to act on a visual target.

### Issue 38

`scripts/repro/handoff/issue-38-migration.md`, `scripts/repro/handoff/issue-38-matrix.tsv`, and `scripts/repro/handoff/issue-38-commands.json`. The selected shape on this checkout is no field added. `command_report` finds no `post_dispatch_observation` symbol, so no implementation SHA was selected and the generator check was not run. That command file is not the implementation-SHA audit the issue requires. `deny_unknown_fields` is on the window and verify inputs. Consumer trials were not run. `PollProvenance` stays internal.

## Assimilation

### Issue 63

`scripts/repro/handoff/issue-63-packet.md`.

Open and blocked. The measurement comment is https://github.com/kvnloo/cua/issues/63#issuecomment-5841776432: head `fb7841be7c9d2ef666a5dd87be6ca78e2de5d254`, element plus screenshot 2 AX walks to 1, window-only plus screenshot 1 to 0, control stayed 1 to 1, screenshot 460×816. This host did not run that walk. The local packet is `scripts/repro/handoff/issue-63-packet.md`. Missing machine: Windows, for a UIA count. `expectation.rs` line 310 closes `elapsed_ms` before `observe(pid, window_id, false, true)` at line 329.

### Issue 64

Open and blocked. https://github.com/kvnloo/cua/issues/64#issuecomment-5841890244 does not contain the pinned-commit desktop A/B. `scripts/repro/handoff/issue-64-block.md` cites the fake-driver report at `147158cf9caed69489607f7e6736dc9282bdd815`, which uses head `24aaf8d1965b3b7c1530cbb9d58758ec89472d92` and is not pinned commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. This Linux host is present. It is not the missing machine. No helper was added on this branch. No verdict was issued.

### Issue 65

`scripts/repro/handoff/issue-65-3904.md`. `test_passive_vectors_match_the_3904_comment` calls `verification_text` and `action_target`.

Vector 1: `verification_text` on `calc-result` returns `6`, and `action_target` on that passive row raises. Vector 2: `action_target` on `calc-equals` returns that id. No competing pull request. The file was not sent to trycua/cua#3904. The Calculator accessibility log was not captured. Missing machine: macOS.

### Issue 66

Closed at https://github.com/kvnloo/cua/issues/66#issuecomment-5841778555. `scripts/repro/handoff/issue-66-comment.md` is the stale-target fixture design. The consolidation note is https://github.com/trycua/cua/issues/3494#issuecomment-5841211600. The latest issue comment names the owner and does not include this fixture.

Canonical owner: trycua/cua#2794 and #3494. The regression fixture is `test_stale_batch.py`: unchanged identity dispatches both children, a disappeared target and a new identity are refused, and a failed or unknown first child does not start the second. `elapsed_ms` is null. No batch API was added.

### Issue 67

`scripts/repro/handoff/issue-67-plan.md`.

Verdict: NEEDS DESIGN DECISION. The seam is the existing request-id owner. `Lifetime` covers cancel-while-queued, cancel-after-admission, capacity until exit, and a foreign issuance. Held keys, pointer cleanup, late cancel, and request-id reuse before dispatch are not in that probe. READY WHEN RFC APPROVES the slice. Not before. No scheduler was added.

### Issue 68

`scripts/repro/handoff/issue-68-map.md`.

trycua/cua#3873 was fetched open on 2026-09-25. Its body describes a snapshot store invalidated on read and does not mention a quota. This branch did not merge it. On the pin, `snapshot_id` and `capture_id` stay distinct, and a later snapshot invalidates a pending token. Unnecessary here: a second snapshot authority, a universal shadow store, and RevisionService.

### Issue 69

Closed at https://github.com/kvnloo/cua/issues/69#issuecomment-5841779599. `scripts/repro/handoff/issue-69-measurement.md` has the decision, the four clock fields, and the no-double-counting diagram. The latest comment names the fields and does not include that diagram. Do not add the report to #4052. `outcome_time` returns `verified_outcome_ms` only. The whole-task battery stays open on issue 10. No trial time was invented.

### Issue 70

`scripts/repro/handoff/issue-70-scope.md`.

NO CHANGE NEEDED on the #3961 provider adapter. `jev_adapter.py` does not import `deterministic_fast_path`, `guarded_run`, `lazy_vision`, or `goal_gates`. `run.py` does not import them either. No code was added.

### Issue 71

Closed at https://github.com/kvnloo/cua/issues/71#issuecomment-5841780594. That comment names `post_dispatch_observation: completed | skipped | unavailable`. `scripts/repro/handoff/issue-71-decision.md` records the comment and the local search: the symbol is absent from this checkout's contract crate. `typed_choice` still returns continue, observe, or stop. `PollProvenance` stays internal and was not compiled on this Linux host.

### Issue 72

Blocked. `scripts/repro/handoff/issue-72-block.md`. This Linux host is present. It is not the missing machine. The missing prerequisite is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. No second cache was implemented. No recommendation was invented.

### Issue 73

Committed at `scripts/repro/handoff/rfc-3963-delta.md`. The draft has the north-star, a disposition table, the remaining deltas, the deleted architecture, and the phase gates. Upstream #3963 was not edited. The #3873 body fetched on 2026-09-25 does not state a quota. `elapsed_ms` stays verification-loop time. Phase 2B has no safe skip evidence.

### Issue 74

Machine-readable DAG: `scripts/repro/handoff/promotion-dag.json`. Human queue: `scripts/repro/handoff/issue-74-queue.md`. Nothing was posted upstream.

| id | status | action |
| --- | --- | --- |
| elapsed-ms-boundary | READY NOW | comment, not posted, no speedup claim |
| run-length-4 | WAITING ON DOWNSTREAM EXPERIMENT | no action |
| 3961-scope | ASSIMILATED | no action, NO CHANGE NEEDED |
| 4009-public-field | ASSIMILATED | no action; the proposal names the field and this checkout does not contain the symbol |
| 4052 | WAITING ON DOWNSTREAM EXPERIMENT | no action |
| 4164 | WAITING ON DOWNSTREAM EXPERIMENT | cited macOS walk counts, description not updated |
| 4165 | WAITING ON DOWNSTREAM EXPERIMENT | not sent |
| 3904 | WAITING ON DOWNSTREAM EXPERIMENT | missing machine: macOS |
| 2794-3494 | WAITING ON DOWNSTREAM EXPERIMENT | elapsed_ms is null |
| 3796 | WAITING ON RFC DECISION | not sent |

The length-4 row waits on fixture latency and cites `test_run_length.py` only for the wasted-child count. No new upstream pull request. Draft pull request 26 was not merged.

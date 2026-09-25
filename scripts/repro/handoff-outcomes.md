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

Missing on this Linux host: an exact-head Driver, a Chromium fixture, and a model run. `linux-host-probe.txt` shows `cua-driver 0.28.2`, no daemon, and no top-level windows. The JSONL receipts, command log, summary table, and promotion verdict for trycua/cua#4165 were not produced and were not invented.

### Issue 3

Blocked. The block file is `scripts/repro/handoff/issue-3-block.md`.

The macOS counts are cited in `scripts/repro/handoff/issue-3-macos-trace.md` from https://github.com/trycua/cua/pull/4164#issuecomment-5840994846. Missing machine: Windows, for a UIA walker count. This Linux host still has no exact-head AT-SPI walker log. No promotion verdict is applied. The call-site lock in `test_verify_elapsed_order.py` is not that trace.

### Issue 4

Blocked. The block file is `scripts/repro/handoff/issue-4-block.md`.

Missing on this Linux host: an exact-head interleaved fixture trial. Installed driver `cua-driver 0.28.2` is not pinned head `c5ee191c02b11448ffefcc38b78b064a87d8ef23`, and no daemon is running. Eligibility metrics were not measured. `single_executable_candidate` is not an eligibility verdict, and the default chooser is unchanged.

### Issue 5

Architecture note: `scripts/repro/handoff/issue-5-architecture.md`.
Receipts from `admit_guarded_run` and `second_child_allowed`: `scripts/repro/handoff/issue-5-receipts.jsonl`.

`wall_time_ms` is null. A refuted first child does not dispatch the second. A single-action provider choice is not admitted. No shared helper.

### Issue 6

Handoff: `scripts/repro/handoff/issue-6-handoff.md`.
Receipts from `stale_batch.run_batch`: `scripts/repro/handoff/issue-6-receipts.jsonl`.

`elapsed_ms` is null. A disappeared target and a rebound identity are refused. Freshness stays caller-managed.

### Issue 8

Blocked. `scripts/repro/handoff/issue-8-block.md`. Missing machine: macOS. The Calculator result in trycua/cua#2958 was not driven. The downstream rule in `passive_observation.py` lets verification read a passive row and refuses to mint an action target. That is not native evidence and not a patch recommendation with a passing Calculator log.

### Issue 9

`cancellation_lifetime.Lifetime` records admitted, cancellation observed, native exit, permit release, then public result. Release before native exit raises. A different issuance raises. This is the order #3796 asked to see. It is not a trace from the existing core owner, and no competing runtime was added. Handoff: slice 1 belongs on the existing request-id owner after RFC approval, not on a new service.

### Issue 10

Blocked. The block file is `scripts/repro/handoff/issue-10-block.md`.

Missing on this Linux host: the 4-arm benchmark on an exact-head driver. Installed binary `cua-driver 0.28.2`, daemon not running, no top-level windows. No task×arm×trial JSONL was written, and no trial time was invented. `task_accounting.outcome_time` returns verified-outcome time only.

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

Both compile `field_value_equals` and `fixture_submitted_equals`. A visual submit also needs `capture_id`. `accept_if_bound` refuses a stale ref before it returns the expectation. Unknown and refuted do not start the next child. Wall time was not measured. Missing machine: this Linux host. No shared abstraction was added.

### Issue 16

Machine-readable matrix: `scripts/repro/handoff/issue-16-matrix.tsv`.

Linux source names `include_accessibility_tree` and `include_screenshot`. Runtime on macOS was not measured. Missing machine: macOS. Runtime on Windows was not measured. Missing machine: Windows. Recommendation: fail closed and do not advertise the selectors as equivalent. No selector was changed.

### Issue 17

Transition table: `scripts/repro/handoff/issue-17-transitions.json`.

Same ref and generation binds. Same label with a new generation is refused. `test_browser_revision.py` is the fixture. This table is what issue 11 has to respect. It is not a CDP log.

### Issue 18

Blocked. `scripts/repro/handoff/issue-18-block.md`. Missing machine: macOS. No AX trace was captured and no miss rate was invented.

### Issue 19

Blocked. `scripts/repro/handoff/issue-19-block.md`. Missing machine: Windows. No UIA trace was captured and no miss rate was invented.

### Issue 20

Trace: `scripts/repro/atspi-census-20260925.json`.
Classification: `scripts/repro/handoff/issue-20-classification.json`.

Every recorded event is a noisy hint. `safe_for_reuse` is false because false negatives were not measured. Recommendation: no Linux scope supports `unchanged_since`. macOS and Windows are not in this file.

### Issue 21

Comparison: `scripts/repro/handoff/issue-21-comparison.json`, written by `observation_replay.replay`.

The recorded GTK text-change is not skipped. A synthetic false reuse kills the policy. Production skipping is off. Break-even skips for macOS and Windows are null. Missing machines: macOS and Windows.

### Issue 23

Result table: `scripts/repro/handoff/issue-23-goals.json`, written by `use_model_done_gate` and `accept_completion`.

The jev-use fixture keeps its `/state` oracle, so the model done-gate stays off. A model that says done does not override a failed oracle. No latency was measured. These heads were not added to #3961.

### Issue 24

Per-task table: `scripts/repro/handoff/issue-24-battery.json`, written by `task_battery.evaluate`.

Form-fill takes the fast path. The ambiguous modal does not. `promote_globally` is false. `wall_time_ms` is null because no interleaved live runner was executed on this Linux host.

### Issue 25

Cap report: `scripts/repro/handoff/issue-25-caps.json`, written by `execute_capped` and `recommend_cap`.

A refuted first child at cap 4 runs 1 and wastes 3. Recommendation: keep the cap at 2 for that mix, and do not embed 4. `wall_time_ms` is null. Run length stays caller-configured.

## Pruning

### Issue 51

Machine-readable matrix: `scripts/repro/handoff/ownership.tsv`.

Columns: requirement, current owner, smallest delta, evidence, disposition. Each disposition is one of: already exists, extend existing owner minimally, caller/recipe-local, shared helper earned by two call sites, new public/runtime owner, delete from plan. No row uses a new public owner or a shared helper. The covered requirements include telemetry, observation projection, the fast path, compiled postconditions, guarded runs, batching, settlement provenance, passive evidence, freshness, cancellation, conditional observation, and provider adapters.

Abstractions that disappear: a universal shadow store, a second verifier, a shared postcondition compiler, a shared guarded-run type, a generic lifecycle service, and a hard-coded run length of 4.

### Issue 52

`scripts/repro/handoff/decision-table.tsv` has evidence, missing evidence, owner, public surface cost, and next action. Every decision cell is BLOCKED. The run-length, passive-row, and shadow-skip rows stay blocked because fixture latency, the macOS Calculator log, and the false-negative census were not produced. The AX and UIA rows name the missing macOS and Windows machines. No downstream issue was closed. #7, #15, and #22 were already closed before this queue. #25, #8, and #11 stay open.

### Issue 53

`scripts/repro/handoff/issue-53-diagram.md`. Browser generation, the shadow probe, and #3873 stay separate. macOS AX and Windows UIA stay ununified because those machines were not available.

### Issue 54

`scripts/repro/handoff/issue-54-recommendation.md`.

Deleted: a shared constant of 4. Local: the per-child check in `guarded_run.py`. Shared: nothing. `recommend_cap(7, 10)` says to keep the cap at 2. A refuted first child under cap 4 runs 1 and wastes 3. Fixture latency was not measured, so #25 stays open.

### Issue 55

`scripts/repro/handoff/issue-55-consumers.md` and `scripts/repro/handoff/issue-55-edges.tsv`. The edges are `typed_choice` results. trycua/cua#3946 adds no wire marker, #3971 asks for an explicit skip and has no failing regression, and #4009 only proposes `post_dispatch_observation`. No new public field. The issue stays open.

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

The five sequences are in `scripts/repro/handoff/sequences.md`: fresh guarded child, stale refusal, cancel while queued, cancel after native admission, and session end during admitted work. Freshness is `browser_revision.bind`. Cancellation is `cancellation_lifetime.Lifetime`. Authorization stays on the existing session policy. There is no ExecutionContext and no LifecycleService.

### Issue 61

The downstream rewrite is `scripts/repro/handoff/rfc-3963-delta.md`. It has the north-star, the invariants, the current owners, the remaining deltas, the phase gates, the deleted abstractions, the dependency graph, and the migration plan. Upstream #3963 was not edited.

### Issue 62

The DAG is `scripts/repro/handoff/promotion-dag.json`. Each item has an owner, a change, a dependency, evidence already complete, evidence still missing, an action, a stop condition, and a posting status. Length 4 waits on the fixture-latency trial. The elapsed-ms order comment is the only `READY NOW` item, and it claims no speedup. The other items wait on a live trial, a missing machine, or an RFC decision. No new upstream pull request.

## Consolidation

### Issue 39

`scripts/repro/handoff/issue-39-report.md` and `scripts/repro/handoff/issue-39-inventory.json`. `extraction_inventory.inventory` finds no production call site outside the jev-use example. Every row stays recipe-local. No refactor was performed.

### Issue 40

Shared fixture: `scripts/repro/handoff/issue-40-fixture.json`.
Python runner: `test_compiled_expectations.py`.
TypeScript runner: `typescript/compiled_expectations.test.ts`.

Both read that fixture. Parity is claimed only for compiled expectations. The other helpers were not mirrored.

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

`scripts/repro/handoff/issue-45-ledger.tsv`. Milliseconds removed are `not measured` on every row.

### Issue 46

Blocked. `scripts/repro/handoff/issue-46-block.md`. Missing session on this Linux host: a live chooser A/B. No receipt was invented.

### Issue 47

Blocked. `scripts/repro/handoff/issue-47-block.md`. Missing session on this Linux host: a per-task history-sensitivity run.

### Issue 48

Blocked. `scripts/repro/handoff/issue-48-block.md`. Missing providers on this Linux host: a live Jev session and a local S1 session.

### Issue 49

`scripts/repro/handoff/issue-49-spike.md`. No second harness was written. Nothing was deleted.

### Issue 50

`scripts/repro/handoff/issue-50-docs.md` and `scripts/repro/handoff/issue-50-matrix.tsv`. The matrix cites `WORKFLOW.md`, the Linux, macOS, and Windows skills, the jev-use README, `action-result-contract.md`, `perception-extension.md`, and RFC 3931. Each cited quote is on the named line. No promotion state is recorded, so the patch plan is to leave those files unedited. Lines that must not be weakened include tree-only observation, unknown-is-not-success, and one capture per action.

## Promotion

### Issue 27

Compatibility matrix: `scripts/repro/handoff/issue-27-matrix.tsv`. No existing contract field gates these optimizations. No new capability field was added.

### Issue 28

`scripts/repro/handoff/issue-28-note.md`. Tests are `test_lazy_vision.py`. Recommendation: no new caller helper and no new public Driver API.

### Issue 29

`scripts/repro/handoff/issue-29-checklist.md`. No public field was added, so the example diff was not kept.

### Issue 30

`scripts/repro/handoff/issue-30-transitions.md`. The off state is `run.py` not calling the functions. No config framework was added.

### Issue 31

`scripts/repro/handoff/issue-31-manifest.json`. Every row sets `historical_green_certifies` to false. macOS and Windows rows name those machines.

### Issue 32

`scripts/repro/handoff/issue-32-negative.md`. Unsupported inputs return none or raise. They do not pretend the optimization succeeded.

### Issue 33

Dispatch counts: `scripts/repro/handoff/issue-33-dispatch.json`, written by `second_child_allowed`.

Verified is the only status in that file with a second dispatch. Refuted, unknown, stale, rebound, and refused stay at one dispatch. An independent app-state oracle was not attached on this Linux host. The recommendation is the typed rule already in `action_consumer.py`: do not replay after unknown.

### Issue 34

`scripts/repro/handoff/issue-34-privacy.md`. `TrialClocks` stores four integer millisecond fields and no window title, token, or screenshot.

### Issue 35

`scripts/repro/handoff/issue-35-budget.md`. No CI wall-clock gate was added. A green unit run does not certify a latency change.

### Issue 36

`scripts/repro/handoff/issue-36-isolation.md`. `finish` rejects a different issuance. Real concurrent sessions were not executed on this Linux host.

### Issue 37

`scripts/repro/handoff/issue-37-fallback.md`. A missing visual result does not become permission to act on a visual target.

### Issue 38

`scripts/repro/handoff/issue-38-migration.md`. No production field was added. `PollProvenance` stays internal.

## Assimilation

### Issue 63

`scripts/repro/handoff/issue-63-packet.md`.

Verdict withheld. Upstream pin `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. Fork evidence `92b5035ea08b2126f947db0dfd8ecf829013d7b4`. `expectation.rs` line 310 closes `elapsed_ms` before `observe(pid, window_id, false, true)` at line 329. Trace: none. Missing machines: macOS and Windows. This Linux host has no exact-head walker log: `linux-host-probe.txt` shows `cua-driver 0.28.2`, no daemon, and no top-level windows. The upstream pull request description was not changed.

### Issue 64

Blocked. `scripts/repro/handoff/issue-64-block.md`. Missing on this Linux host: an exact-head driver session for the trycua/cua#4165 outcome A/B. `linux-host-probe.txt` shows installed `cua-driver 0.28.2`, no daemon, and no top-level windows. The pinned head is `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. No helper was added. No verdict was issued.

### Issue 65

`scripts/repro/handoff/issue-65-3904.md`.

Prepared comment, not posted. No competing pull request. `verification_text` on `calc-result` returns `6` and `action_target` raises. `action_target` on `calc-equals` returns that id. The Calculator log is blocked. Missing machine: macOS.

### Issue 66

`scripts/repro/handoff/issue-66-comment.md`.

Prepared comment, not posted. Canonical owner: trycua/cua#2794 and #3494. The regression fixture is `test_stale_batch.py`: unchanged identity dispatches both children, a disappeared target and a new identity are refused, and a failed or unknown first child does not start the second. `elapsed_ms` is null. No batch API was added.

### Issue 67

`scripts/repro/handoff/issue-67-plan.md`.

Verdict: NEEDS DESIGN DECISION. The seam is the existing request-id owner. `Lifetime` covers cancel-while-queued, cancel-after-admission, capacity until exit, and a foreign issuance. Held keys, pointer cleanup, late cancel, and request-id reuse before dispatch are not in that probe. READY WHEN RFC APPROVES the slice. Not before. No scheduler was added.

### Issue 68

`scripts/repro/handoff/issue-68-map.md`.

trycua/cua#3873 was fetched open on 2026-09-25. Its body describes a snapshot store invalidated on read and does not mention a quota. This branch did not merge it. On the pin, `snapshot_id` and `capture_id` stay distinct, and a later snapshot invalidates a pending token. Unnecessary here: a second snapshot authority, a universal shadow store, and RevisionService.

### Issue 69

`scripts/repro/handoff/issue-69-measurement.md`.

Decision: downstream benchmark-only tooling. Do not add the report to #4052. Fields: `cold_setup_ms`, `verified_outcome_ms`, `runner_lifetime_ms`, `named_span_ms`. `outcome_time` returns `verified_outcome_ms` only. The >90% battery was not run. No trial time was invented.

### Issue 70

`scripts/repro/handoff/issue-70-scope.md`.

NO CHANGE NEEDED on the #3961 provider adapter. `jev_adapter.py` does not import `deterministic_fast_path`, `guarded_run`, `lazy_vision`, or `goal_gates`. `run.py` does not import them either. No code was added.

### Issue 71

`scripts/repro/handoff/issue-71-decision.md`.

Recommendation: NO PUBLIC FIELD. `typed_choice` already returns continue, observe, or stop. Escalation stays advice in `WORKFLOW.md` line 121. `result_suffix` and `needs_restore` stay the existing signals. `PollProvenance` stays internal and was not compiled on this Linux host. No promotion dependency.

### Issue 72

Blocked. `scripts/repro/handoff/issue-72-block.md`. Missing on this Linux host: an exact-head `list_apps` A/B against trycua/cua#3492. The installed binary is `cua-driver 0.28.2` and the daemon is not running. No second cache was implemented.

### Issue 73

Committed at `scripts/repro/handoff/rfc-3963-delta.md`. The draft has the north-star, a disposition table, the remaining deltas, the deleted architecture, and the phase gates. Upstream #3963 was not edited. The #3873 body fetched on 2026-09-25 does not state a quota. `elapsed_ms` stays verification-loop time. Phase 2B has no safe skip evidence.

### Issue 74

Machine-readable DAG: `scripts/repro/handoff/promotion-dag.json`. Human queue: `scripts/repro/handoff/issue-74-queue.md`. Nothing was posted upstream.

| id | status | action |
| --- | --- | --- |
| elapsed-ms-boundary | READY NOW | comment, not posted, no speedup claim |
| run-length-4 | WAITING ON DOWNSTREAM EXPERIMENT | no action |
| 3961-scope | ASSIMILATED | no action, NO CHANGE NEEDED |
| 4009-public-field | ASSIMILATED | no action, NO PUBLIC FIELD |
| 4052 | WAITING ON DOWNSTREAM EXPERIMENT | no action |
| 4164 | WAITING ON DOWNSTREAM EXPERIMENT | verdict withheld, description not updated |
| 4165 | WAITING ON DOWNSTREAM EXPERIMENT | not sent |
| 3904 | WAITING ON DOWNSTREAM EXPERIMENT | missing machine: macOS |
| 2794-3494 | WAITING ON DOWNSTREAM EXPERIMENT | elapsed_ms is null |
| 3796 | WAITING ON RFC DECISION | not sent |

The length-4 row waits on fixture latency and cites `test_run_length.py` only for the wasted-child count. No new upstream pull request. Draft pull request 26 was not merged.

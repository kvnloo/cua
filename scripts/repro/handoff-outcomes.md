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

Blocked. The block file is `scripts/repro/handoff/issue-2-block.md`.

Missing session on this Linux host: a live Driver, Chromium fixture, and model run. The JSONL receipts, command log, summary table, and verdict for trycua/cua#4165 were not produced and were not invented.

### Issue 3

Blocked. The block file is `scripts/repro/handoff/issue-3-block.md`.

Missing trace on this Linux host: an accessibility walker count. The six predicate cases were not traced. The call-site lock in `test_verify_elapsed_order.py` is not that trace and is not a verdict.

### Issue 4

Blocked. The block file is `scripts/repro/handoff/issue-4-block.md`.

Missing session on this Linux host: a live interleaved fixture trial. Eligibility metrics were not measured. `single_executable_candidate` is not an eligibility verdict, and the default chooser is unchanged.

### Issue 5

Architecture note: `scripts/repro/handoff/issue-5-architecture.md`.

Prototype `guarded_run.py`. Tests `test_guarded_run.py`. Facts that survive child 1 are the run decision, the two ids and tools, and the token already held. The pre-type field value, capture id, and a Submit ref the fresh observation no longer shows do not survive.

Raw fixture receipts were not produced on this Linux host. No verdict. No shared helper.

### Issue 6

Handoff: `scripts/repro/handoff/issue-6-handoff.md`.

Invariant: preflight does not authorize child 2. Regression fixture: `test_stale_batch.py`. Latency and an independent app trace were not captured on this Linux host. Recommendation: freshness stays caller-managed.

### Issue 8

Blocked on a macOS machine. The Calculator result in trycua/cua#2958 was not driven. The downstream rule in `passive_observation.py` lets verification read a passive row and refuses to mint an action target. That is not native evidence and not a patch recommendation with a passing Calculator log.

### Issue 9

`cancellation_lifetime.Lifetime` records admitted, cancellation observed, native exit, permit release, then public result. Release before native exit raises. A different issuance raises. This is the order #3796 asked to see. It is not a trace from the existing core owner, and no competing runtime was added. Handoff: slice 1 belongs on the existing request-id owner after RFC approval, not on a new service.

### Issue 10

Blocked. The block file is `scripts/repro/handoff/issue-10-block.md`.

Missing session on this Linux host: the 4-arm benchmark. No task×arm×trial JSONL was written, and no trial time was invented. `task_accounting.outcome_time` returns verified-outcome time only.

### Issue 11

Shadow line, produced by `shadow_probe.record` from the GTK census: `scripts/repro/handoff/issue-11-shadow.jsonl`.

`skip_capture` is false. `false_retention_observed` and `reconciliation_cost_ms` are null because this host did not measure them. No capture skipping was enabled. Phase 2A is not accepted.

### Issue 12

Raw cases, each decided by `typed_choice`: `scripts/repro/handoff/issue-12-cases.jsonl`. `test_action_consumer.py` reloads that file and checks every row against `typed_choice`.

Skipped observation, unavailable observation, suspected noop, and a probe failure after dispatch are `observe`, not a replay. Refusal is `stop`. Passive success is `continue`. No public field was added for #4009. The missing native case is still the macOS Calculator trace.

### Issue 13

Blocked. The block file is `scripts/repro/handoff/issue-13-block.md`.

Missing workload on this Linux host: a slow native tree with per-phase timings. No latency number was invented. `WalkBudget` already starts at the first admitted node. No second budget was added.

### Issue 14

Python: `compiled_expectations.py` and `test_compiled_expectations.py`.
TypeScript: `typescript/compiled_expectations.ts` and `typescript/compiled_expectations.test.ts`.

Both compile `field_value_equals` and `fixture_submitted_equals` for the two executable ids, return null for reobserve and abstain, and ignore a provider replacement. No shared abstraction was added. No upstream change.

### Issue 16

Machine-readable matrix: `scripts/repro/handoff/issue-16-matrix.tsv`.

Linux source names `include_accessibility_tree` and `include_screenshot`. Runtime on macOS was not measured. Missing machine: macOS. Runtime on Windows was not measured. Missing machine: Windows. Recommendation: fail closed and do not advertise the selectors as equivalent. No selector was changed.

### Issue 17

Transition table: `scripts/repro/handoff/issue-17-transitions.json`.

Same ref and generation binds. Same label with a new generation is refused. `test_browser_revision.py` is the fixture. This table is what issue 11 has to respect. It is not a CDP log.

### Issue 18

Blocked. Missing machine: macOS.

Asked for raw AX event and capture traces, a safe/noisy/unusable table, and a recommendation on `unchanged_since`. None of that was captured. No signal is marked safe. No miss rate was invented.

### Issue 19

Blocked. Missing machine: Windows.

Asked for raw UIA event traces and a safe/noisy/unusable table. None of that was captured. No signal is marked safe. No miss rate was invented.

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

Shared fixture: `scripts/repro/handoff/issue-40-fixture.json`.
Python runner: `test_compiled_expectations.py`.
TypeScript runner: `typescript/compiled_expectations.test.ts`.

Both read that fixture. Parity is claimed only for compiled expectations. The other helpers were not mirrored.

### Issue 41

A candidate still carries id, description, tool, arguments, and optional capture id. The fast path and guarded run read those fields. They do not add an authority token.

### Issue 42

Only the jev-use form and submit ids compile expectations. That is one recipe. No shared compiler is created.

### Issue 43

The guarded run is the verification-form pair (type, then submit). A second workflow was not implemented. Reuse is not claimed.

### Issue 44

Routing table: `scripts/repro/handoff/issue-44-routing.json`, written by `caller_route.route`.
Tests: `test_caller_route.py`.

`run.py` does not call `route`. The table is not fed into the runner, because the live verdicts it depends on are still missing.

### Issue 45

Each new function is a file under the jev-use example plus a unit test. No Driver method, schema field, or dependency was added except the internal macOS poll tag. Complexity is not traded against a measured millisecond.

### Issue 46

Blocked. Missing session on this Linux host: a live chooser A/B.

Asked for projection definitions, A/B receipts, and a smallest safe chooser state. Not produced. `run.py` still sends the existing candidate list. No receipt was invented.

### Issue 47

Blocked. Missing session on this Linux host: a per-task history-sensitivity run.

Asked for a sensitivity table and a typed-history proposal. Not produced. No step was removed from the runner.

### Issue 48

Blocked. Missing providers on this Linux host: a live Jev session and a local S1 session.

Asked for a parity matrix across mock, Jev, and S1. Not produced. `choose_mock` remains the offline chooser. `deterministic_fast_path.py` does not import Jev.

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

| Optimization | Gate | Contract field |
| --- | --- | --- |
| lazy visual skip | a semantic executable candidate already exists | none; caller predicate only |
| fast path | exactly one executable candidate | none |
| guarded run | explicit run decision plus a fresh observation | none |
| conditional skip | not enabled | none |

No new capability field. Do not route on a selector the driver has not reported as honored.

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

Dispatch counts: `scripts/repro/handoff/issue-33-dispatch.json`, written by `second_child_allowed`.

Verified is the only status in that file with a second dispatch. Refuted, unknown, stale, rebound, and refused stay at one dispatch. An independent app-state oracle was not attached on this Linux host. The recommendation is the typed rule already in `action_consumer.py`: do not replay after unknown.

### Issue 34

No telemetry field with window titles, tokens, or screenshots was added. `task_accounting` stores milliseconds only.

### Issue 35

Regression budget: do not add a CI wall-clock gate. The sample check is the existing unit tests of the caller functions. A green unit run does not certify a latency change. No workflow file was added.

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

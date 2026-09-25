# Speed RFC delta against current CUA

Downstream draft for kvnloo/cua#61 and #73. This file does not edit trycua/cua#3963.

Pinned upstream main: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Fork prototypes that the tests call: `92b5035ea08b2126f947db0dfd8ecf829013d7b4` on `test/rfc-fast-path-one-candidate-20260925`.

## 1. North-star

The measurable objective stays narrow: fewer model decisions, less unnecessary observation and wait, bounded deterministic verification, and no wider authority. This branch records no speedup. Milliseconds removed are not measured.

## 2. Invariants that remain

- `unknown` is not success. `WORKFLOW.md` line 103. `action-result-contract.md` line 94.
- One capture authorizes at most one action, then the client reobserves. RFC 3931 lines 403 and 405.
- The chooser returns one supplied candidate id and does not execute it. `jev-use` README line 201.
- The fixture completion oracle is `/state`. `goal_gates.accept_completion` lets that oracle override a model that says done.
- `verify_state.elapsed_ms` is verification-loop time. `expectation.rs` line 310 closes it before the optional screenshot `observe` at line 329.
- A passive row is readable and is not an action target.
- A shadow probe does not skip a capture.
- Run length 4 is not a default.

## 3. Current repo-native owners

The machine-readable assignment is `scripts/repro/handoff/ownership.tsv`.

Columns: requirement, current owner, smallest delta, evidence, disposition.

Dispositions used: `already exists`, `caller/recipe-local`, and `delete from plan`. No row uses `new public/runtime owner` or `shared helper earned by two call sites`. `run.py` does not call the new functions.

## 4. Disposition table

`scripts/repro/handoff/decision-table.tsv` gives each mechanism one of KEEP, REVISE, KILL, or BLOCKED, plus the missing evidence, the owner, the public-surface cost, and the next action.

No downstream issue was closed by this draft. #7, #15, and #22 were already closed before this queue.

KILL is recorded only for three behaviors the unit tests demonstrate:

- a shared run length of 4 (`test_run_length.py`)
- using a passive row as an action target (`test_passive_observation.py`)
- skipping a capture from the shadow probe (`test_shadow_probe.py`)

Those KILL rows still leave #25, #8, and #11 open, because fixture latency, the macOS Calculator log, and the false-negative census were not produced. Every other mechanism is BLOCKED. There is no KEEP and no REVISE.

## 5. Remaining deltas

Nothing on the default `run.py` path changes. The remaining work is evidence, not a new subsystem:

- a live interleaved trial for the one-candidate fast path
- live wall-time receipts for the guarded run
- an app-state trace for the stale batch child
- a native walker counter for the screenshot-only observe
- a live outcome A/B for lazy vision
- macOS AX and Windows UIA censuses
- the macOS Calculator case
- a 4-arm benchmark for whole-task time

## 6. Deleted architecture

Removed from the plan:

- universal shadow-state service
- new observation service (`ObservationService`)
- observation budget service (`ObservationBudgetService`)
- revision service (`RevisionService`)
- passive-evidence service (`PassiveEvidenceService`)
- second verifier
- shared postcondition compiler
- shared guarded-run type
- competing batch API
- generic lifecycle service (`ExecutionContext`, `LifecycleService`)
- fixed GuardedRun length
- a blind wait replacement for the 0.25 s interval. kvnloo/cua#15 was already closed: that interval is the existing bounded window poll.

## 7. Phase gates

| Phase | Gate | Record on this host |
| --- | --- | --- |
| 0 | Named spans explain more than 90% of verified-outcome time before speedups are compared | `phase0_spans_cover_outcome` exists. The fixture battery was not run |
| 1A | Live fast-path and lazy-vision A/B | not run |
| 1B | Guarded-run receipts with wall time | `wall_time_ms` is null |
| 2A | Shadow probe with zero capture skipping, plus retention and cost | skip is refused. Retention and cost are null |
| 2B | A real safe skip | no safe skip evidence. Production skipping is off |

## 8. Dependency graph

`scripts/repro/handoff/promotion-dag.json` and the posting queue `scripts/repro/handoff/issue-74-queue.md`.

## 9. Migration plan

Prepare comments. Do not open a new upstream pull request. Do not edit trycua/cua#3963. Do not merge draft pull request 26.

## Corrections kept

- The fixture completion oracle already exists.
- The #15 readiness wait that was inspected is the bounded poll interval, not a blind settle.
- `verify_state.elapsed_ms` is verification-loop time.
- Phase 2B has no safe real skip evidence.
- Run length 4 is not an architectural default.
- trycua/cua#3873 was fetched open on 2026-09-25. Its body names a snapshot store invalidated on read and does not mention a quota. The earlier quota concern is not in that body. This branch did not merge #3873.
- `PollProvenance` is internal to macOS `Changes`. It is not a public field. The crate was not compiled here.

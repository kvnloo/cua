# Issue 56

Before and after, the observation owners stay the ones already on pinned main `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. This branch does not add a service.

| Need | Owner before and after | What this branch did |
| --- | --- | --- |
| Choose screenshot or tree | `get_window_state` flags in `WORKFLOW.md` lines 44 and 45 | `lazy_vision.py` is not called by `run.py` |
| Bound the walk | `WalkBudget`; `WalkSplit.owner` names setup, the native call, or that budget | no second budget |
| Expose passive rows | caller `passive_observation.action_target` | readable via `verification_text`; not an action target. macOS Calculator was not run |
| Completeness or degraded truth | `WORKFLOW.md` line 49, `degraded_reason` | no new field |
| Snapshot and capture identity | `snapshot_id` versus `capture_id` in `perception-extension.md` lines 99–100 | no second identity mint |
| Invalidation hints | `shadow_probe.record` | `skip_capture` stays false |
| Verify a postcondition | `expectation.rs` `verify_state` | `elapsed_ms` is closed at line 310, before `observe(..., false, true)` at line 329 |

Eliminated conceptual services:

- ObservationService
- ObservationBudgetService
- RevisionService
- PassiveEvidenceService

Also eliminated: a second tree for passive rows, a conditional-skip service, another walk budget, and a universal shadow store.

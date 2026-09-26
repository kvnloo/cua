# Issue 5 architecture note

Prototype: `libs/cua-driver/examples/jev-use/python/guarded_run.py`.
Tests: `libs/cua-driver/examples/jev-use/python/tests/test_guarded_run.py`.

## Facts allowed to survive child 1

- The decision kind is `run`.
- The two candidate ids and their Driver tools.
- The token the caller already held.
- The Submit ref the plan named, used only as the identity the fresh observation must still show.

## Facts not allowed to survive child 1

- The field value observed before the type.
- The capture id from before the type.
- A Submit ref that the fresh observation no longer returns.

## Negative cases

`second_child_allowed` returns false for refuted, unknown, stale, a missing fresh observation, a changed field, a rebound Submit ref, a missing Submit ref, a missing capture id, and refusal. The second child is not dispatched in those cases. A provider `single` decision is not admitted as a run.

## Receipts

`scripts/repro/handoff/issue-5-receipts.jsonl` is the unit record from `admit_guarded_run` and `second_child_allowed`. Every row has `wall_time_ms` null. Success, provider-decision counts, observation counts, and stale-incident counts from a live fixture were not measured. No shared helper was added.

# Issue 6 handoff

## Invariant

Preflight of snapshot S does not authorize child 2. Immediately before dispatch, child 2 is resolved again. A missing target or a different identity is refused. Child 1 failed or unknown means child 2 never starts.

## Regression fixture

`libs/cua-driver/examples/jev-use/python/tests/test_stale_batch.py`

Variants covered: target remains valid, target disappears, identity changes while the label stays the same, first child fails, first child postcondition is unknown.

## Latency and turn count

Turn count is `len(dispatched)` in `scripts/repro/handoff/issue-6-receipts.jsonl`, from `stale_batch.run_batch`. Unchanged identity dispatches 2. A disappeared target, a rebound identity, a failed first child, and an unknown first child each dispatch 1. `elapsed_ms` is null. Wall-clock latency was not measured on this host. No speedup is claimed.

## Recommendation

Freshness stays caller-managed, in `stale_batch.py`. It does not move into shared Driver execution code, and no batch API is added.

Native Windows evidence was not captured. Missing machine: Windows.

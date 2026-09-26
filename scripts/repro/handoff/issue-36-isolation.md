# Issue 36

| Object | Shared across issuances | Violation |
| --- | --- | --- |
| `Lifetime` events | no; `finish` rejects another issuance | none found in `test_cancellation_lifetime.py` |
| `GuardedRunPlan` | holds ids and a token only | none found |
| process-global capture | not introduced | none found |

The machine-readable row is `scripts/repro/handoff/issue-36-isolation.json`, from `cancellation_lifetime.isolation_report`. `finish` on another issuance raises, so the events are not shared.

`scripts/repro/handoff/issue-36-sessions.json`, from `handoff_emit.session_isolation`, builds two `Lifetime` values and two browser nodes. The second issuance's events are not the first issuance's events. `bind` refuses the other session's ref and still binds that session's own ref. A token taken from the other plan does not authorize the first plan. No process-global capture registry was introduced.

Concurrent processes were not executed on this Linux host. Existing session owners were not replaced.

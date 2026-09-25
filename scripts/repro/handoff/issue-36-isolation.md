# Issue 36

| Object | Shared across issuances | Violation |
| --- | --- | --- |
| `Lifetime` events | no; `finish` rejects another issuance | none found in `test_cancellation_lifetime.py` |
| `GuardedRunPlan` | holds ids and a token only | none found |
| process-global capture | not introduced | none found |

Real concurrent sessions were not executed on this Linux host. Existing session owners were not replaced.

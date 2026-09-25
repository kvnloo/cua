# Issue 66

Canonical owner for mechanical batching: trycua/cua#2794 and #3494.

Regression fixture: `test_stale_batch.py`. It refuses a disappeared target, a new identity with the same label, and a second child after a failed or unknown first child.

`guarded_run.py` stays on the caller. No batch API was added.

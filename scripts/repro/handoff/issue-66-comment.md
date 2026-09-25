# Issue 66

Prepared comment. Not posted. No batch API was added.

Canonical owner for mechanical composition: trycua/cua#2794 and #3494. kvnloo/cua#6 stays the caller-side regression discussion and should point at those two issues. It should not become a second batch API.

The caller guarded run owns fresh dependency reproof, postcondition evaluation, and semantic continuation. It lives in `guarded_run.py`.

Regression fixture: `test_stale_batch.py`, which calls `run_batch`.

| Case | Result |
| --- | --- |
| Submit identity unchanged after the first child returns ok | both children dispatch |
| Submit disappears during the first child | `submit` is refused |
| Same label, new identity | `submit` is refused |
| First child `failed` or `unknown` | only `field` dispatches |

`elapsed_ms` for this fixture is null. An independent app-state trace was not captured on this Linux host. The comment must not claim a latency or turn-count saving.

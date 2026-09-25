# Issue 59

| | Driver mechanical batch | Caller guarded run |
| --- | --- | --- |
| Owner | trycua/cua#2794 and #3494 | `guarded_run.py` |
| Stale later child | `stale_batch.py` resolves again and refuses a new identity | fresh observation must still show the planned Submit ref |
| New API | none | none |

Integration point: the caller, immediately before the second dispatch.

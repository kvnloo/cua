# Issue 59

| | Driver mechanical batch | Caller guarded run |
| --- | --- | --- |
| Owner | trycua/cua#2794 and #3494 | `guarded_run.py` |
| What it may decide | the next child still has the same identity | the fresh observation still shows the planned token, Submit ref, and capture id |
| What it must not decide | that child N is semantically justified because child N-1 returned ok | that two caller round trips saved a transport batch |
| New API | none | none |

Integration point: the caller, immediately before the second dispatch. `run.py` does not call either function.

Wrong owner, semantic logic pushed into the batch: `stale_batch.run_batch` dispatches `field` and `submit` when both identities are unchanged and the first child returns `ok`. That path never reads the field token. A disappeared Submit or a new identity with the same label is refused. A `failed` or `unknown` first child does not start the second. Identity match is not a postcondition.

Wrong owner, mechanical batching copied into the caller: `second_child_allowed` returns a boolean. It does not build a dispatch list and it does not claim a transport saving. The second child still requires its own fresh observation.

No competing batch API was added.

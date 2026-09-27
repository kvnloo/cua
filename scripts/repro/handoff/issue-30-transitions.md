# Issue 30

| From | Event | To | Owner |
| --- | --- | --- | --- |
| off | do not call the function | off | caller |
| guarded run admitted | fresh observation fails | stopped | `guarded_run.py` |
| conditional skip | not enabled | off | none |

Rollback is not calling the function. No config framework was added. `run.py` does not call these functions, which is the off state.

# Issue 32

| Input | Result | Pretends success |
| --- | --- | --- |
| two executable candidates | `single_executable_candidate` returns none | no |
| provider single-action choice | `admit_guarded_run` returns none | no |
| passive row as target | `action_target` raises | no |
| shadow skip requested | `ShadowSample` raises | no |

Shared recommendation: keep these checks next to the caller. Do not report a slower default as if the optimization ran.

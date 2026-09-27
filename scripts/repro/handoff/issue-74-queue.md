# Issue 74 posting queue

Machine-readable source: `scripts/repro/handoff/promotion-dag.json`.

Nothing in this queue was posted upstream. Draft pull request 26 was not merged. No new upstream pull request was opened.

Order: an item is listed only after the item it depends on. Comments stay inside the measured result.

1. `elapsed-ms-boundary` — READY NOW. Comment, not posted: `elapsed_ms` is closed before the optional screenshot observe. No speedup is claimed. Dependency: none.
2. `run-length-4` — WAITING ON DOWNSTREAM EXPERIMENT. No action. Do not propose `max_run_length=4`. The unit test wastes three planned children. Fixture latency is still missing, so #25 stays open. The Linux host probe found `cua-driver 0.28.2`, no daemon, and no top-level windows.
3. `3961-scope` — ASSIMILATED. No action. NO CHANGE NEEDED on the provider adapter.
4. `4009-public-field` — ASSIMILATED. No action. Comment https://github.com/kvnloo/cua/issues/71#issuecomment-5841780594 names `post_dispatch_observation: completed | skipped | unavailable`. This checkout does not contain the symbol. The macOS crate was not compiled here.
5. `4052` — WAITING ON DOWNSTREAM EXPERIMENT. Depends on the elapsed-ms definition above. The 4-arm benchmark was not run, so this is not sent to #4052.
6. `4164` — WAITING ON DOWNSTREAM EXPERIMENT. https://github.com/kvnloo/cua/issues/63#issuecomment-5841776432 records head `fb7841be7c9d2ef666a5dd87be6ca78e2de5d254`: element plus screenshot 2 AX walks to 1, window-only plus screenshot 1 to 0, control stayed 1 to 1. This host did not run that walk. Missing machine: Windows. The Linux walker log is also missing. The upstream pull-request description was not updated from this branch.
7. `4165` — WAITING ON DOWNSTREAM EXPERIMENT. The outcome A/B was not run. Not sent.
8. `3904` — WAITING ON DOWNSTREAM EXPERIMENT. Missing machine: macOS. The prepared Calculator vectors are caller-side only. Not sent.
9. `2794-3494` — WAITING ON DOWNSTREAM EXPERIMENT. The stale-target fixture exists. The app-state trace does not, so the comment is not sent.
10. `3796` — WAITING ON RFC DECISION. NEEDS DESIGN DECISION. Not sent before that approval.

No other item is READY NOW. No item asks for a new upstream pull request.

# Issue 13

Blocked. The slow-tree timings were not captured.

Missing on this Linux host: a slow native accessibility tree. `scripts/repro/handoff/linux-host-probe.txt` records no top-level windows, so there was no tree to time. The installed driver is `cua-driver 0.28.2`, not pinned head `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Missing machines for the other platforms named by the cross-platform conclusion: macOS and Windows.

Asked for: raw per-phase timings, the app, OS, and Driver identity, no-retry failure logs, and an upstream-ready conclusion for trycua/cua#3906.

Not produced: those timings or logs.
Not invented: a latency number or a new budget type.

`WalkBudget` starts at the first admitted node. Setup before that admit is outside the budget. `walk_budget_owner.WalkSplit` only names an owner from timings the caller supplies. No timings were supplied by a real walk.

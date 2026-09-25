# Issue 13

Blocked. Missing workload on this Linux host: a slow native accessibility tree with per-phase timings.

Asked for: raw per-phase timings, the app, OS, and Driver identity, no-retry failure logs, and an upstream-ready conclusion for trycua/cua#3906.

Not produced: those timings or logs.
Not invented: a latency number or a new budget type.

What the existing `WalkBudget` source already says, without a new measurement: the walk clock starts at the first admitted node, and setup before that admit is outside the budget. `walk_budget_owner.WalkSplit` only names an owner from timings the caller supplies. No timings were supplied by a real walk.

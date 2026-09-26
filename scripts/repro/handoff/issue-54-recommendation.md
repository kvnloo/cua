# Issue 54

Deleted: a shared constant of 4 actions.

Local: the per-child check in `guarded_run.py`. `second_child_allowed` admits the next child only when the first status is `verified` and a fresh observation still has the planned token, Submit ref, and capture id.

Shared: nothing. There is no public `max_run_length`.

`recommend_cap(7, 10)` returns: keep the cap at 2; length 4 is not supported by these early-stops.

`execute_capped` on a refuted first child with cap 4 runs 1 child. `wasted_after_stop(4, 1)` is 3. The same plan with cap 2 and a fresh verified observation runs 2. A fixed cap of 4 does not re-prove the later children; the local guard does. Fixture latency was not measured, so kvnloo/cua#25 stays open.

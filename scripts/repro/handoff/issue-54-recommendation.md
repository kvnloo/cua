# Issue 54

Deleted: a shared constant of 4 actions. `recommend_cap(7, 10)` in `run_length.py` returns advice to keep the cap at 2, and `execute_capped` on a refuted first child wastes the other three.

Local: the dependency check in `guarded_run.py`.

Shared: nothing. Run length stays with the caller.

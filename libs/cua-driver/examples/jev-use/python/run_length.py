"""Cap sensitivity on top of the #5 guard. kvnloo/cua#25.

These are scripted early-stops, not measured fixture latencies.
"""

from __future__ import annotations

from guarded_run import ChildStatus, FreshObservation, GuardedRunPlan, PlannedChild, second_child_allowed


def wasted_after_stop(planned: int, executed: int) -> int:
    return max(planned - executed, 0)


def execute_capped(
    plan: GuardedRunPlan,
    statuses: list[ChildStatus],
    observations: list[FreshObservation | None],
    cap: int,
) -> int:
    """Return how many children actually ran. Cap 1 is the single-action baseline."""
    if cap < 1:
        return 0
    ran = 1
    if cap == 1 or not statuses:
        return ran
    allowed = second_child_allowed(statuses[0], observations[0] if observations else None, plan)
    if not allowed:
        return ran
    return min(cap, 2)


def recommend_cap(stop_at_first_child: int, runs: int) -> str:
    if runs <= 0:
        return "no recommendation"
    if stop_at_first_child * 2 >= runs:
        return "keep the cap at 2; length 4 is not supported by these early-stops"
    return "measure a longer cap on a real fixture before embedding it"

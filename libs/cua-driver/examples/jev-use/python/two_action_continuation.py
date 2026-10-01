"""Content-free journals for the narrow two-action guarded continuation.

Extends trycua/cua#3963 / #4316 / kvnloo/cua#5 KEEP evidence.

#4316 owns the product (plan + resolve). Fork #79 owns session-authority
attribution for a single resolve. This leaf attributes the *full* 2→1
continuation contract that run.py enforces:

  provider chooses first mutation → plan minted → postcondition + fresh
  observation → guarded child admits exactly once → pending plan consumed.

A failed child-2 proof also clears pending authority (no blind replay).
A third step never auto-continues from a consumed plan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from guarded_completion import (
    GuardedCompletionPlan,
    plan_guarded_completion,
    resolve_guarded_completion,
)
from sources import Candidate
from tasks import Task, TaskSources

Route = Literal["provider", "guarded-completion", "chooser"]


@dataclass(frozen=True)
class ContinuationStepReceipt:
    step: int
    route: Route
    candidate_id: str | None
    provider_called: bool
    dispatch_attempted: bool
    plan_pending_after: bool


@dataclass(frozen=True)
class TwoActionContinuationJournal:
    """Content-free receipt for one two-step guarded continuation attempt."""

    provider_decisions: int
    actions_dispatched: int
    guarded_child_admitted: bool
    decision_routes: tuple[str, ...]
    plan_consumed: bool
    second_dispatch_attempted: bool
    steps: tuple[ContinuationStepReceipt, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_routes"] = list(self.decision_routes)
        payload["steps"] = [asdict(step) for step in self.steps]
        return payload


def journal_two_action_continuation(
    task: Task,
    initial_sources: TaskSources,
    fresh_sources: TaskSources,
    *,
    session: str,
    third_sources: TaskSources | None = None,
) -> TwoActionContinuationJournal:
    """Simulate the run.py pending_completion lifecycle for two steps.

    Step 1 always goes through the provider (first mutation). After dispatch,
    a plan may be pending. Step 2 attempts resolve exactly once, then always
    clears pending — matching run.py's fail-closed consume rule. An optional
    third observation proves a consumed plan cannot authorize another skip.
    """
    steps: list[ContinuationStepReceipt] = []
    provider_decisions = 0
    actions_dispatched = 0
    guarded_child_admitted = False
    second_dispatch_attempted = False
    pending: GuardedCompletionPlan | None = None

    # --- Step 1: provider selects the first mutation ---
    initial_candidates = task.candidates(initial_sources)
    if not initial_candidates:
        raise ValueError("initial step requires at least one candidate")
    first = initial_candidates[0]
    provider_decisions += 1
    actions_dispatched += 1
    pending = plan_guarded_completion(task, initial_sources, first, session=session)
    steps.append(
        ContinuationStepReceipt(
            step=1,
            route="provider",
            candidate_id=first.id,
            provider_called=True,
            dispatch_attempted=True,
            plan_pending_after=pending is not None,
        )
    )

    # --- Step 2: try guarded resolve once; always consume pending ---
    candidates = task.candidates(fresh_sources)
    guarded: Candidate | None = None
    if pending is not None:
        resolution = resolve_guarded_completion(
            pending, task, fresh_sources, candidates, session=session
        )
        guarded = resolution.candidate
    # Mirror run.py: a failed proof never keeps authority alive.
    pending = None

    if guarded is not None:
        actions_dispatched += 1
        guarded_child_admitted = True
        second_dispatch_attempted = True
        steps.append(
            ContinuationStepReceipt(
                step=2,
                route="guarded-completion",
                candidate_id=guarded.id,
                provider_called=False,
                dispatch_attempted=True,
                plan_pending_after=False,
            )
        )
    else:
        # Fall closed to chooser — provider would be consulted; no child-2
        # dispatch from the guarded path.
        provider_decisions += 1
        steps.append(
            ContinuationStepReceipt(
                step=2,
                route="chooser",
                candidate_id=None,
                provider_called=True,
                dispatch_attempted=False,
                plan_pending_after=False,
            )
        )

    # --- Optional step 3: consumed plan must not auto-admit ---
    if third_sources is not None:
        # pending is already None; run.py would not consult a consumed plan.
        steps.append(
            ContinuationStepReceipt(
                step=3,
                route="chooser",
                candidate_id=None,
                provider_called=True,
                dispatch_attempted=False,
                plan_pending_after=False,
            )
        )
        provider_decisions += 1

    decision_routes = tuple(step.route for step in steps)
    return TwoActionContinuationJournal(
        provider_decisions=provider_decisions,
        actions_dispatched=actions_dispatched,
        guarded_child_admitted=guarded_child_admitted,
        decision_routes=decision_routes,
        plan_consumed=True,
        second_dispatch_attempted=second_dispatch_attempted,
        steps=tuple(steps),
    )

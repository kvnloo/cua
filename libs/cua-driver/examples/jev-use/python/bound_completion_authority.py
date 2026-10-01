"""Content-free route receipts for bound-completion session authority.

Extends trycua/cua#3963 / #4316 / kvnloo/cua#36.

The revised Phase-1A rule (downstream #4 REVISE) is not generic
``executable_count == 1 => act``. The surviving exception is:

  skip the provider only when a session-bound GuardedCompletionPlan
  re-proves exactly one executable completion candidate with a fresh ref
  in the *same* named Cua session.

This module does not change admission behavior. It attributes the route
so tests can prove which gate fired without reconstructing control flow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

from guarded_completion import GuardedCompletionPlan, resolve_guarded_completion
from sources import Candidate
from tasks import FIXTURE_TASK_ID, Task, TaskSources

Route = Literal["guarded-completion", "chooser"]
Reason = Literal[
    "allowed",
    "session_mismatch",
    "missing_session",
    "task_mismatch",
    "missing_page",
    "postcondition_unverified",
    "non_unique_target",
    "stale_or_reused_ref",
    "non_unique_completion",
    "ref_mismatch",
]


@dataclass(frozen=True)
class BoundCompletionEvidence:
    """Content-free receipt for one resolve attempt."""

    route: Route
    reason: Reason
    executable_count: int
    provider_called: bool
    plan_session: str
    resolve_session: str
    selected_id: str | None
    dispatch_attempted: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matching_refs(
    snapshot: Mapping[str, Any],
    *,
    role: str,
    name: str,
) -> list[Mapping[str, Any]]:
    refs = snapshot.get("refs") or []
    if not isinstance(refs, list):
        return []
    return [
        ref
        for ref in refs
        if isinstance(ref, Mapping)
        and ref.get("role") == role
        and ref.get("name") == name
        and isinstance(ref.get("ref"), str)
        and bool(ref.get("ref"))
    ]


def explain_bound_completion(
    plan: GuardedCompletionPlan,
    task: Task,
    sources: TaskSources,
    candidates: list[Candidate],
    *,
    session: str,
) -> BoundCompletionEvidence:
    """Attribute why a bound-completion resolve admitted or fell closed.

    ``dispatch_attempted`` is True only when the receipt would authorize a
    provider-skip (route=guarded-completion). Foreign-session attempts never
    dispatch; the owning plan remains usable afterward.
    """
    plan_session = plan.session
    resolve_session = session or ""

    def _closed(
        reason: Reason,
        *,
        executable_count: int = 0,
    ) -> BoundCompletionEvidence:
        return BoundCompletionEvidence(
            route="chooser",
            reason=reason,
            executable_count=executable_count,
            provider_called=True,
            plan_session=plan_session,
            resolve_session=resolve_session,
            selected_id=None,
            dispatch_attempted=False,
        )

    if not resolve_session:
        return _closed("missing_session")
    if resolve_session != plan_session:
        return _closed("session_mismatch")
    if task.id != FIXTURE_TASK_ID:
        return _closed("task_mismatch")
    if sources.page is None:
        return _closed("missing_page")

    state = task.state_summary(sources)
    if state.get("verification_field") != "contains_required_token":
        return _closed("postcondition_unverified")

    matches = _matching_refs(
        sources.page.snapshot,
        role=plan.target_role,
        name=plan.target_name,
    )
    if len(matches) != 1:
        return _closed("non_unique_target")
    fresh_ref = str(matches[0]["ref"])
    if fresh_ref == plan.prior_ref:
        return _closed("stale_or_reused_ref")

    executable = [
        candidate
        for candidate in candidates
        if candidate.id == plan.completion_candidate_id
        and candidate.tool == "browser_click"
        and candidate.source == "page"
    ]
    executable_count = len(executable)
    if executable_count != 1:
        return _closed("non_unique_completion", executable_count=executable_count)

    candidate = executable[0]
    if candidate.arguments.get("ref") != fresh_ref:
        return _closed("ref_mismatch", executable_count=1)

    # Cross-check against the live resolver so the receipt cannot drift.
    resolution = resolve_guarded_completion(
        plan, task, sources, candidates, session=resolve_session
    )
    resolved = resolution.candidate
    if (
        resolved is None
        or resolution.telemetry.get("status") != "accepted"
        or resolved.id != candidate.id
    ):
        return _closed("ref_mismatch", executable_count=1)

    return BoundCompletionEvidence(
        route="guarded-completion",
        reason="allowed",
        executable_count=1,
        provider_called=False,
        plan_session=plan_session,
        resolve_session=resolve_session,
        selected_id=candidate.id,
        dispatch_attempted=True,
    )

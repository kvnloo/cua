"""Caller-side two-action run for kvnloo/cua#5.

The model may authorize the run once. Refs, field values, and capture ids from
before the first mutation do not authorize the second action. The plan binds
the logical completion target (semantic role and name). Child 2 may dispatch
only the ref freshly resolved from the post-mutation observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core import Candidate

RESERVED_CANDIDATE_IDS = frozenset({"reobserve", "abstain"})
ChildStatus = Literal["verified", "refuted", "unknown", "stale", "rebound", "refused"]
SecondChildReason = Literal[
    "allowed",
    "refuted",
    "unknown",
    "stale",
    "rebound",
    "refused",
    "missing_observation",
    "missing_capture",
    "field_mismatch",
    "submit_ref_mismatch",
]


@dataclass(frozen=True)
class PlannedChild:
    candidate_id: str
    tool: str


@dataclass(frozen=True)
class GuardedRunPlan:
    """What survives child 1: these two ids, the token, and the logical target.

    ``submit_ref`` is the pre-mutation ref. It is recorded so a later dispatch
    can be shown not to reuse it. It does not identify the target.
    ``target_role`` and ``target_name`` are the semantic_v2 identity.
    """

    first: PlannedChild
    second: PlannedChild
    token: str
    submit_ref: str
    target_role: str | None = None
    target_name: str | None = None


@dataclass(frozen=True)
class FreshObservation:
    field_value: str | None
    submit_ref: str | None
    capture_id: str | None
    role: str | None = None
    name: str | None = None
    match_count: int = 1
    resolved_ref: str | None = None


@dataclass(frozen=True)
class Decision:
    kind: Literal["run", "single", "reobserve", "abstain"]
    child_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecondChildEvidence:
    """Content-free receipt explaining whether child 2 may dispatch.

    ``dispatch_ref`` is set only when the post-mutation resolution is the ref
    that may be clicked. It is never the pre-mutation ref stored on the plan.
    """

    allowed: bool
    reason: SecondChildReason
    dispatch_ref: str | None = None


def admit_guarded_run(
    candidates: list[Candidate],
    decision: Decision,
    *,
    token: str,
    submit_ref: str,
    target_role: str | None = None,
    target_name: str | None = None,
) -> GuardedRunPlan | None:
    if decision.kind != "run" or len(decision.child_ids) != 2:
        return None
    by_id = {candidate.id: candidate for candidate in candidates}
    chosen = []
    for candidate_id in decision.child_ids:
        candidate = by_id.get(candidate_id)
        if (
            candidate is None
            or candidate.id in RESERVED_CANDIDATE_IDS
            or candidate.tool is None
        ):
            return None
        chosen.append(PlannedChild(candidate.id, candidate.tool))
    if not token or not submit_ref:
        return None
    if (target_role is None) != (target_name is None) or target_role == "" or target_name == "":
        return None
    return GuardedRunPlan(chosen[0], chosen[1], token, submit_ref, target_role, target_name)


def explain_second_child(
    status: ChildStatus,
    fresh: FreshObservation | None,
    plan: GuardedRunPlan,
) -> SecondChildEvidence:
    if status != "verified":
        return SecondChildEvidence(False, status)
    if fresh is None:
        return SecondChildEvidence(False, "missing_observation")
    if not fresh.capture_id:
        return SecondChildEvidence(False, "missing_capture")
    if fresh.field_value != plan.token:
        return SecondChildEvidence(False, "field_mismatch")
    if plan.target_role is None:
        if fresh.submit_ref != plan.submit_ref:
            return SecondChildEvidence(False, "submit_ref_mismatch")
        return SecondChildEvidence(True, "allowed", fresh.submit_ref)
    if (
        fresh.role != plan.target_role
        or fresh.name != plan.target_name
        or fresh.match_count != 1
    ):
        return SecondChildEvidence(False, "rebound")
    resolved = fresh.resolved_ref or fresh.submit_ref
    if not resolved:
        return SecondChildEvidence(False, "rebound")
    if fresh.submit_ref != resolved:
        return SecondChildEvidence(False, "submit_ref_mismatch")
    return SecondChildEvidence(True, "allowed", resolved)


def second_child_allowed(
    status: ChildStatus,
    fresh: FreshObservation | None,
    plan: GuardedRunPlan,
) -> bool:
    return explain_second_child(status, fresh, plan).allowed

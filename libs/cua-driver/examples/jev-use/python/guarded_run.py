"""Caller-side two-action run for kvnloo/cua#5.

The model may authorize the run once. Refs, field values, and capture ids from
before the first mutation do not authorize the second action. The caller has to
re-observe, and the fresh Submit ref has to still be the one the plan named.
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
    """What survives child 1: these two ids and the token the caller already held.

    The Submit ref and the capture id from before the type do not survive.
    """

    first: PlannedChild
    second: PlannedChild
    token: str
    submit_ref: str


@dataclass(frozen=True)
class FreshObservation:
    field_value: str | None
    submit_ref: str | None
    capture_id: str | None


@dataclass(frozen=True)
class Decision:
    kind: Literal["run", "single", "reobserve", "abstain"]
    child_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecondChildEvidence:
    """Content-free receipt explaining whether child 2 may dispatch."""

    allowed: bool
    reason: SecondChildReason


def admit_guarded_run(
    candidates: list[Candidate],
    decision: Decision,
    *,
    token: str,
    submit_ref: str,
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
    return GuardedRunPlan(chosen[0], chosen[1], token, submit_ref)


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
    if fresh.submit_ref != plan.submit_ref:
        return SecondChildEvidence(False, "submit_ref_mismatch")
    return SecondChildEvidence(True, "allowed")


def second_child_allowed(
    status: ChildStatus,
    fresh: FreshObservation | None,
    plan: GuardedRunPlan,
) -> bool:
    return explain_second_child(status, fresh, plan).allowed

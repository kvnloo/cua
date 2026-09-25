"""Modality-gated observation for the jev-use Python recipe loop.

Mirrors typescript/observation.ts: the visual observation path
(get_window_state + parse_visual_regions) is consumed only by the
visual-submit fallback in build_candidates, so when the snapshot alone
already yields an actionable candidate, paying for the visual path is
pure overhead. The ObservationLedger records what each step actually
observed — the shape a future post_dispatch_observation driver field
(#4009 / #3971) would feed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from core import Candidate

ObservationKind = Literal["snapshot", "visual"]


@dataclass(frozen=True)
class ObservationRecord:
    step: int
    kind: ObservationKind
    latency_ms: float
    capture_id: str | None = None


class ObservationLedger:
    """Provenance ledger for what the loop actually observed each step."""

    def __init__(self) -> None:
        self._records: list[ObservationRecord] = []

    def record(self, record: ObservationRecord) -> None:
        self._records.append(record)

    def entries(self) -> tuple[ObservationRecord, ...]:
        return tuple(self._records)

    def count(self, kind: ObservationKind) -> int:
        return sum(1 for record in self._records if record.kind == kind)

    def total_latency_ms(self, kind: ObservationKind | None = None) -> float:
        return sum(
            record.latency_ms
            for record in self._records
            if kind is None or record.kind == kind
        )


def has_actionable_candidate(candidates: Sequence[Candidate]) -> bool:
    """True when the candidate set already contains something executable.

    The reserved reobserve/abstain candidates carry no tool; their presence
    alone must not trigger the visual path.
    """
    return any(candidate.tool is not None for candidate in candidates)


def needs_visual_observation(candidates: Sequence[Candidate]) -> bool:
    """Whether the expensive visual observation is worth paying for.

    Mirrors the only consumer of the visual result in build_candidates:
    the visual-submit fallback, which fires only when the DOM refs cannot
    produce the submit candidate.
    """
    return not has_actionable_candidate(candidates)


__all__ = [
    "ObservationKind",
    "ObservationRecord",
    "ObservationLedger",
    "has_actionable_candidate",
    "needs_visual_observation",
]

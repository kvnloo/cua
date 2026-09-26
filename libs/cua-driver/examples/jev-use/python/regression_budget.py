"""Structural counters for kvnloo/cua#35. Milliseconds are not a merge gate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkCounts:
    model_calls: int
    observation_calls: int
    visual_parses: int
    actions: int


def semantic_path_ok(counts: WorkCounts) -> bool:
    """A semantic success path does not call the visual parser or the model."""
    return counts.visual_parses == 0 and counts.model_calls == 0


def ci_may_gate_on_milliseconds() -> bool:
    return False

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


def metric_layer(name: str) -> str:
    layers = {
        "model_calls": "hard CI counter",
        "observation_calls": "hard CI counter",
        "visual_parses": "hard CI counter",
        "actions": "hard CI counter",
        "unnecessary_producer_calls": "hard CI counter",
        "wall_clock_ms": "evidence artifact",
    }
    if name not in layers:
        raise KeyError(name)
    return layers[name]


def structural_ax_walks(*, include_elements: bool) -> int:
    """Screenshot-only verification passes include_elements false. This is not a census."""
    return 1 if include_elements else 0


def decisions_deleted_when_admitted(action_count: int, admitted: bool) -> int | None:
    """One admitted run replaces one decision per action. None when the run is not admitted."""
    if not admitted or action_count < 2:
        return None
    return action_count - 1

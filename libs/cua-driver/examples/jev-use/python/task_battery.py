"""Two task shapes so a form-fill win is not a global promotion. kvnloo/cua#24."""

from __future__ import annotations

from dataclasses import dataclass

from core import Candidate
from deterministic_fast_path import single_executable_candidate


@dataclass(frozen=True)
class TaskResult:
    name: str
    fast_path: bool
    decisions: int


def evaluate(name: str, candidates: list[Candidate]) -> TaskResult:
    admitted = single_executable_candidate(candidates)
    if admitted is None:
        return TaskResult(name, False, 1)
    return TaskResult(name, True, 0)


def promote_globally(results: list[TaskResult]) -> bool:
    return bool(results) and all(result.fast_path for result in results)


def run_interleaved(tasks: list[tuple[str, list[Candidate]]]) -> list[TaskResult]:
    """One decision per task, in the given order. Wall time is not measured."""
    return [evaluate(name, candidates) for name, candidates in tasks]


def standard_battery() -> list[tuple[str, list[Candidate]]]:
    def one(name: str, tool: str | None) -> Candidate:
        return Candidate(name, name, tool, {})

    return [
        ("fill-submit", [one("submit-form", "browser_click"), one("reobserve", None)]),
        ("toggle-confirm", [one("toggle-setting", "browser_click"), one("confirm-dialog", "browser_click")]),
        ("two-fields", [one("field-a", "browser_type"), one("field-b", "browser_type")]),
        ("modal", [one("open-modal", "browser_click"), one("act-inside", "browser_click")]),
        ("visual-needed", [one("reobserve", None)]),
    ]


def battery_table() -> list[dict[str, object]]:
    return [
        {
            "task": result.name,
            "fast_path": result.fast_path,
            "decisions": result.decisions,
            "wall_time_ms": None,
        }
        for result in run_interleaved(standard_battery())
    ]

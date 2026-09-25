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

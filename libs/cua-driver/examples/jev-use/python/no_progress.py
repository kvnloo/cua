"""Bounded no-progress detection for native jev-use runs.

This stays recipe-local. It never inspects model scores, pixels, element values,
or action arguments. App-owned progress is available only for built-in tasks
whose oracle exposes an intermediate monotonic score; otherwise successful
dispatch clears the evidence window because progress cannot be proven either
way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

NO_PROGRESS_LIMIT = 3
StepKind = Literal["reobserve", "stale", "refused", "performed"]


@dataclass(frozen=True)
class NoProgressStop:
    pattern: str
    streak: int


def observed_progress_score(task_id: str, state: Mapping[str, Any]) -> int | None:
    """Return a value-free monotonic progress score when the app oracle exposes one."""
    if task_id.endswith("-counter"):
        counter = state.get("counter")
        return counter if isinstance(counter, int) and not isinstance(counter, bool) and counter >= 0 else None
    if task_id.endswith("-choose-size"):
        return int(state.get("size") == "large") + int(state.get("agreed") is True)
    if task_id == "canvas-cancel":
        return int(state.get("selected") == "cancel" and state.get("action_count") == 1)
    # save-note does not publish the unsaved field value, so its intermediate
    # progress is intentionally unobservable from the app-owned oracle.
    return None


class NoProgressGuard:
    def __init__(self, task_id: str, *, limit: int = NO_PROGRESS_LIMIT) -> None:
        if limit < 1:
            raise ValueError("no-progress limit must be positive")
        self.task_id = task_id
        self.limit = limit
        self.best_progress: int | None = None
        self.pending: tuple[StepKind, str] | None = None
        self.streak = 0
        self.recent: list[str] = []

    def note(self, kind: StepKind, candidate_id: str) -> None:
        self.pending = (kind, candidate_id.removesuffix(":foreground"))

    def before_step(self, oracle_state: Mapping[str, Any]) -> NoProgressStop | None:
        score = observed_progress_score(self.task_id, oracle_state)
        pending = self.pending
        self.pending = None

        if score is not None and (self.best_progress is None or score > self.best_progress):
            self.best_progress = score
            self._reset_evidence()
            return None
        if score is not None and self.best_progress is None:
            self.best_progress = score

        if pending is None:
            return None
        kind, candidate_id = pending

        # When a task exposes no intermediate app-owned progress, a successful
        # dispatch makes the result unknown rather than proven-stuck. Start a
        # fresh evidence window instead of treating delivery as progress.
        if kind == "performed" and score is None:
            self._reset_evidence()
            return None

        token = f"performed:{candidate_id}" if kind == "performed" else kind
        self.streak += 1
        self.recent.append(token)
        self.recent = self.recent[-self.limit :]
        if self.streak < self.limit:
            return None
        return NoProgressStop(self._pattern(), self.streak)

    def _reset_evidence(self) -> None:
        self.streak = 0
        self.recent.clear()

    def _pattern(self) -> str:
        if self.recent and all(item == "reobserve" for item in self.recent):
            return "reobserve"
        if self.recent and all(item.startswith("performed:") for item in self.recent):
            if len(set(self.recent)) == 1:
                return "same_candidate"
        if any(item in {"stale", "refused"} for item in self.recent):
            return "recovery"
        return "unchanged_progress"
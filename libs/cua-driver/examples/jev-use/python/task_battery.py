"""Five task shapes so a form-fill win is not a global result. kvnloo/cua#24."""

from __future__ import annotations

from dataclasses import dataclass

from core import Candidate
from deterministic_fast_path import single_executable_candidate
from guarded_run import Decision, admit_guarded_run
from lazy_vision import needs_visual_capture

RESERVED = frozenset({"reobserve", "abstain"})


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
    """One structural pass per task, in the given order. Wall time is not measured."""
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


def retained_ground_truth(name: str) -> bool:
    """Offline label for the task. evaluate does not receive it."""
    return {
        "fill-submit": True,
        "toggle-confirm": True,
        "two-fields": True,
        "modal": True,
        "visual-needed": False,
    }[name]


def _executable(candidates: list[Candidate]) -> list[Candidate]:
    return [
        candidate
        for candidate in candidates
        if candidate.id not in RESERVED and candidate.tool is not None
    ]


def _stale_refusals(candidates: list[Candidate]) -> int:
    return sum(1 for candidate in candidates if candidate.arguments.get("stale") is True)


def _row(
    name: str,
    arm: str,
    candidates: list[Candidate],
    *,
    decisions: int,
    visual_parses: int | None,
    actions: int,
    abstentions: int,
    fast_path: bool,
    admission: str,
) -> dict[str, object]:
    return {
        "task": name,
        "arm": arm,
        "retained_ground_truth": retained_ground_truth(name),
        "live_success": None,
        "fast_path": fast_path,
        "decisions": decisions,
        "observations": None,
        "visual_parses": visual_parses,
        "actions": actions,
        "abstentions": abstentions,
        "stale_refusals": _stale_refusals(candidates),
        "wall_time_ms": None,
        "admission": admission,
    }


def arm_reports(name: str, candidates: list[Candidate], fast: TaskResult) -> list[dict[str, object]]:
    actions = _executable(candidates)
    visual = int(needs_visual_capture(candidates))
    exact = single_executable_candidate(candidates)
    guarded = None
    if len(actions) == 2:
        guarded = admit_guarded_run(
            candidates,
            Decision("run", (actions[0].id, actions[1].id)),
            token="proof",
            submit_ref="ref-submit",
        )
    baseline_decisions = len(actions) if actions else 1
    return [
        _row(
            name,
            "baseline",
            candidates,
            decisions=baseline_decisions,
            visual_parses=None,
            actions=len(actions),
            abstentions=0 if actions else 1,
            fast_path=False,
            admission="one decision per action",
        ),
        _row(
            name,
            "lazy-vision",
            candidates,
            decisions=fast.decisions,
            visual_parses=visual,
            actions=0 if exact is None else 1,
            abstentions=1 if exact is None else 0,
            fast_path=fast.fast_path,
            admission="needs_visual_capture",
        ),
        _row(
            name,
            "exact-candidate",
            candidates,
            decisions=0 if exact is not None else 1,
            visual_parses=visual,
            actions=0 if exact is None else 1,
            abstentions=1 if exact is None else 0,
            fast_path=exact is not None,
            admission="single_executable_candidate" if exact is not None else "chooser",
        ),
        _row(
            name,
            "guarded-run",
            candidates,
            decisions=1,
            visual_parses=visual,
            actions=2 if guarded is not None else 0,
            abstentions=0 if guarded is not None else 1,
            fast_path=False,
            admission="admitted" if guarded is not None else "not admitted",
        ),
    ]


def battery_table() -> list[dict[str, object]]:
    results = {item.name: item for item in run_interleaved(standard_battery())}
    rows: list[dict[str, object]] = []
    for name, candidates in standard_battery():
        rows.extend(arm_reports(name, candidates, results[name]))
    return rows

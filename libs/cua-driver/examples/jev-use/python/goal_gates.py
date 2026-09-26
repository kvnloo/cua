"""Model done-gates only where no independent oracle exists. kvnloo/cua#23."""

from __future__ import annotations

from dataclasses import dataclass


def use_model_done_gate(*, has_independent_oracle: bool) -> bool:
    return not has_independent_oracle


def accept_completion(*, model_says_done: bool, oracle_succeeded: bool | None) -> bool:
    if oracle_succeeded is not None:
        return oracle_succeeded
    return model_says_done


def done_label(value: bool | None) -> str:
    """Unknown stays distinct from false."""
    if value is None:
        return "unknown"
    return "true" if value else "false"


def needs_reobserve(*, observation_unknown: bool, completed: bool) -> bool:
    return observation_unknown and not completed


@dataclass(frozen=True)
class OfflineTask:
    name: str
    model_says_done: bool | None
    oracle_succeeded: bool | None
    ground_truth: bool


def offline_tasks() -> tuple[OfflineTask, ...]:
    """Ground truth stays in the table. The completion functions do not read it."""
    return (
        OfflineTask("fixture /state oracle", True, True, True),
        OfflineTask("no independent oracle", True, None, True),
        OfflineTask("model done, oracle failed", True, False, False),
        OfflineTask("cannot_answer is not false", None, None, False),
        OfflineTask("model done, ground truth false, no oracle", True, None, False),
        OfflineTask("model not done, ground truth true, no oracle", False, None, True),
    )


def ordinary_completed(task: OfflineTask) -> bool:
    """Arm A stops only when an independent oracle succeeds."""
    return task.oracle_succeeded is True


def factorized_completed(task: OfflineTask) -> bool:
    """Arm B. A missing model answer is not a false completion."""
    if task.model_says_done is None:
        if task.oracle_succeeded is None:
            return False
        return task.oracle_succeeded
    return accept_completion(
        model_says_done=task.model_says_done,
        oracle_succeeded=task.oracle_succeeded,
    )


def local_check(task: OfflineTask) -> str:
    """Arm C. Unavailable when the caller has no deterministic oracle."""
    if task.oracle_succeeded is None:
        return "unavailable"
    return done_label(task.oracle_succeeded)


def task_rows() -> list[dict[str, object]]:
    """Offline comparison. Latency and a confidence threshold were not measured."""
    rows = []
    for task in offline_tasks():
        has_oracle = task.oracle_succeeded is not None
        completed = factorized_completed(task)
        unknown = task.model_says_done is None
        reobserve = needs_reobserve(observation_unknown=unknown, completed=completed)
        rows.append(
            {
                "task": task.name,
                "model_done_gate": use_model_done_gate(has_independent_oracle=has_oracle),
                "done_label": done_label(task.model_says_done),
                "completed": completed,
                "needs_reobserve": reobserve,
                "reobserve_action": "reobserve" if reobserve else "continue",
                "arm_ordinary_completed": ordinary_completed(task),
                "arm_factorized_completed": completed,
                "arm_local": local_check(task),
                "ground_truth": task.ground_truth,
                "premature_stop": completed and not task.ground_truth,
                "missed_completion": task.ground_truth and not completed,
                "confidence_threshold": None,
                "calibration_trials": 0,
                "latency_ms": None,
                "steps_saved": None,
            }
        )
    return rows

"""Model done-gates only where no independent oracle exists. kvnloo/cua#23."""

from __future__ import annotations


def use_model_done_gate(*, has_independent_oracle: bool) -> bool:
    return not has_independent_oracle


def accept_completion(*, model_says_done: bool, oracle_succeeded: bool | None) -> bool:
    if oracle_succeeded is not None:
        return oracle_succeeded
    return model_says_done


def task_rows() -> list[dict[str, object]]:
    """Offline task set. Latency is not measured here."""
    specs = (
        ("fixture /state oracle", True, True),
        ("no independent oracle", True, None),
        ("model done, oracle failed", True, False),
    )
    rows = []
    for name, model_says_done, oracle in specs:
        has_oracle = oracle is not None
        rows.append(
            {
                "task": name,
                "model_done_gate": use_model_done_gate(has_independent_oracle=has_oracle),
                "completed": accept_completion(
                    model_says_done=model_says_done,
                    oracle_succeeded=oracle,
                ),
                "latency_ms": None,
            }
        )
    return rows

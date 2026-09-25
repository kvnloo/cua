"""Model done-gates only where no independent oracle exists. kvnloo/cua#23."""

from __future__ import annotations


def use_model_done_gate(*, has_independent_oracle: bool) -> bool:
    return not has_independent_oracle


def accept_completion(*, model_says_done: bool, oracle_succeeded: bool | None) -> bool:
    if oracle_succeeded is not None:
        return oracle_succeeded
    return model_says_done

"""Caller policy for kvnloo/cua#12.

Skipped observation is not a completed no-change poll. An unverifiable
action is not retried just because the caller cannot see the effect.
"""

from __future__ import annotations

from typing import Literal

Effect = Literal["confirmed", "suspected_noop", "unverifiable", "refused"]
Observation = Literal["skipped", "completed", "unavailable"]
Choice = Literal["continue", "observe", "stop"]


def typed_choice(effect: Effect, observation: Observation, *, passive_success: bool) -> Choice:
    if effect == "refused":
        return "stop"
    if passive_success and effect != "refused":
        return "continue"
    if observation == "skipped":
        return "observe"
    if effect == "unverifiable" or observation == "unavailable" or effect == "suspected_noop":
        return "observe"
    if effect == "confirmed" and observation == "completed":
        return "continue"
    return "stop"


def required_cases() -> list[dict[str, str | bool]]:
    """The cases named by kvnloo/cua#12. Each row is decided by typed_choice."""
    rows = [
        ("observation skipped after successful action", "confirmed", "skipped", False),
        ("observation completed and no relevant change", "confirmed", "completed", False),
        ("observation unavailable", "unverifiable", "unavailable", False),
        ("passive result proves success", "unverifiable", "completed", True),
        ("suspected noop", "suspected_noop", "completed", False),
        ("explicit refusal before dispatch", "refused", "skipped", False),
        ("action may have dispatched then probe failed", "unverifiable", "unavailable", False),
    ]
    decided = []
    for name, effect, observation, passive in rows:
        decided.append(
            {
                "case": name,
                "effect": effect,
                "observation": observation,
                "passive_success": passive,
                "typed": typed_choice(effect, observation, passive_success=passive),
                "naive": naive_choice(effect, observation, passive_success=passive),
            }
        )
    return decided


def naive_choice(effect: Effect, observation: Observation, *, passive_success: bool) -> Choice:
    if passive_success:
        return "continue"
    if effect in {"unverifiable", "suspected_noop"} or observation != "completed":
        return "continue"  # blind replay
    return "stop"

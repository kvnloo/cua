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


def naive_choice(effect: Effect, observation: Observation, *, passive_success: bool) -> Choice:
    if passive_success:
        return "continue"
    if effect in {"unverifiable", "suspected_noop"} or observation != "completed":
        return "continue"  # blind replay
    return "stop"

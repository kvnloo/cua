"""Postconditions for a toggle-then-confirm recipe. kvnloo/cua#42.

This file does not import the form-fill compiler. The predicates are different.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import Candidate


@dataclass(frozen=True)
class ToggleExpectation:
    kind: str
    token: str


def compile_toggle(candidate: Candidate, token: str) -> ToggleExpectation | None:
    if candidate.id in {"reobserve", "abstain"} or candidate.tool is None:
        return None
    if candidate.id == "toggle-setting":
        return ToggleExpectation("setting_equals", token)
    if candidate.id == "confirm-dialog":
        return ToggleExpectation("dialog_closed_equals", token)
    return None

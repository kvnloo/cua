"""Postconditions compiled when a jev-use candidate is built. kvnloo/cua#14.

The provider selects an id. It does not supply the expectation.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import Candidate


@dataclass(frozen=True)
class Expectation:
    kind: str
    token: str


def compile_expectation(candidate: Candidate, token: str) -> Expectation | None:
    if candidate.id in {"reobserve", "abstain"} or candidate.tool is None:
        return None
    if candidate.id == "type-verification-value":
        return Expectation("field_value_equals", token)
    if candidate.id == "submit-form":
        return Expectation("fixture_submitted_equals", token)
    return None


def provider_cannot_replace(compiled: Expectation, offered: Expectation | None) -> Expectation:
    return compiled

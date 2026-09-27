"""When jev-use may skip optional visual capture. kvnloo/cua#2.

This does not change the runner. A live A/B is a separate receipt.
"""

from __future__ import annotations

from core import Candidate

RESERVED = frozenset({"reobserve", "abstain"})


def semantic_executable(candidates: list[Candidate]) -> list[Candidate]:
    return [
        candidate
        for candidate in candidates
        if candidate.id not in RESERVED
        and candidate.tool is not None
        and candidate.capture_id is None
    ]


def needs_visual_capture(candidates: list[Candidate]) -> bool:
    """Visual capture stays on unless a semantic candidate can already execute."""
    return not semantic_executable(candidates)

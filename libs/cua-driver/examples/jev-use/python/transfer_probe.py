"""kvnloo/cua#49. A second harness that drops Candidate is not kept."""

from __future__ import annotations

from core import Candidate
from deterministic_fast_path import single_executable_candidate


def shipped_single_id() -> str | None:
    admitted = single_executable_candidate(
        [
            Candidate("only-action", "only", "browser_click", {}),
            Candidate("reobserve", "reobserve", None, {}),
        ]
    )
    return None if admitted is None else admitted.id


def shipped_two_executable() -> str | None:
    admitted = single_executable_candidate(
        [
            Candidate("first", "first", "browser_click", {}),
            Candidate("second", "second", "browser_type", {}),
        ]
    )
    return None if admitted is None else admitted.id


def comparison_rows() -> list[dict[str, str | None]]:
    return [
        {
            "concept": "one executable candidate",
            "shipped_result": shipped_single_id(),
            "second_harness": "deleted",
            "reason": "a plain dict drops frozen arguments",
        },
        {
            "concept": "two executable candidates",
            "shipped_result": shipped_two_executable(),
            "second_harness": "deleted",
            "reason": "copying the reserved-id rule into a dict adapter is a second implementation",
        },
    ]

"""Exact single-candidate admission for the jev-use caller.

This is an experiment for kvnloo/cua#4. It does not change the default chooser.
Reserved reobserve and abstain candidates are never executable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core import Candidate

RESERVED_CANDIDATE_IDS = frozenset({"reobserve", "abstain"})
FastPathRoute = Literal["fast-path", "chooser"]


@dataclass(frozen=True)
class FastPathEvidence:
    """Content-free route receipt for the fast-path experiment."""

    route: FastPathRoute
    executable_count: int
    candidate_id: str | None
    provider_called: bool


def _executable_candidates(candidates: list[Candidate]) -> list[Candidate]:
    return [
        candidate
        for candidate in candidates
        if candidate.id not in RESERVED_CANDIDATE_IDS and candidate.tool is not None
    ]


def explain_fast_path(
    candidates: list[Candidate],
    *,
    bound_completion_id: str | None = None,
) -> FastPathEvidence:
    """Explain whether a bound completion may act without a provider.

    One executable candidate is not authority to act. The provider is skipped
    only when the caller already names that exact candidate as the required
    completion of a locally proven obligation.
    """

    executable = _executable_candidates(candidates)
    if (
        bound_completion_id is not None
        and len(executable) == 1
        and executable[0].id == bound_completion_id
    ):
        return FastPathEvidence(
            route="fast-path",
            executable_count=1,
            candidate_id=executable[0].id,
            provider_called=False,
        )
    return FastPathEvidence(
        route="chooser",
        executable_count=len(executable),
        candidate_id=None,
        provider_called=True,
    )


def single_executable_candidate(
    candidates: list[Candidate],
    *,
    bound_completion_id: str | None = None,
) -> Candidate | None:
    """Return the bound completion, or None when the chooser must run."""

    evidence = explain_fast_path(candidates, bound_completion_id=bound_completion_id)
    if evidence.route != "fast-path" or evidence.candidate_id is None:
        return None
    return next(candidate for candidate in candidates if candidate.id == evidence.candidate_id)

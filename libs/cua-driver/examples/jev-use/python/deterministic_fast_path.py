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


def explain_fast_path(candidates: list[Candidate]) -> FastPathEvidence:
    """Explain whether the local rule would act without invoking a provider."""

    executable = _executable_candidates(candidates)
    if len(executable) == 1:
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


def single_executable_candidate(candidates: list[Candidate]) -> Candidate | None:
    """Return the only executable candidate, or None when the chooser must run.

    Executable means a candidate with a Driver tool whose id is not reserved.
    Zero or several executable candidates keep the decision with the chooser,
    including a chooser that would reobserve despite one apparent action.
    """

    evidence = explain_fast_path(candidates)
    if evidence.route != "fast-path" or evidence.candidate_id is None:
        return None
    return next(candidate for candidate in candidates if candidate.id == evidence.candidate_id)

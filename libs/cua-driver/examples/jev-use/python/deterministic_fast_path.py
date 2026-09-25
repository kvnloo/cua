"""Exact single-candidate admission for the jev-use caller.

This is an experiment for kvnloo/cua#4. It does not change the default chooser.
Reserved reobserve and abstain candidates are never executable.
"""

from __future__ import annotations

from core import Candidate

RESERVED_CANDIDATE_IDS = frozenset({"reobserve", "abstain"})


def single_executable_candidate(candidates: list[Candidate]) -> Candidate | None:
    """Return the only executable candidate, or None when the chooser must run.

    Executable means a candidate with a Driver tool whose id is not reserved.
    Zero or several executable candidates keep the decision with the chooser,
    including a chooser that would reobserve despite one apparent action.
    """

    executable = [
        candidate
        for candidate in candidates
        if candidate.id not in RESERVED_CANDIDATE_IDS and candidate.tool is not None
    ]
    if len(executable) != 1:
        return None
    return executable[0]

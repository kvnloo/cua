"""Caller routing from evidence already on this branch. kvnloo/cua#44.

Not called by run.py. Wave verdicts that are still missing do not switch the runner.
"""

from __future__ import annotations

from core import Candidate
from deterministic_fast_path import single_executable_candidate
from lazy_vision import needs_visual_capture


def route(candidates: list[Candidate], decision_kind: str) -> str:
    if decision_kind == "run":
        return "guarded-run"
    if decision_kind in {"reobserve", "abstain"}:
        return decision_kind
    admitted = single_executable_candidate(candidates)
    if admitted is not None and not needs_visual_capture(candidates):
        return "fast-path"
    if needs_visual_capture(candidates):
        return "chooser-with-visual"
    return "chooser"

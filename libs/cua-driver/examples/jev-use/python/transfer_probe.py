"""kvnloo/cua#49. A second harness that drops Candidate is not kept."""

from __future__ import annotations

from browser_revision import BrowserNode, StaleRefError, bind
from compiled_expectations import compile_expectation
from core import Candidate
from deterministic_fast_path import single_executable_candidate
from guarded_run import Decision, admit_guarded_run
from lazy_vision import needs_visual_capture


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


def _visual_needed() -> str:
    semantic = [Candidate("type-verification-value", "type", "browser_type", {})]
    return "false" if not needs_visual_capture(semantic) else "true"


def _compiled_kind() -> str | None:
    compiled = compile_expectation(
        Candidate("type-verification-value", "type", "browser_type", {}),
        "proof",
    )
    return None if compiled is None else compiled.kind


def _freshness() -> str:
    try:
        bind(BrowserNode("ref-submit", 2, "Submit"), "ref-submit", 1)
    except StaleRefError:
        return "stale refused"
    return "bound"


def _guarded() -> str:
    plan = admit_guarded_run(
        [
            Candidate("type-verification-value", "type", "browser_type", {}),
            Candidate("submit-form", "submit", "browser_click", {}),
        ],
        Decision("run", ("type-verification-value", "submit-form")),
        token="proof",
        submit_ref="ref-submit",
    )
    return "not admitted" if plan is None else plan.first.candidate_id


def comparison_rows() -> list[dict[str, str | None]]:
    return [
        {
            "concept": "observation modality",
            "shipped_result": _visual_needed(),
            "second_harness": "deleted",
            "reason": "needs_visual_capture reads jev-use Candidate.capture_id",
        },
        {
            "concept": "one executable candidate",
            "shipped_result": shipped_single_id(),
            "second_harness": "deleted",
            "reason": "a plain dict drops frozen arguments",
        },
        {
            "concept": "compiled postconditions",
            "shipped_result": _compiled_kind(),
            "second_harness": "deleted",
            "reason": "the compiler names jev-use fixture ids",
        },
        {
            "concept": "freshness",
            "shipped_result": _freshness(),
            "second_harness": "deleted",
            "reason": "bind is the browser ref rule, not a generic harness type",
        },
        {
            "concept": "guarded continuation",
            "shipped_result": _guarded(),
            "second_harness": "deleted",
            "reason": "the plan carries a submit ref that another harness does not have",
        },
    ]

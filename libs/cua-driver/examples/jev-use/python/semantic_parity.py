"""Fast-path and guarded-run corpus for kvnloo/cua#40.

Each output is the shipped caller function. The TypeScript module computes
the same cases. Neither module is imported by run.py.
"""

from __future__ import annotations

from core import Candidate
from compiled_expectations import compile_expectation
from deterministic_fast_path import explain_fast_path, single_executable_candidate
from guarded_run import (\n    Decision,\n    FreshObservation,\n    admit_guarded_run,\n    explain_second_child,\n)


def _candidate(candidate_id: str, tool: str | None, capture_id: str | None = None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {}, capture_id=capture_id)


def parity_corpus() -> list[dict[str, object]]:
    type_c = _candidate("type-verification-value", "browser_type")
    submit = _candidate("submit-form", "browser_click")
    reobserve = _candidate("reobserve", None)
    abstain = _candidate("abstain", None)
    visual = _candidate("visual-submit", "browser_click", "cap-1")
    visual_bare = _candidate("visual-submit", "browser_click")
    fresh = FreshObservation("proof", "ref-submit", "cap-2")
    rebound = FreshObservation("proof", "other-ref", "cap-2")
    missing_capture = FreshObservation("proof", "ref-submit", None)
    cases: list[tuple] = [
        (
            "one executable candidate",
            [type_c, reobserve],
            "single",
            ("type-verification-value",),
            "verified",
            fresh,
            type_c,
        ),
        (
            "reserved reobserve and abstain",
            [reobserve, abstain],
            "reobserve",
            (),
            "verified",
            fresh,
            reobserve,
        ),
        (
            "provider would reobserve",
            [type_c, reobserve],
            "reobserve",
            (),
            "verified",
            fresh,
            type_c,
        ),
        (
            "guarded continuation admitted",
            [type_c, submit],
            "run",
            ("type-verification-value", "submit-form"),
            "verified",
            fresh,
            submit,
        ),
        (
            "guarded continuation refused",
            [type_c, submit],
            "single",
            ("type-verification-value",),
            "verified",
            fresh,
            submit,
        ),
        (
            "fresh target",
            [type_c, submit],
            "run",
            ("type-verification-value", "submit-form"),
            "verified",
            fresh,
            submit,
        ),
        (
            "stale observation",
            [type_c, submit],
            "run",
            ("type-verification-value", "submit-form"),
            "verified",
            None,
            submit,
        ),
        (
            "rebound ref",
            [type_c, submit],
            "run",
            ("type-verification-value", "submit-form"),
            "verified",
            rebound,
            submit,
        ),
        (
            "missing capture",
            [type_c, submit],
            "run",
            ("type-verification-value", "submit-form"),
            "verified",
            missing_capture,
            submit,
        ),
        (
            "postcondition refuted",
            [type_c, submit],
            "run",
            ("type-verification-value", "submit-form"),
            "refuted",
            fresh,
            submit,
        ),
        (
            "postcondition unknown",
            [type_c, submit],
            "run",
            ("type-verification-value", "submit-form"),
            "unknown",
            fresh,
            submit,
        ),
        (
            "visual submit expectation",
            [visual, reobserve],
            "single",
            ("visual-submit",),
            "verified",
            fresh,
            visual,
        ),
        (
            "visual submit without capture",
            [visual_bare, reobserve],
            "single",
            ("visual-submit",),
            "verified",
            fresh,
            visual_bare,
        ),
    ]
    rows: list[dict[str, object]] = []
    for name, candidates, kind, child_ids, status, observation, focus in cases:
        fast_evidence = explain_fast_path(candidates)
        exact = single_executable_candidate(candidates)
        plan = admit_guarded_run(
            candidates,
            Decision(kind, child_ids),
            token="proof",
            submit_ref="ref-submit",
        )
        second_evidence = (
            None if plan is None else explain_second_child(status, observation, plan)
        )
        second = False if second_evidence is None else second_evidence.allowed
        compiled = compile_expectation(focus, "proof")
        rows.append(
            {
                "case": name,
                "fast_path_id": None if exact is None else exact.id,
                "fast_path_route": fast_evidence.route,
                "executable_count": fast_evidence.executable_count,
                "provider_called": fast_evidence.provider_called,
                "run_admitted": plan is not None,
                "second_dispatch": second,
                "second_reason": None if second_evidence is None else second_evidence.reason,
                "expectation_kind": None if compiled is None else compiled.kind,
            }
        )
    return rows

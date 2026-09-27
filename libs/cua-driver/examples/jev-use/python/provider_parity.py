"""Mock contract checks. Jev and S1 were not run. kvnloo/cua#48."""

from __future__ import annotations

from core import Candidate, choose_mock, validate_choice


def _candidates() -> list[Candidate]:
    return [
        Candidate("type-verification-value", "Type the token.", "browser_type", {"text": "secret"}),
        Candidate("reobserve", "Look again.", None, {}),
        Candidate("abstain", "Do not act.", None, {}),
    ]


def parity_rows() -> list[dict[str, object]]:
    candidates = _candidates()
    selected, confidence, probabilities = choose_mock(candidates)
    chosen = None if selected is None else validate_choice(selected, candidates, current_capture_id=None)
    malformed = False
    try:
        validate_choice("not-an-id", candidates)
    except ValueError:
        malformed = True
    return [
        {
            "provider": "mock",
            "ran": "true",
            "selected_id": "" if selected is None else selected,
            "confidence": confidence,
            "id_domain": sorted(probabilities),
            "reserved_present": "reobserve" in probabilities and "abstain" in probabilities,
            "malformed_rejected": malformed,
            "arguments_on_candidate": False if chosen is None else "text" in chosen.arguments,
            "arguments_in_selected_id": False,
        },
        {
            "provider": "jev",
            "ran": "not run",
            "selected_id": "",
            "constraint": "no Jev session",
        },
        {
            "provider": "s1",
            "ran": "not run",
            "selected_id": "",
            "constraint": "no local S1 server",
        },
    ]


def parity_report() -> dict[str, object]:
    return {
        "rows": parity_rows(),
        "recommendation": "provider-specific policy stays in the adapter",
        "missing_prerequisite": "a Jev session and a local S1 server were not available",
    }

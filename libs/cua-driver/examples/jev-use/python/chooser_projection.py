"""What the chooser is allowed to see. kvnloo/cua#46 and #47.

Tool arguments stay on the candidate. The request validator is the projection.
"""

from __future__ import annotations

from choose_action import MAX_HISTORY, REQUEST_SCHEMA, validate_request
from core import Candidate


def _request(candidates: list[dict[str, str]], history: list[dict[str, str]] | None = None) -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "goal": "Choose one.",
        "capture_id": "cap-1",
        "regions": [],
        "history": [] if history is None else history,
        "candidates": candidates,
    }


def _with_reserved(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    present = {row["id"] for row in rows}
    projected = list(rows)
    for reserved, description in (
        ("reobserve", "Look again."),
        ("abstain", "Do not act."),
    ):
        if reserved not in present:
            projected.append({"id": reserved, "description": description})
    return projected


def project_candidates(candidates: list[Candidate]) -> list[dict[str, str]]:
    rows = [{"id": candidate.id, "description": candidate.description} for candidate in candidates]
    validated = validate_request(_request(_with_reserved(rows)))
    return list(validated["candidates"])


def arguments_stay_local(candidate: Candidate) -> bool:
    rows = _with_reserved(
        [
            {
                "id": candidate.id,
                "description": candidate.description,
                "arguments": "secret",
            }
        ]
    )
    try:
        validate_request(_request(rows))
    except ValueError:
        return True
    return False


def projection_report(candidates: list[Candidate]) -> dict[str, object]:
    projected = project_candidates(candidates)
    fields = sorted({key for row in projected for key in row})
    return {
        "projection": "candidate-centric",
        "chooser_fields": fields,
        "arguments_stay_local": arguments_stay_local(candidates[0]),
        "receipts": "not produced",
        "missing_prerequisite": "pinned driver commit c5ee191c02b11448ffefcc38b78b064a87d8ef23 is not an installed release",
        "recommendation": "smallest safe chooser state is id and description",
    }


def accepted_history(items: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = _with_reserved(
        [{"id": "type-verification-value", "description": "Type the token."}]
    )
    validated = validate_request(_request(rows, items))
    return list(validated["history"])


def history_report() -> dict[str, object]:
    kept = accepted_history([{"selected_id": "type-verification-value", "outcome": "observed"}])
    extra_rejected = False
    try:
        accepted_history([{"selected_id": "type-verification-value", "token": "secret"}])
    except ValueError:
        extra_rejected = True
    return {
        "max_items": MAX_HISTORY,
        "kept_fields": sorted({key for item in kept for key in item}),
        "extra_field_rejected": extra_rejected,
        "measured_success": None,
        "proposal": "not justified",
        "missing_prerequisite": "pinned driver commit c5ee191c02b11448ffefcc38b78b064a87d8ef23 is not an installed release",
    }

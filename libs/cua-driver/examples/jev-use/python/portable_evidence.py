from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


_SCHEMA = "z0.evidence.v0"
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_OUTCOME_MAP = {
    "verified": "pass",
    "refuted": "fail",
    "abstained": "abstain",
    "unknown": "unknown",
}


def load_events(path: str | Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def normalize_events(
    events: Iterable[dict[str, Any]],
    *,
    revision: str,
    subject_id: str = "jev-use",
) -> dict[str, Any]:
    if not _SHA.match(revision):
        raise ValueError("revision must be a full 40-character Git SHA")

    rows = list(events)
    final = next(
        (
            row
            for row in reversed(rows)
            if row.get("event") == "outcome"
            and row.get("outcome") in _OUTCOME_MAP
        ),
        None,
    )

    if final is None:
        outcome = "unknown"
        final_native = None
        evidence_result = "unknown"
    else:
        final_native = str(final["outcome"])
        outcome = _OUTCOME_MAP[final_native]
        evidence_result = {
            "pass": "pass",
            "fail": "fail",
            "abstain": "unknown",
            "unknown": "unknown",
        }[outcome]

    backend = None
    for row in reversed(rows):
        value = row.get("backend")
        if isinstance(value, str) and value:
            backend = value
            break

    evidence = [
        {
            "id": "final-outcome",
            "kind": "cua-driver-outcome",
            "result": evidence_result,
            "details": {
                "native_outcome": final_native,
                "backend": backend,
                "event_count": len(rows),
            },
        }
    ]

    invariants = [
        {
            "name": "abstention-is-not-success",
            "result": "pass" if outcome == "abstain" else "unknown",
            "evidence_refs": ["final-outcome"],
        }
    ]

    return {
        "schema": _SCHEMA,
        "producer": {
            "name": "cua",
            "repository": "kvnloo/cua",
            "revision": revision,
        },
        "subject": {
            "kind": "computer-use-run",
            "id": subject_id,
        },
        "outcome": outcome,
        "evidence": evidence,
        "invariants": invariants,
    }

"""Caller fallback against a fake session. kvnloo/cua#28.

These rows call the shipped helper. They are not a live current-vs-old driver trial.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core import Candidate
from lazy_vision import needs_visual_capture
from run import Driver, optional_visual_observation, supports_capture_bound_click

PIN = "c5ee191c02b11448ffefcc38b78b064a87d8ef23"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "parse-visual-regions-submit-v1.json"


class FakeSession:
    def __init__(self, responses=None) -> None:
        self.calls = []
        self.responses = list(responses or [])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        structured = self.responses.pop(0) if self.responses else {"status": "ok"}
        return SimpleNamespace(isError=False, structuredContent=structured)


def _row(case: str, session: FakeSession, outcome: str, path: str) -> dict[str, object]:
    return {
        "case": case,
        "calls": len(session.calls),
        "retries": 0,
        "path": path,
        "outcome": outcome,
        "gains_authority": False,
        "live_driver": "not used",
        "pinned_upstream": PIN,
    }


async def decision_rows() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    semantic = [Candidate("type-verification-value", "type", "browser_type", {})]
    skipped = FakeSession()
    rows = [
        _row(
            "semantic executable candidate",
            skipped,
            "not called" if not needs_visual_capture(semantic) else "called",
            "skip visual",
        )
    ]

    both = FakeSession(responses=[{"capture_id": "capture-submit"}, payload])
    visual = await optional_visual_observation(
        Driver(both, "jev-test"),
        7,
        9,
        {"get_window_state", "parse_visual_regions"},
        True,
    )
    tree_flag = both.calls[0][1].get("include_accessibility_tree") if both.calls else None
    both_row = _row(
        "both selectors advertised",
        both,
        "none" if visual is None else visual.capture_id,
        "visual",
    )
    both_row["include_accessibility_tree"] = tree_flag
    rows.append(both_row)

    missing = FakeSession()
    missing_result = await optional_visual_observation(
        Driver(missing, "jev-test"),
        7,
        9,
        {"get_window_state"},
        True,
    )
    rows.append(
        _row(
            "older schema missing parse_visual_regions",
            missing,
            "none" if missing_result is None else "observation",
            "preserve old observation",
        )
    )

    subset = FakeSession()
    click = SimpleNamespace(name="click", inputSchema={"properties": {"x": {}}})
    bound = supports_capture_bound_click([click])
    subset_result = await optional_visual_observation(
        Driver(subset, "jev-test"),
        7,
        9,
        {"get_window_state", "parse_visual_regions"},
        bound,
    )
    subset_row = _row(
        "platform subset without capture_id",
        subset,
        "none" if subset_result is None else "observation",
        "preserve old observation",
    )
    subset_row["capture_bound_click"] = bound
    rows.append(subset_row)

    refused = FakeSession(responses=[{"status": "refused", "refusal": "permission"}])
    refused_result = await optional_visual_observation(
        Driver(refused, "jev-test"),
        7,
        9,
        {"get_window_state", "parse_visual_regions"},
        True,
    )
    rows.append(
        _row(
            "permission refusal",
            refused,
            "none" if refused_result is None else "observation",
            "refusal is not a retry",
        )
    )

    malformed = FakeSession(responses=[{"capture_id": 5}])
    malformed_result = await optional_visual_observation(
        Driver(malformed, "jev-test"),
        7,
        9,
        {"get_window_state", "parse_visual_regions"},
        True,
    )
    rows.append(
        _row(
            "malformed capture id",
            malformed,
            "none" if malformed_result is None else "observation",
            "malformed",
        )
    )
    return rows

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import build_candidates
from observation import (
    ObservationLedger,
    ObservationRecord,
    has_actionable_candidate,
    needs_visual_observation,
)


def snapshot(field_value: str | None, with_button: bool) -> dict:
    refs = [
        {
            "role": "textbox",
            "name": "verification value",
            "ref": "r1",
            "value": field_value,
        }
    ]
    if with_button:
        refs.append({"role": "button", "name": "Submit", "ref": "r2"})
    return {"target_id": "t", "tab_id": "tab", "refs": refs}


class ObservationLedgerTest(unittest.TestCase):
    def test_records_entries_in_order(self) -> None:
        ledger = ObservationLedger()
        ledger.record(ObservationRecord(step=1, kind="snapshot", latency_ms=12.5))
        ledger.record(
            ObservationRecord(step=1, kind="visual", latency_ms=40.0, capture_id="cap-1")
        )
        entries = ledger.entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].kind, "snapshot")
        self.assertEqual(entries[1].capture_id, "cap-1")

    def test_counts_and_sums_per_kind(self) -> None:
        ledger = ObservationLedger()
        ledger.record(ObservationRecord(step=1, kind="snapshot", latency_ms=10.0))
        ledger.record(ObservationRecord(step=1, kind="visual", latency_ms=30.0))
        ledger.record(ObservationRecord(step=2, kind="snapshot", latency_ms=20.0))
        self.assertEqual(ledger.count("snapshot"), 2)
        self.assertEqual(ledger.count("visual"), 1)
        self.assertAlmostEqual(ledger.total_latency_ms("visual"), 30.0)
        self.assertAlmostEqual(ledger.total_latency_ms(), 60.0)


class NeedsVisualObservationTest(unittest.TestCase):
    def test_skips_visual_when_snapshot_yields_action(self) -> None:
        # dom-complete: field needs typing -> type-verification-value is actionable
        candidates = build_candidates(snapshot("other", True), "expected")
        self.assertTrue(has_actionable_candidate(candidates))
        self.assertFalse(needs_visual_observation(candidates))

    def test_skips_visual_when_submit_ready(self) -> None:
        # dom-complete: field already holds the token, button present
        candidates = build_candidates(snapshot("expected", True), "expected")
        self.assertTrue(has_actionable_candidate(candidates))
        self.assertFalse(needs_visual_observation(candidates))

    def test_requests_visual_for_fallback(self) -> None:
        # visual-fallback: field holds the token but no DOM button ->
        # only reserved candidates, the visual path is load-bearing
        candidates = build_candidates(snapshot("expected", False), "expected")
        self.assertFalse(has_actionable_candidate(candidates))
        self.assertTrue(needs_visual_observation(candidates))

    def test_reserved_candidates_alone_do_not_trigger_visual(self) -> None:
        # empty snapshot -> build_candidates returns only reobserve/abstain
        candidates = build_candidates(
            {"target_id": "t", "tab_id": "tab", "refs": []}, "expected"
        )
        self.assertTrue(all(candidate.tool is None for candidate in candidates))
        self.assertTrue(needs_visual_observation(candidates))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from core import Candidate
from lazy_vision import needs_visual_capture


def candidate(candidate_id: str, tool: str | None, capture_id: str | None = None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {}, capture_id=capture_id)


class LazyVisionTest(unittest.TestCase):
    def test_semantic_success_skips_optional_visual_capture(self) -> None:
        calls = {"visual": 0}
        candidates = [
            candidate("type-verification-value", "browser_type"),
            candidate("reobserve", None),
            candidate("abstain", None),
        ]
        if needs_visual_capture(candidates):
            calls["visual"] += 1
        self.assertEqual(calls["visual"], 0)

    def test_visual_fallback_still_captures(self) -> None:
        candidates = [
            candidate("submit-form", "click", capture_id="cap-1"),
            candidate("reobserve", None),
        ]
        self.assertTrue(needs_visual_capture(candidates))

    def test_no_executable_candidate_still_captures(self) -> None:
        self.assertTrue(needs_visual_capture([candidate("reobserve", None), candidate("abstain", None)]))


if __name__ == "__main__":
    unittest.main()

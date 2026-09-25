from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from caller_route import route
from core import Candidate


def candidate(candidate_id: str, tool: str | None, capture_id: str | None = None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {}, capture_id=capture_id)


class CallerRouteTest(unittest.TestCase):
    def test_table(self) -> None:
        semantic = [candidate("type-verification-value", "browser_type"), candidate("reobserve", None)]
        visual = [candidate("submit-form", "click", "cap"), candidate("reobserve", None)]
        two = [candidate("click-a", "click"), candidate("click-b", "click"), candidate("reobserve", None)]
        self.assertEqual(route(semantic, "single"), "fast-path")
        self.assertEqual(route(visual, "single"), "chooser-with-visual")
        self.assertEqual(route(two, "single"), "chooser")
        self.assertEqual(route(semantic, "run"), "guarded-run")
        self.assertEqual(route(semantic, "reobserve"), "reobserve")
        self.assertEqual(route(semantic, "abstain"), "abstain")


if __name__ == "__main__":
    unittest.main()

"""The extraction report matches a live scan. kvnloo/cua#39."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from extraction_inventory import inventory

ROOT = Path(__file__).resolve().parents[6]


class ExtractionInventoryTest(unittest.TestCase):
    def test_report_matches_the_live_scan(self) -> None:
        found = inventory(ROOT)
        path = ROOT / "scripts" / "repro" / "handoff" / "issue-39-inventory.json"
        recorded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(recorded, found)
        for row in found:
            for path in row["production_call_sites"]:
                self.assertTrue(str(path).startswith("libs/cua-driver/examples/jev-use/"))
            self.assertEqual(row["independent_harnesses"], [])
            self.assertEqual(row["disposition"], "recipe-local")


if __name__ == "__main__":
    unittest.main()

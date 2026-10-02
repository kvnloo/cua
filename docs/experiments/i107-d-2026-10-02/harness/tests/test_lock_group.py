"""Unit test: a lock group is consecutive schedule blocks (PREREG-AMENDMENT-1)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_d as R  # noqa: E402


class LockGroupTest(unittest.TestCase):
    def test_consecutive_blocks_resolve_in_order(self) -> None:
        names = ["cmpd-b1", "cmpd-b2", "cmpd-b3"]
        self.assertEqual([b["block"] for b in R.resolve_blocks(names)], names)
        self.assertEqual([b["block"] for b in R.resolve_blocks(["smoke"])], ["smoke"])

    def test_gaps_or_reordering_are_refused(self) -> None:
        for names in (["cmpd-b1", "cmpd-b3"], ["cmpd-b2", "cmpd-b1"]):
            with self.subTest(names=names), self.assertRaises(SystemExit):
                R.resolve_blocks(names)


if __name__ == "__main__":
    unittest.main()

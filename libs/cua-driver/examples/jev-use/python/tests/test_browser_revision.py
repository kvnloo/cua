from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from browser_revision import BrowserNode, StaleRefError, bind, transition_rows


class BrowserRevisionTest(unittest.TestCase):
    def test_same_generation_binds(self) -> None:
        node = BrowserNode("ref-1", 3, "Submit")
        self.assertIs(bind(node, "ref-1", 3), node)

    def test_transition_rows_come_from_bind(self) -> None:
        rows = {row["event"]: row for row in transition_rows()}
        self.assertEqual(rows["same ref and generation"]["dispatch"], "allowed")
        self.assertEqual(rows["same label, new generation"]["next"], "stale")
        self.assertEqual(rows["ref missing"]["refusal"], "ref does not match the current node generation")
        current = BrowserNode("ref-submit", 2, "Submit")
        with self.assertRaises(StaleRefError):
            bind(current, "ref-submit", 1)

    def test_replacement_with_the_same_label_does_not_bind(self) -> None:
        current = BrowserNode("ref-2", 4, "Submit")
        with self.assertRaises(StaleRefError):
            bind(current, "ref-1", 3)


if __name__ == "__main__":
    unittest.main()

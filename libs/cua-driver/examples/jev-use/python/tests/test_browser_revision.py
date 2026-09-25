from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from browser_revision import BrowserNode, StaleRefError, bind


class BrowserRevisionTest(unittest.TestCase):
    def test_same_generation_binds(self) -> None:
        node = BrowserNode("ref-1", 3, "Submit")
        self.assertIs(bind(node, "ref-1", 3), node)

    def test_replacement_with_the_same_label_does_not_bind(self) -> None:
        current = BrowserNode("ref-2", 4, "Submit")
        with self.assertRaises(StaleRefError):
            bind(current, "ref-1", 3)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from walk_budget_owner import WalkSplit


class WalkBudgetOwnerTest(unittest.TestCase):
    def test_setup_is_not_a_reason_to_add_another_budget(self) -> None:
        self.assertIn("outside WalkBudget", WalkSplit(800, 50, 20).owner())

    def test_one_native_call_needs_its_own_timeout(self) -> None:
        self.assertIn("per-request timeout", WalkSplit(10, 40, 900).owner())

    def test_walk_admission_stays_on_the_shared_budget(self) -> None:
        self.assertIn("WalkBudget already owns", WalkSplit(10, 400, 30).owner())


if __name__ == "__main__":
    unittest.main()

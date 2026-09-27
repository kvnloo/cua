from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from guarded_run import FreshObservation, GuardedRunPlan, PlannedChild
from run_length import execute_capped, recommend_cap, wasted_after_stop


def plan() -> GuardedRunPlan:
    return GuardedRunPlan(
        PlannedChild("type-verification-value", "browser_type"),
        PlannedChild("submit-form", "browser_click"),
        "proof",
        "ref-submit",
    )


class RunLengthTest(unittest.TestCase):
    def test_length_four_still_stops_when_the_guard_fails(self) -> None:
        ran = execute_capped(plan(), ["refuted"], [FreshObservation("proof", "ref-submit", "c2")], 4)
        self.assertEqual(ran, 1)
        self.assertEqual(wasted_after_stop(4, ran), 3)

    def test_length_two_runs_the_second_child_when_fresh(self) -> None:
        ran = execute_capped(plan(), ["verified"], [FreshObservation("proof", "ref-submit", "c2")], 2)
        self.assertEqual(ran, 2)

    def test_most_early_stops_do_not_justify_embedding_four(self) -> None:
        self.assertIn("cap at 2", recommend_cap(stop_at_first_child=7, runs=10))


if __name__ == "__main__":
    unittest.main()

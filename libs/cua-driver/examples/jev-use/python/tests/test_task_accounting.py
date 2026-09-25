from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from task_accounting import TrialClocks, outcome_time, phase0_spans_cover_outcome, residual_ms


class TaskAccountingTest(unittest.TestCase):
    def test_runner_lifetime_is_not_the_verified_outcome(self) -> None:
        trial = TrialClocks(cold_setup_ms=800, verified_outcome_ms=1200, runner_lifetime_ms=4000, named_span_ms=1100)
        self.assertEqual(outcome_time(trial), 1200)
        self.assertNotEqual(outcome_time(trial), trial.runner_lifetime_ms)
        self.assertEqual(residual_ms(trial), 100)
        self.assertTrue(phase0_spans_cover_outcome(trial))

    def test_large_residual_fails_the_phase0_gate(self) -> None:
        trial = TrialClocks(0, 1000, 1000, 400)
        self.assertFalse(phase0_spans_cover_outcome(trial))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from goal_gates import accept_completion, use_model_done_gate


class GoalGateTest(unittest.TestCase):
    def test_fixture_oracle_does_not_ask_the_model_if_done(self) -> None:
        self.assertFalse(use_model_done_gate(has_independent_oracle=True))
        self.assertFalse(accept_completion(model_says_done=True, oracle_succeeded=False))
        self.assertTrue(accept_completion(model_says_done=False, oracle_succeeded=True))

    def test_task_without_an_oracle_can_use_the_model_gate(self) -> None:
        self.assertTrue(use_model_done_gate(has_independent_oracle=False))
        self.assertTrue(accept_completion(model_says_done=True, oracle_succeeded=None))


if __name__ == "__main__":
    unittest.main()

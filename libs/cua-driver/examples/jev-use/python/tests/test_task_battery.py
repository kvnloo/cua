from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from core import Candidate
from task_battery import evaluate, promote_globally


def candidate(candidate_id: str, tool: str | None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {})


class TaskBatteryTest(unittest.TestCase):
    def test_form_fill_admits_and_ambiguous_task_does_not(self) -> None:
        form = evaluate(
            "form-fill",
            [candidate("type-verification-value", "browser_type"), candidate("reobserve", None)],
        )
        modal = evaluate(
            "ambiguous-modal",
            [
                candidate("click-a", "click"),
                candidate("click-b", "click"),
                candidate("reobserve", None),
            ],
        )
        self.assertTrue(form.fast_path)
        self.assertEqual(form.decisions, 0)
        self.assertFalse(modal.fast_path)
        self.assertEqual(modal.decisions, 1)
        self.assertFalse(promote_globally([form, modal]))


if __name__ == "__main__":
    unittest.main()

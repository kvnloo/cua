"""Two recipes stay separate. kvnloo/cua#42 and #43."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from compiled_expectations import compile_expectation
from core import Candidate
from guarded_run import FreshObservation, GuardedRunPlan, PlannedChild, second_child_allowed
from toggle_expectations import compile_toggle
from toggle_run import admit_toggle, second_toggle_allowed


def candidate(candidate_id: str, tool: str) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {})


class ToggleRecipeTest(unittest.TestCase):
    def test_toggle_predicates_are_not_the_form_predicates(self) -> None:
        form = compile_expectation(candidate("submit-form", "browser_click"), "proof")
        toggle = compile_toggle(candidate("confirm-dialog", "browser_click"), "closed")
        assert form is not None and toggle is not None
        self.assertNotEqual(form.kind, toggle.kind)
        self.assertIsNone(compile_toggle(candidate("reobserve", "browser_click"), "closed"))
        self.assertEqual(toggle.kind, "dialog_closed_equals")

    def test_toggle_second_child_uses_a_boolean_not_a_submit_ref(self) -> None:
        plan = admit_toggle("run", ("toggle-setting", "confirm-dialog"))
        assert plan is not None
        self.assertTrue(second_toggle_allowed("verified", True))
        self.assertFalse(second_toggle_allowed("verified", False))
        self.assertFalse(second_toggle_allowed("unknown", True))
        form = GuardedRunPlan(
            PlannedChild("type-verification-value", "browser_type"),
            PlannedChild("submit-form", "browser_click"),
            "proof",
            "ref-submit",
        )
        self.assertFalse(
            second_child_allowed("verified", FreshObservation("proof", "other", "cap"), form)
        )
        self.assertIsNone(admit_toggle("run", ("type-verification-value", "submit-form")))


if __name__ == "__main__":
    unittest.main()

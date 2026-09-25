from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from compiled_expectations import Expectation, compile_expectation, provider_cannot_replace
from core import Candidate
from guarded_run import Decision, FreshObservation, admit_guarded_run, second_child_allowed


def candidate(candidate_id: str, tool: str | None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {})


class CompiledExpectationTest(unittest.TestCase):
    def test_type_and_submit_compile_stable_expectations(self) -> None:
        typed = compile_expectation(candidate("type-verification-value", "browser_type"), "proof")
        submit = compile_expectation(candidate("submit-form", "browser_click"), "proof")
        self.assertEqual(typed, Expectation("field_value_equals", "proof"))
        self.assertEqual(submit, Expectation("fixture_submitted_equals", "proof"))
        self.assertIsNone(compile_expectation(candidate("reobserve", None), "proof"))

    def test_provider_output_does_not_replace_the_compiled_expectation(self) -> None:
        compiled = Expectation("field_value_equals", "proof")
        offered = Expectation("field_value_equals", "attacker")
        self.assertEqual(provider_cannot_replace(compiled, offered), compiled)

    def test_failed_postcondition_does_not_authorize_the_next_child(self) -> None:
        plan = admit_guarded_run(
            [
                candidate("type-verification-value", "browser_type"),
                candidate("submit-form", "browser_click"),
            ],
            Decision("run", ("type-verification-value", "submit-form")),
            token="proof",
            submit_ref="ref-submit",
        )
        assert plan is not None
        self.assertFalse(
            second_child_allowed("unknown", FreshObservation("proof", "ref-submit", "cap"), plan)
        )


if __name__ == "__main__":
    unittest.main()

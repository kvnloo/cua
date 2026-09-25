from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from browser_revision import BrowserNode, StaleRefError
from compiled_expectations import (
    Expectation,
    accept_if_bound,
    compile_expectation,
    provider_cannot_replace,
)
from core import Candidate
from guarded_run import Decision, FreshObservation, admit_guarded_run, second_child_allowed


def candidate(candidate_id: str, tool: str | None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {})


class CompiledExpectationTest(unittest.TestCase):
    def test_shared_fixture_matches_compile_expectation(self) -> None:
        path = Path(__file__).resolve().parents[6] / "scripts/repro/handoff/issue-40-fixture.json"
        for row in json.loads(path.read_text(encoding="utf-8")):
            built = Candidate(
                row["id"],
                row["id"],
                row["tool"],
                {},
                capture_id=row.get("capture_id"),
            )
            compiled = compile_expectation(built, row["token"])
            if row["expect"] is None:
                self.assertIsNone(compiled)
            else:
                self.assertEqual(compiled.kind, row["expect"]["kind"])
                self.assertEqual(compiled.token, row["expect"]["token"])

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
        fresh = FreshObservation("proof", "ref-submit", "cap")
        self.assertFalse(second_child_allowed("unknown", fresh, plan))
        self.assertFalse(second_child_allowed("refuted", fresh, plan))

    def test_stale_ref_refuses_before_the_expectation_can_succeed(self) -> None:
        compiled = compile_expectation(
            Candidate("visual-submit", "visual-submit", "browser_click", {}, capture_id="cap-1"),
            "proof",
        )
        assert compiled is not None
        stale = BrowserNode("ref-submit", 2, "Submit")
        with self.assertRaises(StaleRefError):
            accept_if_bound(stale, "ref-submit", 1, compiled)
        current = BrowserNode("ref-submit", 1, "Submit")
        self.assertEqual(accept_if_bound(current, "ref-submit", 1, compiled), compiled)

    def test_visual_submit_without_a_capture_has_no_expectation(self) -> None:
        bare = Candidate("visual-submit", "visual-submit", "browser_click", {})
        self.assertIsNone(compile_expectation(bare, "proof"))


if __name__ == "__main__":
    unittest.main()

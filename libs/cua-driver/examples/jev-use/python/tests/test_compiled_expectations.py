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
    fixture_rows,
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

    def test_python_and_typescript_agree_on_the_corpus(self) -> None:
        import subprocess

        from semantic_parity import parity_corpus

        root = Path(__file__).resolve().parents[6]
        recorded = json.loads((root / "scripts/repro/handoff/issue-40-semantic.json").read_text(encoding="utf-8"))
        python_rows = parity_corpus()
        self.assertEqual(recorded, python_rows)
        typescript = root / "libs/cua-driver/examples/jev-use/typescript"
        completed = subprocess.run(
            [
                "node",
                "--experimental-strip-types",
                "--input-type=module",
                "-e",
                "import { parityCorpus } from './semantic_parity.ts'; process.stdout.write(JSON.stringify(parityCorpus()));",
            ],
            cwd=typescript,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(python_rows, json.loads(completed.stdout))
        by_case = {row["case"]: row for row in python_rows}
        self.assertEqual(by_case["one executable candidate"]["fast_path_id"], "type-verification-value")
        self.assertIsNone(by_case["reserved reobserve and abstain"]["fast_path_id"])
        self.assertEqual(by_case["provider would reobserve"]["fast_path_id"], "type-verification-value")
        self.assertFalse(by_case["provider would reobserve"]["run_admitted"])
        self.assertTrue(by_case["guarded continuation admitted"]["second_dispatch"])
        self.assertFalse(by_case["guarded continuation refused"]["run_admitted"])
        self.assertFalse(by_case["stale observation"]["second_dispatch"])
        self.assertFalse(by_case["rebound ref"]["second_dispatch"])
        self.assertFalse(by_case["missing capture"]["second_dispatch"])
        self.assertFalse(by_case["postcondition refuted"]["second_dispatch"])
        self.assertFalse(by_case["postcondition unknown"]["second_dispatch"])
        self.assertIsNone(by_case["visual submit without capture"]["expectation_kind"])

    def test_parity_report_is_the_compiled_fixture(self) -> None:
        root = Path(__file__).resolve().parents[6]
        payload = json.loads((root / "scripts/repro/handoff/issue-40-fixture.json").read_text(encoding="utf-8"))
        recorded = json.loads((root / "scripts/repro/handoff/issue-40-parity.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, fixture_rows(payload))
        by_id = {row["id"]: row for row in recorded}
        self.assertEqual(by_id["type-verification-value"]["kind"], "field_value_equals")
        self.assertEqual(by_id["visual-submit"]["kind"], "fixture_submitted_equals")
        self.assertIsNone(by_id["reobserve"]["kind"])


if __name__ == "__main__":
    unittest.main()

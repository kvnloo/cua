from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from core import Candidate
from deterministic_fast_path import single_executable_candidate


def candidate(candidate_id: str, tool: str | None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {})


def reserved() -> list[Candidate]:
    return [candidate("reobserve", None), candidate("abstain", None)]


class DeterministicFastPathTest(unittest.TestCase):
    def test_one_executable_candidate_is_admitted(self) -> None:
        admitted = single_executable_candidate(
            [candidate("type-verification-value", "browser_type"), *reserved()]
        )
        self.assertIsNotNone(admitted)
        assert admitted is not None
        self.assertEqual(admitted.id, "type-verification-value")

    def test_submit_candidate_is_admitted(self) -> None:
        admitted = single_executable_candidate(
            [candidate("submit-form", "browser_click"), *reserved()]
        )
        self.assertIsNotNone(admitted)
        assert admitted is not None
        self.assertEqual(admitted.tool, "browser_click")

    def test_two_executable_candidates_call_the_chooser(self) -> None:
        self.assertIsNone(
            single_executable_candidate(
                [
                    candidate("type-verification-value", "browser_type"),
                    candidate("submit-form", "browser_click"),
                    *reserved(),
                ]
            )
        )

    def test_reserved_only_calls_the_chooser(self) -> None:
        self.assertIsNone(single_executable_candidate(reserved()))

    def test_reserved_ids_are_not_executable_even_with_a_tool(self) -> None:
        self.assertIsNone(
            single_executable_candidate(
                [candidate("reobserve", "browser_snapshot"), candidate("abstain", "noop")]
            )
        )

    def test_rule_acts_when_a_chooser_would_reobserve(self) -> None:
        candidates = [candidate("submit-form", "browser_click"), *reserved()]
        admitted = single_executable_candidate(candidates)
        chooser_choice = "reobserve"
        self.assertEqual(getattr(admitted, "id", None), "submit-form")
        self.assertNotEqual(chooser_choice, getattr(admitted, "id", None))


if __name__ == "__main__":
    unittest.main()

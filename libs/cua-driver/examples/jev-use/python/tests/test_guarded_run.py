from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from core import Candidate
from guarded_run import (\n    Decision,\n    FreshObservation,\n    admit_guarded_run,\n    explain_second_child,\n    second_child_allowed,\n)


def candidate(candidate_id: str, tool: str | None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {})


def pool() -> list[Candidate]:
    return [
        candidate("type-verification-value", "browser_type"),
        candidate("submit-form", "browser_click"),
        candidate("reobserve", None),
        candidate("abstain", None),
    ]


def plan():
    return admit_guarded_run(
        pool(),
        Decision("run", ("type-verification-value", "submit-form")),
        token="proof",
        submit_ref="ref-submit",
    )


class GuardedRunTest(unittest.TestCase):
    def test_run_decision_admits_two_children(self) -> None:
        admitted = plan()
        self.assertIsNotNone(admitted)
        assert admitted is not None
        self.assertEqual(
            (admitted.first.candidate_id, admitted.second.candidate_id),
            ("type-verification-value", "submit-form"),
        )

    def test_single_action_choice_is_not_a_run(self) -> None:
        self.assertIsNone(
            admit_guarded_run(
                pool(),
                Decision("single", ("type-verification-value",)),
                token="proof",
                submit_ref="ref-submit",
            )
        )

    def test_verified_fresh_same_ref_allows_second(self) -> None:
        admitted = plan()
        assert admitted is not None
        fresh = FreshObservation("proof", "ref-submit", "capture-2")
        self.assertTrue(second_child_allowed("verified", fresh, admitted))

    def test_negative_cases_do_not_execute_the_second_child(self) -> None:
        admitted = plan()
        assert admitted is not None
        executed: list[str] = []
        cases = [
            ("refuted", FreshObservation("proof", "ref-submit", "capture-2")),
            ("unknown", FreshObservation("proof", "ref-submit", "capture-2")),
            ("stale", None),
            ("verified", None),
            ("verified", FreshObservation("other", "ref-submit", "capture-2")),
            ("verified", FreshObservation("proof", "ref-other", "capture-2")),
            ("verified", FreshObservation("proof", None, "capture-2")),
            ("verified", FreshObservation("proof", "ref-submit", None)),
            ("refused", FreshObservation("proof", "ref-submit", "capture-2")),
        ]
        for status, fresh in cases:
            with self.subTest(status=status, fresh=fresh):
                if second_child_allowed(status, fresh, admitted):
                    executed.append(admitted.second.candidate_id)
        self.assertEqual(executed, [])

    def test_second_child_evidence_explains_each_refusal_class(self) -> None:
        admitted = plan()
        assert admitted is not None
        cases = [
            ("refuted", FreshObservation("proof", "ref-submit", "capture-2"), "refuted"),
            ("unknown", FreshObservation("proof", "ref-submit", "capture-2"), "unknown"),
            ("stale", None, "stale"),
            ("verified", None, "missing_observation"),
            ("verified", FreshObservation("other", "ref-submit", "capture-2"), "field_mismatch"),
            ("verified", FreshObservation("proof", "ref-other", "capture-2"), "submit_ref_mismatch"),
            ("verified", FreshObservation("proof", "ref-submit", None), "missing_capture"),
            ("refused", FreshObservation("proof", "ref-submit", "capture-2"), "refused"),
        ]
        for status, fresh, reason in cases:
            with self.subTest(status=status, fresh=fresh):
                evidence = explain_second_child(status, fresh, admitted)
                self.assertFalse(evidence.allowed)
                self.assertEqual(evidence.reason, reason)

    def test_second_child_evidence_marks_fresh_verified_path_allowed(self) -> None:
        admitted = plan()
        assert admitted is not None
        evidence = explain_second_child(
            "verified", FreshObservation("proof", "ref-submit", "capture-2"), admitted
        )
        self.assertTrue(evidence.allowed)
        self.assertEqual(evidence.reason, "allowed")


if __name__ == "__main__":
    unittest.main()

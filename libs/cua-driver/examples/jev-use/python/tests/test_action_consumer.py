from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from action_consumer import naive_choice, required_cases, typed_choice


class ActionConsumerTest(unittest.TestCase):
    def test_skipped_observation_is_not_treated_as_no_change(self) -> None:
        self.assertEqual(typed_choice("confirmed", "skipped", passive_success=False), "observe")
        self.assertEqual(naive_choice("confirmed", "skipped", passive_success=False), "continue")

    def test_passive_proof_continues_without_a_replay(self) -> None:
        self.assertEqual(typed_choice("unverifiable", "completed", passive_success=True), "continue")

    def test_refusal_stops(self) -> None:
        self.assertEqual(typed_choice("refused", "skipped", passive_success=False), "stop")

    def test_written_cases_match_typed_choice(self) -> None:
        path = Path(__file__).resolve().parents[6] / "scripts/repro/handoff/issue-12-cases.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(rows, required_cases())

    def test_required_cases_are_decided_by_typed_choice(self) -> None:
        rows = required_cases()
        self.assertEqual(len(rows), 7)
        for row in rows:
            self.assertEqual(
                row["typed"],
                typed_choice(row["effect"], row["observation"], passive_success=row["passive_success"]),
            )
            self.assertNotEqual(row["case"], "")

    def test_unavailable_or_noop_observes_instead_of_replaying(self) -> None:
        self.assertEqual(typed_choice("suspected_noop", "completed", passive_success=False), "observe")
        self.assertEqual(typed_choice("unverifiable", "unavailable", passive_success=False), "observe")
        self.assertEqual(naive_choice("unverifiable", "unavailable", passive_success=False), "continue")


if __name__ == "__main__":
    unittest.main()

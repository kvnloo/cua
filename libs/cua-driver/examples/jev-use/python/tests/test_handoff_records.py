from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from core import Candidate
from deterministic_fast_path import single_executable_candidate
from passive_observation import AuthorityError, Row, action_target
from run_length import recommend_cap
from shadow_probe import ShadowSample

ROOT = Path(__file__).resolve().parents[6]
HANDOFF = ROOT / "scripts" / "repro" / "handoff"


def candidate(candidate_id: str, tool: str | None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {})


class HandoffRecordTest(unittest.TestCase):
    def test_ownership_rows_name_a_real_evidence_path(self) -> None:
        with (HANDOFF / "ownership.tsv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertGreaterEqual(len(rows), 10)
        for row in rows:
            evidence = ROOT / row["evidence"]
            self.assertTrue(evidence.is_file(), row["evidence"])

    def test_killed_run_length_matches_the_shipped_function(self) -> None:
        advice = recommend_cap(stop_at_first_child=7, runs=10)
        self.assertIn("cap at 2", advice)
        dag = json.loads((HANDOFF / "promotion-dag.json").read_text(encoding="utf-8"))
        length = next(item for item in dag["items"] if item["id"] == "run-length-4")
        self.assertEqual(length["posting_status"], "WAITING ON DOWNSTREAM EXPERIMENT")
        self.assertTrue((ROOT / length["evidence"]).is_file())

    def test_fast_path_and_passive_rules_match_the_decision_table(self) -> None:
        admitted = single_executable_candidate(
            [candidate("type-verification-value", "browser_type"), candidate("reobserve", None)]
        )
        self.assertEqual(admitted.id, "type-verification-value")
        with self.assertRaises(AuthorityError):
            action_target(Row("calc-result", "6", passive=True))
        with self.assertRaises(RuntimeError):
            ShadowSample("gtk3-entry", "probe", (), skip_capture=True)
        table = (HANDOFF / "decision-table.tsv").read_text(encoding="utf-8")
        self.assertIn("do not embed 4", table)
        self.assertIn("do not skip", table)
        self.assertIn("macOS machine", table)
        self.assertIn("Windows machine", table)


if __name__ == "__main__":
    unittest.main()

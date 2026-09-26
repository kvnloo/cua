"""Open-packet tables are the results of the shipped functions."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from goal_gates import task_rows
from regression_budget import WorkCounts, ci_may_gate_on_milliseconds, semantic_path_ok
from task_battery import battery_table, promote_globally, run_interleaved, standard_battery
from transfer_probe import comparison_rows

ROOT = Path(__file__).resolve().parents[6]
HANDOFF = ROOT / "scripts" / "repro" / "handoff"


class OpenPacketTest(unittest.TestCase):
    def test_goal_rows_match_the_file_and_leave_latency_unset(self) -> None:
        rows = task_rows()
        recorded = json.loads((HANDOFF / "issue-23-goals.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, rows)
        self.assertTrue(any(row["model_done_gate"] is False for row in rows))
        self.assertTrue(all(row["latency_ms"] is None for row in rows))

    def test_battery_table_is_the_interleaved_runner(self) -> None:
        recorded = json.loads((HANDOFF / "issue-24-battery.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, battery_table())
        self.assertEqual(len(standard_battery()), 5)
        self.assertFalse(promote_globally(run_interleaved(standard_battery())))

    def test_semantic_budget_does_not_use_milliseconds(self) -> None:
        self.assertFalse(ci_may_gate_on_milliseconds())
        self.assertTrue(semantic_path_ok(WorkCounts(0, 1, 0, 1)))
        self.assertFalse(semantic_path_ok(WorkCounts(1, 1, 0, 1)))
        self.assertFalse(semantic_path_ok(WorkCounts(0, 1, 1, 1)))
        text = (HANDOFF / "issue-35-budget.md").read_text(encoding="utf-8")
        self.assertIn("do not add a CI wall-clock gate", text)
        self.assertIn("semantic_path_ok", text)

    def test_second_harness_spike_stays_deleted(self) -> None:
        rows = comparison_rows()
        recorded = json.loads((HANDOFF / "issue-49-comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded, rows)
        self.assertEqual(rows[0]["shipped_result"], "only-action")
        self.assertIsNone(rows[1]["shipped_result"])
        self.assertTrue(all(row["second_harness"] == "deleted" for row in rows))


if __name__ == "__main__":
    unittest.main()

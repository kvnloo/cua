from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from handoff_emit import (
    browser_not_run,
    cap_report,
    dispatch_counts,
    injection_report,
    replay_comparison,
    routing_table,
    selector_report,
    session_isolation,
    write_all,
)

ROOT = Path(__file__).resolve().parents[6]
HANDOFF = ROOT / "scripts" / "repro" / "handoff"


class HandoffEmitTest(unittest.TestCase):
    def test_written_tables_match_the_shipped_functions(self) -> None:
        write_all(HANDOFF)
        self.assertEqual(json.loads((HANDOFF / "issue-25-caps.json").read_text()), cap_report())
        self.assertEqual(json.loads((HANDOFF / "issue-33-dispatch.json").read_text()), dispatch_counts())
        self.assertEqual(json.loads((HANDOFF / "issue-44-routing.json").read_text()), routing_table())
        comparison = json.loads((HANDOFF / "issue-21-comparison.json").read_text())
        self.assertEqual(comparison["break_even"][1]["missing_machine"], "macOS")
        self.assertEqual(comparison["break_even"][2]["missing_machine"], "Windows")
        self.assertFalse(comparison["production_skipping"])
        fresh = replay_comparison()
        self.assertTrue(fresh["false_reuse_kills"])
        counts = dispatch_counts()
        self.assertEqual(counts[0]["second_dispatch"], 1)
        unknown = next(row for row in counts if row["status"] == "unknown")
        self.assertEqual(unknown["second_dispatch"], 0)
        self.assertTrue(unknown["app_state_reached"])
        from guarded_run import second_child_allowed
        import inspect

        self.assertNotIn("fixture_submitted", inspect.getsource(second_child_allowed))
        from handoff_emit import stale_receipts as fresh_stale

        turns = [len(row["dispatched"]) for row in fresh_stale()]
        self.assertEqual(turns, [2, 1, 1, 1, 1])
        self.assertTrue(all(row["elapsed_ms"] is None for row in fresh_stale()))
        self.assertEqual(cap_report()["rows"][2]["wasted"], 3)
        self.assertIn("fast-path", json.dumps(routing_table()))
        from handoff_emit import guarded_receipts, stale_receipts

        receipts = json.loads((HANDOFF / "issue-5-receipts.jsonl").read_text().splitlines()[1])
        self.assertFalse(receipts["second_dispatch"])
        self.assertEqual(guarded_receipts()[1]["case"], "refuted")
        stale = stale_receipts()
        self.assertEqual(stale[1]["refused"], ["submit"])
        self.assertIsNone(stale[0]["elapsed_ms"])
        injections = injection_report()
        self.assertEqual(
            json.loads((HANDOFF / "issue-33-injections.json").read_text(encoding="utf-8")),
            injections,
        )
        lost = next(row for row in injections if row["case"] == "response lost")
        self.assertEqual(lost["replay_dispatch"], 0)
        self.assertEqual(lost["second_dispatch"], 0)
        self.assertTrue(lost["app_state_reached"])
        self.assertNotEqual(lost["typed"], "continue")
        sessions = session_isolation()
        self.assertEqual(
            json.loads((HANDOFF / "issue-36-sessions.json").read_text(encoding="utf-8")),
            sessions,
        )
        self.assertTrue(sessions["lifetime_foreign_rejected"])
        self.assertFalse(sessions["lifetime_events_shared"])
        self.assertTrue(sessions["browser_cross_ref_refused"])
        self.assertFalse(sessions["borrowed_token_authorizes_plan"])
        self.assertEqual(sessions["concurrent_processes"], "not executed")
        self.assertEqual(
            json.loads((HANDOFF / "issue-17-not-run.json").read_text(encoding="utf-8")),
            browser_not_run(),
        )
        self.assertEqual(browser_not_run()["live_browser_battery"], "not run")
        selectors = selector_report(ROOT)
        self.assertIn("daemon is not running", selectors[0]["linux_runtime"])
        self.assertIn("Missing machine: macOS", selectors[0]["missing_machine"])
        self.assertIn("Missing machine: Windows", selectors[0]["missing_machine"])
        self.assertEqual(selectors[2]["linux_source"], "rejected by validate")
        self.assertEqual((HANDOFF / "issue-16-matrix.tsv").read_text(encoding="utf-8").splitlines()[0].count("\t"), 5)


if __name__ == "__main__":
    unittest.main()

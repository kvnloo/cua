from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from handoff_emit import cap_report, dispatch_counts, replay_comparison, routing_table, write_all

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
        self.assertEqual(dispatch_counts()[0]["second_dispatch"], 1)
        self.assertEqual(cap_report()["rows"][2]["wasted"], 3)
        self.assertIn("fast-path", json.dumps(routing_table()))
        from handoff_emit import guarded_receipts, stale_receipts

        receipts = json.loads((HANDOFF / "issue-5-receipts.jsonl").read_text().splitlines()[1])
        self.assertFalse(receipts["second_dispatch"])
        self.assertEqual(guarded_receipts()[1]["case"], "refuted")
        stale = stale_receipts()
        self.assertEqual(stale[1]["refused"], ["submit"])
        self.assertIsNone(stale[0]["elapsed_ms"])


if __name__ == "__main__":
    unittest.main()

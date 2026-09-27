from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from cancellation_lifetime import Lifetime, coverage_report, isolation_report, trace_record


class CancellationLifetimeTest(unittest.TestCase):
    def test_legal_order_releases_only_after_native_exit(self) -> None:
        life = Lifetime("req-1")
        life.admit()
        life.observe_cancel()
        life.native_exit()
        life.release()
        life.finish()
        self.assertEqual(
            life.events,
            [
                "admitted:req-1",
                "cancellation-observed:req-1",
                "native-exit:req-1",
                "permit-released:req-1",
                "public-result:req-1",
            ],
        )

    def test_early_release_is_rejected(self) -> None:
        life = Lifetime("req-1")
        life.admit()
        with self.assertRaises(RuntimeError):
            life.release()

    def test_recorded_trace_matches_the_legal_order(self) -> None:
        root = Path(__file__).resolve().parents[6]
        recorded = json.loads(
            (root / "scripts" / "repro" / "handoff" / "issue-9-trace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recorded, trace_record())
        events = recorded["events"]
        self.assertLess(events.index("native-exit:req-1"), events.index("permit-released:req-1"))
        self.assertFalse(recorded["competing_runtime"])
        self.assertEqual(recorded["owner"], "existing request-id owner")

    def test_isolation_report_rejects_a_foreign_issuance(self) -> None:
        root = Path(__file__).resolve().parents[6]
        recorded = json.loads(
            (root / "scripts/repro/handoff/issue-36-isolation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recorded, isolation_report())
        self.assertFalse(recorded["shared_across_issuances"])
        self.assertTrue(recorded["foreign_issuance_rejected"])

    def test_coverage_report_keeps_queued_work_out_of_native(self) -> None:
        root = Path(__file__).resolve().parents[6]
        recorded = json.loads(
            (root / "scripts/repro/handoff/issue-9-coverage.json").read_text(encoding="utf-8")
        )
        report = coverage_report()
        self.assertEqual(recorded, report)
        self.assertFalse(report["queued_cancel_enters_native"])
        self.assertNotIn("native-exit:req-1", report["queued_events"])
        self.assertTrue(report["release_before_native_exit_rejected"])
        self.assertTrue(report["foreign_issuance_rejected"])
        self.assertTrue(report["public_result_before_release_rejected"])
        self.assertEqual(report["held_input"], "not in this probe")
        self.assertEqual(report["held_input_missing_machine"], "macOS")
        self.assertFalse(report["competing_scheduler"])

    def test_wrong_issuance_is_rejected(self) -> None:
        life = Lifetime("req-1")
        life.admit()
        life.native_exit()
        life.release()
        with self.assertRaises(RuntimeError):
            life.finish("req-2")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from cancellation_lifetime import Lifetime, trace_record


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

    def test_wrong_issuance_is_rejected(self) -> None:
        life = Lifetime("req-1")
        life.admit()
        life.native_exit()
        life.release()
        with self.assertRaises(RuntimeError):
            life.finish("req-2")


if __name__ == "__main__":
    unittest.main()

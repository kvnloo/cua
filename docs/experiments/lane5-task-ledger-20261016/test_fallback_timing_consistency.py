"""Fallback overhead must be a measured subset of the complete runner."""
import unittest

from paired_task_gate import analyze
from test_paired_task_gate import pairs


class FallbackTimingConsistencyTests(unittest.TestCase):
    def test_fallback_cannot_exceed_runner_lifetime(self):
        for value in (109.0, 10000.0):
            with self.subTest(value=value):
                rows = pairs(2)
                rows[0]["fallback_used"] = True
                rows[0]["timing"]["fallback_ms"] = value
                self.assertGreater(value, rows[0]["timing"]["t_runner_ms"])
                report = analyze(rows)
                self.assertFalse(report["valid"])
                self.assertFalse(report["speed_claim_eligible"])

    def test_unused_fallback_cannot_have_charged_latency(self):
        rows = pairs(2)
        rows[0]["fallback_used"] = False
        rows[0]["timing"]["fallback_ms"] = 1.5
        report = analyze(rows)
        self.assertFalse(report["valid"])
        self.assertFalse(report["speed_claim_eligible"])

    def test_measured_fallback_within_runner_remains_valid(self):
        rows = pairs(2)
        rows[0]["fallback_used"] = True
        rows[0]["timing"]["fallback_ms"] = 12.5
        self.assertTrue(analyze(rows)["valid"])

    def test_no_fallback_with_zero_overhead_remains_valid(self):
        rows = pairs(2)
        self.assertFalse(rows[0]["fallback_used"])
        self.assertEqual(rows[0]["timing"]["fallback_ms"], 0)
        self.assertTrue(analyze(rows)["valid"])


if __name__ == "__main__":
    unittest.main()

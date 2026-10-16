"""Regression: equal arm counts alone do not establish an AB/BA interleaved run.

This offline validator treats the JSONL row stream as an append-only execution
record: a pair's sequence position is its first row's position. It cannot
independently prove timestamps, Driver participation, or actual wall-clock order.
"""
import unittest

from paired_task_gate import analyze
from test_paired_task_gate import pairs


def order_pairs(rows, first_arm_by_pair):
    for r in rows:
        first = first_arm_by_pair[int(r["pair_id"])]
        r["slot"] = 0 if r["arm"] == first else 1
    return rows


class InterleavingTests(unittest.TestCase):
    def test_balanced_but_clustered_order_must_fail(self):
        rows = order_pairs(pairs(20), ["run_steps"] * 10 + ["run_script"] * 10)
        result = analyze(rows)
        self.assertEqual(result["order_first"], {"run_steps": 10, "run_script": 10})
        self.assertFalse(result["valid"])
        self.assertIn("not AB/BA interleaved", " ".join(result["errors"]))
        self.assertFalse(result["speed_claim_eligible"])

    def test_alternating_steps_first_remains_valid(self):
        self.assertTrue(analyze(pairs(20))["valid"])

    def test_alternating_script_first_remains_valid(self):
        first = ["run_script" if i % 2 == 0 else "run_steps" for i in range(20)]
        self.assertTrue(analyze(order_pairs(pairs(20), first))["valid"])

    def test_odd_alternation_remains_valid(self):
        self.assertTrue(analyze(pairs(3))["valid"])

    def test_single_pair_remains_valid(self):
        self.assertTrue(analyze(pairs(1))["valid"])

    def test_balanced_adjacent_duplicate_order_rejected(self):
        first = ["run_steps", "run_script", "run_script", "run_steps"]
        self.assertFalse(analyze(order_pairs(pairs(4), first))["valid"])


if __name__ == "__main__":
    unittest.main()

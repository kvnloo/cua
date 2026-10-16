"""Boundary cases for cross-language-safe whole-task timing evidence."""
import copy
import unittest

from paired_task_gate import analyze
from test_paired_task_gate import pairs


class NumericDurationGuardTests(unittest.TestCase):
    def test_extreme_json_integers_are_invalid_not_exceptions(self):
        for field in ("t_oracle_ms", "t_runner_ms", "fallback_ms"):
            for value in (10**400, -(10**400)):
                with self.subTest(field=field, sign=value > 0):
                    rows = pairs(2)
                    rows[0]["timing"][field] = value
                    out = analyze(rows)
                    self.assertFalse(out["valid"])
                    self.assertFalse(out["speed_claim_eligible"])

    def test_js_unsafe_integer_duration_is_rejected(self):
        for value in (2**53, 2**53 + 1, 10**100):
            with self.subTest(value=value):
                rows = pairs(2)
                rows[0]["timing"]["t_oracle_ms"] = value
                out = analyze(rows)
                self.assertFalse(out["valid"])

    def test_negative_zero_nonfinite_and_bool_rejected(self):
        for value in (-1, float('nan'), float('inf'), -float('inf'), True):
            with self.subTest(value=repr(value)):
                rows = pairs(2)
                rows[0]["timing"]["fallback_ms"] = value
                self.assertFalse(analyze(rows)["valid"])

    def test_typical_duration_is_preserved(self):
        rows = pairs(2)
        rows[0]["fallback_used"] = True
        rows[0]["timing"]["fallback_ms"] = 140.5
        rows[0]["timing"]["t_runner_ms"] = 180.0
        self.assertTrue(analyze(rows)["valid"])


if __name__ == "__main__":
    unittest.main()

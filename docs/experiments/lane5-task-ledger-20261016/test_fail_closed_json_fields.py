"""Regression: malformed JSONL measurement fields must not crash ledger QA."""
import unittest

from paired_task_gate import analyze
from test_paired_task_gate import pairs


class MalformedInputTests(unittest.TestCase):
    def test_non_scalar_enums_are_rejected(self):
        for field in ("arm", "outcome", "evidence_class"):
            for malformed in ([], {}, ["verified"]):
                with self.subTest(field=field, malformed=malformed):
                    rows = pairs(2)
                    rows[0][field] = malformed
                    self.assertFalse(analyze(rows)["valid"])
        for field in ("delivery", "effect"):
            rows = pairs(2)
            rows[0]["actions"][0][field] = []
            self.assertFalse(analyze(rows)["valid"])

    def test_non_scalar_slots_do_not_raise(self):
        for malformed in ([], {}, [0], {"slot": 0}):
            rows = pairs(2)
            rows[0]["slot"] = malformed
            result = analyze(rows)
            self.assertFalse(result["valid"])
            self.assertFalse(result["speed_claim_eligible"])

    def test_invalid_fallback_durations_are_rejected(self):
        for malformed in (None, "1", [], {}):
            with self.subTest(malformed=malformed):
                rows = pairs(2)
                rows[0]["fallback_used"] = True
                rows[0]["timing"]["fallback_ms"] = malformed
                self.assertFalse(analyze(rows)["valid"])


if __name__ == "__main__":
    unittest.main()

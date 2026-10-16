"""Offline A/B ledger must not silently pool different benchmark cohorts.

These checks validate only author-asserted metadata, not live Driver provenance.
"""
import unittest
from paired_task_gate import analyze
from test_paired_task_gate import pairs

class CohortIntegrityTests(unittest.TestCase):
    def test_mixed_driver_binary_across_pairs_is_not_one_cohort(self):
        rows = pairs(20)
        for row in rows:
            if row["pair_id"] == "19":
                row["driver_build_sha"] = "c" * 64
        result = analyze(rows)
        self.assertFalse(result["valid"])
        self.assertIn("mixed cohort", " ".join(result["errors"]))

    def test_mixed_task_contract_across_pairs_is_not_one_task(self):
        rows = pairs(20)
        for row in rows:
            if row["pair_id"] == "19":
                row["task_contract_sha"] = "different-task-v2"
        self.assertFalse(analyze(rows)["valid"])

    def test_mixed_provider_or_policy_across_pairs_rejected(self):
        for field, value in (("provider_id", "different-provider"), ("permission_sha", "other-policy")):
            with self.subTest(field=field):
                rows = pairs(20)
                for row in rows:
                    if row["pair_id"] == "19":
                        row[field] = value
                self.assertFalse(analyze(rows)["valid"])

    def test_unique_reset_state_per_pair_is_allowed(self):
        rows = pairs(20)
        for row in rows:
            row["initial_state_sha"] = "reset-snapshot-" + row["pair_id"]
        self.assertTrue(analyze(rows)["valid"])

if __name__ == "__main__":
    unittest.main()

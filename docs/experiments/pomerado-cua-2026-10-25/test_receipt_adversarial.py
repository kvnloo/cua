"""Adversarial UNIT-only receipt tampering checks; no Pomerado/CUA task is run."""

import copy
import unittest

from analyze_receipts import InvalidReceipts, summarize
from test_analyze_receipts import block


class ReceiptAdversarialTests(unittest.TestCase):
    def test_dirty_audit_before_reset_is_not_independent_clean_state(self):
        rows = block()
        rows[0]["audit_before"] = 9
        rows[0]["audit_after"] = 10
        with self.assertRaisesRegex(InvalidReceipts, "nonzero audit_before"):
            summarize(rows)

    def test_mixed_driver_versions_across_blocks_are_invalid(self):
        rows = block("b1", "ABBA") + block("b2", "BAAB")
        for row in rows[4:]:
            row["driver_sha"] = "other-driver-pin"
        with self.assertRaisesRegex(InvalidReceipts, "mixed driver_sha"):
            summarize(rows)

    def test_mixed_mint_artifacts_across_blocks_are_invalid(self):
        rows = block("b1", "ABBA") + block("b2", "BAAB")
        for row in rows[4:]:
            row["pomerado_sha"] = "different-mint"
        with self.assertRaisesRegex(InvalidReceipts, "mixed pomerado_sha"):
            summarize(rows)

    def test_mixed_read_write_blocks_in_one_comparison_are_invalid(self):
        rows = block("b1", "ABBA") + block("b2", "BAAB")
        for row in rows[4:]:
            row["effect_kind"] = "read"
            row["audit_after"] = 0
            row["total_commits_after"] = 0
        with self.assertRaisesRegex(InvalidReceipts, "mixed effect_kind"):
            summarize(rows)

    def test_REAL_pins_must_be_exact_sha_not_prose(self):
        rows = block()
        for row in rows:
            row["evidence_class"] = "REAL"
        with self.assertRaisesRegex(InvalidReceipts, "unverifiable fixture_sha"):
            summarize(rows)

    def test_unit_rows_still_cannot_trigger_timing_claim(self):
        rows = copy.deepcopy(block())
        c = summarize(rows, minimum_blocks=1)["cohorts"]["form-submit/default"]
        self.assertEqual(c["status"], "NOT_READY")
        self.assertIsNone(c["paired_median_B_minus_A_ms"])


if __name__ == "__main__":
    unittest.main()

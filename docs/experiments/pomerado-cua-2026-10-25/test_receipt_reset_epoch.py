"""UNIT-only hidden-reset and lifetime-write receipt adversaries; not A/B data."""
import unittest

from analyze_receipts import InvalidReceipts, summarize
from test_analyze_receipts import block


class ResetEpochReceiptTests(unittest.TestCase):
    def test_valid_unit_receipts_remain_not_ready(self):
        result = summarize(block(), minimum_blocks=2)
        self.assertEqual(result["cohorts"]["form-submit/default"]["status"], "NOT_READY")

    def test_hidden_intermediate_reset_refused(self):
        rows = block()
        rows[0]["reset_epoch_after"] += 1
        with self.assertRaisesRegex(InvalidReceipts, "reset epoch changed"):
            summarize(rows)

    def test_hidden_extra_commit_across_reset_refused(self):
        rows = block()
        rows[0]["total_commits_after"] += 1
        # Per-reset audit still reads one, but lifetime count reveals two writes.
        self.assertEqual(rows[0]["audit_after"] - rows[0]["audit_before"], 1)
        with self.assertRaisesRegex(InvalidReceipts, "lifetime mutation count mismatch"):
            summarize(rows)

    def test_missing_epoch_counter_refused(self):
        rows = block()
        del rows[0]["reset_epoch_before"]
        with self.assertRaisesRegex(InvalidReceipts, "missing"):
            summarize(rows)

    def test_boolean_lifetime_counter_refused(self):
        rows = block()
        rows[0]["total_commits_after"] = True
        with self.assertRaisesRegex(InvalidReceipts, "total_commits_after"):
            summarize(rows)


if __name__ == "__main__":
    unittest.main()

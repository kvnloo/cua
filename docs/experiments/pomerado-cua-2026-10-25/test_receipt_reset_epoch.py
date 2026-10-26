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


    def test_ordered_write_chain_remains_unit_not_benchmark(self):
        rows = block()
        self.assertEqual([r["reset_epoch_before"] for r in rows], [1, 2, 3, 4])
        self.assertEqual([r["total_commits_before"] for r in rows], [0, 1, 2, 3])
        report = summarize(rows, minimum_blocks=1)["cohorts"]["form-submit/default"]
        self.assertEqual(report["status"], "NOT_READY")

    def test_read_only_chain_with_zero_writes_remains_unit(self):
        rows = block()
        for row in rows:
            row["effect_kind"] = "read"
            row["audit_after"] = 0
            row["total_commits_before"] = 0
            row["total_commits_after"] = 0
        report = summarize(rows, minimum_blocks=1)["cohorts"]["form-submit/default"]
        self.assertEqual(report["status"], "NOT_READY")

    def test_missing_reset_between_trials_refused(self):
        rows = block()
        rows[1]["reset_epoch_before"] -= 1
        rows[1]["reset_epoch_after"] -= 1
        with self.assertRaisesRegex(InvalidReceipts, "missing/extra intertrial reset"):
            summarize(rows)

    def test_extra_reset_between_trials_refused(self):
        rows = block()
        rows[1]["reset_epoch_before"] += 1
        rows[1]["reset_epoch_after"] += 1
        with self.assertRaisesRegex(InvalidReceipts, "missing/extra intertrial reset"):
            summarize(rows)

    def test_hidden_write_between_trials_refused(self):
        rows = block()
        rows[1]["total_commits_before"] += 1
        rows[1]["total_commits_after"] += 1
        with self.assertRaisesRegex(InvalidReceipts, "lifetime writes missing"):
            summarize(rows)

    def test_rolled_back_lifetime_counter_between_trials_refused(self):
        rows = block()
        rows[1]["total_commits_before"] = 0
        rows[1]["total_commits_after"] = 1
        with self.assertRaisesRegex(InvalidReceipts, "lifetime writes missing"):
            summarize(rows)

if __name__ == "__main__":
    unittest.main()

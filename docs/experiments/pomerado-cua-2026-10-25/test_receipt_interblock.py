"""UNIT_ONLY cross-block audit continuity controls; never benchmark evidence."""
import unittest

from analyze_receipts import InvalidReceipts, summarize
from test_analyze_receipts import block


def paired():
    return block("b1", "ABBA") + block("b2", "BAAB")


def shift_second(rows, *, epochs=0, commits=0):
    for row in rows[4:]:
        row["reset_epoch_before"] += epochs
        row["reset_epoch_after"] += epochs
        row["total_commits_before"] += commits
        row["total_commits_after"] += commits


class InterblockAuditTests(unittest.TestCase):
    def test_valid_crossblock_chain_remains_unit_not_benchmark(self):
        report = summarize(paired(), minimum_blocks=2)["cohorts"]["form-submit/default"]
        self.assertEqual(report["status"], "NOT_READY")
        self.assertIsNone(report["paired_median_B_minus_A_ms"])

    def test_missing_interblock_reset_refused(self):
        rows = paired()
        shift_second(rows, epochs=-1)
        with self.assertRaisesRegex(InvalidReceipts, "missing/extra interblock reset"):
            summarize(rows)

    def test_extra_interblock_reset_refused(self):
        rows = paired()
        shift_second(rows, epochs=1)
        with self.assertRaisesRegex(InvalidReceipts, "missing/extra interblock reset"):
            summarize(rows)

    def test_hidden_write_between_blocks_refused(self):
        rows = paired()
        shift_second(rows, commits=1)
        with self.assertRaisesRegex(InvalidReceipts, "lifetime writes missing between blocks"):
            summarize(rows)

    def test_rolled_back_counter_between_blocks_refused(self):
        rows = paired()
        shift_second(rows, commits=-1)
        with self.assertRaisesRegex(InvalidReceipts, "lifetime writes missing between blocks"):
            summarize(rows)

    def test_interleaved_cohort_boundary_needs_same_audit_chain(self):
        rows = paired()
        for row in rows[4:]:
            row["variant"] = "label_churn"
        report = summarize(rows, minimum_blocks=2)
        self.assertEqual(set(report["cohorts"]), {"form-submit/default", "form-submit/label_churn"})
        shift_second(rows, commits=1)
        with self.assertRaisesRegex(InvalidReceipts, "lifetime writes missing between blocks"):
            summarize(rows)


if __name__ == "__main__":
    unittest.main()

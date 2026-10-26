"""UNIT_ONLY audit-process provenance controls; fabricated receipts, not A/B."""
import unittest

from analyze_receipts import InvalidReceipts, summarize
from test_analyze_receipts import block


INSTANCE = "a" * 32
ALT_INSTANCE = "b" * 32


def tagged(block_id="b1", order="ABBA"):
    rows = block(block_id, order)
    for row in rows:
        row["fixture_instance_before"] = INSTANCE
        row["fixture_instance_after"] = INSTANCE
    return rows


class FixtureIncarnationReceiptTests(unittest.TestCase):
    def test_matching_unit_receipts_are_still_not_benchmarks(self):
        result = summarize(tagged(), minimum_blocks=1)
        self.assertEqual(result["cohorts"]["form-submit/default"]["status"], "NOT_READY")

    def test_missing_incarnation_refused(self):
        rows = tagged()
        rows[0].pop("fixture_instance_before")
        with self.assertRaisesRegex(InvalidReceipts, "missing"):
            summarize(rows)

    def test_restart_midtrial_refused_even_if_counters_match(self):
        rows = tagged()
        rows[0]["fixture_instance_after"] = ALT_INSTANCE
        self.assertEqual(rows[0]["reset_epoch_after"], rows[0]["reset_epoch_before"])
        self.assertEqual(rows[0]["total_commits_after"] - rows[0]["total_commits_before"], 1)
        with self.assertRaisesRegex(InvalidReceipts, "fixture instance changed"):
            summarize(rows)

    def test_invalid_instance_id_shape_refused(self):
        for bad in (False, "short", "G" * 32, 4):
            with self.subTest(bad=bad):
                rows = tagged()
                rows[0]["fixture_instance_before"] = bad
                with self.assertRaisesRegex(InvalidReceipts, "fixture_instance_before"):
                    summarize(rows)

    def test_mixed_incarnation_inside_block_refused(self):
        rows = tagged()
        rows[2]["fixture_instance_before"] = ALT_INSTANCE
        rows[2]["fixture_instance_after"] = ALT_INSTANCE
        with self.assertRaisesRegex(InvalidReceipts, "mismatched fixture_instance_before"):
            summarize(rows)

    def test_mixed_incarnation_across_abba_baab_blocks_refused(self):
        rows = tagged("b1", "ABBA") + tagged("b2", "BAAB")
        for row in rows[4:]:
            row["fixture_instance_before"] = ALT_INSTANCE
            row["fixture_instance_after"] = ALT_INSTANCE
        with self.assertRaisesRegex(InvalidReceipts, "mixed fixture_instance_before"):
            summarize(rows)


if __name__ == "__main__":
    unittest.main()

"""Synthetic UNIT tests for the Pomerado/CUA receipt verifier; not runtime evidence."""

import copy
import unittest

from analyze_receipts import InvalidReceipts, summarize


def block(block_id="b1", order="ABBA"):
    rows = []
    for position, arm in enumerate(order, start=1):
        rows.append({
            "schema": "cua.pomerado.trial.v1",
            "evidence_class": "UNIT",
            "run_id": f"{block_id}-{position}",
            "block_id": block_id,
            "position": position,
            "arm": arm,
            "workflow": "form-submit",
            "variant": "default",
            "input_fingerprint": "redacted-test-fingerprint",
            "fixture_sha": "test-fixture-pin",
            "caller_sha": "test-caller-pin",
            "driver_sha": "test-driver-pin",
            "pomerado_sha": "test-pomerado-pin",
            "browser_version": "test-chromium-pin",
            "route_observed": "cua-driver" if arm == "A" else "pomerado-mcp",
            "route_evidence": f"synthetic-route-{position}",
            "reset_verified": True,
            "oracle_outcome": "verified",
            "oracle_evidence": f"synthetic-oracle-{position}",
            "elapsed_ms": 110 if arm == "A" else 80,
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "wrong_target": False,
            "unauthorized_effect": False,
            "duplicate_effect": False,
            "uncertain_effect": False,
            "fallback_count": 0,
            "mint_ms": 250 if position == 2 else 0,
            "effect_kind": "write",
            "audit_before": 0,
            "audit_after": 1,
            "audit_evidence": f"synthetic-independent-audit-{position}",
            "reset_epoch_before": 1,
            "reset_epoch_after": 1,
            "total_commits_before": 0,
            "total_commits_after": 1,
        })
    return rows


class ReceiptValidationTests(unittest.TestCase):
    def test_valid_unit_is_never_presented_as_real_speedup(self):
        rows = []
        for n in range(30):
            rows.extend(block(f"b{n}", "ABBA" if n % 2 == 0 else "BAAB"))
        c = summarize(rows)["cohorts"]["form-submit/default"]
        self.assertEqual(c["status"], "NOT_READY")
        self.assertIsNone(c["paired_median_B_minus_A_ms"])
        self.assertIn("non-real/unit evidence present", c["reasons"])
        self.assertEqual(c["arms"]["A"]["attempted"], 60)
        self.assertEqual(c["arms"]["B"]["attempted"], 60)

    def test_cannot_hide_incomplete_pair(self):
        with self.assertRaisesRegex(InvalidReceipts, "exactly four"):
            summarize(block()[:-1])

    def test_reject_unbalanced_order(self):
        with self.assertRaisesRegex(InvalidReceipts, "ABBA/BAAB"):
            summarize(block("b2", "AABB"))

    def test_fail_gate_on_wrong_target(self):
        rows = block()
        rows[1]["wrong_target"] = True
        c = summarize(rows, minimum_blocks=1)["cohorts"]["form-submit/default"]
        self.assertEqual(c["status"], "NOT_READY")
        self.assertIn("unsafe or uncertain side effect", c["reasons"])

    def test_fail_gate_on_fallback(self):
        rows = block()
        rows[1]["route_observed"] = "fallback-cua"
        rows[1]["fallback_count"] = 1
        c = summarize(rows, minimum_blocks=1)["cohorts"]["form-submit/default"]
        self.assertIn("fallback present (retain attempted-arm accounting)", c["reasons"])

    def test_write_without_audit_is_rejected(self):
        rows = block()
        rows[0].pop("audit_evidence")
        with self.assertRaisesRegex(InvalidReceipts, "missing"):
            summarize(rows)

    def test_duplicate_commit_is_rejected_despite_matching_state(self):
        rows = block()
        rows[0]["audit_after"] = 2
        rows[0]["total_commits_after"] = 2
        with self.assertRaisesRegex(InvalidReceipts, "exactly one committed write"):
            summarize(rows)

    def test_read_only_case_with_commit_is_rejected(self):
        rows = block()
        for row in rows:
            row["effect_kind"] = "read"
        with self.assertRaisesRegex(InvalidReceipts, "read-only task mutated state"):
            summarize(rows)

    def test_reject_nonfinite_time(self):
        rows = copy.deepcopy(block())
        rows[0]["elapsed_ms"] = float("nan")
        with self.assertRaisesRegex(InvalidReceipts, "elapsed_ms"):
            summarize(rows)

    def test_reject_unproven_reset(self):
        rows = block()
        rows[1]["reset_verified"] = False
        with self.assertRaisesRegex(InvalidReceipts, "reset not independently verified"):
            summarize(rows)


if __name__ == "__main__":
    unittest.main()

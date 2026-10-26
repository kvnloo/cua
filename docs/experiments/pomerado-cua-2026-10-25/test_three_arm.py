"""UNIT tests for A/B/C interleaving. Synthetic rows only; not runtime evidence."""
import copy
import json
from pathlib import Path
import unittest

from analyze_receipts import InvalidReceipts, summarize
from plan_blocks import PlanError, build_plan

PIN = "f2704c1fe528c1e86287db808e7259c5483ef64c"
ROUTE = {"A": "cua-driver", "B": "pomerado-mcp", "C": "opencli-adapter-cdp"}


def prereg():
    return json.loads(Path(__file__).with_name("PREREG.json").read_text())


def block(block_id, order, effect="read", real=False):
    rows = []
    for position, arm in enumerate(order, 1):
        row = {
            "schema": "cua.pomerado.trial.v1", "evidence_class": "UNIT",
            "run_id": f"{block_id}-{position}", "block_id": block_id, "position": position,
            "arm": arm, "workflow": "form-submit", "variant": "default",
            "input_fingerprint": "fp", "fixture_sha": "f", "caller_sha": "c",
            "driver_sha": "d", "pomerado_sha": "p", "browser_version": "b",
            "route_observed": ROUTE[arm], "route_evidence": f"trace-{position}",
            "reset_verified": True, "oracle_outcome": "verified",
            "oracle_evidence": f"o-{position}", "elapsed_ms": {"A": 110, "B": 80, "C": 60}[arm],
            "model_calls": 0, "input_tokens": 0, "output_tokens": 0,
            "wrong_target": False, "unauthorized_effect": False, "duplicate_effect": False,
            "uncertain_effect": False, "fallback_count": 0,
            "mint_ms": 100 if arm != "A" else 0, "effect_kind": effect,
            "audit_before": 0, "audit_after": 1 if effect == "write" else 0,
            "audit_evidence": f"a-{position}",
        }
        if real:
            row["evidence_class"] = "REAL"
            for k, ch in (("fixture_sha", "1"), ("caller_sha", "2"), ("driver_sha", "3"),
                          ("pomerado_sha", "4")):
                row[k] = ch * 40
        if arm == "C":
            row["opencli_sha"] = "5" * 40 if real else "opencli-test-pin"
        rows.append(row)
    return rows


class ThreeArmPlan(unittest.TestCase):
    def test_default_two_arm_plan_is_unchanged(self):
        m = build_plan(prereg(), head_sha=PIN, variants=["default"])
        self.assertNotIn("arms", m)
        self.assertEqual(m["cohort_orders"], {"default": {"ABBA": 15, "BAAB": 15}})
        self.assertEqual(m["block_count"], 30)
        self.assertNotIn("arm_pair", m["blocks"][0])

    def test_three_arm_plan_is_pairwise_balanced_and_deterministic(self):
        x = build_plan(prereg(), head_sha=PIN, arms=("A", "B", "C"))
        y = build_plan(prereg(), head_sha=PIN, arms=("A", "B", "C"))
        self.assertEqual(x, y)
        self.assertEqual(x["arms"], ["A", "B", "C"])
        self.assertEqual(x["block_count"], 11 * 3 * 30)
        self.assertEqual(x["actual_executions"], 0)
        self.assertEqual(x["cohort_orders"]["default/AC"], {"ACCA": 15, "CAAC": 15})
        self.assertEqual(x["cohort_orders"]["default/BC"], {"BCCB": 15, "CBBC": 15})
        ids = [b["block_id"] for b in x["blocks"]]
        self.assertEqual(len(ids), len(set(ids)))
        for b in x["blocks"]:
            self.assertEqual("".join(t["arm_assigned"] for t in b["attempts"]), b["order"])
            for t in b["attempts"]:
                self.assertEqual(t["route_assigned_not_observed"], ROUTE[t["arm_assigned"]])
                self.assertEqual(t["status"], "NOT_RUN")
        # pair cohorts are interleaved, not run back to back
        self.assertGreater(len({b["arm_pair"] for b in x["blocks"][:12]}), 1)

    def test_invalid_arm_sets_rejected(self):
        for arms in (("A",), ("B", "A"), ("A", "D"), ("A", "A")):
            with self.assertRaisesRegex(PlanError, "arms"):
                build_plan(prereg(), head_sha=PIN, arms=arms)


class ThreeArmAnalysis(unittest.TestCase):
    def rows(self, order, n=2):
        out = []
        for i in range(n):
            out += block(f"b{order}{i}", order)
        return out

    def test_original_two_arm_summary_key_is_preserved(self):
        s = summarize(block("x", "ABBA", real=True) + block("y", "BAAB", real=True),
                      minimum_blocks=2)
        cohort = s["cohorts"]["form-submit/default"]
        self.assertEqual(cohort["status"], "COMPARABLE_DESCRIPTIVE_ONLY", cohort["reasons"])
        self.assertEqual(cohort["paired_median_B_minus_A_ms"], -30)
        unit = summarize(block("x", "ABBA") + block("y", "BAAB"), minimum_blocks=2)
        self.assertIn("paired_median_B_minus_A_ms", unit["cohorts"]["form-submit/default"])
        self.assertIsNone(unit["cohorts"]["form-submit/default"]["paired_median_B_minus_A_ms"])

    def test_c_versus_a_cohort_is_separate_and_compared(self):
        rows = [r for b in (block("x", "ACCA", real=True), block("y", "CAAC", real=True),
                            block("p", "ABBA", real=True), block("q", "BAAB", real=True))
                for r in b]
        s = summarize(rows, minimum_blocks=2)
        ac = s["cohorts"]["form-submit/default[AC]"]
        self.assertEqual(ac["status"], "COMPARABLE_DESCRIPTIVE_ONLY", ac["reasons"])
        self.assertEqual(ac["paired_median_C_minus_A_ms"], -50)
        self.assertEqual(set(ac["arms"]), {"A", "C"})
        self.assertIn("form-submit/default", s["cohorts"])

    def test_wrong_route_for_c_blocks_comparison(self):
        rows = block("x", "ACCA") + block("y", "CAAC")
        rows[1]["route_observed"] = "fallback-cua"
        s = summarize(rows, minimum_blocks=2)
        self.assertIn("requested route was not always exercised",
                      s["cohorts"]["form-submit/default[AC]"]["reasons"])

    def test_c_without_prep_cost_is_not_ready(self):
        rows = block("x", "ACCA") + block("y", "CAAC")
        for r in rows:
            r["mint_ms"] = 0
        s = summarize(rows, minimum_blocks=2)
        self.assertIn("arm C preparation cost not measured",
                      s["cohorts"]["form-submit/default[AC]"]["reasons"])

    def test_c_requires_opencli_pin(self):
        rows = block("x", "ACCA")
        rows[1].pop("opencli_sha")
        with self.assertRaisesRegex(InvalidReceipts, "opencli_sha"):
            summarize(rows)

    def test_real_c_needs_exact_opencli_sha_and_stable_across_blocks(self):
        rows = block("x", "ACCA", real=True) + block("y", "CAAC", real=True)
        rows[1]["opencli_sha"] = "6" * 40
        with self.assertRaisesRegex(InvalidReceipts, "mixed opencli_sha"):
            summarize(rows)

    def test_three_distinct_arms_in_one_block_rejected(self):
        with self.assertRaisesRegex(InvalidReceipts, "two-arm"):
            summarize(block("x", "ABCA"))
        with self.assertRaisesRegex(InvalidReceipts, "two-arm"):
            summarize(block("x", "AABB"))

    def test_unsafe_c_write_is_flagged(self):
        rows = block("x", "ACCA", "write") + block("y", "CAAC", "write")
        rows[1]["wrong_target"] = True
        s = summarize(rows, minimum_blocks=2)
        self.assertIn("unsafe or uncertain side effect",
                      s["cohorts"]["form-submit/default[AC]"]["reasons"])

    def test_unknown_arm_rejected(self):
        rows = block("x", "ABBA")
        rows[0]["arm"] = "D"
        with self.assertRaisesRegex(InvalidReceipts, "invalid arm"):
            summarize(rows)


if __name__ == "__main__":
    unittest.main()

"""PLAN_ONLY checks. No client, runner, network, browser or model calls."""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import unittest

from plan_blocks import PlanError, build_plan, digest

PIN = "f2704c1fe528c1e86287db808e7259c5483ef64c"


def prereg():
    path = Path(__file__).with_name("PREREG.json")
    return json.loads(path.read_text())


class PlanBlocksTests(unittest.TestCase):
    def test_full_default_coverage_interleaved_and_exactly_balanced(self):
        reg = prereg()
        m = build_plan(reg, head_sha=PIN)
        self.assertEqual(m["evidence_class"], "PLAN_ONLY")
        self.assertEqual(m["actual_executions"], 0)
        self.assertEqual(m["block_count"], 330)
        self.assertEqual(m["planned_attempt_count"], 1320)
        self.assertEqual(len(m["cohort_orders"]), 11)
        for orders in m["cohort_orders"].values():
            self.assertEqual(orders, {"ABBA": 15, "BAAB": 15})
        self.assertGreater(len({b["variant"] for b in m["blocks"][:15]}), 1)
        self.assertEqual(m["manifest_sha256"], digest({k: v for k, v in m.items()
                                                        if k != "manifest_sha256"}))

    def test_identical_source_seed_and_configuration_produce_identical_hash(self):
        reg = prereg()
        x = build_plan(reg, head_sha=PIN)
        y = build_plan(reg, head_sha=PIN)
        self.assertEqual(x, y)
        self.assertEqual(x["manifest_sha256"], y["manifest_sha256"])

    def test_changing_seed_changes_order_and_digest(self):
        reg = prereg()
        first = build_plan(reg, head_sha=PIN)
        mutated = copy.deepcopy(reg)
        mutated["design"]["seed"] += 1
        second = build_plan(mutated, head_sha=PIN)
        self.assertNotEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertNotEqual([b["block_id"] for b in first["blocks"]],
                            [b["block_id"] for b in second["blocks"]])

    def test_no_observed_route_or_oracle_is_invented(self):
        m = build_plan(prereg(), head_sha=PIN, variants=["default"])
        for b in m["blocks"]:
            self.assertEqual("".join(t["arm_assigned"] for t in b["attempts"]), b["order"])
            for t in b["attempts"]:
                self.assertEqual(t["status"], "NOT_RUN")
                self.assertNotIn("route_observed", t)
                self.assertNotIn("oracle_outcome", t)
                self.assertEqual(t["effect_kind_planned"], "read")
                self.assertEqual(t["blind_retry"], "PROHIBITED")

    def test_write_planning_requires_read_only_proof_and_remains_inert(self):
        with self.assertRaisesRegex(PlanError, "read-only proof"):
            build_plan(prereg(), head_sha=PIN, phase="synthetic_write")
        m = build_plan(prereg(), head_sha=PIN, phase="synthetic_write",
                       read_only_proof_sha256="f" * 64, variants=["default"])
        self.assertEqual(m["actual_executions"], 0)
        self.assertEqual(m["phase"], "synthetic_write")
        self.assertTrue(all(t["effect_kind_planned"] == "write"
                            for b in m["blocks"] for t in b["attempts"]))

    def test_unrecognized_variant_sha_or_changed_contract_is_rejected(self):
        reg = prereg()
        with self.assertRaisesRegex(PlanError, "cohort"):
            build_plan(reg, head_sha=PIN, variants=["default", "default"])
        with self.assertRaisesRegex(PlanError, "commit SHA"):
            build_plan(reg, head_sha="not-an-exact-sha")
        mutated = copy.deepcopy(reg)
        mutated["design"]["blocks_per_order"] = 14
        with self.assertRaisesRegex(PlanError, "block contract"):
            build_plan(mutated, head_sha=PIN)

    def test_permission_is_default_off(self):
        reg = prereg()
        reg["ownership"]["default_off"] = False
        with self.assertRaisesRegex(PlanError, "isolation"):
            build_plan(reg, head_sha=PIN)


if __name__ == "__main__":
    unittest.main()

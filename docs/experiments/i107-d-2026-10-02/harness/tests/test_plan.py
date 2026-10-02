"""Unit tests for the lane-D schedule and control registry (d_plan.py)."""

from __future__ import annotations

import collections
import re
import string
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import d_plan as P  # noqa: E402
import i107_fixture as fx  # noqa: E402


class ScheduleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.blocks = P.schedule()
        self.by_name = {b["block"]: b for b in self.blocks}

    def trials(self, plan: str) -> list[dict]:
        return [t for b in self.blocks if b["plan"] == plan for t in b["trials"]]

    def test_cmpd_has_30_pairs_per_condition_with_alternating_order(self) -> None:
        trials = self.trials("cmpd")
        pairs = collections.defaultdict(list)
        for t in trials:
            pairs[t["pair"]].append(t)
        by_cond = collections.Counter(v[0]["condition"] for v in pairs.values())
        self.assertEqual(by_cond, {"W-quiet": 30, "W-churn": 30})
        orders = []
        for pid in sorted(pairs):
            a, b = pairs[pid]
            self.assertEqual(a["condition"], b["condition"])
            self.assertEqual({a["arm"], b["arm"]}, {"A", "D"})
            self.assertEqual(a["order"], b["order"])
            self.assertEqual(a["order"], a["arm"] + b["arm"])
            orders.append(a["order"])
        self.assertEqual(orders[:4], ["AD", "DA", "AD", "DA"])
        self.assertEqual(collections.Counter(orders), {"AD": 30, "DA": 30})
        for t in trials:
            self.assertEqual((t["cohort"], t["comparison"], t["kind"]), ("K1", "CMP-D", "measured"))

    def test_cmpd_blocks_are_counterbalanced_and_consecutive_pairs_stay_adjacent(self) -> None:
        cmpd = [b for b in self.blocks if b["plan"] == "cmpd"]
        self.assertEqual([b["trials"][0]["condition"] for b in cmpd],
                         ["W-quiet", "W-churn", "W-churn", "W-quiet", "W-quiet", "W-churn"])
        for b in cmpd:
            self.assertEqual(len(b["trials"]), 20)
            for i in range(0, 20, 2):
                self.assertEqual(b["trials"][i]["pair"], b["trials"][i + 1]["pair"])

    def test_continuation_blocks_are_predeclared_and_not_run_by_default(self) -> None:
        cont = [b for b in self.blocks if b["plan"] == "cmpd-continuation"]
        self.assertEqual(sorted(b["block"] for b in cont),
                         ["cmpd-xc1", "cmpd-xc2", "cmpd-xc3", "cmpd-xq1", "cmpd-xq2", "cmpd-xq3"])
        for b in cont:
            self.assertEqual(b["run_if"], "continuation_rule")
            self.assertEqual(len(b["trials"]), 20)

    def test_k2_runs_after_k1_with_a_64_char_token_of_another_class(self) -> None:
        plans = [b["plan"] for b in self.blocks]
        self.assertLess(max(i for i, p in enumerate(plans) if p == "cmpd"),
                        min(i for i, p in enumerate(plans) if p == "k2"))
        trials = self.trials("k2")
        self.assertEqual(len({t["pair"] for t in trials}), 30)
        self.assertTrue(all(t["condition"] == "W-quiet" and t["cohort"] == "K2" for t in trials))
        tok1, tok2 = P.make_token("K1"), P.make_token("K2")
        self.assertRegex(tok1, r"^jev-[0-9a-f]{10}$")
        self.assertEqual(len(tok2), 64)
        self.assertTrue(set(tok2) <= set(string.ascii_uppercase))
        self.assertFalse(set(tok2) & set(string.hexdigits.lower() + "-"))
        self.assertNotEqual(P.make_token("K2"), tok2)

    def test_controls_have_at_least_5_per_arm_and_alternate_order(self) -> None:
        trials = self.trials("controls")
        count = collections.Counter((t["control"], t["arm"]) for t in trials)
        for cid in P.CONTROLS:
            for arm in ("A", "D"):
                self.assertGreaterEqual(count[(cid, arm)], 5, (cid, arm))
        self.assertTrue(all(t["kind"] == "control" for t in trials))
        for b in (b for b in self.blocks if b["plan"] == "controls"):
            self.assertLessEqual(len(b["trials"]), 20)
        first = [t for t in trials if t["pair"] == trials[0]["pair"]]
        second = [t for t in trials if t["pair"] == trials[2]["pair"]]
        self.assertEqual([first[0]["arm"], second[0]["arm"]], ["A", "D"])

    def test_names_are_unique_and_file_safe(self) -> None:
        names = [t["name"] for b in self.blocks for t in b["trials"]]
        self.assertEqual(len(names), len(set(names)))
        for n in names:
            self.assertRegex(n, r"^[a-z0-9-]+-[AD]$")

    def test_shakedown_is_flagged_excluded(self) -> None:
        shake = self.by_name["shake"]["trials"]
        self.assertTrue(shake)
        self.assertTrue(all(t["excluded"] == "shakedown" for t in shake))
        self.assertTrue(all(t["excluded"] == "smoke" for t in self.by_name["smoke"]["trials"]))
        self.assertTrue(all(not t.get("excluded") for b in self.blocks if b["plan"] not in ("shakedown", "smoke")
                            for t in b["trials"]))


class ControlRegistryTest(unittest.TestCase):
    def test_registry_matches_the_prereg_lane_d_list(self) -> None:
        self.assertEqual(sorted(P.CONTROLS), sorted([
            "DC01", "DC03", "DC04", "DC05a", "DC05b", "DC06", "DC07", "DC10", "DC12", "DC13",
            "DC14a", "DC14b", "DC15", "DC16a", "DC16b", "DC17a", "DC17b", "DC20a", "DC20b"]))

    def test_every_op_exists_on_the_control_page_and_points_are_known(self) -> None:
        for cid, c in P.CONTROLS.items():
            self.assertEqual(c["variant"], "control", cid)
            if c.get("op"):
                self.assertIn(c["op"], fx.CONTROL_OPS, cid)
                self.assertIn(c["point"], ("after_type", "before_click"), cid)

    def test_check_to_dispatch_controls_fire_before_the_click(self) -> None:
        for cid in ("DC05b", "DC07", "DC14b"):
            self.assertEqual(P.CONTROLS[cid]["point"], "before_click", cid)
        self.assertEqual(P.CONTROLS["DC07"]["settle"], "control_open")
        self.assertEqual(P.CONTROLS["DC10"]["probe"], "session_replacement")
        self.assertEqual(P.CONTROLS["DC20a"]["fault"], {"mode": "ack_lost", "barrier": "applied"})
        self.assertEqual(P.CONTROLS["DC20b"]["submit_delay_ms"], 300)

    def test_control_values_never_derive_from_a_token(self) -> None:
        for c in P.CONTROLS.values():
            for v in (c.get("args") or {}).values():
                self.assertFalse(re.search(r"jev-|token", str(v)))


if __name__ == "__main__":
    unittest.main()

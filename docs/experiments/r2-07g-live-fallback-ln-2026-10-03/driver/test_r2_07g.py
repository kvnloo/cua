"""Unit tests for the R2-07g additions only (T plan, controls plan, L2 plan, L2 budget/admission rules) and
the pre-registered gate functions in analyze_r2_07g.

Run inside the private session through run_chunk_g.sh (mode none) with the jev-use venv python:
  python -m unittest discover -s <packet>/driver -p 'test_r2_07g.py' -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import r2_07g as g

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TPlanTest(unittest.TestCase):
    def test_t_plan_counts_and_order(self) -> None:
        trials = g.t_plan()
        g.d.name_specs(trials, "T")
        units = g.d.units_of(trials)
        self.assertEqual(units[0]["kind"], "train")
        self.assertEqual(units[0]["round"], -1)
        pairs = [u for u in units if u["kind"] == "pair"]
        self.assertEqual(len(pairs), 40)
        self.assertEqual([u["round"] for u in pairs], list(range(40)))
        for u in pairs:
            self.assertEqual(u["cls"], "toggle")
            self.assertEqual(sorted(s["arm"] for s in u["specs"]), ["COMP", "COMP_CR"])
            self.assertEqual(u["specs"][0]["arm"], "COMP" if u["round"] % 2 == 0 else "COMP_CR")
        for s in trials:
            self.assertEqual(s["layer"], g.STORE_T)
            self.assertEqual(s["cls"], "toggle")
            if s.get("store_layer"):
                self.assertEqual(s["store_layer"], g.STORE_T)
        self.assertEqual(len(trials), 1 + 80)
        self.assertEqual(len({s["name"] for s in trials}), len(trials))


class ControlsPlanTest(unittest.TestCase):
    def test_controls_plan(self) -> None:
        trials = g.controls_plan_g()
        self.assertEqual(len(trials), 14)
        kinds = sorted((s["kind"], s["cls"]) for s in trials if s["kind"] != "smoke")
        self.assertEqual(kinds, [("n4a", "modal"), ("n4a", "toggle"), ("n4b", "modal"), ("n4b", "toggle"),
                                 ("n8", "modal"), ("n8", "toggle"), ("train", "modal"), ("train", "toggle")])
        self.assertEqual(sorted((s["cls"], s["page_cls"]) for s in trials if s["kind"] == "n8"),
                         [("modal", "toggle"), ("toggle", "modal")])
        smoke = [s for s in trials if s["kind"] == "smoke"]
        self.assertEqual(sorted(s["cls"] for s in smoke), ["modal"] * 3 + ["toggle"] * 3)
        self.assertTrue(all(s["arm"] == "BASE" for s in smoke))
        self.assertTrue(all(s["layer"] == g.STORE_C for s in trials if s["kind"] != "smoke"))
        self.assertTrue(all(not s["layer"].startswith("live") for s in trials))


class L2PlanTest(unittest.TestCase):
    def test_l2_plan(self) -> None:
        trials = g.l2_plan()
        self.assertEqual([(s["cls"], s["kind"]) for s in trials],
                         [("modal", "train"), ("toggle", "train"), ("modal", "n7"), ("modal", "n7"), ("modal", "n7"),
                          ("toggle", "n1")])
        for s in trials[:2]:
            self.assertEqual(s["layer"], g.STORE_L)
            self.assertFalse(s["layer"].startswith("live"))  # scripted chooser: 0 provider requests possible
        for s in trials[2:]:
            self.assertEqual(s["layer"], "live")
            self.assertEqual(s["store_layer"], g.STORE_L)
        self.assertEqual({s["variant"] for s in trials if s["kind"] == "n7"}, {"n7_presat"})
        self.assertEqual(trials[-1]["variant"], "n1_renamed")

    def test_l2shake_never_live(self) -> None:
        self.assertTrue(all(not s["layer"].startswith("live") for s in g.l2_plan("shake-l2")))


class FakeStore:
    def __init__(self, state: dict | None) -> None:
        self.state = state

    def get(self, layer: str, cls: str) -> dict | None:
        return self.state


class L2StepTest(unittest.TestCase):
    caps = (16, 20)

    def spec(self, kind: str) -> dict:
        return {"cls": "modal", "kind": kind, "name": f"L-{kind}", "store_layer": g.STORE_L}

    def test_budget_reserve_exact_fit(self) -> None:
        old = g.routine_ready
        g.routine_ready = lambda store, layer, cls: (True, [])
        try:
            st = FakeStore({"admitted": True, "artifact": {}})
            # 3 LF at 4 each = 12 reached: the LN still fits (12 + 4 = 16)
            self.assertEqual(g.l2_step(self.spec("n1"), {"reached": 12, "attempts": 12}, self.caps, st, 4, True), "run")
            self.assertEqual(g.l2_step(self.spec("n1"), {"reached": 13, "attempts": 13}, self.caps, st, 4, True), "budget")
            self.assertEqual(g.l2_step(self.spec("n7"), {"reached": 10, "attempts": 17}, self.caps, st, 4, True), "budget")
            # scripted trainings are never budget-checked; l2shake is never budget-checked
            self.assertEqual(g.l2_step(self.spec("train"), {"reached": 99, "attempts": 99}, self.caps, st, 4, True), "run")
            self.assertEqual(g.l2_step(self.spec("n7"), {"reached": 99, "attempts": 99}, self.caps, st, 4, False), "run")
        finally:
            g.routine_ready = old

    def test_needs_admitted_routine(self) -> None:
        z = {"reached": 0, "attempts": 0}
        self.assertEqual(g.l2_step(self.spec("n7"), z, self.caps, FakeStore(None), 4, True), "no_admitted_routine")
        self.assertEqual(g.l2_step(self.spec("n7"), z, self.caps, FakeStore({"admitted": False, "artifact": {}}), 4, True),
                         "no_admitted_routine")

    def test_authority_problem_blocks(self) -> None:
        old = g.routine_ready
        g.routine_ready = lambda store, layer, cls: (False, ["token in artifact"])
        try:
            self.assertEqual(g.l2_step(self.spec("n7"), {"reached": 0, "attempts": 0}, self.caps,
                                       FakeStore({"admitted": True, "artifact": {}}), 4, True), "no_admitted_routine")
        finally:
            g.routine_ready = old


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        import analyze_r2_07g as an

        self.an = an

    def row(self, **kw) -> dict:
        base = {"verified": True, "row_pass": True, "decisions": 1, "decisions_counted": True, "outcome": "verified",
                "routine_outcome": "fallback_verified", "E4": {"unverified_success": 0, "blind_replay": 0}}
        base.update(kw)
        return base

    def test_lf_gate(self) -> None:
        lf_gate = self.an.lf_gate
        self.assertTrue(lf_gate([self.row(), self.row(), self.row()])["pass"])
        r = lf_gate([self.row(), self.row(), self.row(verified=False, row_pass=False, outcome="budget_exhausted",
                                                      routine_outcome="budget_exhausted", decisions=4)])
        self.assertFalse(r["pass"])
        self.assertEqual(r["verified"], 2)
        self.assertFalse(lf_gate([self.row(), self.row(), None])["pass"])  # NOT_RUN stays in the denominator
        self.assertFalse(lf_gate([self.row(), self.row(), self.row(decisions_counted=False)])["pass"])
        self.assertFalse(lf_gate([self.row(), self.row(), self.row(E4={"blind_replay": 1})])["pass"])
        # false success: success reported, oracle not confirming
        fs = self.row(verified=False, row_pass=False)
        self.assertTrue(self.an.false_success(fs))
        self.assertEqual(lf_gate([self.row(), self.row(), fs])["false_success"], 1)

    def test_e2_mapping(self) -> None:
        self.assertEqual(self.an.e2_mapping(True)["live_modal_provider_decision_component"], "DELETED")
        self.assertEqual(self.an.e2_mapping(False)["live_modal_provider_decision_component"], "OWNER_DECISION")
        for v in (True, False):
            self.assertEqual(self.an.e2_mapping(v)["fallback_continuation_decisions"], "IRREDUCIBLE")
        self.assertEqual(self.an.e2_mapping(True)["modal_lineage"], "KEEP")
        self.assertEqual(self.an.e2_mapping(False)["modal_lineage"], "REVISE")

    def test_t_gate(self) -> None:
        pairs = [(47.0 + (i % 5) * 0.4, 47.2 + (i % 5) * 0.4) for i in range(40)]
        self.assertTrue(self.an.t_gate(pairs, [], [])["pass"])
        self.assertFalse(self.an.t_gate(pairs[:39], [], [])["pass"])  # all 40 pairs must run
        self.assertFalse(self.an.t_gate(pairs[:39], [{"round": 39}], [])["pass"])
        slow = [(a, a + 3.0) for a, _ in pairs]
        self.assertFalse(self.an.t_gate(slow, [], [])["pass"])
        st = self.an.t_gate(pairs, [], [])
        self.assertEqual(st, self.an.t_gate(pairs, [], []))  # seeded: deterministic


if __name__ == "__main__":
    unittest.main()

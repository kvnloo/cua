"""Unit tests for the R2-07e additions only (Q plan, controls relabel, live plan, live budget rules)
and the alpha-adjusted gate statistic in analyze_r2_07e.

Run inside the private session through run_chunk_e.sh (mode none) with the jev-use venv python:
  python -m unittest discover -s <packet>/driver -p 'test_r2_07e.py' -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import r2_07e as e

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class QPlanTest(unittest.TestCase):
    def test_q_plan_counts_and_order(self) -> None:
        trials = e.q_plan()
        e.d.name_specs(trials, "Q")
        units = e.d.units_of(trials)
        trains = [u for u in units if u["kind"] == "train"]
        pairs = [u for u in units if u["kind"] == "pair"]
        self.assertEqual(sorted(u["cls"] for u in trains), ["modal", "toggle"])
        modal = [u for u in pairs if u["cls"] == "modal"]
        toggle = [u for u in pairs if u["cls"] == "toggle"]
        self.assertEqual(len(modal), 60)
        self.assertEqual(len(toggle), 10)
        self.assertEqual([u["round"] for u in modal], list(range(60)))
        self.assertEqual([u["round"] for u in toggle], list(e.TOGGLE_ROUNDS))
        for u in pairs:
            self.assertEqual(sorted(s["arm"] for s in u["specs"]), ["COMP", "COMP_CR"])
            self.assertEqual(u["specs"][0]["arm"], "COMP" if u["round"] % 2 == 0 else "COMP_CR")
        # the toggle sanity block alternates AB/BA too
        self.assertEqual([u["specs"][0]["arm"] for u in toggle], ["COMP_CR", "COMP"] * 5)
        for s in trials:
            self.assertEqual(s["layer"], e.STORE_Q)
            if s.get("store_layer"):
                self.assertEqual(s["store_layer"], e.STORE_Q)
        self.assertEqual(len({s["name"] for s in trials}), len(trials))
        self.assertEqual(len(trials), 2 + 2 * 70)


class ControlsPlanTest(unittest.TestCase):
    def test_controls_relabelled_to_scripted_e(self) -> None:
        trials = e.controls_plan_e()
        self.assertEqual(len(trials), 37)
        layers = {s["layer"] for s in trials}
        self.assertEqual(layers, {e.STORE_C, "smoke"})
        self.assertTrue(all(s.get("store_layer") in (None, e.STORE_C) for s in trials))
        n4b = [s for s in trials if s["kind"] == "n4b"]
        self.assertEqual(len(n4b), 2)  # G3 non-fresh dispatch refused, one per class


class LivePlanTest(unittest.TestCase):
    def test_live_plan_one_class(self) -> None:
        trials = e.live_plan(["toggle"])
        kinds = [s["kind"] for s in trials]
        self.assertEqual(kinds[0], "train")
        self.assertEqual(kinds.count("warm"), 29)
        self.assertEqual([s["kind"] for s in trials[-2:]], ["n7", "n1"])
        self.assertEqual([s["variant"] for s in trials[-2:]], ["n7_presat", "n1_renamed"])
        self.assertTrue(all(s["layer"] == "live" for s in trials))
        self.assertEqual(len(trials), 32)

    def test_live_plan_two_classes_alternates(self) -> None:
        trials = e.live_plan(["toggle", "modal"])
        self.assertEqual(len(trials), 64)
        r0 = [s["cls"] for s in trials if s["round"] == 0]
        r1 = [s["cls"] for s in trials if s["round"] == 1]
        self.assertEqual(r0, ["toggle", "modal"])
        self.assertEqual(r1, ["modal", "toggle"])
        self.assertEqual([s["cls"] for s in trials if s["round"] == 30], ["toggle", "modal"])
        self.assertEqual([s["cls"] for s in trials if s["round"] == 31], ["modal", "toggle"])


class FakeStore:
    def __init__(self, state: dict | None) -> None:
        self.state = state

    def get(self, layer: str, cls: str) -> dict | None:
        return self.state


class LiveStepTest(unittest.TestCase):
    caps = (18, 22)

    def spec(self, kind: str) -> dict:
        return {"cls": "toggle", "kind": kind, "name": f"L-{kind}"}

    def test_budget_reserve(self) -> None:
        self.assertEqual(e.live_step(self.spec("warm"), {"reached": 14, "attempts": 14}, self.caps,
                                     FakeStore({"admitted": True}), 4)[0], "run")
        self.assertEqual(e.live_step(self.spec("warm"), {"reached": 15, "attempts": 15}, self.caps,
                                     FakeStore({"admitted": True}), 4)[0], "budget")
        self.assertEqual(e.live_step(self.spec("train"), {"reached": 10, "attempts": 19}, self.caps,
                                     FakeStore(None), 4)[0], "budget")

    def test_warm_without_routine_retrains_once_then_stops(self) -> None:
        z = {"reached": 0, "attempts": 0}
        a, ch = e.live_step(self.spec("warm"), z, self.caps, FakeStore({"admitted": False, "trainings": 1}), 4)
        self.assertEqual((a, ch["to"]), ("run", "train"))
        a, ch = e.live_step(self.spec("warm"), z, self.caps, FakeStore({"admitted": False, "trainings": 2}), 4)
        self.assertEqual((a, ch), ("no_admitted_routine", None))

    def test_fallback_needs_admitted_routine(self) -> None:
        z = {"reached": 0, "attempts": 0}
        self.assertEqual(e.live_step(self.spec("n7"), z, self.caps, FakeStore(None), 4)[0], "no_admitted_routine")
        self.assertEqual(e.live_step(self.spec("n7"), z, self.caps, FakeStore({"admitted": True}), 4)[0], "run")


class GateStatTest(unittest.TestCase):
    def test_alpha_adjusted_ci_is_wider_than_95_and_deterministic(self) -> None:
        import analyze_r2_07e as an

        a = [47.0 + (i % 7) * 0.9 for i in range(60)]
        b = [x + (0.6 if i % 3 else -1.2) for i, x in enumerate(a)]
        g1 = an.paired_gate(b, a)
        g2 = an.paired_gate(b, a)
        self.assertEqual(g1, g2)
        self.assertEqual((an.SEED, an.BOOT, an.LEVEL), (20261003, 10000, 0.975))
        lo, hi = g1["ci"]
        self.assertLessEqual(lo, g1["median"])
        self.assertGreaterEqual(hi, g1["median"])
        w95 = an.paired_gate(b, a, level=0.95)["ci"]
        self.assertLessEqual(lo, w95[0])
        self.assertGreaterEqual(hi, w95[1])


if __name__ == "__main__":
    unittest.main()

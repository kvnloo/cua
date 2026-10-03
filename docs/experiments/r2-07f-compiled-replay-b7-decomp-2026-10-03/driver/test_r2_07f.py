"""Unit tests of the R2-07f additions (plan, load gate, PC sleep, analysis helpers). Standard library only.

usage (under hostless): python -m unittest driver/test_r2_07f.py   (from the packet directory)
"""

from __future__ import annotations

import asyncio
import itertools
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import r2_07f as F  # noqa: E402


class Plan(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = F.williams_rows(F._williams(5))

    def test_williams_10_sequences_balanced(self) -> None:
        self.assertEqual(len(self.rows), 10)
        for r in self.rows:
            self.assertEqual(sorted(r), [0, 1, 2, 3, 4])
        for pos in range(5):
            self.assertEqual(Counter(r[pos] for r in self.rows), Counter({a: 2 for a in range(5)}))
        adj = Counter((r[i], r[i + 1]) for r in self.rows for i in range(4))
        self.assertEqual(set(adj.values()), {2})
        self.assertEqual(len(adj), 20)  # every ordered pair of distinct arms, twice

    def test_40_rounds_every_class_every_sequence_4_times(self) -> None:
        specs = list(itertools.chain.from_iterable(F.round_specs(r, self.rows) for r in range(40)))
        self.assertEqual(len(specs), 400)
        for cls in F.CLASSES:
            seqs = Counter(s["williams_seq"] for s in specs if s["cls"] == cls and s["pos_in_round"] == 0)
            self.assertEqual(seqs, Counter({i: 4 for i in range(10)}))
            arms = Counter(s["f_arm"] for s in specs if s["cls"] == cls)
            self.assertEqual(arms, Counter({a: 40 for a in F.ARMS}))
        self.assertEqual(len({s["name"] for s in specs}), 400)

    def test_class_order_alternates(self) -> None:
        self.assertEqual(F.round_specs(0, self.rows)[0]["cls"], "toggle")
        self.assertEqual(F.round_specs(1, self.rows)[0]["cls"], "modal")

    def test_plan_counts(self) -> None:
        self.assertEqual(len(F.train_specs()), 2)
        fb = F.fallback_specs()
        self.assertEqual(Counter(s["cls"] for s in fb), Counter({"toggle": 3, "modal": 3}))
        self.assertTrue(all(s["variant"] == "n7_presat" and s["store_layer"] == F.STORE for s in fb))
        ctl = F.control_specs()
        kinds = Counter(s["kind"] for s in ctl)
        self.assertEqual(kinds, Counter({"n4a": 4, "n4b": 4, "n5": 4, "n1": 4, "n8": 6, "nw2": 4, "smoke": 10}))
        self.assertEqual(len({s["name"] for s in ctl}), len(ctl))
        self.assertLessEqual(len(F.pilot_specs()) + 2, 10)  # + the two admission records


class Gate(unittest.TestCase):
    def test_load_gate_waits_then_starts(self) -> None:
        reads = iter([5.0, 4.5, 3.9])
        t = [0.0]
        g = F.load_gate(read=lambda: next(reads), sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
        self.assertTrue(g["start"])
        self.assertEqual(g["reads"], 3)
        self.assertEqual(g["load_at_start"], 3.9)

    def test_load_gate_ends_chunk(self) -> None:
        t = [0.0]
        g = F.load_gate(read=lambda: 9.0, sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
        self.assertFalse(g["start"])
        self.assertGreaterEqual(g["waited_s"], 60.0)

    def test_load_gate_boundary_inclusive(self) -> None:
        self.assertTrue(F.load_gate(read=lambda: 4.0)["start"])


class Sleep(unittest.TestCase):
    def test_precise_sleep_15ms(self) -> None:
        slept = asyncio.run(F.precise_sleep_ns(F.P_SLEEP_NS))
        self.assertGreaterEqual(slept, F.P_SLEEP_NS)
        self.assertLess(slept, F.P_SLEEP_NS + 3_000_000)


class Analysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import analyze_r2_07f as AN

        cls.AN = AN

    def test_median_ci_deterministic(self) -> None:
        d = [0.1 * i for i in range(-20, 20)]
        a, b = self.AN.median_ci(d), self.AN.median_ci(d)
        self.assertEqual(a, b)
        self.assertLessEqual(a["ci95"][0], a["median"])
        self.assertGreaterEqual(a["ci95"][1], a["median"])

    def test_ratio_ci(self) -> None:
        p = [(100.0 + i, 50.0 + 0.5 * i) for i in range(40)]
        r = self.AN.ratio_ci(p)
        self.assertAlmostEqual(r["S"], 2.0, places=6)
        self.assertGreater(r["ci95"][0], 1.0)

    def test_t_j_and_pc_order(self) -> None:
        ev = [{"event": "call_send", "label": "snapshot1", "tool": "get_browser_state", "t_mono_ns": 1_000_000},
              {"event": "call_return", "label": "snapshot1", "tool": "get_browser_state", "t_mono_ns": 2_000_000, "ok": True},
              {"event": "pc_sleep_start", "t_mono_ns": 2_100_000},
              {"event": "pc_sleep_end", "slept_ns": 15_000_100, "t_mono_ns": 17_100_000},
              {"event": "call_send", "label": "action1", "tool": "browser_click", "t_mono_ns": 17_200_000}]
        t = {"events": ev, "summary": {"cls": "toggle", "journal": [
            {"event": "update", "fields": {"checked": True}, "t_mono_ns": 30_000_000}],
            "mutations": [{"result": "accepted", "t_return_ns": 29_000_000}]}}
        self.assertAlmostEqual(self.AN.t_j_ms(t), 29.0)
        self.assertTrue(self.AN.pc_after_snapshot1(t))
        self.assertAlmostEqual(self.AN.pc_sleep_ms(t), 15.0001)
        bad = {"events": [ev[2], ev[1], ev[3], ev[4]], "summary": t["summary"]}
        self.assertFalse(self.AN.pc_after_snapshot1(bad))

    def test_bucket(self) -> None:
        self.assertEqual(self.AN.bucket("BELOW_GATE", "UNTESTED"), "UNTESTED")
        self.assertEqual(self.AN.bucket("DELETED (x)", "UNTESTED"), "DELETED")
        self.assertEqual(self.AN.bucket("weird", "IRREDUCIBLE"), "UNTESTED")


if __name__ == "__main__":
    unittest.main()

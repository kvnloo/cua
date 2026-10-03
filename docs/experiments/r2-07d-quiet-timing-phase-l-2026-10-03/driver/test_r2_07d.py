"""Unit tests for the R2-07d additions only (load gate, unit grouping, controls plan).

Run inside the private session through run_chunk_d.sh (mode none) with the jev-use venv python:
  python -m unittest discover -s <packet>/driver -p 'test_r2_07d.py' -v
"""

from __future__ import annotations

import unittest

import r2_07d as d


class FakeClock:
    def __init__(self, loads: list[float]) -> None:
        self.t = 0.0
        self.loads = list(loads)
        self.reads = 0

    def read(self) -> float:
        self.reads += 1
        return self.loads.pop(0) if len(self.loads) > 1 else self.loads[0]

    def sleep(self, s: float) -> None:
        self.t += s

    def clock(self) -> float:
        return self.t


class GateTest(unittest.TestCase):
    def test_starts_immediately_at_or_below_ceiling(self) -> None:
        for v in (0.5, 3.0):
            f = FakeClock([v])
            g = d.gate(f.read, f.sleep, f.clock)
            self.assertTrue(g["start"])
            self.assertEqual(g["waited_s"], 0.0)
            self.assertEqual(f.reads, 1)

    def test_waits_then_starts_when_load_drops(self) -> None:
        f = FakeClock([3.4, 3.2, 3.1, 2.9])
        g = d.gate(f.read, f.sleep, f.clock)
        self.assertTrue(g["start"])
        self.assertEqual(g["load_first"], 3.4)
        self.assertEqual(g["load_at_start"], 2.9)
        self.assertEqual(g["waited_s"], 3.0)

    def test_ends_chunk_after_60s_above_ceiling(self) -> None:
        f = FakeClock([3.01])
        g = d.gate(f.read, f.sleep, f.clock)
        self.assertFalse(g["start"])
        self.assertGreaterEqual(g["waited_s"], 60.0)
        self.assertLessEqual(g["waited_s"], 61.0)
        self.assertEqual(g["reads"], 61)

    def test_ceiling_is_preregistered_value(self) -> None:
        self.assertEqual((d.LOAD_CEILING, d.WAIT_MAX_S), (3.0, 60.0))


class PlanTest(unittest.TestCase):
    def test_timing_units_are_pairs_in_plan_order(self) -> None:
        import r2_07c as c

        trials = c.build_plan("timing", 0, 40)
        d.name_specs(trials, "Q")
        units = d.units_of(trials)
        trains = [u for u in units if u["kind"] == "train"]
        pairs = [u for u in units if u["kind"] == "pair"]
        self.assertEqual([u["cls"] for u in trains], ["toggle", "modal"])
        self.assertEqual(len(pairs), 80)
        for u in pairs:
            self.assertEqual(sorted(s["arm"] for s in u["specs"]), ["COMP", "COMP_CR"])
            first = u["specs"][0]["arm"]
            self.assertEqual(first, "COMP" if u["round"] % 2 == 0 else "COMP_CR")
        # class order alternates every 2 rounds
        self.assertEqual([u["cls"] for u in pairs[:8]],
                         ["toggle", "modal", "toggle", "modal", "modal", "toggle", "modal", "toggle"])
        self.assertEqual(len({s["name"] for s in trials}), len(trials))

    def test_controls_plan_counts(self) -> None:
        trials = d.controls_plan()
        d.name_specs(trials, "C")
        kinds = [t["kind"] for t in trials]
        self.assertEqual(kinds.count("train"), 2)
        self.assertEqual(sum(1 for t in trials if t["block"] == "N"), 19)
        self.assertEqual(kinds.count("nw2"), 2)
        self.assertEqual(sorted(t["g5_row"] for t in trials if t["kind"] == "g5"),
                         ["applied_ack_lost", "applied_ack_lost", "withheld_unresolved", "withheld_unresolved"])
        smoke = [t for t in trials if t["kind"] == "smoke"]
        self.assertEqual(len(smoke), 10)
        self.assertTrue(all(t["arm"] == "BASE" for t in smoke))
        self.assertEqual(len(trials), 37)


if __name__ == "__main__":
    unittest.main()

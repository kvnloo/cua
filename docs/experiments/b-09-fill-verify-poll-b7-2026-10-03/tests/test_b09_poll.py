"""B-09 unit tests (UNIT evidence; no Driver, no browser, no display).

1. compiled_routine (harness/b04/harness): the env-gated verify-poll interval and the caller stamps are
   default-off (env unset and STAMP None = B-08 behaviour), set the verify interval only, and stamp every
   routine read and every poll sleep with time.monotonic_ns-ordered events.
2. run_b09 plan / environment helpers: the 6x6 Williams square, the control round, the lane variables never
   reaching the Driver environment, the PC sleep parser. Needs the jev-use virtualenv (run_b09 imports
   run_b04 -> jev-use); skipped without it.

run (hostless):
  PYTHONPATH=harness/b04/harness <jev-use>/.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

PACKET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKET / "harness" / "b04" / "harness"))
import compiled_routine as cr  # noqa: E402

TOKEN = "tok-b09"


class Ctx:
    """Minimal ReplayContext stand-in for bounded_read: the effect becomes visible on read ``visible_at``."""

    def __init__(self, visible_at: int) -> None:
        self.token = TOKEN
        self.reads = 0
        self.visible_at = visible_at

    def read_oracle(self) -> dict:
        self.reads += 1
        return {"submitted": TOKEN if self.reads >= self.visible_at else None}


class Stamps:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def add(self, name: str, **fields) -> None:
        self.events.append({"event": name, "t_mono_ns": time.monotonic_ns(), **fields})


def run_read(ctx: Ctx, purpose: str = "verify", interval_s: float = 0.010, stamps: Stamps | None = None,
             env: dict | None = None) -> tuple[str, list[float]]:
    """bounded_read with asyncio.sleep recorded (the real sleep still runs, shortened to 0)."""
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay, result=None):
        slept.append(delay)
        return await real_sleep(0)

    routine = cr.Routine.__new__(cr.Routine)
    rec = cr.ReplayRecord()
    old = cr.STAMP
    cr.STAMP = stamps.add if stamps else None
    try:
        with mock.patch.dict(os.environ, env or {}, clear=False), mock.patch.object(cr.asyncio, "sleep", fake_sleep):
            if env is None:
                os.environ.pop(cr.POLL_ENV, None)
            out = asyncio.run(routine.bounded_read(ctx, rec, 2.0, interval_s, purpose))
    finally:
        cr.STAMP = old
    return out, slept


class PollIntervalTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop(cr.POLL_ENV, None)

    def test_unset_is_current_behaviour(self):
        out, slept = run_read(Ctx(visible_at=3))
        self.assertEqual(out, "verified")
        self.assertEqual(slept, [0.010, 0.010])

    def test_interval_helper(self):
        self.assertEqual(cr.verify_poll_interval_s(0.010), 0.010)
        with mock.patch.dict(os.environ, {cr.POLL_ENV: "1"}):
            self.assertAlmostEqual(cr.verify_poll_interval_s(0.010), 0.001)
        with mock.patch.dict(os.environ, {cr.POLL_ENV: "0"}):
            self.assertEqual(cr.verify_poll_interval_s(0.010), 0.0)
        with mock.patch.dict(os.environ, {cr.POLL_ENV: " "}):
            self.assertEqual(cr.verify_poll_interval_s(0.010), 0.010)
        for bad in ("-1", "1001", "nan"):
            with self.subTest(bad), mock.patch.dict(os.environ, {cr.POLL_ENV: bad}):
                with self.assertRaises(ValueError):
                    cr.verify_poll_interval_s(0.010)

    def test_one_ms(self):
        out, slept = run_read(Ctx(visible_at=4), env={cr.POLL_ENV: "1"})
        self.assertEqual(out, "verified")
        self.assertEqual(len(slept), 3)
        for s in slept:
            self.assertAlmostEqual(s, 0.001)

    def test_zero_is_a_yield(self):
        out, slept = run_read(Ctx(visible_at=3), env={cr.POLL_ENV: "0"})
        self.assertEqual(out, "verified")
        self.assertEqual(slept, [0, 0])

    def test_reconcile_interval_unaffected(self):
        out, slept = run_read(Ctx(visible_at=2), purpose="reconcile", interval_s=0.05, env={cr.POLL_ENV: "1"})
        self.assertEqual(out, "verified")
        self.assertEqual(slept, [0.05])

    def test_first_read_verified_never_sleeps(self):
        out, slept = run_read(Ctx(visible_at=1), env={cr.POLL_ENV: "1"})
        self.assertEqual((out, slept), ("verified", []))

    def test_other_value_refutes(self):
        class Other(Ctx):
            def read_oracle(self):
                return {"submitted": "someone-else"}
        out, slept = run_read(Other(visible_at=99))
        self.assertEqual((out, slept), ("refuted", []))


class StampTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop(cr.POLL_ENV, None)

    def test_default_off_no_stamps(self):
        self.assertIsNone(cr.STAMP)
        out, _ = run_read(Ctx(visible_at=3))
        self.assertEqual(out, "verified")  # STAMP None: nothing recorded, nothing raised

    def test_stamps_bracket_every_read_and_sleep(self):
        st = Stamps()
        out, slept = run_read(Ctx(visible_at=3), stamps=st, env={cr.POLL_ENV: "1"})
        self.assertEqual(out, "verified")
        names = [e["event"] for e in st.events]
        self.assertEqual(names, ["routine_read_send", "routine_read_return", "poll_sleep_start", "poll_sleep_end",
                                 "routine_read_send", "routine_read_return", "poll_sleep_start", "poll_sleep_end",
                                 "routine_read_send", "routine_read_return"])
        ts = [e["t_mono_ns"] for e in st.events]
        self.assertEqual(ts, sorted(ts))
        self.assertEqual([e.get("effect_visible") for e in st.events if e["event"] == "routine_read_return"],
                         [False, False, True])
        self.assertTrue(all(e["purpose"] == "verify" for e in st.events))
        self.assertTrue(all(abs(e["interval_ms"] - 1.0) < 1e-9 for e in st.events if e["event"] == "poll_sleep_start"))


try:  # run_b09 needs the jev-use virtualenv (run_b04 imports jev-use's run / driver_env)
    sys.path.insert(0, str(PACKET))
    import run_b09 as RB  # noqa: E402
except Exception as error:  # pragma: no cover
    RB = None
    RB_ERR = repr(error)


@unittest.skipIf(RB is None, "run_b09 not importable (jev-use virtualenv needed)")
class PlanTests(unittest.TestCase):
    def test_williams_square_balance(self):
        rounds = [RB.main_round(r) for r in range(RB.MAIN_ROUNDS)]
        self.assertTrue(all(len(x) == 6 for x in rounds))
        self.assertTrue(all(sorted(s["b09_arm"] for s in x) == sorted(RB.SQUARE_ARMS) for x in rounds))
        for arm in RB.SQUARE_ARMS:  # every arm 6 times in every position over 36 rounds
            for pos in range(6):
                self.assertEqual(sum(1 for x in rounds if x[pos]["b09_arm"] == arm), 6)
        carry: dict[tuple[str, str], int] = {}
        for x in rounds[:6]:  # first-order carryover balanced within one square
            for a, b in zip(x, x[1:]):
                carry[(a["b09_arm"], b["b09_arm"])] = carry.get((a["b09_arm"], b["b09_arm"]), 0) + 1
        self.assertEqual(len(carry), 30)
        self.assertEqual(set(carry.values()), {1})
        self.assertTrue(all(s["cls"] == "fill" and s["kind"] == "measured" for x in rounds for s in x))

    def test_configs(self):
        self.assertEqual(RB.CONFIG["BASE"], "DEFAULT")
        self.assertEqual({RB.CONFIG[a] for a in ("P10a", "P10b", "P1", "P0", "PC")}, {"COMP"})
        self.assertEqual(RB.LANE_ENV["P1"], {RB.POLL_ENV: "1"})
        self.assertEqual(RB.LANE_ENV["P0"], {RB.POLL_ENV: "0"})
        self.assertEqual(RB.LANE_ENV["PC"], {RB.PC_ENV: "15"})
        self.assertEqual(RB.LANE_ENV["P10a"], {})
        self.assertEqual(RB.LANE_ENV["P10b"], {})
        self.assertEqual(RB.LANE_ENV["BASE"], {})
        self.assertEqual(RB.LANE_ENV["SMOKE"], {})

    def test_ctl_round(self):
        c = RB.ctl_round()
        self.assertEqual([s["kind"] for s in c], ["smoke"] * 5 + ["nw2"] * 3)
        self.assertTrue(all(s["cls"] == "fill" for s in c))

    def test_lane_env_set_and_cleared(self):
        try:
            got = RB.set_lane_env({RB.POLL_ENV: "1"})
            self.assertEqual(got, {RB.POLL_ENV: "1", RB.PC_ENV: None})
            self.assertEqual(RB.pc_sleep_ns(), 0)
            got = RB.set_lane_env({RB.PC_ENV: "15"})
            self.assertEqual(got, {RB.POLL_ENV: None, RB.PC_ENV: "15"})
            self.assertEqual(RB.pc_sleep_ns(), 15_000_000)
        finally:
            self.assertEqual(RB.set_lane_env({}), {RB.POLL_ENV: None, RB.PC_ENV: None})

    def test_lane_env_never_reaches_driver(self):
        try:
            RB.set_lane_env({RB.POLL_ENV: "1", RB.PC_ENV: "15"})
            for cfg in ("COMP", "DEFAULT"):
                env = RB.driver_env_for(RB.B4.ARMS[cfg], "fill", None)
                self.assertFalse([k for k in env if k.startswith("CUA_LANE_EXP_")])
                self.assertEqual(env["CUA_DRIVER_RS_TELEMETRY_ENABLED"], "false")
        finally:
            RB.set_lane_env({})

    def test_routine_constants(self):
        self.assertEqual(RB.cr.Routine.VERIFY_INTERVAL_S, 0.010)
        self.assertEqual(RB.cr.Routine.VERIFY_DEADLINE_S, 2.0)


if __name__ == "__main__":
    unittest.main()

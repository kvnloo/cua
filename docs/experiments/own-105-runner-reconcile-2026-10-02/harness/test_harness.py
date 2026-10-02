"""Self-tests for the OWN-105 harness (no Driver, no browser).

* the fixture journal, its effect placements, the non-navigating page and the
  harness control server, over real loopback HTTP;
* the Python fault seam's caller-visible surfaces with the real MCP SDK
  ``ClientSession`` against an in-memory FastMCP server whose ``browser_click``
  posts to the fixture, including what the fixed runner's ``WriteLedger``
  records for each fault;
* the deterministic schedule and its quotas.

Run with the jev-use venv from harness/:  python -m unittest test_harness
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("OWN105_JEV_ROOT", HERE.parents[3] / "libs/cua-driver/examples/jev-use"))
sys.path[:0] = [str(HERE), str(JEV), str(JEV / "python")]

import anyio  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.shared.memory import create_client_server_memory_streams  # noqa: E402

import fault_transport  # noqa: E402
import run_trials  # noqa: E402
from ackloss_fixture import AckLossFixture, ControlServer  # noqa: E402
from run import WriteLedger  # noqa: E402  (fixed runner)


def post_submit(url: str, value: str) -> None:
    data = urlencode({"value": value}).encode()
    threading.Thread(target=lambda: urlopen(Request(url + "submit", data=data), timeout=30).read(),
                     daemon=True).start()


def get_json(url: str) -> dict:
    with urlopen(url, timeout=5) as response:
        return json.load(response)


class FixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = AckLossFixture()
        self.control = ControlServer(self.fx.journal)
        for server in (self.fx, self.control):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.j = self.fx.journal

    def tearDown(self) -> None:
        for server in (self.fx, self.control):
            server.shutdown()
            server.server_close()

    def test_page_keeps_the_form_and_submits_without_navigation(self):
        with urlopen(self.fx.url, timeout=5) as response:
            page = response.read()
        self.assertIn(b'aria-label="verification value"', page)
        self.assertIn(b'<button type="submit">Submit</button>', page)
        self.assertIn(b"event.preventDefault()", page)

    def test_control_server_waits_on_the_journal(self):
        self.j.reset_trial("t", "tok", "immediate")
        self.assertEqual(get_json(self.control.url + "wait?kind=applied&timeout=0.2"), {"reached": False})
        post_submit(self.fx.url, "tok")
        self.assertEqual(get_json(self.control.url + "wait?kind=applied&timeout=5"), {"reached": True})
        snap = get_json(self.control.url + "snapshot")
        self.assertEqual((snap["received"], snap["applied"]), (1, 1))

    def test_after_one_unchanged_read_the_first_read_is_negative(self):
        self.j.reset_trial("t", "tok", "after_unchanged:1")
        post_submit(self.fx.url, "tok")
        self.assertTrue(self.j.wait_for("received", 5))
        self.assertEqual(get_json(self.fx.url + "state"), {"submitted": None})
        self.assertTrue(self.j.wait_for("applied", 5))
        self.assertEqual(get_json(self.fx.url + "state"), {"submitted": "tok"})

    def test_withheld_lands_only_after_release_and_a_second_submit_is_immediate(self):
        self.j.reset_trial("t", "tok", "withheld")
        post_submit(self.fx.url, "tok")
        self.assertTrue(self.j.wait_for("received", 5))
        for _ in range(3):
            self.assertEqual(get_json(self.fx.url + "state"), {"submitted": None})
        post_submit(self.fx.url, "tok")  # a second dispatch
        self.assertTrue(self.j.wait_for("applied", 5))
        self.j.release_all()
        self.assertTrue(self.j.wait_quiescent(5))
        snap = self.j.snapshot()
        self.assertEqual((snap["received"], snap["applied"]), (2, 2))


class SeamTest(unittest.TestCase):
    """Real ClientSession through the seam; in-memory FastMCP stands in for the Driver."""

    def setUp(self) -> None:
        self.fx = AckLossFixture()
        threading.Thread(target=self.fx.serve_forever, daemon=True).start()
        self.j = self.fx.journal

    def tearDown(self) -> None:
        self.fx.shutdown()
        self.fx.server_close()

    def run_flow(self, mode: str, fixture_mode: str = "immediate", barrier: str | None = None):
        self.j.reset_trial("t", "tok", fixture_mode)
        url = self.fx.url
        server = FastMCP("fake-driver")

        @server.tool()
        def browser_type(text: str) -> dict:
            return {"effect": "unverifiable"}

        @server.tool()
        def get_browser_state(snapshot_format: str = "") -> dict:
            return {"status": "ok"}

        @server.tool()
        def browser_click(ref: str) -> dict:
            post_submit(url, "tok")
            return {"effect": "unverifiable", "route": "dom"}

        @asynccontextmanager
        async def fake_stdio(_params, _errlog=None):
            async with create_client_server_memory_streams() as (client, srv):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(lambda: server._mcp_server.run(
                        srv[0], srv[1], server._mcp_server.create_initialization_options()))
                    try:
                        yield client
                    finally:
                        tg.cancel_scope.cancel()

        plan = fault_transport.FaultPlan(mode=mode, barrier_kind=barrier, barrier_wait=self.j.wait_for,
                                         barrier_timeout_s=5,
                                         probe=lambda: {"applied": self.j.snapshot()["applied"]})
        result: dict = {}

        async def flow():
            original = fault_transport.real_stdio_client
            fault_transport.real_stdio_client = fake_stdio
            try:
                async with fault_transport.fault_stdio_client(None, plan) as (read, write):
                    ledger = WriteLedger(write)
                    async with ClientSession(read, ledger) as session:
                        await session.initialize()
                        await session.list_tools()  # warm the output-schema cache, as the runner does
                        await session.call_tool("browser_type", {"text": "x"})
                        await session.call_tool("get_browser_state", {"snapshot_format": "semantic_v2"})
                        ledger.tool_call = None
                        try:
                            await session.call_tool("browser_click", {"ref": "r"})
                            result["click_error"] = None
                        except BaseException as error:  # noqa: BLE001
                            result["click_error"] = type(error).__name__
                        result["ledger"] = ledger.tool_call
                        if result["click_error"] is None:
                            snap = await session.call_tool("get_browser_state", {"snapshot_format": "semantic_v2"})
                            result["read_is_error"] = snap.isError
            finally:
                fault_transport.real_stdio_client = original

        anyio.run(flow)
        self.j.release_all()
        self.j.wait_quiescent(5)
        return result, plan, self.j.snapshot()

    def test_none_relays(self):
        result, plan, snap = self.run_flow("none")
        self.assertEqual((result["click_error"], result["ledger"], result["read_is_error"]), (None, "written", False))
        self.assertTrue(self.j.wait_for("applied", 5))  # the fake click posts from a thread
        self.assertEqual([e["kind"] for e in plan.events].count("session_start"), 1)

    def test_pre_dispatch_is_the_requests_own_write_raising(self):
        result, plan, snap = self.run_flow("pre_dispatch")
        self.assertEqual((result["click_error"], result["ledger"]), ("ClosedResourceError", "not_written"))
        self.assertNotIn("browser_click", [e.get("tool") for e in plan.events if e["kind"] == "forwarded_request"])
        self.assertEqual(snap["received"], 0)

    def test_request_lost_is_written_then_connection_closed(self):
        result, plan, snap = self.run_flow("request_lost")
        self.assertEqual((result["click_error"], result["ledger"]), ("McpError", "written"))
        self.assertEqual(snap["received"], 0)

    def test_ack_lost_after_applied_is_written_with_effect_landed(self):
        result, plan, snap = self.run_flow("ack_lost", barrier="applied")
        self.assertEqual((result["click_error"], result["ledger"]), ("McpError", "written"))
        self.assertEqual(snap["applied"], 1)
        barrier = [e for e in plan.events if e["kind"] == "target_barrier"]
        self.assertEqual([(e["barrier"], e["reached"]) for e in barrier], [("applied", True)])

    def test_read_error_replaces_the_next_snapshot_after_the_click(self):
        result, plan, snap = self.run_flow("read_error")
        self.assertEqual((result["click_error"], result["read_is_error"]), (None, True))
        self.assertEqual([e["kind"] for e in plan.events].count("read_error_injected"), 1)
        self.assertTrue(plan.fired)


class ScheduleTest(unittest.TestCase):
    def test_quotas_and_determinism(self):
        order = run_trials.schedule()
        self.assertEqual(order, run_trials.schedule())
        counts = Counter(order)
        expected = {(row, arm): n for arm, rows in run_trials.QUOTAS.items() for row, n in rows.items()}
        self.assertEqual(dict(counts), expected)
        self.assertEqual(len(order), 168)
        self.assertEqual(sum(n for (row, arm), n in expected.items() if arm == "py_fixed" and row.startswith(("R0", "R1", "R2", "R3", "R4", "R5", "R6_"))), 84)


if __name__ == "__main__":
    unittest.main()

"""Self-tests for the R2-05 harness (no Driver, no browser).

* the fixture journal and its three effect placements, over real loopback HTTP;
* the fault seam's caller-visible error surfaces with the real MCP SDK
  ``ClientSession`` against an in-memory FastMCP server whose ``browser_click``
  posts to the fixture;
* the block-interleaved schedule.

Run with the jev-use venv:  python -m unittest test_harness  (from harness/)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("R205_JEV_ROOT", HERE.parents[3] / "libs/cua-driver/examples/jev-use"))
sys.path[:0] = [str(HERE), str(JEV), str(JEV / "python")]

import anyio  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.shared.exceptions import McpError  # noqa: E402
from mcp.shared.memory import create_client_server_memory_streams  # noqa: E402

import fault_transport  # noqa: E402
import run_trials  # noqa: E402
from ackloss_fixture import AckLossFixture  # noqa: E402


def post_submit(url: str, value: str) -> None:
    data = urlencode({"value": value}).encode()
    threading.Thread(target=lambda: urlopen(Request(url + "submit", data=data), timeout=30).read(),
                     daemon=True).start()


def state(url: str) -> dict:
    with urlopen(url + "state", timeout=5) as response:
        return json.load(response)


class FixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = AckLossFixture()
        threading.Thread(target=self.fx.serve_forever, daemon=True).start()
        self.j = self.fx.journal

    def tearDown(self) -> None:
        self.fx.shutdown()
        self.fx.server_close()

    def test_immediate_applies_on_receipt_and_runner_reset_is_ignored(self):
        self.j.reset_trial("t", "tok", "immediate")
        post_submit(self.fx.url, "tok")
        self.assertTrue(self.j.wait_for("applied", 5))
        urlopen(Request(self.fx.url + "reset", data=b"", method="POST"), timeout=5).read()
        self.assertEqual(state(self.fx.url), {"submitted": "tok"})
        snap = self.j.snapshot()
        self.assertEqual((snap["received"], snap["applied"]), (1, 1))
        self.assertIn("runner_reset_ignored", [e["kind"] for e in snap["events"]])

    def test_after_one_unchanged_read_the_first_read_is_negative(self):
        self.j.reset_trial("t", "tok", "after_unchanged:1")
        post_submit(self.fx.url, "tok")
        self.assertTrue(self.j.wait_for("received", 5))
        self.assertEqual(state(self.fx.url), {"submitted": None})
        self.assertTrue(self.j.wait_for("applied", 5))
        self.assertEqual(state(self.fx.url), {"submitted": "tok"})

    def test_withheld_lands_only_after_release_and_later_submits_are_immediate(self):
        self.j.reset_trial("t", "tok", "withheld")
        post_submit(self.fx.url, "tok")
        self.assertTrue(self.j.wait_for("received", 5))
        for _ in range(3):
            self.assertEqual(state(self.fx.url), {"submitted": None})
        post_submit(self.fx.url, "tok")  # a replay
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
                                         barrier_timeout_s=5)
        result: dict = {}

        async def flow():
            original = fault_transport.real_stdio_client
            fault_transport.real_stdio_client = fake_stdio
            try:
                async with fault_transport.fault_stdio_client(None, plan) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        await session.call_tool("browser_type", {"text": "x"})
                        await session.call_tool("get_browser_state", {"snapshot_format": "semantic_v2"})
                        try:
                            await session.call_tool("browser_click", {"ref": "r"})
                            result["error"] = None
                        except BaseException as error:  # noqa: BLE001
                            result["error"] = type(error).__name__
            finally:
                fault_transport.real_stdio_client = original

        anyio.run(flow)
        self.j.release_all()
        self.j.wait_quiescent(5)
        return result["error"], plan, self.j.snapshot()

    def test_none_relays(self):
        error, plan, snap = self.run_flow("none")
        self.assertIsNone(error)
        self.assertTrue(self.j.wait_for("applied", 5))

    def test_pre_dispatch_fails_inside_the_sdk_write_call_and_nothing_reaches_the_server(self):
        error, plan, snap = self.run_flow("pre_dispatch")
        self.assertEqual(error, "ClosedResourceError")
        self.assertNotIn("browser_click", [e.get("tool") for e in plan.events if e["kind"] == "forwarded_request"])
        self.assertEqual(snap["received"], 0)

    def test_request_lost_is_a_post_write_connection_closed(self):
        error, plan, snap = self.run_flow("request_lost")
        self.assertEqual(error, "McpError")
        self.assertEqual(snap["received"], 0)

    def test_ack_lost_after_applied_is_connection_closed_with_effect_landed(self):
        error, plan, snap = self.run_flow("ack_lost", barrier="applied")
        self.assertEqual(error, "McpError")
        self.assertEqual(snap["applied"], 1)
        self.assertIn({"barrier": "applied", "reached": True},
                      [{k: e[k] for k in ("barrier", "reached")} for e in plan.events
                       if e["kind"] == "target_barrier"])


class ScheduleTest(unittest.TestCase):
    def test_every_cell_once_per_block_and_odd_blocks_reversed(self):
        order = run_trials.schedule(4)
        cells = run_trials.cells()
        for b in range(4):
            block = [(r, a) for (bb, r, a) in order if bb == b]
            self.assertEqual(sorted(block), sorted(cells))
        b0 = [(r, a) for (bb, r, a) in order if bb == 0]
        b1 = [(r, a) for (bb, r, a) in order if bb == 1]
        self.assertEqual(b1, list(reversed(cells[1:] + cells[:1])))
        self.assertEqual(b0, cells)


if __name__ == "__main__":
    unittest.main()

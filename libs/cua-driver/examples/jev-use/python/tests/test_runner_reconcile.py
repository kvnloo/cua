"""Runner hardening for a possibly landed completion (kvnloo/cua#105).

The Driver is an in-memory double, but every ``tools/call`` is first handed to
the runner's transport write stream, exactly where ``ClientSession`` writes it.
That stream is the simulated seam. The HTTP fixture is the independent target
oracle and counts every submission.

Rows mirror the TypeScript ``run_reconcile.test.ts`` scenarios:

* R0 an acknowledged completion that lands ends with a ``verified`` receipt;
* R1 acknowledgement lost after the effect: reconcile to ``verified``;
* R2 effect lands only after the first unchanged read: still ``verified``;
* R3 effect never lands in the window: ``unresolved_unknown``, no retry;
* R4 a read fails after an unverified completion: receipt, no crash;
* R5 the loop re-plans the completion while it is unresolved: no dispatch;
* R6 the request's own write raised: exactly one reconsideration;
* a raise after the write (the post-response ``list_tools`` refresh in
  mcp 1.30.0) is not pre-write proof.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import anyio
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCRequest

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))
sys.path.insert(0, str(BASE))

import run
import tasks
from verify_setup import fixture

TOKEN = "private-reconcile-canary-105"


class SeamDriver:
    """Driver double behind the runner's real write stream.

    ``click`` selects what the Submit click does:
    ``ok``, ``ack_lost`` (lands, then the acknowledgement is lost),
    ``ack_lost_late`` (lands after the first unchanged oracle read),
    ``ack_lost_never``, ``withheld`` (acknowledged, never lands during the run),
    ``pre_write`` / ``pre_write_twice`` (the request's own write raises), and
    ``post_write_raise`` (written, lands, then a closed-stream error).
    """

    def __init__(self, url: str, click: str, read_error_after_click: bool = False) -> None:
        self.url = url
        self.click = click
        self.read_error_after_click = read_error_after_click
        self.write = None
        self.value = ""
        self.request_id = 0
        self.prepares = 0
        self.observations = 0
        self.clicks_written = 0
        self.clicked = False
        self.late_pending = False

    def bind(self, _read, write):
        self.write = write
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def initialize(self):
        pass

    async def list_tools(self):
        return SimpleNamespace(tools=[])

    def submit(self) -> None:
        with urlopen(
            Request(self.url + "submit", data=urlencode({"value": self.value}).encode()),
            timeout=2,
        ):
            pass

    async def call_tool(self, name, args):
        if name == "browser_click" and (
            self.click == "pre_write_twice" or (self.click == "pre_write" and self.prepares == 1)
        ):
            # The transport closed between the snapshot and the Submit write.
            self.write.close()
        self.request_id += 1
        await self.write.send(
            SessionMessage(
                JSONRPCMessage(
                    JSONRPCRequest(
                        jsonrpc="2.0",
                        id=self.request_id,
                        method="tools/call",
                        params={"name": name},
                    )
                )
            )
        )
        if name == "browser_prepare":
            self.prepares += 1
            self.value = ""  # a fresh session launches a fresh browser
            data = {"prepared_pid": self.prepares}
        elif name == "list_windows":
            data = {
                "windows": [
                    {"window_id": 1, "is_on_screen": True, "bounds": {"width": 100, "height": 100}}
                ]
            }
        elif name == "get_browser_state":
            if args.get("snapshot_format") == "semantic_v2":
                self.observations += 1
                if self.clicked and self.read_error_after_click:
                    return SimpleNamespace(
                        isError=True,
                        structuredContent=None,
                        content=[{"type": "text", "text": "injected read failure"}],
                    )
            data = {
                "target_id": "target",
                "tabs": [{"tab_id": "tab", "active": True}],
                "tab_id": "tab",
                "refs": [
                    {
                        "role": "textbox",
                        "name": "verification value",
                        "ref": f"p{self.observations}:0",
                        "value": self.value,
                    },
                    {"role": "button", "name": "Submit", "ref": f"p{self.observations}:1"},
                ],
            }
        elif name == "browser_type":
            self.value = args["text"]
            data = {}
        elif name == "browser_click":
            self.clicks_written += 1
            self.clicked = True
            if self.click in {"ok", "ack_lost", "post_write_raise", "pre_write"}:
                self.submit()
            if self.click == "ack_lost_late":
                self.late_pending = True
            if self.click in {"ack_lost", "ack_lost_late", "ack_lost_never"}:
                raise RuntimeError("simulated acknowledgement loss")
            if self.click == "post_write_raise":
                # mcp 1.30.0 refreshes list_tools after the response; that write
                # can raise the same class after the effect landed.
                raise anyio.ClosedResourceError()
            data = {}
        else:
            assert name == "browser_navigate", name
            data = {}
        return SimpleNamespace(isError=False, structuredContent=data)


class RunnerReconcileTest(unittest.TestCase):
    def execute(self, click: str, *, read_error_after_click: bool = False):
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            driver = SeamDriver(url, click, read_error_after_click)
            oracle_reads = {"after_click": 0}
            original_state = tasks.fixture_state

            def oracle(fixture_url):
                state = original_state(fixture_url)
                if driver.clicked:
                    oracle_reads["after_click"] += 1
                if driver.late_pending and state["submitted"] is None:
                    # The first unchanged read has been served; now the effect lands.
                    driver.late_pending = False
                    driver.submit()
                return state

            @asynccontextmanager
            async def transport(_params):
                send, receive = anyio.create_memory_object_stream(math.inf)
                try:
                    yield receive, send
                finally:
                    send.close()
                    receive.close()

            args = argparse.Namespace(
                token=TOKEN,
                fixture_url=url,
                max_steps=4,
                log=str(Path(directory) / "run.jsonl"),
                provider="mock",
                guarded_completion=True,
                visual_observation="off",
                dry_run=False,
            )
            with (
                patch.object(run, "stdio_client", transport),
                patch.object(run, "ClientSession", side_effect=driver.bind),
                patch.object(tasks, "fixture_state", side_effect=oracle),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                outcome = asyncio.run(run.run(args))
            text = Path(args.log).read_text()
            self.assertNotIn(TOKEN, text)
            with urlopen(url + "state", timeout=2) as response:
                observed = json.load(response)
            events = [json.loads(line) for line in text.splitlines()]
            return outcome, events, driver, observed, oracle_reads["after_click"]

    def assert_receipt(self, event, *, resolution, **fields):
        receipt = event["mutation_outcome"]
        self.assertEqual(receipt["receiptKind"], "mutation-outcome/v0")
        self.assertEqual(receipt["mutationKey"], "2:submit-form")
        self.assertTrue(receipt["authorityScope"].startswith("jev-python-"))
        self.assertEqual(receipt["resolution"], resolution)
        for key, value in fields.items():
            self.assertEqual(receipt[key], value, key)

    def test_r0_acknowledged_completion_ends_with_verified_receipt(self):
        outcome, events, driver, observed, _ = self.execute("ok")
        self.assertEqual(outcome, "verified")
        self.assertEqual(observed, {"submitted": TOKEN})
        self.assertEqual(driver.clicks_written, 1)
        self.assertEqual(events[-1]["outcome"], "verified")
        self.assert_receipt(
            events[-1],
            resolution="verified",
            attempted=True,
            effect="applied",
            verification="verified",
            retryDisposition="none",
        )

    def test_r1_ack_lost_after_effect_reconciles_to_verified(self):
        outcome, events, driver, observed, reads = self.execute("ack_lost")
        self.assertEqual(outcome, "verified")
        self.assertEqual(observed, {"submitted": TOKEN})
        self.assertEqual(driver.clicks_written, 1)
        self.assertGreaterEqual(reads, 1)
        self.assertEqual(events[-1]["phase"], "action")
        self.assert_receipt(events[-1], resolution="verified", effect="applied")

    def test_r2_effect_after_first_unchanged_read_is_reconciled(self):
        outcome, events, driver, observed, reads = self.execute("ack_lost_late")
        self.assertEqual(outcome, "verified")
        self.assertEqual(observed, {"submitted": TOKEN})
        # The first negative read did not authorize a second dispatch.
        self.assertEqual(driver.clicks_written, 1)
        self.assertGreaterEqual(reads, 2)
        self.assert_receipt(events[-1], resolution="verified")

    def test_r3_effect_past_deadline_stays_unresolved_without_retry(self):
        outcome, events, driver, observed, reads = self.execute("ack_lost_never")
        self.assertEqual(outcome, "unknown")
        self.assertEqual(observed, {"submitted": None})
        self.assertEqual(driver.clicks_written, 1)
        self.assertEqual(driver.prepares, 1)
        self.assertGreater(reads, 2)
        self.assert_receipt(
            events[-1],
            resolution="unresolved_unknown",
            attempted=True,
            effect="unknown",
            verification="unverified",
            retryDisposition="observe",
        )

    def test_r4_read_failure_after_unverified_completion_emits_receipt(self):
        outcome, events, driver, _, _ = self.execute("withheld", read_error_after_click=True)
        self.assertEqual(outcome, "unknown")
        self.assertEqual(driver.clicks_written, 1)
        self.assertEqual(events[-1]["event"], "outcome")
        self.assertEqual(events[-1]["error"], "DriverToolError")
        self.assert_receipt(events[-1], resolution="unresolved_unknown", effect="unknown")

    def test_r5_replanned_completion_is_not_dispatched_while_unresolved(self):
        outcome, events, driver, _, _ = self.execute("withheld")
        self.assertEqual(outcome, "unknown")
        self.assertEqual(driver.clicks_written, 1)
        self.assertEqual(events[-1]["phase"], "completion_blocked")
        self.assert_receipt(events[-1], resolution="unresolved_unknown", retryDisposition="observe")

    def test_r6_own_write_raised_allows_exactly_one_reconsideration(self):
        outcome, events, driver, observed, _ = self.execute("pre_write")
        self.assertEqual(outcome, "verified")
        self.assertEqual(observed, {"submitted": TOKEN})
        self.assertEqual(driver.prepares, 2)
        self.assertEqual(driver.clicks_written, 1)
        reconsider = [event for event in events if event["event"] == "reconsider"]
        self.assertEqual(len(reconsider), 1)
        self.assert_receipt(
            reconsider[0],
            resolution="pre_write_failed",
            attempted=False,
            effect="none",
            retryDisposition="reconsider",
        )
        self.assertEqual(events[-1]["outcome"], "verified")

    def test_second_pre_write_failure_is_not_reconsidered_again(self):
        outcome, events, driver, observed, _ = self.execute("pre_write_twice")
        self.assertEqual(outcome, "unknown")
        self.assertEqual(observed, {"submitted": None})
        self.assertEqual(driver.prepares, 2)
        self.assertEqual(driver.clicks_written, 0)
        self.assertEqual(sum(event["event"] == "reconsider" for event in events), 1)
        self.assert_receipt(events[-1], resolution="pre_write_failed", retryDisposition="none")

    def test_closed_stream_after_the_write_is_not_pre_write_proof(self):
        outcome, events, driver, observed, _ = self.execute("post_write_raise")
        self.assertEqual(outcome, "verified")
        self.assertEqual(observed, {"submitted": TOKEN})
        self.assertEqual(driver.prepares, 1)
        self.assertEqual(driver.clicks_written, 1)
        self.assertFalse(any(event["event"] == "reconsider" for event in events))
        self.assert_receipt(events[-1], resolution="verified")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))
sys.path.insert(0, str(BASE))

import run
from verify_setup import fixture

STALE_TEXT = "refused (browser_ref_stale): the ref's node is no longer connected to the document"


def refused_result():
    """An action result as the Driver's MCP boundary emits it: not an MCP error."""
    return SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(type="text", text=STALE_TEXT)],
        structuredContent={"effect": "refused", "route": "dom"},
    )


class Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def initialize(self):
        pass

    async def list_tools(self):
        return SimpleNamespace(tools=[])


class OneResult(Session):
    def __init__(self, result):
        self.result = result

    async def call_tool(self, _name, _args):
        return self.result


class FixtureSession(Session):
    """In-memory Driver; the HTTP fixture is the outcome oracle."""

    def __init__(self, url, *, refuse_clicks=0, click_lands=True, type_kept=True):
        self.url = url
        self.value = ""
        self.refuse_clicks = refuse_clicks
        self.click_lands = click_lands
        self.type_kept = type_kept
        self.calls = []
        self.observations = 0

    async def call_tool(self, name, args):
        self.calls.append(name)
        if name == "browser_prepare":
            data = {"prepared_pid": 1}
        elif name == "list_windows":
            data = {
                "windows": [
                    {"window_id": 1, "is_on_screen": True, "bounds": {"width": 100, "height": 100}}
                ]
            }
        elif name == "get_browser_state":
            self.observations += 1
            n = self.observations
            data = {
                "target_id": "target",
                "tabs": [{"tab_id": "tab"}],
                "tab_id": "tab",
                "refs": [
                    {"role": "textbox", "name": "verification value", "ref": f"p{n}:0", "value": self.value},
                    {"role": "button", "name": "Submit", "ref": f"p{n}:1"},
                ],
            }
        elif name == "browser_type":
            if self.type_kept:
                self.value = args["text"]
            data = {"effect": "unverifiable", "route": "trusted_input"}
        elif name == "browser_click":
            if self.refuse_clicks > 0:
                self.refuse_clicks -= 1
                return refused_result()
            if self.click_lands:
                with urlopen(
                    Request(self.url + "submit", data=urlencode({"value": self.value}).encode()),
                    timeout=2,
                ):
                    pass
            data = {"effect": "unverifiable", "route": "dom"}
        else:
            assert name == "browser_navigate", name
            data = {}
        return SimpleNamespace(isError=False, content=[], structuredContent=data)

    def mutations(self):
        return [name for name in self.calls if name in {"browser_type", "browser_click"}]


async def no_wait(_seconds):
    return None


class DriverCallRefusalTest(unittest.TestCase):
    def call(self, result):
        driver = run.Driver(OneResult(result), "jev-python-test")
        return asyncio.run(driver.call("browser_click", {"ref": "p1:1"}))

    def test_effect_refused_without_is_error_is_a_refusal_not_success(self):
        with self.assertRaises(run.DriverToolError) as raised:
            self.call(refused_result())
        self.assertTrue(raised.exception.refused)
        self.assertEqual(raised.exception.code, "browser_ref_stale")

    def test_status_refused_envelope_keeps_its_structured_code(self):
        result = SimpleNamespace(
            isError=False,
            content=[],
            structuredContent={"status": "refused", "refusal": {"code": "browser_binding_stale"}},
        )
        with self.assertRaises(run.DriverToolError) as raised:
            self.call(result)
        self.assertTrue(raised.exception.refused)
        self.assertEqual(raised.exception.code, "browser_binding_stale")

    def test_accepted_unverifiable_result_is_returned(self):
        result = SimpleNamespace(
            isError=False, content=[], structuredContent={"effect": "unverifiable", "route": "dom"}
        )
        self.assertEqual(self.call(result)["effect"], "unverifiable")

    def test_mcp_error_is_not_marked_refused(self):
        result = SimpleNamespace(isError=True, content=[], structuredContent={"code": "x"})
        with self.assertRaises(run.DriverToolError) as raised:
            self.call(result)
        self.assertFalse(raised.exception.refused)


class RunnerRefusalTest(unittest.TestCase):
    def execute(self, expected, **session_options):
        token = "fix01-private-token"
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            session = FixtureSession(url, **session_options)
            args = argparse.Namespace(
                token=token,
                fixture_url=url,
                max_steps=4,
                log=str(Path(directory) / "run.jsonl"),
                provider="mock",
                guarded_completion=False,
                visual_observation="off",
                dry_run=False,
            )

            @asynccontextmanager
            async def transport(_params):
                yield None, None

            with (
                patch.object(run, "stdio_client", transport),
                patch.object(run, "ClientSession", return_value=session),
                patch.object(run.asyncio, "sleep", no_wait),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(asyncio.run(run.run(args)), expected)
            events = [json.loads(line) for line in Path(args.log).read_text().splitlines()]
            return events, session

    def test_one_refusal_gets_one_fresh_observation_and_one_fresh_dispatch(self):
        events, session = self.execute("verified", refuse_clicks=1)
        self.assertEqual(session.mutations(), ["browser_type", "browser_click", "browser_click"])
        refused = [event for event in events if event.get("action_refused")]
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0]["event"], "step")
        self.assertEqual(refused[0]["action_refused"], "browser_ref_stale")
        # The retry used a ref from an observation taken after the refusal.
        clicks = [i for i, name in enumerate(session.calls) if name == "browser_click"]
        self.assertIn("get_browser_state", session.calls[clicks[0] + 1 : clicks[1]])

    def test_second_refusal_stops_without_another_dispatch(self):
        events, session = self.execute("unknown", refuse_clicks=2)
        self.assertEqual(session.mutations(), ["browser_type", "browser_click", "browser_click"])
        self.assertEqual(events[-1]["phase"], "refused")
        self.assertEqual(events[-1]["action_refused"], "browser_ref_stale")

    def test_unconfirmed_accepted_click_is_never_dispatched_again(self):
        events, session = self.execute("unknown", click_lands=False)
        self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
        self.assertEqual(events[-1], {"event": "outcome", "outcome": "unknown", "step": 2, "phase": "reconcile"})

    def test_accepted_mutation_is_not_repeated_on_a_fresh_ref(self):
        events, session = self.execute("unknown", type_kept=False)
        self.assertEqual(session.mutations(), ["browser_type"])
        self.assertEqual(events[-1]["phase"], "redispatch_blocked")
        self.assertEqual(events[-1]["tool"], "browser_type")

    def test_ordinary_path_is_unchanged(self):
        events, session = self.execute("verified")
        self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
        self.assertFalse(any(event.get("action_refused") for event in events))


if __name__ == "__main__":
    unittest.main()

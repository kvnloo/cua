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
TRUST_UNKNOWN_TEXT = (
    "refused (browser_input_trust_unavailable): trusted click was acknowledged but CDP focus "
    "emulation could not be restored (x); delivery is unknown and must not be retried automatically"
)


POST_ASSIGNMENT_TEXT = (
    "refused (browser_ref_stale): the ref's node was not connected to the document after the "
    "file assignment; the files may have been assigned to the detached node, so delivery is "
    "unknown and must not be retried automatically"
)


def detail_refusal(detail, effect=None, text=POST_ASSIGNMENT_TEXT):
    """A status-refused browser envelope with a refusal detail (FIX-03 F5 / FIX-04 shapes)."""
    structured = {"status": "refused", "refusal": {"code": "browser_ref_stale", "detail": detail}}
    if effect:
        structured["effect"] = effect
    return SimpleNamespace(
        isError=False, content=[SimpleNamespace(type="text", text=text)], structuredContent=structured
    )


def refused_result(kind="stale"):
    """An action result as the Driver's MCP boundary emits it: not an MCP error."""
    if kind == "post_assignment":
        # F5's post-assignment refusal (the input may have landed).
        return detail_refusal({"delivery": "unknown", "retryable": False})
    if kind == "post_assignment_f6":
        # The same refusal with FIX-04's envelope effect.
        return detail_refusal({"delivery": "unknown", "retryable": False}, effect="unverifiable")
    if kind == "delivery_unknown_only":
        return detail_refusal({"delivery": "unknown"})
    if kind == "not_delivered":
        return detail_refusal({"delivery": "not_delivered"}, text=STALE_TEXT)
    if kind == "not_retryable":
        return SimpleNamespace(
            isError=False,
            content=[SimpleNamespace(type="text", text="refused (browser_reconnect_exhausted): x")],
            structuredContent={
                "status": "refused",
                "refusal": {"code": "browser_reconnect_exhausted", "detail": {"retryable": False}},
            },
        )
    text = STALE_TEXT if kind == "stale" else TRUST_UNKNOWN_TEXT
    return SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(type="text", text=text)],
        structuredContent={"effect": "refused", "route": "dom" if kind == "stale" else "trusted_input"},
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

    def __init__(
        self, url, *, refuse_clicks=0, click_lands=True, type_kept=True, refusal="stale", refused_lands=False
    ):
        self.url = url
        self.value = ""
        self.refuse_clicks = refuse_clicks
        self.refusal = refusal
        # The refused click's effect lands anyway (Chromium assigned the files / the trusted
        # click was delivered before the refusal): the fixture records the submit.
        self.refused_lands = refused_lands
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
                if self.refused_lands:
                    self.submit()
                return refused_result(self.refusal)
            if self.click_lands:
                self.submit()
            data = {"effect": "unverifiable", "route": "dom"}
        else:
            assert name == "browser_navigate", name
            data = {}
        return SimpleNamespace(isError=False, content=[], structuredContent=data)

    def submit(self):
        with urlopen(
            Request(self.url + "submit", data=urlencode({"value": self.value}).encode()),
            timeout=2,
        ):
            pass

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

    def test_retryable_is_read_from_the_refusal_detail(self):
        with self.assertRaises(run.DriverToolError) as raised:
            self.call(refused_result("not_retryable"))
        self.assertTrue(raised.exception.refused)
        self.assertEqual(raised.exception.code, "browser_reconnect_exhausted")
        self.assertIs(raised.exception.retryable, False)

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

    def test_refusal_with_unknown_delivery_ends_unknown_without_redispatch(self):
        events, session = self.execute("unknown", refuse_clicks=1, refusal="trust_unknown")
        self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
        self.assertEqual(events[-1]["outcome"], "unknown")
        self.assertEqual(events[-1]["action_refused"], "browser_input_trust_unavailable")

    def test_refusal_marked_not_retryable_ends_unknown_without_redispatch(self):
        events, session = self.execute("unknown", refuse_clicks=1, refusal="not_retryable")
        self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
        self.assertEqual(events[-1]["outcome"], "unknown")
        self.assertEqual(events[-1]["action_refused"], "browser_reconnect_exhausted")

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

    # FIX-04 Part B (kvnloo/cua#105): a post-assignment refusal may have landed.
    def test_post_assignment_refusal_is_reconciled_from_state_not_redispatched(self):
        for kind in ("post_assignment", "post_assignment_f6"):
            with self.subTest(kind=kind):
                events, session = self.execute(
                    "verified", refuse_clicks=1, refusal=kind, refused_lands=True
                )
                self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
                self.assertEqual(events[-1]["outcome"], "verified")
                self.assertEqual(events[-1]["phase"], "reconcile")
                self.assertEqual(events[-1]["action_refused"], "browser_ref_stale")

    def test_post_assignment_refusal_that_did_not_land_ends_unknown_after_reconcile(self):
        events, session = self.execute("unknown", refuse_clicks=1, refusal="post_assignment")
        self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
        self.assertEqual(events[-1]["outcome"], "unknown")
        self.assertEqual(events[-1]["phase"], "reconcile")

    def test_declared_unknown_delivery_without_retryable_is_never_redispatched(self):
        events, session = self.execute("unknown", refuse_clicks=1, refusal="delivery_unknown_only")
        self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
        self.assertEqual(events[-1]["outcome"], "unknown")

    def test_pre_dispatch_refusal_declared_not_delivered_may_be_rebound_once(self):
        events, session = self.execute("verified", refuse_clicks=1, refusal="not_delivered")
        self.assertEqual(session.mutations(), ["browser_type", "browser_click", "browser_click"])
        refused = [event for event in events if event.get("action_refused")]
        self.assertEqual([event["event"] for event in refused], ["step"])

    def test_ordinary_path_is_unchanged(self):
        events, session = self.execute("verified")
        self.assertEqual(session.mutations(), ["browser_type", "browser_click"])
        self.assertFalse(any(event.get("action_refused") for event in events))


if __name__ == "__main__":
    unittest.main()

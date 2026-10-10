"""Native geometry is finite before it can supply an executable candidate.

MCP result parsing and the real runner are exercised with a mock transport;
these tests do not start a native Driver or deliver host input.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp.types import CallToolResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from native import NativeObservation
from native_tasks import native_task
from run_native import run_task
from sources import NativeAccessibilitySource

ROOT = Path(__file__).resolve().parents[2]
MARKER = "__geometry_number__"
INVALID_JSON_NUMBERS = ("1e309", "-1e309", "1" + "0" * 400)
INVALID_JSON_TYPES = ("null", "true", "false", '"20"')


def result_from_wire(payload: dict, value_json: str) -> CallToolResult:
    wire = json.dumps({"isError": False, "structuredContent": payload, "content": []})
    return CallToolResult.model_validate_json(wire.replace(json.dumps(MARKER), value_json))


def window_state() -> dict:
    return {
        "pid": 7,
        "window_id": 9,
        "snapshot_id": "s1",
        "capture_id": "cap-1",
        "elements_complete": True,
        "window_bounds": {"x": 0, "y": 0, "width": 100, "height": 100},
        "elements": [
            {
                "element_index": 0,
                "role": "button",
                "label": "Increment",
                "enabled": True,
                "element_token": "s1:0",
                "frame": {"x": 0, "y": 0, "w": 20, "h": 20},
            }
        ],
    }


def source_from_wire(payload: dict, value_json: str, platform: str) -> NativeAccessibilitySource:
    data = result_from_wire(payload, value_json).structuredContent
    observation = NativeObservation.from_window_state(data, expected_pid=7, expected_window_id=9)
    return NativeAccessibilitySource.from_observation(observation, platform)


class NativeGeometryTest(unittest.TestCase):
    def assert_geometry_excluded(self, value_json: str) -> None:
        for platform in ("macos", "windows", "linux"):
            for owner, fields in (
                ("frame", ("x", "y", "w", "h")),
                ("window_bounds", ("x", "y", "width", "height")),
            ):
                for field in fields:
                    with self.subTest(
                        value=value_json[:24], platform=platform, owner=owner, field=field
                    ):
                        payload = window_state()
                        rect = (
                            payload["elements"][0]["frame"] if owner == "frame" else payload[owner]
                        )
                        rect[field] = MARKER
                        source = source_from_wire(payload, value_json, platform)
                        self.assertIsNone(source.find("button", "Increment"))
                        self.assertEqual(source.native.excluded, {"off_screen": 1})

    def test_invalid_json_numbers_and_types_cannot_supply_candidates(self) -> None:
        for value_json in (*INVALID_JSON_NUMBERS, *INVALID_JSON_TYPES):
            self.assert_geometry_excluded(value_json)

    def test_python_mcp_nonstandard_numbers_cannot_supply_candidates(self) -> None:
        # Pydantic's MCP decoder accepts these extensions; JavaScript rejects
        # them at JSON.parse, before the TypeScript observation boundary.
        for value_json in ("NaN", "Infinity", "-Infinity"):
            self.assert_geometry_excluded(value_json)

    def test_finite_frames_keep_existing_geometry_rules(self) -> None:
        cases = (
            ({"x": 0, "y": 0, "w": 20, "h": 20}, True),
            ({"x": -5, "y": -5, "w": 20, "h": 20}, True),
            ({"x": 0, "y": 0, "w": 1.7976931348623157e308, "h": 20}, True),
            ({"x": 0, "y": 0, "w": 5e-324, "h": 5e-324}, True),
            ({"x": 0, "y": 0, "w": 0, "h": 20}, False),
            ({"x": 0, "y": 0, "w": 20, "h": -1}, False),
            ({"x": 101, "y": 0, "w": 20, "h": 20}, False),
        )
        for platform in ("macos", "windows", "linux"):
            for frame, expected in cases:
                with self.subTest(platform=platform, frame=frame):
                    payload = window_state()
                    payload["elements"][0]["frame"] = frame
                    source = source_from_wire(payload, "0", platform)
                    control = source.find("button", "Increment")
                    self.assertEqual(control is not None, expected)
                    if control is not None:
                        candidate = source.click(
                            control, candidate_id="increment", description="Increment"
                        )
                        self.assertEqual(
                            dict(candidate.arguments),
                            {
                                "pid": 7,
                                "window_id": 9,
                                "element_token": "s1:0",
                                "delivery_mode": "background",
                            },
                        )


class NativeGeometryRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_geometry_never_dispatches_and_finite_control_does(self) -> None:
        for value_json in (*INVALID_JSON_NUMBERS, "20"):
            with self.subTest(value=value_json[:24]), tempfile.TemporaryDirectory() as directory:
                payload = json.loads(
                    (ROOT / "fixtures/native/gtk3-window-state-initial-v1.json").read_text()
                )
                increment = next(
                    item for item in payload["elements"] if item.get("label") == "Increment"
                )
                increment["frame"]["w"] = MARKER
                state_path = Path(directory) / "state.json"
                log_path = Path(directory) / "run.jsonl"
                task = native_task("gtk3-counter", state_path, pid=payload["pid"])
                state = {"schema": task.oracle.schema, "pid": payload["pid"], "counter": 0}
                state_path.write_text(json.dumps(state))
                actions: list[dict] = []
                reads: list[dict] = []

                class Session:
                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        return False

                    async def initialize(self):
                        return None

                    async def list_tools(self):
                        return SimpleNamespace(tools=[])

                    async def call_tool(self, name, arguments):
                        if name == "list_windows":
                            data = {
                                "windows": [
                                    {
                                        "window_id": payload["window_id"],
                                        "title": task.scope.window_title,
                                    }
                                ]
                            }
                        elif name == "get_window_state":
                            reads.append(dict(arguments))
                            return result_from_wire(copy.deepcopy(payload), value_json)
                        elif name == "click":
                            actions.append(dict(arguments))
                            state["counter"] = 3
                            state_path.write_text(json.dumps(state))
                            data = {"effect": "confirmed"}
                        else:
                            raise AssertionError(f"unexpected tool {name}")
                        return result_from_wire(data, "0")

                @asynccontextmanager
                async def transport(_):
                    yield None, None

                args = argparse.Namespace(
                    platform="linux", pid=payload["pid"], provider="mock", log=str(log_path)
                )
                with (
                    patch("run_native.stdio_client", transport),
                    patch("run_native.ClientSession", return_value=Session()),
                    redirect_stdout(io.StringIO()),
                ):
                    outcome = await run_task(args, task)
                finite = value_json == "20"
                self.assertEqual(outcome, "verified" if finite else "budget_exhausted")
                self.assertEqual(len(actions), 1 if finite else 0)
                self.assertEqual(len(reads), 1 if finite else task.max_steps)
                self.assertEqual(json.loads(state_path.read_text())["counter"], 3 if finite else 0)
                events = [json.loads(line) for line in log_path.read_text().splitlines()]
                steps = [event for event in events if event["event"] == "step"]
                self.assertEqual(
                    [event["candidate"] for event in steps],
                    ["ax:button:increment"] if finite else ["reobserve"] * task.max_steps,
                )
                if not finite:
                    self.assertTrue(all(event["expected_offered"] is False for event in steps))


if __name__ == "__main__":
    unittest.main()

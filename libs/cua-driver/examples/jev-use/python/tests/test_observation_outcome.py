from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_guarded_runner import FixtureSession, fixture, run, transport


class ObservationOutcomeTest(unittest.TestCase):
    def exercise_failure(self, *, programmer_fault: bool) -> None:
        canary = "synthetic-observation-private-value"
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            class ObservationSession(FixtureSession):
                failed_reads = 0

                async def call_tool(self, name, args):
                    if (
                        name == "get_browser_state"
                        and args.get("snapshot_format") == "semantic_v2"
                        and self.mutations
                    ):
                        self.failed_reads += 1
                        if programmer_fault:
                            raise TypeError(canary)
                        return SimpleNamespace(
                            isError=True,
                            structuredContent={"code": "browser_route_unavailable"},
                            content=[SimpleNamespace(type="text", text=canary)],
                        )
                    return await super().call_tool(name, args)

            session = ObservationSession(url, "xy")
            args = argparse.Namespace(
                token="xy", fixture_url=url, max_steps=4,
                log=str(Path(directory) / "events.jsonl"), provider="mock",
                guarded_completion=True, visual_observation="off", dry_run=False,
            )
            with (
                patch.object(run, "stdio_client", transport),
                patch.object(run, "ClientSession", return_value=session),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                if programmer_fault:
                    with self.assertRaisesRegex(TypeError, canary):
                        asyncio.run(run.run(args))
                else:
                    self.assertEqual(asyncio.run(run.run(args)), "unknown")
            text = Path(args.log).read_text()
            events = [json.loads(line) for line in text.splitlines()]
            outcomes = [event for event in events if event["event"] == "outcome"]
            self.assertEqual(session.mutations, ["browser_type"])
            self.assertEqual(session.failed_reads, 1)
            self.assertIsNone(run.fixture_state(url)["submitted"])
            self.assertNotIn(canary, text)
            self.assertTrue(all("guarded_completion" not in event for event in events))
            self.assertEqual(outcomes, [] if programmer_fault else [{
                "event": "outcome", "outcome": "unknown", "step": 2,
                "phase": "observation", "error": "DriverToolError",
            }])

    def test_observation_refusal_is_redacted_unknown_without_replay(self):
        self.exercise_failure(programmer_fault=False)

    def test_programmer_error_is_not_reclassified_as_observation_refusal(self):
        self.exercise_failure(programmer_fault=True)

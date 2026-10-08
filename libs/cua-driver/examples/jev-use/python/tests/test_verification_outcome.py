"""An unavailable post-completion oracle is unknown, never proof of success."""
from __future__ import annotations
import argparse
import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from test_guarded_runner import FixtureSession, transport, fixture, run


class VerificationOutcomeTest(unittest.TestCase):
    def execute(self, *, guarded=True, programmer_fault=False, early=False):
        token = "verification-error-canary"
        with tempfile.TemporaryDirectory() as directory, fixture() as url:
            session = FixtureSession(url, token)
            args = argparse.Namespace(token=token, fixture_url=url, max_steps=4,
                log=str(Path(directory) / "events.jsonl"), provider="mock",
                guarded_completion=guarded, visual_observation="off", dry_run=False)
            original_read = run.FixtureFormTask.read_oracle
            error = TypeError(token) if programmer_fault else HTTPError(url + "state", 503, token, None, None)
            def read(task):
                if early or "browser_click" in session.mutations:
                    raise error
                return original_read(task)
            with patch.object(run, "stdio_client", transport), \
                 patch.object(run, "ClientSession", return_value=session), \
                 patch.object(run.FixtureFormTask, "read_oracle", read), \
                 contextlib.redirect_stdout(io.StringIO()):
                if programmer_fault or early:
                    with self.assertRaises(type(error)):
                        asyncio.run(run.run(args))
                else:
                    self.assertEqual(asyncio.run(run.run(args)), "unknown")
            events = [json.loads(line) for line in Path(args.log).read_text().splitlines()]
            self.assertNotIn(token, Path(args.log).read_text())
            self.assertEqual(session.mutations, [] if early else ["browser_type", "browser_click"])
            self.assertEqual(run.fixture_state(url)["submitted"], None if early else token)
            return events

    def test_accepted_completion_preserves_unknown_and_proof(self):
        event = self.execute()[-1]
        self.assertEqual(event["event"], "outcome")
        self.assertEqual(event["outcome"], "unknown")
        self.assertEqual(event["phase"], "verification")
        self.assertEqual(event["error"], "HTTPError")
        self.assertEqual(event["step"], 2)
        self.assertEqual(event["decision_route"], "guarded-completion")
        self.assertEqual(event["guarded_completion"]["status"], "accepted")

    def test_default_off_does_not_invent_guard_proof(self):
        event = self.execute(guarded=False)[-1]
        self.assertEqual(event["outcome"], "unknown")
        self.assertEqual(event["phase"], "verification")
        self.assertEqual(event["decision_route"], "provider")
        self.assertNotIn("guarded_completion", event)

    def test_verification_programmer_fault_is_not_operational_unknown(self):
        events = self.execute(programmer_fault=True)
        self.assertFalse(any(e["event"] == "outcome" for e in events))

    def test_precompletion_oracle_failure_is_outside_handler(self):
        self.assertEqual(self.execute(early=True), [])

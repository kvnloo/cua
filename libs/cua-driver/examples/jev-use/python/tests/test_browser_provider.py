from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from browser_provider import backend_name, browser_decision_request, choose_browser_provider
from tasks import FixtureFormTask, fixture_sources


class BrowserProviderTest(unittest.TestCase):
    def sources(self, token: str):
        snapshot = {
            "target_id": "target",
            "tab_id": "tab",
            "capture_id": "browser-capture-1",
            "refs": [
                {
                    "role": "textbox",
                    "name": "verification value",
                    "ref": "p1:0",
                    "value": "",
                },
                {"role": "button", "name": "Submit", "ref": "p1:1"},
            ],
        }
        return fixture_sources(snapshot)

    def test_browser_request_is_bounded_and_contains_no_action_arguments_or_secret(self):
        token = "secret-proof-token"
        task = FixtureFormTask(token)
        sources = self.sources(token)
        candidates = task.candidates(sources)
        request = browser_decision_request(task, sources, candidates, [])
        self.assertEqual(request["schema"], "cua.jev_choice_request_v1")
        self.assertEqual(request["capture_id"], "browser-capture-1")
        self.assertEqual(
            [item["id"] for item in request["candidates"]],
            ["type-verification-value", "reobserve", "abstain"],
        )
        wire = json.dumps(request)
        self.assertNotIn(token, wire)
        self.assertNotIn("arguments", wire)
        self.assertNotIn("browser_type", wire)

    def test_mock_uses_existing_task_policy_and_reports_actual_backend(self):
        token = "proof-token"
        task = FixtureFormTask(token)
        sources = self.sources(token)
        candidates = task.candidates(sources)
        choice, confidence, probabilities, backend = choose_browser_provider(
            "mock", task, sources, candidates, []
        )
        self.assertEqual(choice, "type-verification-value")
        self.assertEqual(confidence, 1.0)
        self.assertEqual(backend, "mock")
        self.assertEqual(probabilities[choice], 1.0)
        self.assertEqual(backend_name("live"), "typesafe")
        self.assertEqual(backend_name("typesafe"), "typesafe")
        self.assertEqual(backend_name("openjev"), "openjev")
        self.assertEqual(backend_name("s1"), "s1")


if __name__ == "__main__":
    unittest.main()
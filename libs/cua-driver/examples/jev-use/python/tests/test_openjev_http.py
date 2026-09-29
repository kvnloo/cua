"""Real loopback HTTP tests for the OpenJev DecisionModel adapter."""

from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from choose_action import REQUEST_SCHEMA_V2, validate_request
from decision_models import DecisionRequest
from openjev_model import (
    MAX_RESPONSE_BYTES,
    OpenJevConfig,
    OpenJevDecisionModel,
    OpenJevError,
)


def request() -> DecisionRequest:
    return DecisionRequest.from_validated(
        validate_request(
            {
                "schema": REQUEST_SCHEMA_V2,
                "goal": "Submit.",
                "capture_id": "cap-1",
                "snapshot_id": "snap-1",
                "regions": [],
                "elements": [],
                "progress": [],
                "history": [],
                "candidates": [
                    {"id": "submit", "description": "Submit.", "source": "page"},
                    {"id": "reobserve", "description": "Observe again."},
                    {"id": "abstain", "description": "Stop."},
                ],
            }
        )
    )


def decision() -> dict[str, Any]:
    return {
        "model": "loopback-openjev",
        "answers": {
            "candidate": {
                "type": "choice",
                "choice": "submit",
                "confidence": 0.9,
                "probabilities": {
                    "submit": 0.9,
                    "reobserve": 0.05,
                    "abstain": 0.05,
                },
            }
        },
    }


@contextmanager
def fixture(mode: str):
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            received.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "payload": json.loads(body),
                }
            )
            if mode == "stall":
                time.sleep(0.35)
                return
            if mode == "redirect":
                self.send_response(307)
                self.send_header("Location", "/other")
                self.end_headers()
                return
            if mode == "503":
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if mode == "malformed":
                self.wfile.write(b"not-json")
            elif mode == "oversized":
                self.wfile.write(b"{" + b" " * (MAX_RESPONSE_BYTES + 1) + b"}")
            else:
                self.wfile.write(json.dumps(decision()).encode())

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class OpenJevHttpTest(unittest.TestCase):
    def model(self, url: str, timeout_ms: int = 1000) -> OpenJevDecisionModel:
        return OpenJevDecisionModel(
            OpenJevConfig(url, "", "fixture-model", timeout_ms)
        )

    def test_success_posts_current_cua_request_without_credentials(self) -> None:
        with fixture("ok") as (url, received):
            scores = self.model(url).score(request())
        self.assertEqual(scores.selected_id, "submit")
        self.assertEqual(scores.model, "loopback-openjev")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["path"], "/v1/systemone")
        self.assertNotIn("Authorization", received[0]["headers"])
        sent = received[0]["payload"]["state"]["request"]
        self.assertEqual(sent["schema"], REQUEST_SCHEMA_V2)
        self.assertEqual(
            [item["id"] for item in sent["candidates"]],
            ["submit", "reobserve", "abstain"],
        )

    def test_redirect_is_refused_without_repost(self) -> None:
        with fixture("redirect") as (url, received):
            with self.assertRaises(OpenJevError) as caught:
                self.model(url).score(request())
        self.assertEqual(caught.exception.code, "redirect_refused")
        self.assertEqual(len(received), 1)

    def test_http_error_is_bounded_and_not_retried(self) -> None:
        with fixture("503") as (url, received):
            with self.assertRaises(OpenJevError) as caught:
                self.model(url).score(request())
        self.assertEqual(caught.exception.code, "http_error")
        self.assertEqual(len(received), 1)

    def test_malformed_and_oversized_responses_fail_closed(self) -> None:
        for mode, expected in [
            ("malformed", "invalid_response"),
            ("oversized", "response_too_large"),
        ]:
            with self.subTest(mode=mode):
                with fixture(mode) as (url, _received):
                    with self.assertRaises(OpenJevError) as caught:
                        self.model(url).score(request())
                self.assertEqual(caught.exception.code, expected)

    def test_timeout_is_bounded_and_not_retried(self) -> None:
        with fixture("stall") as (url, received):
            with self.assertRaises(OpenJevError) as caught:
                self.model(url, 100).score(request())
        self.assertEqual(caught.exception.code, "timeout")
        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main()

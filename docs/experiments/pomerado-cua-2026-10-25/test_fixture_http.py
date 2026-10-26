"""Live HTTP contract tests against the unmodified repository-owned CUA fixture.

Evidence is REAL_FIXTURE_HTTP_ONLY: no CUA Driver, Pomerado, browser
automation, cloud provider or user account is exercised here.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "libs/cua-driver/examples/jev-use/fixture_server.py"


def make_server(*, visual=False):
    spec = importlib.util.spec_from_file_location("cua_jev_fixture_http", FIXTURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = module.FixtureServer(("127.0.0.1", 0), visual=visual)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def get(base: str, suffix: str):
    with urlopen(base + suffix, timeout=3) as response:
        return response.status, response.read().decode()


def post(base: str, suffix: str, payload: dict | None = None):
    data = urlencode(payload).encode() if payload is not None else b""
    req = Request(base + suffix, data=data, method="POST")
    with urlopen(req, timeout=3) as response:
        return response.status, response.read().decode()


class OriginalFixtureHttpTests(unittest.TestCase):
    def setUp(self):
        self.server, self.worker, self.base = make_server()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)

    def state(self):
        status, body = get(self.base, "/state")
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_initial_state_is_empty_and_read_is_not_a_write(self):
        self.assertEqual(self.state(), {"submitted": None})
        status, body = get(self.base, "/")
        self.assertEqual(status, 200)
        self.assertIn('aria-label="verification value"', body)
        self.assertIn('<button type="submit">Submit</button>', body)
        self.assertEqual(self.state(), {"submitted": None})

    def test_happy_submission_is_proven_by_external_state(self):
        status, response = post(self.base, "/submit", {"value": "synthetic_001"})
        self.assertEqual(status, 200)
        self.assertIn("status=submitted:synthetic_001", response)
        self.assertEqual(self.state(), {"submitted": "synthetic_001"})

    def test_reset_changes_external_state_and_is_idempotent(self):
        post(self.base, "/submit", {"value": "test_value"})
        for _ in range(2):
            status, _ = post(self.base, "/reset")
            self.assertEqual(status, 204)
            self.assertEqual(self.state(), {"submitted": None})

    def test_empty_submission_fails_without_effect(self):
        with self.assertRaises(HTTPError) as captured:
            post(self.base, "/submit", {})
        self.assertEqual(captured.exception.code, 400)
        self.assertEqual(self.state(), {"submitted": None})

    def test_unknown_get_and_post_paths_refuse(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                with self.assertRaises(HTTPError) as captured:
                    if method == "GET":
                        get(self.base, "/nonexistent")
                    else:
                        post(self.base, "/nonexistent", {})
                self.assertEqual(captured.exception.code, 404)
        self.assertEqual(self.state(), {"submitted": None})

    def test_submitted_html_is_escaped_in_page(self):
        attack = "<script>alert(1)</script>"
        _, page = post(self.base, "/submit", {"value": attack})
        self.assertNotIn(attack, page)
        self.assertIn("&lt;script&gt;", page)
        self.assertEqual(self.state(), {"submitted": attack})

    def test_visual_fixture_has_no_semantic_submit_button(self):
        other, thread, url = make_server(visual=True)
        try:
            status, page = get(url, "/")
            self.assertEqual(status, 200)
            self.assertIn('role="presentation"', page)
            self.assertNotIn('<button type="submit">Submit</button>', page)
            self.assertEqual(json.loads(get(url, "/state")[1]), {"submitted": None})
        finally:
            other.shutdown()
            other.server_close()
            thread.join(timeout=5)

    def test_read_oracle_concurrently_without_cross_thread_errors(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            responses = list(pool.map(lambda _: self.state(), range(50)))
        self.assertEqual(responses, [{"submitted": None}] * 50)

    def test_duplicate_write_cannot_be_detected_by_existing_oracle(self):
        # Explicit limitation, not a passing idempotency proof:
        # /state remembers only the final value, not submission count.
        post(self.base, "/submit", {"value": "repeat"})
        post(self.base, "/submit", {"value": "repeat"})
        self.assertEqual(self.state(), {"submitted": "repeat"})
        self.assertFalse(hasattr(self.server.state, "submission_count"))


if __name__ == "__main__":
    unittest.main()

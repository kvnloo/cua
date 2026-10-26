"""True HTTP mutation accounting, independent of the calling executor.

These are REAL_FIXTURE_HTTP_ONLY tests, not Pomerado or CUA Driver E2E.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_fixture import AuditedFixtureServer  # noqa: E402


class MutationAuditTests(unittest.TestCase):
    def setUp(self):
        self.server = AuditedFixtureServer(("127.0.0.1", 0))
        self.worker = Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)

    def read(self, suffix: str):
        with urlopen(self.base + suffix, timeout=3) as response:
            return json.loads(response.read())

    def submit(self, value: str):
        payload = urlencode({"value": value}).encode()
        req = Request(self.base + "/submit", data=payload, method="POST")
        with urlopen(req, timeout=3) as response:
            self.assertEqual(response.status, 200)

    def reset(self):
        req = Request(self.base + "/reset", data=b"", method="POST")
        with urlopen(req, timeout=3) as response:
            self.assertEqual(response.status, 204)

    def test_empty_audit(self):
        self.assertEqual(self.read("/audit"), {"commit_count": 0, "commits": []})
        self.assertEqual(self.read("/state"), {"submitted": None})

    def test_one_submission_has_one_independent_commit(self):
        self.submit("synthetic")
        oracle = self.read("/audit")
        self.assertEqual(oracle["commit_count"], 1)
        self.assertEqual(oracle["commits"][0]["sequence"], 1)
        self.assertEqual(oracle["commits"][0]["value_sha256"],
                         hashlib.sha256(b"synthetic").hexdigest())

    def test_same_value_twice_is_detected_as_two_effects(self):
        self.submit("synthetic")
        self.submit("synthetic")
        self.assertEqual(self.read("/state"), {"submitted": "synthetic"})
        self.assertEqual(self.read("/audit")["commit_count"], 2)

    def test_reset_clears_commits_and_previous_value(self):
        self.submit("old")
        self.reset()
        self.assertEqual(self.read("/audit")["commit_count"], 0)
        self.assertEqual(self.read("/state"), {"submitted": None})
        self.submit("new")
        self.assertEqual(self.read("/audit")["commit_count"], 1)

    def test_refused_empty_write_does_not_increment(self):
        req = Request(self.base + "/submit", data=b"", method="POST")
        with self.assertRaises(HTTPError) as error:
            urlopen(req, timeout=3)
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.read("/audit")["commit_count"], 0)

    def test_receipt_contains_only_digest_not_sensitive_value(self):
        self.submit("synthetic-private-value")
        receipt = json.dumps(self.read("/audit"))
        self.assertNotIn("synthetic-private-value", receipt)
        self.assertIn("value_sha256", receipt)

    def _delayed_server(self, *, ack_delay_s=0.0, dispatch_delay_s=0.0):
        server = AuditedFixtureServer(("127.0.0.1", 0),
                                      ack_delay_s=ack_delay_s,
                                      dispatch_delay_s=dispatch_delay_s)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def test_commit_then_lost_ack_is_reconciled_without_retry(self):
        base = self._delayed_server(ack_delay_s=0.2)
        request = Request(base + "/submit", data=b"value=synthetic", method="POST")
        with self.assertRaises(TimeoutError):
            urlopen(request, timeout=0.025)
        with urlopen(base + "/audit", timeout=3) as response:
            self.assertEqual(json.load(response)["commit_count"], 1)
        time.sleep(0.25)
        with urlopen(base + "/audit", timeout=3) as response:
            self.assertEqual(json.load(response)["commit_count"], 1)

    def test_dispatch_timeout_may_commit_later(self):
        base = self._delayed_server(dispatch_delay_s=0.2)
        request = Request(base + "/submit", data=b"value=synthetic", method="POST")
        with self.assertRaises(TimeoutError):
            urlopen(request, timeout=0.025)
        with urlopen(base + "/audit", timeout=3) as response:
            self.assertEqual(json.load(response)["commit_count"], 0)
        # Absence at the timeout is NOT proof that a delayed write cannot land.
        time.sleep(0.25)
        with urlopen(base + "/audit", timeout=3) as response:
            self.assertEqual(json.load(response)["commit_count"], 1)

    def test_parallel_commits_get_unique_total_order(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(self.submit, [f"synthetic-{i}" for i in range(20)]))
        oracle = self.read("/audit")
        self.assertEqual(oracle["commit_count"], 20)
        self.assertEqual([r["sequence"] for r in oracle["commits"]], list(range(1, 21)))


if __name__ == "__main__":
    unittest.main()

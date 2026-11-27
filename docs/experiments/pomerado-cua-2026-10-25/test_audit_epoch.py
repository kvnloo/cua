"""REAL_FIXTURE_HTTP_ONLY epoch/lifetime audit controls, never a CUA/Pomerado A/B."""
from __future__ import annotations

import json
from threading import Thread
import unittest
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from audit_fixture import AuditedFixtureServer


class PersistentAuditControls(unittest.TestCase):
    def setUp(self):
        self.server = AuditedFixtureServer(("127.0.0.1", 0))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post(self, path, body=b""):
        with urlopen(Request(self.base + path, method="POST", data=body), timeout=3) as response:
            return response.status

    def audit(self):
        with urlopen(self.base + "/audit", timeout=3) as response:
            return json.load(response)

    def submit(self):
        return self.post("/submit", urlencode({"value": "synthetic"}).encode())

    def test_same_reset_epoch_and_lifetime_count_for_single_write(self):
        self.assertEqual(self.post("/reset"), 204)
        before = self.audit()
        self.assertEqual(self.submit(), 200)
        after = self.audit()
        self.assertEqual(before["reset_epoch"], after["reset_epoch"])
        self.assertEqual(after["total_commit_count"] - before["total_commit_count"], 1)
        self.assertEqual(after["commit_count"], 1)

    def test_midtrial_reset_cannot_hide_second_effect_in_lifetime_audit(self):
        self.assertEqual(self.post("/reset"), 204)
        before = self.audit()
        self.assertEqual(self.submit(), 200)
        self.assertEqual(self.post("/reset"), 204)
        self.assertEqual(self.submit(), 200)
        after = self.audit()
        self.assertEqual(after["commit_count"], 1)  # old per-reset counter masks first write
        self.assertEqual(after["total_commit_count"] - before["total_commit_count"], 2)
        self.assertNotEqual(before["reset_epoch"], after["reset_epoch"])

    def test_clean_resets_increment_epoch_without_decreasing_lifetime(self):
        original = self.audit()
        self.assertEqual(self.submit(), 200)
        self.assertEqual(self.post("/reset"), 204)
        one = self.audit()
        self.assertEqual(self.post("/reset"), 204)
        two = self.audit()
        self.assertEqual(one["commit_count"], 0)
        self.assertEqual(two["commit_count"], 0)
        self.assertEqual(two["reset_epoch"] - original["reset_epoch"], 2)
        self.assertEqual(one["total_commit_count"], 1)
        self.assertEqual(two["total_commit_count"], 1)


if __name__ == "__main__":
    unittest.main()

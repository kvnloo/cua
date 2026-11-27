"""FIXTURE_HTTP_ONLY server-incarnation controls; never a CUA/Pomerado A/B."""
from __future__ import annotations

import json
from threading import Thread
import unittest
from urllib.request import Request, urlopen

from audit_fixture import AuditedFixtureServer


class FixtureIncarnationHTTPTests(unittest.TestCase):
    @staticmethod
    def start(port=0):
        server = AuditedFixtureServer(("127.0.0.1", port))
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        return server, worker, f"http://127.0.0.1:{server.server_port}"

    @staticmethod
    def stop(server, worker):
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        if worker.is_alive():
            raise AssertionError("fixture server failed to terminate")

    @staticmethod
    def audit(base):
        with urlopen(base + "/audit", timeout=3) as result:
            return json.load(result)

    @staticmethod
    def post(base, path, body=b""):
        with urlopen(Request(base + path, data=body, method="POST"), timeout=3) as result:
            return result.status

    def test_incarnation_stable_across_clean_reset(self):
        server, worker, base = self.start()
        try:
            first = self.audit(base)
            self.assertEqual(self.post(base, "/reset"), 204)
            self.assertEqual(self.post(base, "/submit", b"value=synthetic"), 200)
            self.assertEqual(self.post(base, "/reset"), 204)
            second = self.audit(base)
            self.assertRegex(first["instance_id"], r"\A[0-9a-f]{32}\Z")
            self.assertEqual(first["instance_id"], second["instance_id"])
            self.assertEqual(second["reset_epoch"] - first["reset_epoch"], 2)
            self.assertEqual(second["total_commit_count"], 1)
        finally:
            self.stop(server, worker)

    def test_restart_same_port_cannot_erase_identity_of_two_commits(self):
        server, worker, base = self.start()
        port = server.server_port
        try:
            self.assertEqual(self.post(base, "/reset"), 204)
            before = self.audit(base)
            for _ in range(2):
                self.assertEqual(self.post(base, "/submit", b"value=synthetic"), 200)
            self.assertEqual(self.audit(base)["total_commit_count"], 2)
        finally:
            self.stop(server, worker)
        # A new process bound to the SAME port has identical reset and lifetime
        # counts after a reset. Only a fresh incarnation ID distinguishes it.
        replacement, worker2, base2 = self.start(port)
        try:
            self.assertEqual(self.post(base2, "/reset"), 204)
            after = self.audit(base2)
            self.assertEqual(before["reset_epoch"], after["reset_epoch"])
            self.assertEqual(before["commit_count"], after["commit_count"])
            self.assertEqual(before["total_commit_count"], after["total_commit_count"])
            self.assertNotEqual(before["instance_id"], after["instance_id"])
        finally:
            self.stop(replacement, worker2)


if __name__ == "__main__":
    unittest.main()

"""Real HTTP, synthetic-only reset-versus-pending-submit safety controls.

These tests never launch CUA Driver, Pomerado, a browser, Boat or Avrea.
"""
from __future__ import annotations

import json
from threading import Event, Thread
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from audit_fixture import AuditedFixtureServer, AuditedHandler


class InflightResetControls(unittest.TestCase):
    def setUp(self):
        self.servers: list[tuple[AuditedFixtureServer, Thread]] = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def start(self, **delays):
        server = AuditedFixtureServer(("127.0.0.1", 0), **delays)
        entered = Event()
        class SignalHandler(AuditedHandler):
            def do_POST(self):
                if self.path == "/submit":
                    entered.set()
                super().do_POST()
        server.RequestHandlerClass = SignalHandler
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}", entered

    @staticmethod
    def post(base: str, path: str, body=b"") -> int:
        with urlopen(Request(base+path, method="POST", data=body), timeout=3) as response:
            return response.status

    @staticmethod
    def read(base: str, path: str) -> dict:
        with urlopen(base + path, timeout=3) as response:
            return json.load(response)

    def launch_submit(self, base: str) -> Thread:
        failures = []
        def submit():
            try:
                self.assertEqual(self.post(base, "/submit", b"value=synthetic"), 200)
            except BaseException as error:
                failures.append(error)
        thread = Thread(target=submit, daemon=True)
        thread.start()
        self.addCleanup(lambda: self.assertFalse(failures, repr(failures)))
        self.addCleanup(thread.join, 3)
        return thread

    def conflict(self, base: str) -> None:
        try:
            status = self.post(base, "/reset")
        except HTTPError as error:
            self.assertEqual(error.code, 409)
        else:
            self.fail(f"reset unexpectedly accepted with in-flight submit: HTTP {status}")

    def test_dispatch_pending_reset_refused_before_mutation(self):
        base, entered = self.start(dispatch_delay_s=0.35)
        writer = self.launch_submit(base)
        self.assertTrue(entered.wait(timeout=2), "submit handler never entered")
        time.sleep(0.05)  # below 350ms dispatch delay, above handler entry
        self.assertEqual(self.read(base, "/audit")["commit_count"], 0)
        self.conflict(base)
        self.assertTrue(writer.is_alive(), "reset was not tested against pending dispatch")
        writer.join(timeout=2)
        self.assertFalse(writer.is_alive())
        self.assertEqual(self.read(base, "/audit")["commit_count"], 1)
        self.assertEqual(self.post(base, "/reset"), 204)
        self.assertEqual(self.read(base, "/audit")["commit_count"], 0)

    def test_ack_pending_reset_refused_after_mutation(self):
        base, entered = self.start(ack_delay_s=0.35)
        writer = self.launch_submit(base)
        self.assertTrue(entered.wait(timeout=2), "submit handler never entered")
        deadline = time.monotonic() + 2
        while self.read(base, "/audit")["commit_count"] != 1:
            self.assertLess(time.monotonic(), deadline, "commit did not occur")
            time.sleep(0.01)
        self.assertTrue(writer.is_alive(), "ack was no longer pending")
        self.conflict(base)
        writer.join(timeout=2)
        self.assertFalse(writer.is_alive())
        self.assertEqual(self.read(base, "/audit")["commit_count"], 1)
        self.assertEqual(self.post(base, "/reset"), 204)
        self.assertEqual(self.read(base, "/audit")["commit_count"], 0)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the lane-D fixture server (i107_fixture.py). No browser."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
JEV = Path(os.environ.get("JEV_USE_DIR", HERE.parents[4] / "libs/cua-driver/examples/jev-use"))
sys.path.insert(0, str(JEV))

import fixture_server as jev  # noqa: E402
import i107_fixture as fx  # noqa: E402


def post(url: str, body: bytes = b"", ctype: str = "application/json") -> tuple[int, bytes]:
    with urlopen(Request(url, data=body, method="POST", headers={"Content-Type": ctype}), timeout=5) as r:
        return r.status, r.read()


def get_json(url: str) -> dict:
    with urlopen(url, timeout=10) as r:
        return json.loads(r.read())


class PagesTest(unittest.TestCase):
    def test_quiet_page_is_the_jev_page_byte_for_byte(self) -> None:
        self.assertEqual(fx.page_for("quiet"), jev.PAGE)

    def test_churn_page_keeps_the_form_and_adds_a_seeded_region(self) -> None:
        page = fx.page_for("churn").decode()
        form = jev.PAGE.decode()
        self.assertTrue(page.startswith(form[: form.index("</main>") + len("</main>")]))
        self.assertIn(f"const N={fx.CHURN_NODES}", page)
        self.assertIn(f"HZ={fx.CHURN_HZ}", page)
        self.assertIn(f"PER={fx.CHURN_PER_TICK}", page)
        self.assertIn(f"let s={fx.CHURN_SEED}", page)
        self.assertEqual((fx.CHURN_NODES, fx.CHURN_HZ, fx.CHURN_PER_TICK), (500, 20, 10))
        self.assertNotIn("EventSource", page)

    def test_churn_words_never_name_the_form_controls(self) -> None:
        for word in fx.CHURN_WORDS:
            self.assertNotIn("submit", word.lower())
            self.assertNotIn("verification", word.lower())
        region = fx.page_for("churn").decode().split("</main>", 1)[1].lower()
        self.assertNotIn("submit", region)
        self.assertNotIn("verification", region)

    def test_control_page_has_the_channel_and_every_registered_op(self) -> None:
        page = fx.page_for("control").decode()
        self.assertIn("new EventSource('/events')", page)
        for op in fx.CONTROL_OPS:
            self.assertRegex(page, rf"\b{op}\(")
        self.assertTrue(page.startswith(jev.PAGE.decode()[: jev.PAGE.decode().index("</main>")]))

    def test_inline_scripts_parse(self) -> None:
        node = shutil.which("node") or os.environ.get("NODE_BIN")
        if not node:
            self.skipTest("node not available")
        for variant in ("churn", "control"):
            scripts = re.findall(r"<script>(.*?)</script>", fx.page_for(variant).decode(), re.S)
            self.assertTrue(scripts, variant)
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write("\n".join(scripts))
            try:
                done = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
            finally:
                os.unlink(f.name)


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = fx.make_server(0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def configure(self, **cfg) -> None:
        post(self.url + "config", json.dumps({"variant": "quiet", "token": "tok-1", **cfg}).encode())

    def submit(self, path: str, value: str) -> None:
        post(self.url + path.lstrip("/"), urlencode({"value": value}).encode(), "application/x-www-form-urlencoded")

    def test_state_is_jev_compatible_and_poller_records_first_ok(self) -> None:
        self.configure()
        self.assertEqual(get_json(self.url + "state")["submitted"], None)
        t_before = time.monotonic_ns()
        self.submit("/submit", "tok-1")
        self.assertEqual(get_json(self.url + "state")["submitted"], "tok-1")
        time.sleep(0.05)
        trial = get_json(self.url + "trial")
        self.assertIsNotNone(trial["poller_first_ok_ns"])
        self.assertGreaterEqual(trial["poller_first_ok_ns"], t_before)
        journal = get_json(self.url + "journal")["journal"]
        submits = [e for e in journal if e["event"] == "submit"]
        self.assertEqual(len(submits), 1)
        self.assertEqual(submits[0]["endpoint"], "/submit")
        self.assertEqual(submits[0]["value_len"], 5)
        self.assertNotIn("tok-1", json.dumps(journal))
        self.assertEqual(get_json(self.url + "journal")["journal"], [])  # drained

    def test_wrong_value_is_not_ok_and_reset_clears(self) -> None:
        self.configure()
        self.submit("/submit", "other")
        time.sleep(0.02)
        self.assertIsNone(get_json(self.url + "trial")["poller_first_ok_ns"])
        post(self.url + "reset")
        self.assertIsNone(get_json(self.url + "state")["submitted"])

    def test_decoy_and_competing_are_wrong_target_and_never_set_submitted(self) -> None:
        self.configure()
        self.submit("/submit-decoy", "tok-1")
        self.submit("/submit-competing", "tok-1")
        self.assertIsNone(get_json(self.url + "state")["submitted"])
        events = [e for e in get_json(self.url + "journal")["journal"] if e["event"] == "wrong_target_submit"]
        self.assertEqual([e["endpoint"] for e in events], ["/submit-decoy", "/submit-competing"])

    def test_submit_delay_journals_receipt_then_apply(self) -> None:
        self.configure(submit_delay_ms=150)
        t0 = time.monotonic_ns()
        self.submit("/submit", "tok-1")
        submit = [e for e in get_json(self.url + "journal")["journal"] if e["event"] == "submit"][0]
        self.assertGreaterEqual(submit["t_mono_ns"] - submit["received_t_mono_ns"], 140_000_000)
        self.assertGreaterEqual(submit["received_t_mono_ns"], t0)

    def test_count_does_not_drain(self) -> None:
        self.configure()
        self.submit("/submit", "tok-1")
        self.assertEqual(get_json(self.url + "journal-count?event=submit")["count"], 1)
        self.assertEqual(get_json(self.url + "journal-count?event=submit")["count"], 1)

    def test_control_channel_delivers_once_and_journals_ack(self) -> None:
        self.configure(variant="control")
        received: list[dict] = []

        def page() -> None:
            with urlopen(self.url + "events", timeout=10) as stream:
                post(self.url + "note", json.dumps({"kind": "control_open"}).encode())  # what es.onopen does
                for raw in stream:
                    line = raw.decode().strip()
                    if line.startswith("data:"):
                        msg = json.loads(line[5:])
                        received.append(msg)
                        post(self.url + "ack", json.dumps({"id": msg["id"], "result": {"applied": True}}).encode())
                        return

        t = threading.Thread(target=page, daemon=True)
        t.start()
        fx.wait_note(self.url, "control_open", 0, 5.0)
        op_id = json.loads(post(self.url + "control", json.dumps({"op": "remove_submit", "args": {}}).encode())[1])["id"]
        ack = get_json(self.url + f"ack-wait?id={op_id}&timeout=5")
        t.join(5)
        self.assertTrue(ack["acked"])
        self.assertEqual(received[0]["op"], "remove_submit")
        journal = get_json(self.url + "journal")["journal"]
        kinds = [e["event"] for e in journal]
        self.assertIn("control_posted", kinds)
        self.assertIn("control_ack", kinds)
        posted = next(e for e in journal if e["event"] == "control_posted")
        acked = next(e for e in journal if e["event"] == "control_ack")
        self.assertLessEqual(posted["t_mono_ns"], acked["t_mono_ns"])
        self.assertEqual(acked["result"], {"applied": True})

    def test_a_stream_from_an_earlier_trial_never_takes_a_later_op(self) -> None:
        self.configure(variant="control")
        got: dict[str, list] = {"old": [], "new": []}

        def page(tag: str) -> None:
            try:
                with urlopen(self.url + "events", timeout=6) as stream:
                    post(self.url + "note", json.dumps({"kind": f"open_{tag}"}).encode())
                    for raw in stream:
                        line = raw.decode().strip()
                        if line.startswith("data:"):
                            got[tag].append(json.loads(line[5:]))
                            return
            except OSError:
                return

        old = threading.Thread(target=page, args=("old",), daemon=True)
        old.start()
        fx.wait_note(self.url, "open_old", 0, 5.0)
        self.configure(variant="control")  # next trial
        new = threading.Thread(target=page, args=("new",), daemon=True)
        new.start()
        fx.wait_note(self.url, "open_new", 0, 5.0)
        post(self.url + "control", json.dumps({"op": "blur_field", "args": {}}).encode())
        new.join(5)
        old.join(3)
        self.assertEqual([m["op"] for m in got["new"]], ["blur_field"])
        self.assertEqual(got["old"], [])

    def test_unknown_op_is_refused(self) -> None:
        with self.assertRaises(Exception):
            post(self.url + "control", json.dumps({"op": "rm -rf", "args": {}}).encode())

    def test_ack_wait_times_out(self) -> None:
        self.assertFalse(get_json(self.url + "ack-wait?id=999&timeout=0.2")["acked"])

    def test_note_and_wait_note(self) -> None:
        t0 = time.monotonic_ns()
        post(self.url + "note", json.dumps({"kind": "detached_click", "connected": False}).encode())
        hit = fx.wait_note(self.url, "detached_click", t0, 2.0)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["connected"], False)
        self.assertIsNone(fx.wait_note(self.url, "detached_click", time.monotonic_ns(), 0.2))


if __name__ == "__main__":
    unittest.main()

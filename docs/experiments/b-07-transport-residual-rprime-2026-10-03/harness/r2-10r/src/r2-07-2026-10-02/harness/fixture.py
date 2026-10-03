"""R2-07 owned loopback fixture: target-side journal + page variants (measurement harness only).

The journal technique (received / applied events, held first submit, unchanged-read
placement) is adapted from R2-05 ``harness/ackloss_fixture.py`` (branch
exp/r2-05-ack-loss-real-20261001, commit 236e37e01). The default page is the unchanged
jev-use ``fixture_server.PAGE`` of the tested source.

The TARGET owns the journal; callers never read it. Callers see only ``GET /state`` ->
``{"submitted": ...}`` (unchanged shape). Harness oracle polls send the header
``X-R207-Oracle: 1`` and are not journaled as caller reads (so they can never release a
held effect). The journal stores no submitted values, only whether a value equals the
trial token.

Page variants (``configure(..., variant=...)``):
  normal              unchanged fixture page
  n1_renamed          Submit button relabelled "Send"
  n2_missing          no Submit control
  n3_duplicate        two Submit buttons in the same form
  rerender_on_signal  N4a: the page long-polls /__signal; when the harness triggers it, the page
                      replaces the Submit button node with a fresh clone (same role/name) and
                      POSTs /__rerendered
  n6_modal            typing into the field opens a modal <dialog> (showModal) over the form
  n7_prefilled        the field is prefilled with a different value
  n8_toggle           the toggle->confirm page from scripts/repro/issue24_battery_live.py
                      (commit 5474aa31f), verbatim, with its /event/toggle journaled

Hold modes for the FIRST submit (later submits apply at once): immediate,
after_unchanged:K (apply after K caller /state reads returned unchanged after receipt), withheld.
"""

from __future__ import annotations

import html
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

from fixture_server import PAGE  # unchanged jev-use form page (tested source)

HOLD_CAP_S = 60.0
SUBMIT_BUTTON = b'<button type="submit">Submit</button>'
assert SUBMIT_BUTTON in PAGE

RERENDER_SCRIPT = b"""<script>
fetch('/__signal').then(() => {
  const old = document.querySelector('button[type=submit]');
  const fresh = old.cloneNode(true);
  old.replaceWith(fresh);
  return fetch('/__rerendered', {method: 'POST'});
});
</script>"""

MODAL_SCRIPT = b"""<dialog id="interrupt"><p>Your session is about to expire.</p>
<button type="button" id="stay">Stay signed in</button></dialog>
<script>
document.querySelector('input[name=value]').addEventListener('input', () => {
  const d = document.getElementById('interrupt');
  if (!d.open) { d.showModal(); fetch('/__modal_opened', {method: 'POST'}); }
}, {once: true});
</script>"""

# Verbatim from scripts/repro/issue24_battery_live.py @ 5474aa31f (PAGES["toggle-confirm"]).
TOGGLE_CONFIRM = """<!doctype html><title>toggle</title>
<input type="checkbox" aria-label="feature">
<button type="button" id="go">Confirm</button>
<script>
document.getElementById("go").onclick = () => {
  const on = document.querySelector("[aria-label=feature]").checked;
  fetch("/event/toggle", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:"checked="+(on?"1":"0")});
};
</script>""".encode()


def page_for(variant: str) -> bytes:
    if variant == "normal":
        return PAGE
    if variant == "n1_renamed":
        return PAGE.replace(SUBMIT_BUTTON, b'<button type="submit">Send</button>')
    if variant == "n2_missing":
        return PAGE.replace(SUBMIT_BUTTON, b"")
    if variant == "n3_duplicate":
        return PAGE.replace(SUBMIT_BUTTON, SUBMIT_BUTTON + SUBMIT_BUTTON)
    if variant == "rerender_on_signal":
        return PAGE.replace(b"</main></html>", b"</main>" + RERENDER_SCRIPT + b"</html>")
    if variant == "n6_modal":
        return PAGE.replace(b"</main></html>", b"</main>" + MODAL_SCRIPT + b"</html>")
    if variant == "n7_prefilled":
        return PAGE.replace(b'<input name="value" required', b'<input name="value" value="r2-07-other-value" required')
    if variant == "n8_toggle":
        return TOGGLE_CONFIRM
    raise ValueError(f"unknown variant {variant}")


class TargetJournal:
    def __init__(self) -> None:
        self.lock = threading.Condition()
        self.trial: str | None = None
        self.token: str | None = None
        self.mode = "immediate"
        self.k = 0
        self.events: list[dict[str, Any]] = []
        self.submitted: str | None = None
        self.submit_count = 0
        self.pending: dict[int, dict[str, Any]] = {}
        self.t0 = time.monotonic_ns()
        self.first_visible_ns: int | None = None

    # harness side
    def reset_trial(self, trial: str, token: str, mode: str) -> None:
        with self.lock:
            self._release_locked("trial_reset")
            self.lock.notify_all()
        self.wait_quiescent(10)
        with self.lock:
            self.trial, self.token = trial, token
            if mode.startswith("after_unchanged:"):
                self.mode, self.k = "after_unchanged", int(mode.split(":", 1)[1])
            else:
                self.mode, self.k = mode, 0
            self.events, self.submitted, self.submit_count, self.pending = [], None, 0, {}
            self.t0 = time.monotonic_ns()
            self.first_visible_ns = None
            self._add_locked("trial_reset", mode=mode)

    def release_all(self, reason: str = "harness_release") -> None:
        with self.lock:
            self._release_locked(reason)
            self.lock.notify_all()

    def wait_for(self, kind: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.lock:
            while not any(e["kind"] == kind for e in self.events):
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.lock.wait(left)
            return True

    def wait_quiescent(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.lock:
            while any(not p["applied"] for p in self.pending.values()):
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.lock.wait(left)
            return True

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "trial": self.trial,
                "mode": self.mode if self.mode != "after_unchanged" else f"after_unchanged:{self.k}",
                "received": sum(1 for e in self.events if e["kind"] == "received"),
                "applied": sum(1 for e in self.events if e["kind"] == "applied"),
                "toggle_events": sum(1 for e in self.events if e["kind"] == "toggle_event"),
                "pending_unapplied": sum(1 for p in self.pending.values() if not p["applied"]),
                "state_matches_token": self.submitted is not None and self.submitted == self.token,
                "submitted_other_value": self.submitted is not None and self.submitted != self.token,
                "caller_state_reads": sum(1 for e in self.events if e["kind"] == "state_read"),
                "first_visible_ns": self.first_visible_ns,
                "events": [dict(e) for e in self.events],
            }

    # target side
    def _add_locked(self, kind: str, **fields: Any) -> dict[str, Any]:
        event = {"seq": len(self.events) + 1, "kind": kind,
                 "t_ms": round((time.monotonic_ns() - self.t0) / 1e6, 3), "t_ns": time.monotonic_ns(), **fields}
        self.events.append(event)
        return event

    def add(self, kind: str, **fields: Any) -> None:
        with self.lock:
            self._add_locked(kind, **fields)
            self.lock.notify_all()

    def _release_locked(self, reason: str) -> None:
        for p in self.pending.values():
            if not p["released"]:
                p["released"], p["release_reason"] = True, reason

    def receive_submit(self, value: str) -> int:
        with self.lock:
            self.submit_count += 1
            n = self.submit_count
            hold = n == 1 and self.mode in {"after_unchanged", "withheld"}
            self.pending[n] = {"value": value, "released": not hold, "applied": False,
                               "release_reason": None if hold else "immediate", "unchanged_reads": 0}
            self._add_locked("received", op=n, held=hold, value_matches_token=value == self.token)
            self.lock.notify_all()
            return n

    def apply_when_released(self, n: int) -> None:
        deadline = time.monotonic() + HOLD_CAP_S
        with self.lock:
            p = self.pending.get(n)
            if p is None:
                return
            while not p["released"]:
                left = deadline - time.monotonic()
                if left <= 0:
                    p["released"], p["release_reason"] = True, "hold_cap"
                    break
                self.lock.wait(left)
            if self.pending.get(n) is p:
                self.submitted = p["value"]
                p["applied"] = True
                if self.submitted == self.token and self.first_visible_ns is None:
                    self.first_visible_ns = time.monotonic_ns()
                self._add_locked("applied", op=n, release_reason=p["release_reason"],
                                 value_matches_token=p["value"] == self.token)
            self.lock.notify_all()

    def read_state(self, caller: bool) -> dict[str, Any]:
        with self.lock:
            if caller:
                visible = self.submitted is not None and self.submitted == self.token
                self._add_locked("state_read", effect_visible=visible,
                                 pending_unapplied=sum(1 for p in self.pending.values() if not p["applied"]))
            return {"submitted": self.submitted}

    def after_state_read_served(self) -> None:
        with self.lock:
            if self.mode != "after_unchanged":
                return
            for p in self.pending.values():
                if not p["released"] and not p["applied"]:
                    p["unchanged_reads"] += 1
                    if p["unchanged_reads"] >= self.k:
                        p["released"], p["release_reason"] = True, f"after_{self.k}_unchanged_reads"
            self.lock.notify_all()


class Handler(BaseHTTPRequestHandler):
    server: "JournalFixture"
    protocol_version = "HTTP/1.0"

    def do_GET(self) -> None:  # noqa: N802
        srv = self.server
        if self.path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", page_for(srv.variant))
        elif self.path == "/state":
            caller = self.headers.get("X-R207-Oracle") != "1"
            body = json.dumps(srv.journal.read_state(caller)).encode()
            if self._send(HTTPStatus.OK, "application/json", body) and caller:
                srv.journal.after_state_read_served()
        elif self.path == "/__signal":
            srv.signal.wait(30)
            self._send(HTTPStatus.OK, "text/plain", b"go")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode()
        srv, journal = self.server, self.server.journal
        if self.path == "/reset":
            journal.add("runner_reset_ignored")
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/__rerendered":
            journal.add("page_rerendered")
            srv.rerendered.set()
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/__modal_opened":
            journal.add("modal_opened")
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/event/toggle":
            journal.add("toggle_event")
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path != "/submit":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        value = parse_qs(raw).get("value", [""])[0]
        if not value:
            journal.add("submit_rejected_empty")
            self.send_error(HTTPStatus.BAD_REQUEST, "value is required")
            return
        n = journal.receive_submit(value)
        journal.apply_when_released(n)
        body = ("<!doctype html><title>Cua Driver Jev verified</title>"
                f"<h1>Action received</h1><output>status=submitted:{html.escape(value)}</output>").encode()
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> bool:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False


class JournalFixture(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        self.journal = TargetJournal()
        self.variant = "normal"
        self.signal = threading.Event()
        self.rerendered = threading.Event()
        super().__init__(("127.0.0.1", 0), Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/"

    def configure(self, trial: str, token: str, *, variant: str = "normal", mode: str = "immediate") -> None:
        page_for(variant)
        self.signal.set()  # release any long-poll from an earlier page
        self.variant = variant
        self.journal.reset_trial(trial, token, mode)
        self.signal = threading.Event()
        self.rerendered = threading.Event()

    def trigger_rerender(self) -> None:
        self.signal.set()

    def wait_rerendered(self, timeout: float) -> bool:
        return self.rerendered.wait(timeout)

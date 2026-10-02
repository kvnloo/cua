"""Owned loopback fixture for OWN-105 with a target-side mutation journal.

Copied from the R2-05 packet (``r2-05-2026-10-01/harness/ackloss_fixture.py``,
sha256 730cbfe5...) with two changes: the page is the jev-use form with a
non-navigating Submit (``FETCH_PAGE``: the same form and accessible names; a
submit handler posts the same form body with ``fetch`` and stays on the page,
so Submit remains observable after an unresolved completion), and a separate
harness-only control server (``ControlServer``) lets child-process seams wait on
journal barriers. The runner never talks to the control server.

The target, not
the caller, owns the journal: every ``POST /submit`` appends ``received`` and,
when the target applies it, ``applied``. ``GET /state`` (the caller's oracle,
unchanged shape ``{"submitted": ...}``) is journaled as ``state_read`` with
whether the effect was visible.

Effect placement for the FIRST submit of a trial (later submits apply at once):

* ``immediate``          apply on receipt (normal fixture behaviour);
* ``after_unchanged:K``  hold; apply only after the target has served K
                         ``/state`` reads that returned "unchanged" after receipt
                         (explicit target phase, no sleeps);
* ``withheld``           hold until the harness calls ``release_all()``
                         (after the caller has finished).

The HTTP response for a held submit is sent only after the effect is applied,
like a slow synchronous server. A received operation is always applied even if
the client disconnected meanwhile: that is the "may still land" hazard.

``POST /reset`` from the runner is journaled and ignored; the harness resets the
target between trials with ``reset_trial()``.

The journal stores no submitted values, only whether a value equals the trial
token, so the packet stays content-free.
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

from fixture_server import PAGE  # unchanged jev-use form page

FETCH_SCRIPT = (
    b"<script>document.querySelector('form').addEventListener('submit', (event) => {"
    b"event.preventDefault();"
    b"fetch('/submit', {method: 'POST', body: new URLSearchParams(new FormData(event.target))});"
    b"});</script>"
)
FETCH_PAGE = PAGE.replace(b"</main></html>", b"</main>" + FETCH_SCRIPT + b"</html>")
assert FETCH_PAGE != PAGE

HOLD_CAP_S = 120.0


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

    # -- harness side -------------------------------------------------
    def reset_trial(self, trial: str, token: str, mode: str) -> None:
        with self.lock:
            # Any operation still held from an earlier trial is applied first so it
            # cannot leak into this trial's journal.
            self._release_locked("trial_reset")
            self.lock.notify_all()
        self.wait_quiescent(10)
        with self.lock:
            self.trial, self.token = trial, token
            if mode.startswith("after_unchanged:"):
                self.mode, self.k = "after_unchanged", int(mode.split(":", 1)[1])
            else:
                self.mode, self.k = mode, 0
            self.events = []
            self.submitted = None
            self.submit_count = 0
            self.pending = {}
            self.t0 = time.monotonic_ns()
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
            received = sum(1 for e in self.events if e["kind"] == "received")
            applied = sum(1 for e in self.events if e["kind"] == "applied")
            return {
                "trial": self.trial,
                "mode": self.mode if self.mode != "after_unchanged" else f"after_unchanged:{self.k}",
                "received": received,
                "applied": applied,
                "pending_unapplied": sum(1 for p in self.pending.values() if not p["applied"]),
                "state_matches_token": self.submitted is not None and self.submitted == self.token,
                "events": [dict(e) for e in self.events],
            }

    # -- target side --------------------------------------------------
    def _add_locked(self, kind: str, **fields: Any) -> dict[str, Any]:
        event = {"seq": len(self.events) + 1, "kind": kind,
                 "t_ms": round((time.monotonic_ns() - self.t0) / 1e6, 3), **fields}
        self.events.append(event)
        return event

    def _release_locked(self, reason: str) -> None:
        for p in self.pending.values():
            if not p["released"]:
                p["released"] = True
                p["release_reason"] = reason

    def receive_submit(self, value: str, ua_chrome: bool) -> int:
        with self.lock:
            self.submit_count += 1
            n = self.submit_count
            hold = n == 1 and self.mode in {"after_unchanged", "withheld"}
            self.pending[n] = {"value": value, "released": not hold, "applied": False,
                               "release_reason": None if hold else "immediate", "unchanged_reads": 0}
            self._add_locked("received", op=n, held=hold, value_matches_token=value == self.token,
                             user_agent_chrome=ua_chrome)
            self.lock.notify_all()
            return n

    def apply_when_released(self, n: int) -> None:
        deadline = time.monotonic() + HOLD_CAP_S
        with self.lock:
            p = self.pending[n] if n in self.pending else None
            if p is None:
                return
            while not p["released"]:
                left = deadline - time.monotonic()
                if left <= 0:
                    p["released"], p["release_reason"] = True, "hold_cap"
                    break
                self.lock.wait(left)
            if n in self.pending and self.pending[n] is p:
                self.submitted = p["value"]
                p["applied"] = True
                self._add_locked("applied", op=n, release_reason=p["release_reason"],
                                 value_matches_token=p["value"] == self.token)
            self.lock.notify_all()

    def read_state(self) -> dict[str, Any]:
        with self.lock:
            visible = self.submitted is not None and self.submitted == self.token
            self._add_locked("state_read", effect_visible=visible,
                             pending_unapplied=sum(1 for p in self.pending.values() if not p["applied"]))
            return {"submitted": self.submitted}

    def after_state_read_served(self) -> None:
        """Explicit target phase: count an unchanged read only after it was sent."""
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
    server: "AckLossFixture"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", FETCH_PAGE)
        elif self.path == "/state":
            body = json.dumps(self.server.journal.read_state()).encode()
            ok = self._send(HTTPStatus.OK, "application/json", body)
            if ok:
                self.server.journal.after_state_read_served()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode()
        journal = self.server.journal
        if self.path == "/reset":
            with journal.lock:
                journal._add_locked("runner_reset_ignored")
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path != "/submit":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        value = parse_qs(raw).get("value", [""])[0]
        if not value:
            self.send_error(HTTPStatus.BAD_REQUEST, "value is required")
            return
        n = journal.receive_submit(value, "Chrome" in (self.headers.get("User-Agent") or ""))
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
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False


class AckLossFixture(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        self.journal = TargetJournal()
        super().__init__(("127.0.0.1", 0), Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/"


class ControlHandler(BaseHTTPRequestHandler):
    """Harness-only barrier endpoint for seams running in child processes."""

    server: "ControlServer"

    def do_GET(self) -> None:  # noqa: N802
        from urllib.parse import urlsplit

        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        journal = self.server.journal
        if parts.path == "/wait":
            kind = query.get("kind", [""])[0]
            timeout = float(query.get("timeout", ["20"])[0])
            body = {"reached": journal.wait_for(kind, timeout)}
        elif parts.path == "/snapshot":
            body = {k: v for k, v in journal.snapshot().items() if k != "events"}
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = json.dumps(body).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, journal: TargetJournal) -> None:
        self.journal = journal
        super().__init__(("127.0.0.1", 0), ControlHandler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/"

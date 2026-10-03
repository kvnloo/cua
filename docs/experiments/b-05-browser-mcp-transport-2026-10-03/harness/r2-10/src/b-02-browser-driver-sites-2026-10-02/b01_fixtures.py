"""Experiment-owned #24 fixtures for B-01 (toggle->confirm, modal->act).

The page HTML, the ``State``/``Handler``/``Server`` classes and ``oracle_ok``
below are copied verbatim from kvnloo/cua commit
5474aa31f090529e2a53466993bd19ce03406225, ``scripts/repro/issue24_battery_live.py``
(only the 'toggle-confirm' and 'modal' pages are kept in ``PAGES``).
``verify_artifacts.py`` re-checks the copy against that commit when the git
object is available. ``JournalState`` adds a server-side CLOCK_MONOTONIC
journal of every state mutation; the server state is the oracle.
"""

from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

PAGES = {
    "toggle-confirm": """<!doctype html><title>toggle</title>
<input type="checkbox" aria-label="feature">
<button type="button" id="go">Confirm</button>
<script>
document.getElementById("go").onclick = () => {
  const on = document.querySelector("[aria-label=feature]").checked;
  fetch("/event/toggle", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:"checked="+(on?"1":"0")});
};
</script>""",
    "modal": """<!doctype html><title>modal</title>
<button type="button" id="open">Open dialog</button>
<div id="panel" hidden><button type="button" id="ok">Confirm choice</button></div>
<script>
document.getElementById("open").onclick = () => {
  document.getElementById("panel").hidden = false;
  fetch("/event/opened", {method:"POST"});
};
document.getElementById("ok").onclick = () => fetch("/event/modal", {method:"POST"});
</script>""",
}


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: dict[str, Any] = {}

    def reset(self) -> None:
        with self.lock:
            self.data = {
                "filled": None,
                "checked": None,
                "given": None,
                "family": None,
                "opened": False,
                "modal": False,
                "ambiguous": None,
            }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.data)

    def update(self, **items: Any) -> None:
        with self.lock:
            self.data.update(items)


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/state":
            body = json.dumps(self.server.state.snapshot()).encode()
            self._send(HTTPStatus.OK, "application/json", body)
            return
        task = self.path.removeprefix("/")
        page = PAGES.get(task)
        if page is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", page.encode())

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        path = self.path
        state = self.server.state
        if path == "/reset":
            state.reset()
        elif path == "/event/fill":
            state.update(filled=(form.get("value") or [""])[0])
        elif path == "/event/toggle":
            state.update(checked=(form.get("checked") or ["0"])[0] == "1")
        elif path == "/event/fields":
            state.update(
                given=(form.get("given") or [""])[0],
                family=(form.get("family") or [""])[0],
            )
        elif path == "/event/opened":
            state.update(opened=True)
        elif path == "/event/modal":
            state.update(modal=True)
        elif path == "/event/ambiguous":
            state.update(ambiguous=(form.get("which") or [""])[0])
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Server(ThreadingHTTPServer):
    def __init__(self) -> None:
        self.state = State()
        self.state.reset()
        super().__init__(("127.0.0.1", 0), Handler)


def oracle_ok(task: str, state: dict[str, Any], token: str) -> bool:
    if task == "fill-submit":
        return state.get("filled") == token
    if task == "toggle-confirm":
        return state.get("checked") is True
    if task == "two-fields":
        return state.get("given") == token and state.get("family") == token + "-b"
    if task == "modal":
        return state.get("opened") is True and state.get("modal") is True
    if task == "ambiguous":
        return state.get("ambiguous") is None
    return False



class JournalState(State):
    """``State`` plus a CLOCK_MONOTONIC journal of every mutation."""

    def __init__(self) -> None:
        self.journal: list[dict[str, Any]] = []
        self._jlock = threading.Lock()
        super().__init__()

    def reset(self) -> None:
        t = time.monotonic_ns()
        super().reset()
        with self._jlock:
            self.journal.append({"event": "reset", "t_mono_ns": t})

    def update(self, **items: Any) -> None:
        t = time.monotonic_ns()
        super().update(**items)
        with self._jlock:
            self.journal.append({"event": "update", "t_mono_ns": t, "fields": dict(items)})

    def drain(self) -> list[dict[str, Any]]:
        with self._jlock:
            out, self.journal = self.journal, []
        return out


class JournalServer(Server):
    def __init__(self) -> None:
        super().__init__()
        self.state = JournalState()
        self.state.reset()
        self.state.drain()

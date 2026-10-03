"""R2-07c owned loopback fixtures for the #24 toggle->confirm and modal->act pages (harness only).

The ``normal`` pages are the B-01 copies (``b01_fixtures.PAGES``, verbatim from kvnloo/cua
5474aa31f ``scripts/repro/issue24_battery_live.py``); the state, ``oracle_ok`` semantics and the
CLOCK_MONOTONIC ``update`` journal are B-01's ``JournalState``. This module adds, for the G4/G5
controls only:

* page variants (one per trial, set with ``configure``):
    normal          unchanged #24 page
    n1_renamed      the step-2 target is relabelled (toggle "Confirm" -> "Save";
                    modal "Confirm choice" -> "Accept choice")
    n2_missing      the step-2 target is removed (an empty <span> keeps the script's id lookup)
    n3_duplicate    a second step-2 target with the same role and name (same handler)
    n6_dialog       action 1 (checkbox click / "Open dialog" click) also opens an unexpected
                    modal <dialog> (showModal) that makes the rest of the page inert
    n7_presat       the precondition is already satisfied: the checkbox starts checked / the
                    dialog panel starts open (and the page reports /event/opened on load)
* a target-side hold journal for the FIRST completion event (``/event/toggle`` for toggle,
  ``/event/modal`` for modal), adapted from the R2-07 fixture (R2-05 technique): modes
  ``immediate``, ``after_unchanged:K`` (apply after K caller ``/state`` reads returned unchanged
  after receipt) and ``withheld`` (apply only on harness release after the caller finished).
  Caller reads are ``GET /state`` without ``X-R207-Oracle: 1``; the independent oracle thread reads
  the state in process and is never a caller read.

Journal entries all carry ``event`` and ``t_mono_ns`` (``update`` entries are B-01's; ``received``,
``applied``, ``state_read``, ``dialog_opened`` are added here). No values are stored.
"""

from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

import b01_fixtures as bf
import run_critpath as rc

HOLD_CAP_S = 60.0
TOGGLE = bf.PAGES["toggle-confirm"]
MODAL = bf.PAGES["modal"]
_T_BTN = '<button type="button" id="go">Confirm</button>'
_M_BTN = '<button type="button" id="ok">Confirm choice</button>'
assert _T_BTN in TOGGLE and _M_BTN in MODAL
_DIALOG = """<dialog id="interrupt"><p>Your session is about to expire.</p>
<button type="button" id="stay">Stay signed in</button></dialog>"""


def _interrupt_on(selector: str) -> str:
    return (_DIALOG + "\n<script>\ndocument.querySelector(%s).addEventListener('click', () => {\n"
            "  const d = document.getElementById('interrupt');\n"
            "  if (!d.open) { d.showModal(); fetch('/__dialog_opened', {method: 'POST'}); }\n"
            "}, {once: true});\n</script>") % json.dumps(selector)


VARIANTS: dict[str, dict[str, str]] = {
    "toggle": {
        "normal": TOGGLE,
        "n1_renamed": TOGGLE.replace(_T_BTN, '<button type="button" id="go">Save</button>'),
        "n2_missing": TOGGLE.replace(_T_BTN, '<span id="go"></span>'),
        "n3_duplicate": TOGGLE.replace(_T_BTN, _T_BTN + '\n<button type="button" id="go2">Confirm</button>')
        + '\n<script>document.getElementById("go2").onclick = document.getElementById("go").onclick;</script>',
        "n6_dialog": TOGGLE + "\n" + _interrupt_on("[aria-label=feature]"),
        "n7_presat": TOGGLE.replace('<input type="checkbox" aria-label="feature">',
                                    '<input type="checkbox" aria-label="feature" checked>'),
    },
    "modal": {
        "normal": MODAL,
        "n1_renamed": MODAL.replace(_M_BTN, '<button type="button" id="ok">Accept choice</button>'),
        "n2_missing": MODAL.replace(_M_BTN, '<span id="ok"></span>'),
        "n3_duplicate": MODAL.replace(_M_BTN, _M_BTN + '<button type="button" id="ok2">Confirm choice</button>')
        + '\n<script>document.getElementById("ok2").onclick = () => fetch("/event/modal", {method:"POST"});</script>',
        "n6_dialog": MODAL + "\n" + _interrupt_on("#open"),
        "n7_presat": MODAL.replace('<div id="panel" hidden>', '<div id="panel">')
        + '\n<script>fetch("/event/opened", {method:"POST"});</script>',
    },
}
for _cls, _pages in VARIANTS.items():
    base = TOGGLE if _cls == "toggle" else MODAL
    for _name, _page in _pages.items():
        assert _name == "normal" or _page != base, (_cls, _name)
COMPLETION_PATH = {"toggle": "/event/toggle", "modal": "/event/modal"}
PATH_CLASS = {"/toggle-confirm": "toggle", "/modal": "modal"}


class HoldState(bf.JournalState):
    """B-01 JournalState + the hold journal for the first completion event of a trial."""

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.mode, self.k = "immediate", 0
        self.pending: dict[int, dict[str, Any]] = {}
        self.completions = 0
        super().__init__()

    def _note(self, event: str, **fields: Any) -> None:
        with self._jlock:
            self.journal.append({"event": event, "t_mono_ns": time.monotonic_ns(), **fields})
        with self.cond:
            self.cond.notify_all()

    def update(self, **items: Any) -> None:
        super().update(**items)
        with self.cond:
            self.cond.notify_all()

    def configure(self, mode: str) -> None:
        self.release_all("configure")
        self.wait_quiescent(10)
        with self.cond:
            if mode.startswith("after_unchanged:"):
                self.mode, self.k = "after_unchanged", int(mode.split(":", 1)[1])
            else:
                self.mode, self.k = mode, 0
            self.pending, self.completions = {}, 0

    def release_all(self, reason: str = "harness_release") -> None:
        with self.cond:
            for p in self.pending.values():
                if not p["released"]:
                    p["released"], p["reason"] = True, reason
            self.cond.notify_all()

    def wait_quiescent(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.cond:
            while any(not p["applied"] for p in self.pending.values()):
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.cond.wait(left)
            return True

    def wait_for(self, kind: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                with self._jlock:
                    if any(e["event"] == kind for e in self.journal):
                        return True
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.cond.wait(min(left, 0.05))

    def completion(self, fields: dict[str, Any]) -> None:
        """Receive one completion event; the first one may be held by the configured mode."""
        with self.cond:
            self.completions += 1
            n = self.completions
            hold = n == 1 and self.mode in ("after_unchanged", "withheld")
            self.pending[n] = {"released": not hold, "applied": False, "unchanged": 0,
                               "reason": None if hold else "immediate"}
        self._note("received", op=n, held=hold)
        deadline = time.monotonic() + HOLD_CAP_S
        with self.cond:
            p = self.pending[n]
            while not p["released"]:
                left = deadline - time.monotonic()
                if left <= 0:
                    p["released"], p["reason"] = True, "hold_cap"
                    break
                self.cond.wait(left)
        self.update(**fields)
        with self.cond:
            p["applied"] = True
            self.cond.notify_all()
        self._note("applied", op=n, reason=p["reason"])

    def caller_read(self) -> dict[str, Any]:
        snap = self.snapshot()
        if self.mode != "immediate":
            self._note("state_read", pending=sum(1 for p in self.pending.values() if not p["applied"]))
        return snap

    def after_caller_read(self) -> None:
        with self.cond:
            if self.mode != "after_unchanged":
                return
            for p in self.pending.values():
                if not p["released"] and not p["applied"]:
                    p["unchanged"] += 1
                    if p["unchanged"] >= self.k:
                        p["released"], p["reason"] = True, f"after_{self.k}_unchanged_reads"
            self.cond.notify_all()


class Handler(BaseHTTPRequestHandler):
    server: "VariantServer"

    def do_GET(self) -> None:  # noqa: N802
        srv = self.server
        if self.path == "/state":
            caller = self.headers.get("X-R207-Oracle") != "1"
            body = json.dumps(srv.state.caller_read() if caller else srv.state.snapshot()).encode()
            if self._send(HTTPStatus.OK, "application/json", body) and caller:
                srv.state.after_caller_read()
            return
        cls = PATH_CLASS.get(self.path)
        if cls is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", VARIANTS[cls][srv.variant].encode())

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        state = self.server.state
        if self.path == "/reset":
            state.reset()
        elif self.path == "/event/toggle":
            state.completion({"checked": (form.get("checked") or ["0"])[0] == "1"})
        elif self.path == "/event/opened":
            state.update(opened=True)
        elif self.path == "/event/modal":
            state.completion({"modal": True})
        elif self.path == "/__dialog_opened":
            state._note("dialog_opened")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> bool:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False


class VariantServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        self.state = HoldState()
        self.state.reset()
        self.state.drain()
        self.variant = "normal"
        super().__init__(("127.0.0.1", 0), Handler)


class FixturesC:
    """rc.Fixtures' interface (fill server unchanged; #24 server = VariantServer)."""

    def __init__(self) -> None:
        self.fill = rc.FixtureServer(("127.0.0.1", 0))
        self.fill.state = rc.FillJournalState()
        self.i24 = VariantServer()
        for server in (self.fill, self.i24):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.fill_url = f"http://127.0.0.1:{self.fill.server_port}/"
        self.i24_origin = f"http://127.0.0.1:{self.i24.server_port}/"

    def configure(self, variant: str = "normal", mode: str = "immediate") -> None:
        for cls in VARIANTS:
            if variant not in VARIANTS[cls]:
                raise ValueError(variant)
        self.i24.state.configure(mode)
        self.i24.variant = variant

    def state(self, cls: str) -> Any:
        return self.fill.state if cls == "fill" else self.i24.state

    def page_url(self, cls: str) -> str:
        return self.fill_url if cls == "fill" else self.i24_origin + ("toggle-confirm" if cls == "toggle" else "modal")

    def oracle_ok_direct(self, cls: str, token: str) -> bool:
        snap = self.state(cls).snapshot()
        if cls == "fill":
            return snap.get("submitted") == token
        return bf.oracle_ok("toggle-confirm" if cls == "toggle" else "modal", snap, token)

    def close(self) -> None:
        self.i24.state.release_all("close")
        for server in (self.fill, self.i24):
            server.shutdown()
            server.server_close()

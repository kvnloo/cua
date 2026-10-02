"""FIX-01 fixture: the R2-07 journaled fixture plus page variants for detached-node rows.

MEASUREMENT HARNESS ONLY. Extends ``docs/experiments/r2-07-2026-10-02/harness/fixture.py``
(imported unchanged) with:

* ``POST /__page_event`` (``navigator.sendBeacon``): the page reports which Submit node
  received a click/pointer event (``node=old|fresh``) with its page clock, so "0 page events
  on the detached node" is observed by the target, not by the caller.
* ``POST /submit`` with ``src=detached``: an effect written by the detached node's own JS
  handler is journaled as ``submit_src`` with ``src=detached`` before the ordinary
  received/applied events, so effects can be attributed to the node that produced them.

Variants (all start from the unchanged jev-use form page):
  n4a_instr     R2-07 ``rerender_on_signal`` + click listeners on the old and fresh Submit node
  n4a_handler   n4a_instr, and the OLD node keeps a click handler that writes the token to the
                journal itself (fetch POST /submit ... src=detached): the "could land" hazard
  reattach      on signal the SAME Submit node is detached and re-attached at its place
                (connected again, same backend node): a re-attached ref must still dispatch
  trusted_probe n4a_instr with pointerdown/mousedown/click listeners and the replacement time,
                for the trusted (coordinate) route rows
  modal_act     the #24 battery "modal" page (scripts/repro/issue24_battery_live.py @ 5474aa31f,
                verbatim) with its /event/opened and /event/modal journaled
Variants inherited from R2-07: normal, n1_renamed, n2_missing, n3_duplicate, rerender_on_signal,
n6_modal, n7_prefilled, n8_toggle (toggle->confirm page verbatim from 5474aa31f).
"""

from __future__ import annotations

import json
import sys
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

R207 = Path(__file__).resolve().parents[2] / "r2-07-2026-10-02" / "harness"
sys.path.insert(0, str(R207))

import fixture as r207  # noqa: E402  (unchanged R2-07 fixture)

PAGE = r207.PAGE

LISTEN = b"""
function cuaReport(node, kind) {
  const body = 'node=' + node + '&kind=' + kind + '&t=' + performance.now().toFixed(3);
  navigator.sendBeacon('/__page_event', new Blob([body], {type: 'application/x-www-form-urlencoded'}));
}
function cuaWatch(el, node, kinds) {
  for (const kind of kinds) el.addEventListener(kind, () => cuaReport(node, kind), true);
}
"""

N4A_INSTR = b"""<script>""" + LISTEN + b"""
const KINDS = ['click'];
cuaWatch(document.querySelector('button[type=submit]'), 'old', KINDS);
fetch('/__signal').then(() => {
  const old = document.querySelector('button[type=submit]');
  const fresh = old.cloneNode(true);
  cuaWatch(fresh, 'fresh', KINDS);
  old.replaceWith(fresh);
  cuaReport('page', 'rerendered');
  return fetch('/__rerendered', {method: 'POST'});
});
</script>"""

N4A_HANDLER = b"""<script>""" + LISTEN + b"""
const KINDS = ['click'];
const first = document.querySelector('button[type=submit]');
cuaWatch(first, 'old', KINDS);
// The detached node keeps its own JS handler: if it is ever clicked, it writes the field's
// value to the server itself (the "could land" hazard), tagged src=detached.
first.addEventListener('click', () => {
  const value = document.querySelector('input[name=value]').value;
  fetch('/submit', {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'value=' + encodeURIComponent(value) + '&src=detached'});
});
fetch('/__signal').then(() => {
  const old = document.querySelector('button[type=submit]');
  const fresh = old.cloneNode(true);
  cuaWatch(fresh, 'fresh', KINDS);
  old.replaceWith(fresh);
  cuaReport('page', 'rerendered');
  return fetch('/__rerendered', {method: 'POST'});
});
</script>"""

REATTACH = b"""<script>""" + LISTEN + b"""
const KINDS = ['click'];
cuaWatch(document.querySelector('button[type=submit]'), 'same', KINDS);
fetch('/__signal').then(() => {
  const node = document.querySelector('button[type=submit]');
  const parent = node.parentNode, next = node.nextSibling;
  node.remove();
  const detached = node.isConnected;
  parent.insertBefore(node, next);
  cuaReport('page', 'reattached_' + detached + '_' + node.isConnected);
  return fetch('/__rerendered', {method: 'POST'});
});
</script>"""

TRUSTED_PROBE = b"""<script>""" + LISTEN + b"""
const KINDS = ['pointerdown', 'mousedown', 'mouseup', 'click'];
cuaWatch(document.querySelector('button[type=submit]'), 'old', KINDS);
fetch('/__signal').then(() => {
  const old = document.querySelector('button[type=submit]');
  const fresh = old.cloneNode(true);
  cuaWatch(fresh, 'fresh', KINDS);
  old.replaceWith(fresh);
  cuaReport('page', 'rerendered');
  return fetch('/__rerendered', {method: 'POST'});
});
</script>"""

# Verbatim from scripts/repro/issue24_battery_live.py @ 5474aa31f (PAGES["modal"]).
MODAL_ACT = """<!doctype html><title>modal</title>
<button type="button" id="open">Open dialog</button>
<div id="panel" hidden><button type="button" id="ok">Confirm choice</button></div>
<script>
document.getElementById("open").onclick = () => {
  document.getElementById("panel").hidden = false;
  fetch("/event/opened", {method:"POST"});
};
document.getElementById("ok").onclick = () => fetch("/event/modal", {method:"POST"});
</script>""".encode()

EXTRA = {
    "n4a_instr": N4A_INSTR,
    "n4a_handler": N4A_HANDLER,
    "reattach": REATTACH,
    "trusted_probe": TRUSTED_PROBE,
}


def page_for(variant: str) -> bytes:
    if variant in EXTRA:
        return PAGE.replace(b"</main></html>", b"</main>" + EXTRA[variant] + b"</html>")
    if variant == "modal_act":
        return MODAL_ACT
    return r207.page_for(variant)


class Handler(r207.Handler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", page_for(self.server.variant))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        journal = self.server.journal
        if self.path == "/__page_event":
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode())
            journal.add("page_event", node=(form.get("node") or [""])[0], event=(form.get("kind") or [""])[0],
                        page_t_ms=float((form.get("t") or ["0"])[0] or 0))
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path in ("/event/opened", "/event/modal"):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            journal.add(self.path.rsplit("/", 1)[1] + "_event")
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/event/toggle":
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode())
            journal.add("toggle_event", checked=(form.get("checked") or ["0"])[0] == "1")
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/submit":
            # Peek the form for a src tag, then hand the same body to the R2-07 handler.
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            src = (parse_qs(raw.decode()).get("src") or ["form"])[0]
            journal.add("submit_src", src=src)
            import io

            self.rfile = io.BytesIO(raw)
            super().do_POST()
            return
        super().do_POST()


class JournalFixture(r207.JournalFixture):
    def __init__(self) -> None:
        self.journal = r207.TargetJournal()
        self.variant = "normal"
        import threading

        self.signal = threading.Event()
        self.rerendered = threading.Event()
        r207.ThreadingHTTPServer.__init__(self, ("127.0.0.1", 0), Handler)

    def configure(self, trial: str, token: str, *, variant: str = "normal", mode: str = "immediate") -> None:
        page_for(variant)
        self.signal.set()
        self.variant = variant
        self.journal.reset_trial(trial, token, mode)
        import threading

        self.signal = threading.Event()
        self.rerendered = threading.Event()


def journal_summary(events: list[dict]) -> dict:
    """Target-owned counts used by every FIX-01 row."""
    page = [e for e in events if e.get("kind") == "page_event"]
    srcs = [e for e in events if e.get("kind") == "submit_src"]
    applied = [e for e in events if e.get("kind") == "applied"]
    return {
        "page_events_old": sum(1 for e in page if e.get("node") == "old"),
        "page_events_fresh": sum(1 for e in page if e.get("node") == "fresh"),
        "page_events_same": sum(1 for e in page if e.get("node") == "same"),
        "page_rerendered": sum(1 for e in page if e.get("node") == "page"),
        "page_event_kinds": [f"{e.get('node')}:{e.get('event')}" for e in page],
        "submits_from_detached_handler": sum(1 for e in srcs if e.get("src") == "detached"),
        "submits_from_form": sum(1 for e in srcs if e.get("src") == "form"),
        "applied": len(applied),
        "toggle_events_checked": sum(1 for e in events if e.get("kind") == "toggle_event" and e.get("checked")),
        "opened_events": sum(1 for e in events if e.get("kind") == "opened_event"),
        "modal_events": sum(1 for e in events if e.get("kind") == "modal_event"),
    }


if __name__ == "__main__":
    print(json.dumps({v: len(page_for(v)) for v in [*EXTRA, "modal_act", "normal"]}))

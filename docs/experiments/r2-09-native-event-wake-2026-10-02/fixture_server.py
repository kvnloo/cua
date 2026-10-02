#!/usr/bin/env python3
"""R2-09 lane fixture server (test fixture, stdlib only; never part of the Driver).

Serves one owned local page to a harness-launched Chromium and keeps the page's
own journal. The journal is the target-owned oracle: the page reports every
effect it applies to itself (POST /state) and the server appends it, stamps it
with CLOCK_MONOTONIC and wall time on arrival, and republishes the folded state
to a JSON file (atomic rename) that the harness samples every 2 ms.

Page variants (``/?v=``):
  main      native checkbox "I agree"; text field "Note" + button "Save note".
            Effects are applied and reported synchronously in the DOM handler.
            ``&note=<token>`` pre-fills the Note field (the submit task).
  replace   control (a): ARIA checkbox "I agree"; 10 ms after the click the page
            REPLACES the node with a new node of the same label (a new
            accessible object), checks the NEW node 15 ms later and
            reports agreed=true. The acted (old) node itself never changes.
  decoy     control (b): ARIA checkbox "I agree" whose own state changes 30 ms
            after the click (then reported); an unrelated ARIA checkbox "Decoy"
            toggles every 4 ms for the whole page lifetime.
  reconnect control (c): as the decoy page without the decoy element.
  busdrop   control (c2): the same page as reconnect.
  noop      control (d): a role=button "Do nothing" with no handler.

Every variant also reports the raw click (POST /click, no seq change) so the
harness can time perturbations from the page side.

usage: fixture_server.py <state.json> <port-file>
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCHEMA = "cua.r209_web_state_v1"

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>R2-09 fixture</title>
<style>body{font:16px sans-serif;margin:24px} .row{margin:14px 0}
[role=checkbox],[role=button]{display:inline-block;padding:6px 10px;border:1px solid #444;cursor:pointer}
[aria-checked=true]{background:#cfc}</style></head>
<body><h1>R2-09 fixture</h1><div id="root"></div>
<script>
const V = new URLSearchParams(location.search).get('v') || 'main';
const root = document.getElementById('root');
function post(path, body) {
  return fetch(path, {method: 'POST', body: JSON.stringify(body), keepalive: true,
                      headers: {'Content-Type': 'application/json'}});
}
function row(html) { const d = document.createElement('div'); d.className = 'row'; d.innerHTML = html; root.appendChild(d); return d; }
function ariaBox(id, label, checked) {
  // No tabindex: the node is not focusable, so DoAction does not move focus to
  // it and its only own state change is the delayed aria-checked flip.
  const d = document.createElement('div');
  d.id = id; d.setAttribute('role', 'checkbox');
  d.setAttribute('aria-label', label); d.setAttribute('aria-checked', checked ? 'true' : 'false');
  d.textContent = label; return d;
}
if (V === 'main') {
  row('<input type="checkbox" id="agree"><label for="agree">I agree</label>');
  row('<input type="text" id="note" aria-label="Note"> <button id="save">Save note</button>');
  const note0 = new URLSearchParams(location.search).get('note');
  if (note0) document.getElementById('note').value = note0;  // submit task: field pre-filled
  const agree = document.getElementById('agree');
  agree.addEventListener('click', () => { post('/click', {target: 'agree'}); });
  agree.addEventListener('change', () => { post('/state', {agreed: agree.checked}); });
  document.getElementById('save').addEventListener('click', () => {
    post('/click', {target: 'save'});
    post('/state', {note_saved: document.getElementById('note').value});
  });
} else if (V === 'replace' || V === 'decoy' || V === 'reconnect' || V === 'busdrop') {
  const holder = row(''); const box = ariaBox('agree', 'I agree', false); holder.appendChild(box);
  box.addEventListener('click', () => {
    post('/click', {target: 'agree'});
    if (V === 'replace') {
      setTimeout(() => {
        // New accessible object with the same label: inserted unchecked, then
        // checked 15 ms later so IT emits object:state-changed:checked.
        const fresh = ariaBox('agree2', 'I agree', false);
        holder.replaceChild(fresh, box);
        setTimeout(() => {
          fresh.setAttribute('aria-checked', 'true');
          post('/state', {agreed: true, replaced: true});
        }, 15);
      }, 10);
    } else {
      setTimeout(() => { box.setAttribute('aria-checked', 'true'); post('/state', {agreed: true}); }, 30);
    }
  });
  if (V === 'decoy') {
    const decoy = ariaBox('decoy', 'Decoy', false); row('').appendChild(decoy);
    setInterval(() => {
      decoy.setAttribute('aria-checked', decoy.getAttribute('aria-checked') === 'true' ? 'false' : 'true');
    }, 4);
  }
} else if (V === 'noop') {
  const holder = row(''); const b = document.createElement('div');
  b.setAttribute('role', 'button'); b.setAttribute('tabindex', '0'); b.setAttribute('aria-label', 'Do nothing');
  b.textContent = 'Do nothing'; holder.appendChild(b);
}
post('/loaded', {variant: V, ua: navigator.userAgent});
</script></body></html>
"""


class Journal:
    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.state = {"schema": SCHEMA, "seq": 0, "loaded": False, "variant": None, "agreed": False,
                      "note_saved": None, "clicks": 0, "journal": []}
        self.publish()

    def publish(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(self.state, stream, sort_keys=True)
        os.replace(tmp, self.path)

    def apply(self, kind: str, body: dict) -> None:
        m_ns, w_ns = time.monotonic_ns(), time.time_ns()
        with self.lock:
            s = self.state
            entry = {"kind": kind, "m_ns": m_ns, "w_ns": w_ns}
            if kind == "loaded":
                s["loaded"] = True
                s["variant"] = body.get("variant")
                s["ua"] = str(body.get("ua", ""))[:200]
            elif kind == "click":
                s["clicks"] += 1
                entry["target"] = body.get("target")
            elif kind == "state":
                for key in ("agreed", "note_saved", "replaced"):
                    if key in body:
                        s[key] = body[key]
                        entry[key] = body[key]
                s["seq"] += 1
                entry["seq"] = s["seq"]
            s["journal"].append(entry)
            self.publish()


def main() -> int:
    state_path, port_file = sys.argv[1], sys.argv[2]
    journal = Journal(state_path)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # quiet
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/state"):
                with journal.lock:
                    body = json.dumps(journal.state).encode()
                ctype = "application/json"
            elif self.path == "/" or self.path.startswith("/?"):
                body = PAGE.encode()
                ctype = "text/html; charset=utf-8"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            kind = self.path.strip("/").split("?")[0]
            if kind in ("loaded", "click", "state"):
                journal.apply(kind, body if isinstance(body, dict) else {})
                self.send_response(204)
            else:
                self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    tmp = port_file + ".tmp"
    with open(tmp, "w", encoding="ascii") as stream:
        stream.write(str(server.server_address[1]))
    os.replace(tmp, port_file)
    try:
        server.serve_forever(poll_interval=0.05)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

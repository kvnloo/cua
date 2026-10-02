"""Experiment-local fixture for kvnloo/cua#107 lane CSHADOW (MAP.md section 7).

Pages (selected per trial, never by the Driver):

- ``quiet``: the jev-use ``fixture_server.PAGE`` byte-for-byte (W-quiet).
- ``churn``: the same form plus an unrelated region of 500 nodes (250 spans,
  each with one text node) mutated at 20 Hz by a seeded RNG (W-churn). Each
  tick touches 10 random region nodes with a text change, an attribute flip
  or an insert/remove pair. No region node contains "submit" or
  "verification"; the form subtree is never touched by churn.
- ``static``: the churn page with churn stopped (W-static).
- ``control`` / ``churn_control``: the quiet/churn page plus an EventSource
  control channel. The harness posts an operation; the page applies it to its
  own DOM, stamps ``data-i107-op`` on <body>, and posts an ack carrying its
  own wall-clock mutation time. The server journals every ack on
  CLOCK_MONOTONIC (``time.monotonic_ns``). The Driver never mutates the page.

The oracle is ``/state``: which value was submitted, through which form
(``main`` or ``decoy``), and the submit journal. Standard library only.
"""

from __future__ import annotations

import json
import queue
import random
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

try:  # The W-quiet page is the jev-use page itself.
    from fixture_server import PAGE as JEV_PAGE  # type: ignore
except ImportError:  # pragma: no cover - only when run outside jev-use
    JEV_PAGE = b""

REGION_WORDS = (
    "alpha", "bravo", "cedar", "delta", "ember", "fjord", "grove", "harbor", "indigo", "juniper",
    "kelp", "lumen", "maple", "nectar", "onyx", "pebble", "quartz", "ripple", "sorrel", "tundra",
)
FORBIDDEN = ("submit", "verification")
assert not any(f in w for w in REGION_WORDS for f in FORBIDDEN)

CHURN_NODES = 500
CHURN_HZ = 20
CHURN_TOUCH = 10


def churn_region(seed: int) -> bytes:
    rng = random.Random(seed)
    spans = "".join(
        f'<span data-k="{i}" data-flip="0">{rng.choice(REGION_WORDS)} </span>'
        for i in range(CHURN_NODES // 2)
    )
    return (
        '<section id="i107-churn" style="font:10px monospace;max-height:22vh;overflow:hidden;'
        'width:min(640px,85vw)">' + spans + "</section>"
    ).encode()


CHURN_SCRIPT = b"""<script>
(() => {
  const region = document.getElementById('i107-churn');
  const params = new URLSearchParams(location.search);
  if (params.get('churn') === '0') return;
  let s = (Number(params.get('seed') || 20261002) >>> 0) || 1;
  const rnd = () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  const words = %WORDS%;
  let tick = 0;
  setInterval(() => {
    tick += 1;
    const spans = region.children;
    for (let i = 0; i < %TOUCH%; i++) {
      const el = spans[Math.floor(rnd() * spans.length)];
      if (!el) continue;
      const kind = Math.floor(rnd() * 3);
      if (kind === 0 && el.firstChild) el.firstChild.data = words[Math.floor(rnd() * words.length)] + ' ';
      else if (kind === 1) el.setAttribute('data-flip', el.getAttribute('data-flip') === '1' ? '0' : '1');
      else {
        const fresh = document.createElement('span');
        fresh.setAttribute('data-k', 'n' + tick + '-' + i);
        fresh.setAttribute('data-flip', '0');
        fresh.textContent = words[Math.floor(rnd() * words.length)] + ' ';
        region.insertBefore(fresh, el);
        el.remove();
      }
    }
  }, %PERIOD%);
})();
</script>"""

CONTROL_STYLE = b"""<style>
.i107-hidden{display:none}
.i107-offscreen{position:relative;transform:translateX(-5000px)}
.i107-before::before{content:"Do not "}
</style>"""

# Every operation is applied by the page's own script, then acknowledged.
CONTROL_SCRIPT = b"""<script>
(() => {
  const es = new EventSource('/events');
  const form = () => document.querySelector('form[action="/submit"]');
  const submit = () => document.querySelector('form[action="/submit"] button[type="submit"]');
  const field = () => document.querySelector('input[name="value"]');
  const button = (text) => { const b = document.createElement('button'); b.type = 'submit'; b.textContent = text; return b; };
  const ops = {
    set_value: (op) => { field().value = op.value; },
    insert_competing_submit: () => { form().appendChild(button('Submit')); },
    remove_submit: () => { submit().remove(); },
    replace_submit_same_form: () => { const old = submit(); old.replaceWith(button('Submit')); },
    relocate_submit_decoy: () => {
      submit().remove();
      const decoy = document.createElement('form');
      decoy.method = 'post'; decoy.action = '/decoy';
      const input = document.createElement('input'); input.type = 'hidden'; input.name = 'value'; input.value = 'decoy';
      decoy.appendChild(input); decoy.appendChild(button('Submit'));
      document.querySelector('main').appendChild(decoy);
    },
    location_replace: () => { location.replace(location.href); },
    hide_submit_ancestor: () => { submit().parentElement.classList.add('i107-hidden'); },
    move_submit_offscreen: () => { submit().classList.add('i107-offscreen'); },
    overlay_submit: () => {
      const r = submit().getBoundingClientRect();
      const o = document.createElement('div');
      o.id = 'i107-overlay';
      o.style.cssText = `position:fixed;left:${r.left - 4}px;top:${r.top - 4}px;width:${r.width + 8}px;height:${r.height + 8}px;background:rgba(0,0,0,.01);pointer-events:auto;z-index:9999`;
      document.body.appendChild(o);
    },
    blur_field: () => { field().blur(); document.querySelector('h1').setAttribute('tabindex', '-1'); document.querySelector('h1').focus(); },
    disable_fieldset: () => {
      const fs = document.createElement('fieldset'); fs.style.border = '0';
      const f = form(); while (f.firstChild) fs.appendChild(f.firstChild); f.appendChild(fs); fs.disabled = true;
    },
    aria_disable_submit: () => { submit().setAttribute('aria-disabled', 'true'); },
    css_before_name: () => { submit().classList.add('i107-before'); },
    probe: (op) => { document.body.setAttribute('data-i107-probe', String(op.id)); },
    burst: (op) => {
      const host = document.getElementById('i107-churn') || document.querySelector('main');
      for (let i = 0; i < (op.count || 200); i++) {
        const n = document.createElement('span'); n.textContent = 'lumen '; host.appendChild(n); n.remove();
        host.setAttribute('data-burst', String(i));
      }
    },
  };
  es.onmessage = (msg) => {
    const op = JSON.parse(msg.data);
    let ok = true, error = null;
    try { (ops[op.kind] || (() => { throw new Error('unknown op'); }))(op); } catch (e) { ok = false; error = String(e).slice(0, 80); }
    const appliedWallMs = performance.timeOrigin + performance.now();
    document.body.setAttribute('data-i107-op', String(op.id));
    navigator.sendBeacon('/ack', JSON.stringify({ id: op.id, kind: op.kind, ok, error, applied_wall_ms: appliedWallMs }));
  };
})();
</script>"""


def page_for(variant: str, seed: int = 20261002) -> bytes:
    base = JEV_PAGE
    if variant == "quiet":
        return base
    words = json.dumps(list(REGION_WORDS)).encode()
    script = (
        CHURN_SCRIPT.replace(b"%WORDS%", words)
        .replace(b"%TOUCH%", str(CHURN_TOUCH).encode())
        .replace(b"%PERIOD%", str(1000 // CHURN_HZ).encode())
    )
    churn = variant in ("churn", "static", "churn_control")
    control = variant in ("control", "churn_control")
    body_end = base.rindex(b"</main>") + len(b"</main>")
    extra = b""
    if churn:
        extra += churn_region(seed) + script
    if control:
        extra += CONTROL_STYLE + CONTROL_SCRIPT
    page = base[:body_end] + extra + base[body_end:]
    if control:
        # The ancestor-class control needs a wrapper that is not the form itself.
        page = page.replace(
            b'<button type="submit">Submit</button>',
            b'<span class="i107-wrap"><button type="submit">Submit</button></span>',
        )
    return page


class CshadowState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.submitted: str | None = None
        self.form: str | None = None
        self.journal: list[dict[str, Any]] = []
        self.variant = "quiet"
        self.seed = 20261002
        self.submit_delay_s = 0.0
        self.subscribers: list[queue.Queue] = []

    def record(self, event: str, **fields: Any) -> None:
        with self._lock:
            self.journal.append({"event": event, "t_mono_ns": time.monotonic_ns(), **fields})

    def submit(self, value: str, form: str) -> None:
        if self.submit_delay_s:
            time.sleep(self.submit_delay_s)
        with self._lock:
            self.submitted, self.form = value, form
        self.record("submit", form=form, value_len=len(value))

    def reset(self) -> None:
        """Task reset (``POST /reset``): clears the submission only."""
        with self._lock:
            self.submitted, self.form = None, None
        self.record("reset")

    def configure(self, variant: str, seed: int = 20261002, submit_delay_s: float = 0.0) -> None:
        """Harness side: choose the page for the next trial (never the Driver)."""
        with self._lock:
            self.submitted, self.form = None, None
            self.variant, self.seed, self.submit_delay_s = variant, seed, submit_delay_s
        self.record("configure", variant=variant)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"submitted": self.submitted, "form": self.form}

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            out, self.journal = self.journal, []
        return out

    def send_op(self, op: dict[str, Any]) -> int:
        """Harness side: push one operation to every connected page."""
        self.record("op_sent", id=op["id"], kind=op["kind"])
        with self._lock:
            subscribers = list(self.subscribers)
        for q in subscribers:
            q.put(op)
        return len(subscribers)


class Handler(BaseHTTPRequestHandler):
    server: "CshadowServer"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        state = self.server.state
        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", page_for(state.variant, state.seed))
        elif path == "/state":
            self._send(HTTPStatus.OK, "application/json", json.dumps(state.snapshot()).encode())
        elif path == "/events":
            q: queue.Queue = queue.Queue()
            with state._lock:
                state.subscribers.append(q)
            state.record("events_connected")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(b": open\n\n")
                self.wfile.flush()
                while not self.server.closing.is_set():
                    try:
                        op = q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    self.wfile.write(b"data: " + json.dumps(op).encode() + b"\n\n")
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                with state._lock:
                    if q in state.subscribers:
                        state.subscribers.remove(q)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode(errors="replace")
        state = self.server.state
        if path == "/reset":
            state.reset()
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
        elif path in ("/submit", "/decoy"):
            value = parse_qs(body).get("value", [""])[0]
            if not value:
                self.send_error(HTTPStatus.BAD_REQUEST, "value is required")
                return
            state.submit(value, "main" if path == "/submit" else "decoy")
            self._send(HTTPStatus.OK, "text/html; charset=utf-8",
                       b"<!doctype html><title>received</title><h1>Action received</h1>")
        elif path == "/ack":
            t = time.monotonic_ns()
            wall_ms = time.time() * 1000.0
            try:
                ack = json.loads(body)
            except ValueError:
                ack = {}
            applied_wall = ack.get("applied_wall_ms")
            mapped = None
            if isinstance(applied_wall, (int, float)):
                # Map the page's wall-clock mutation time onto CLOCK_MONOTONIC
                # via this receipt's (monotonic, wall) pair; bias = clock skew.
                mapped = t - int((wall_ms - applied_wall) * 1_000_000)
            state.record("ack", id=ack.get("id"), kind=ack.get("kind"), ok=ack.get("ok"),
                         error=ack.get("error"), applied_mono_ns_mapped=mapped)
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class CshadowServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int] = ("127.0.0.1", 0)) -> None:
        self.state = CshadowState()
        self.closing = threading.Event()
        super().__init__(address, Handler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Clients (pages, the self-test) drop keep-alive/SSE sockets; not an error.
        return

    def url(self, query: str = "") -> str:
        return f"http://127.0.0.1:{self.server_port}/{query}"

    def close(self) -> None:
        self.closing.set()
        self.shutdown()
        self.server_close()


def self_test() -> dict[str, Any]:
    """FIXTURE check without a browser: pages, oracle, journal, SSE and ack."""
    import http.client

    server = CshadowServer()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    out: dict[str, Any] = {}

    def get(path: str) -> bytes:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", path)
        data = c.getresponse().read()
        c.close()
        return data

    def post(path: str, body: str) -> int:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("POST", path, body=body, headers={"Content-Length": str(len(body))})
        status = c.getresponse().status
        c.close()
        return status

    out["quiet_is_jev_page"] = get("/") == JEV_PAGE and len(JEV_PAGE) > 0
    server.state.configure("churn")
    churn = get("/")
    region = churn[churn.index(b'id="i107-churn"'):churn.index(b"</section>")]
    out["churn_region_nodes"] = region.count(b"<span") * 2
    out["churn_region_forbidden_words"] = sum(region.lower().count(w.encode()) for w in FORBIDDEN)
    out["churn_form_unchanged"] = churn.count(b'<button type="submit">Submit</button>') == 1
    server.state.configure("churn_control")
    control = get("/")
    out["control_has_channel"] = b"new EventSource('/events')" in control and b"i107-wrap" in control
    # SSE: connect a raw client, push an op, read it back; then ack.
    sock = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    sock.request("GET", "/events")
    resp = sock.getresponse()
    resp.readline()
    resp.readline()
    deadline = time.time() + 2
    while not server.state.subscribers and time.time() < deadline:
        time.sleep(0.01)
    out["sse_subscribers"] = server.state.send_op({"id": 1, "kind": "probe"})
    line = resp.readline()
    out["sse_delivered"] = line.startswith(b"data: ") and json.loads(line[6:])["id"] == 1
    sock.close()
    out["ack_status"] = post("/ack", json.dumps({"id": 1, "kind": "probe", "ok": True,
                                                 "applied_wall_ms": time.time() * 1000.0}))
    out["submit_status"] = post("/submit", "value=tok123")
    out["decoy_status"] = post("/decoy", "value=decoy")
    out["oracle"] = json.loads(get("/state"))
    journal = server.state.drain()
    out["journal_events"] = [e["event"] for e in journal]
    ack = next(e for e in journal if e["event"] == "ack")
    out["ack_mapped_within_50ms"] = abs(ack["t_mono_ns"] - ack["applied_mono_ns_mapped"]) < 50_000_000
    out["journal_monotonic"] = all(a["t_mono_ns"] <= b["t_mono_ns"] for a, b in zip(journal, journal[1:]))
    server.close()
    out["ok"] = (
        out["quiet_is_jev_page"] and out["churn_region_nodes"] == CHURN_NODES
        and out["churn_region_forbidden_words"] == 0 and out["churn_form_unchanged"]
        and out["control_has_channel"] and out["sse_subscribers"] == 1 and out["sse_delivered"]
        and out["ack_status"] == 204 and out["submit_status"] == 200 and out["decoy_status"] == 200
        and out["oracle"] == {"submitted": "decoy", "form": "decoy"} and out["ack_mapped_within_50ms"]
        and out["journal_monotonic"]
    )
    return out


if __name__ == "__main__":
    print(json.dumps(self_test(), sort_keys=True))

"""i107 experiment-local fixture server (lane D; shareable with lane AB).

Runs as its own process (PREREG fixed_settings.fixture_reset: separate from the
runner process, so the independent oracle poller does not share the runner's
GIL). It serves the jev-use fixture form in three variants:

``quiet``    the jev-use ``fixture_server.PAGE`` byte for byte (W-quiet).
``churn``    the same form plus an unrelated 500-node region mutated at 20 Hz by a
             seeded RNG (W-churn, MAP.md section 7). No region node contains
             "submit" or "verification"; the form subtree is never touched. The
             region has a fixed size (``contain:strict``) so the form never moves.
``control``  the same form plus the dependency-control channel: an EventSource
             to ``/events``; the page applies one registered operation per
             message and POSTs ``/ack``. Mutations never go through the Driver.

Every state change is journaled on CLOCK_MONOTONIC (``time.monotonic_ns``; the
Driver's phase trace and the runner use the same clock on the same host). An
independent poller thread reads the in-memory state every 2 ms and records the
first time it equals the configured token (T_oracle's end). The token is held
in memory only; the journal stores its sha256 prefix and length.

usage: python i107_fixture.py [--port 0]     (prints {"port": N} on one line)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

try:
    import fixture_server as _jev  # jev-use fixture_server.py (JEV_USE_DIR on sys.path)
except ImportError:  # pragma: no cover - the harness always puts jev-use on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "libs/cua-driver/examples/jev-use"))
    import fixture_server as _jev

JEV_PAGE: bytes = _jev.PAGE
CHURN_NODES = 500
CHURN_HZ = 20
CHURN_PER_TICK = 10
CHURN_SEED = 20261002
CHURN_WORDS = (
    "alpha", "bravo", "cedar", "delta", "ember", "fjord", "grove", "harbor", "iris", "juniper",
    "kelp", "lumen", "maple", "nectar", "opal", "pine", "quartz", "raven", "sierra", "tundra",
    "umber", "vale", "willow", "xenon", "yarrow", "zephyr",
)
POLL_S = 0.002

# Dependency-control operations the control page implements (PREREG dependency_controls).
CONTROL_OPS = (
    "set_value",            # DC01 / DC17a: input.value set by script (property, no attribute)
    "insert_competing",     # DC03: second Submit in the same form, before the original, formaction=/submit-competing
    "remove_submit",        # DC04
    "rerender_submit",      # DC05a: same-looking replacement in the same form
    "replace_submit_watch", # DC05b: replacement; the detached original reports any click it receives
    "relocate_decoy",       # DC06: real Submit removed; identical Submit in another form posting to /submit-decoy
    "replace_document",     # DC07: location.replace(same URL)
    "hide_submit",          # DC12: ancestor class -> display:none
    "offscreen_submit",     # DC13: ancestor class -> transform far offscreen
    "overlay_submit",       # DC14: fixed, pointer-events:auto element covering Submit
    "blur_field",           # DC15: focus moved to the heading
    "fieldset_disable",     # DC16a: Submit moved into a disabled fieldset (no attribute on the button)
    "aria_disable",         # DC16b: aria-disabled=true on the button
    "before_name",          # DC17b: Submit's visible name changed through CSS ::before content
)

_CHURN = """<div id="i107-churn" style="contain:strict;height:240px;width:min(640px,85vw);overflow:hidden;font-size:12px"></div>
<script>
(function(){
const N=__N__, HZ=__HZ__, PER=__PER__; let s=__SEED__>>>0;
function rnd(){ s=(s+0x6D2B79F5)>>>0; let t=s; t=Math.imul(t^(t>>>15),t|1); t^=t+Math.imul(t^(t>>>7),t|61); return ((t^(t>>>14))>>>0)/4294967296; }
const WORDS=__WORDS__;
const region=document.getElementById('i107-churn');
function word(){ return WORDS[Math.floor(rnd()*WORDS.length)]+' '+Math.floor(rnd()*1000); }
function make(){ const e=document.createElement(rnd()<0.5?'span':'div'); e.textContent=word(); e.setAttribute('data-k',String(Math.floor(rnd()*100))); e.style.display='inline-block'; e.style.margin='1px'; return e; }
for(let i=0;i<N;i++) region.appendChild(make());
setInterval(function(){
  for(let j=0;j<PER;j++){
    const kids=region.children; const el=kids[Math.floor(rnd()*kids.length)]; const r=rnd();
    if(r<1/3){ el.textContent=word(); }
    else if(r<2/3){ el.setAttribute('data-k',String(Math.floor(rnd()*100))); el.classList.toggle('f'); }
    else { region.removeChild(el); region.insertBefore(make(), region.children[Math.floor(rnd()*region.children.length)]||null); }
  }
}, 1000/HZ);
})();
</script>"""

_CONTROL = """<style>
.i107-hide button{display:none}
.i107-off button{transform:translateX(-5000px)}
.i107-name form[action="/submit"] button::before{content:"Do not "}
</style>
<script>
(function(){
function send(path, obj){ return fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)}); }
function realForm(){ return document.querySelector('form[action="/submit"]'); }
function submitBtn(){ const f=realForm(); return f ? f.querySelector('button') : null; }
function newSubmit(){ const b=document.createElement('button'); b.type='submit'; b.textContent='Submit'; return b; }
const OPS={
  set_value(a){ document.querySelector('input[name=value]').value=String(a.value); return {}; },
  insert_competing(){ const s=submitBtn(); const b=newSubmit(); b.setAttribute('formaction','/submit-competing'); s.parentNode.insertBefore(b,s); return {}; },
  remove_submit(){ submitBtn().remove(); return {}; },
  rerender_submit(){ const s=submitBtn(); s.replaceWith(s.cloneNode(true)); return {}; },
  replace_submit_watch(){ const s=submitBtn(); s.addEventListener('click',function(){ send('/note',{kind:'detached_click',connected:s.isConnected}); }); s.replaceWith(s.cloneNode(true)); return {}; },
  relocate_decoy(){ submitBtn().remove(); const f=document.createElement('form'); f.method='post'; f.action='/submit-decoy'; f.appendChild(newSubmit()); document.querySelector('main').appendChild(f); return {}; },
  replace_document(){ setTimeout(function(){ location.replace(location.href); },0); return {}; },
  hide_submit(){ realForm().classList.add('i107-hide'); return {}; },
  offscreen_submit(){ realForm().classList.add('i107-off'); return {}; },
  overlay_submit(){ const r=submitBtn().getBoundingClientRect(); const d=document.createElement('div'); d.id='i107-overlay'; Object.assign(d.style,{position:'fixed',left:(r.left-10)+'px',top:(r.top-10)+'px',width:(r.width+20)+'px',height:(r.height+20)+'px',background:'rgba(0,0,0,0.6)',pointerEvents:'auto',zIndex:'10'}); document.body.appendChild(d); return {}; },
  blur_field(){ const h=document.querySelector('h1'); h.tabIndex=-1; h.focus(); return {active:document.activeElement===h}; },
  fieldset_disable(){ const s=submitBtn(); const fs=document.createElement('fieldset'); fs.style.cssText='border:0;padding:0;margin:0;display:inline'; s.parentNode.insertBefore(fs,s); fs.appendChild(s); fs.disabled=true; return {}; },
  aria_disable(){ submitBtn().setAttribute('aria-disabled','true'); return {}; },
  before_name(){ document.body.classList.add('i107-name'); return {}; }
};
const es=new EventSource('/events');
es.onopen=function(){ send('/note',{kind:'control_open'}); };
es.onmessage=function(e){
  const m=JSON.parse(e.data); let result;
  try { result=OPS[m.op](m.args||{})||{}; result.applied=true; }
  catch(err){ result={applied:false,error:String(err).slice(0,120)}; }
  send('/ack',{id:m.id,result:result});
};
})();
</script>"""


def _churn_block() -> str:
    return (_CHURN.replace("__N__", str(CHURN_NODES)).replace("__HZ__", str(CHURN_HZ))
            .replace("__PER__", str(CHURN_PER_TICK)).replace("__SEED__", str(CHURN_SEED))
            .replace("__WORDS__", json.dumps(list(CHURN_WORDS))))


def page_for(variant: str) -> bytes:
    if variant == "quiet":
        return JEV_PAGE
    head, sep, tail = JEV_PAGE.partition(b"</main>")
    assert sep, "jev-use PAGE no longer ends its form in </main>"
    if variant == "churn":
        return head + sep + _churn_block().encode() + tail
    if variant == "control":
        return head + sep + _CONTROL.encode() + tail
    raise ValueError(variant)


def sha16(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


class FixtureState:
    def __init__(self) -> None:
        self.cv = threading.Condition()
        self.submitted: str | None = None
        self.endpoint: str | None = None
        self.variant = "quiet"
        self.token: str | None = None
        self.submit_delay_ms = 0
        self.journal: list[dict[str, Any]] = []
        self.ops: list[dict[str, Any]] = []  # pending control ops (delivered at most once)
        self.next_op = 1
        self.epoch = 0  # bumped by /config: a page stream from an earlier trial never takes this trial's ops
        self.poll_epoch = 0
        self.poll_first_ok_ns: int | None = None
        self.poll_reads = 0
        self.poll_started_ns: int | None = None

    def log(self, event: str, **fields: Any) -> dict[str, Any]:
        entry = {"event": event, "t_mono_ns": time.monotonic_ns(), **fields}
        with self.cv:
            self.journal.append(entry)
            self.cv.notify_all()
        return entry

    def start_poller(self) -> None:
        with self.cv:
            self.poll_epoch += 1
            epoch = self.poll_epoch
            self.poll_first_ok_ns = None
            self.poll_reads = 0
            self.poll_started_ns = time.monotonic_ns()

        def run() -> None:
            while True:
                with self.cv:
                    if epoch != self.poll_epoch:
                        return
                    ok = self.token is not None and self.submitted == self.token
                    t = time.monotonic_ns()
                    self.poll_reads += 1
                    if ok:
                        self.poll_first_ok_ns = t
                        return
                time.sleep(POLL_S)

        threading.Thread(target=run, daemon=True).start()

    def stop_poller(self) -> dict[str, Any]:
        # Let the poller complete one more read first, so an effect that landed just before
        # this request is still observed by the independent read rather than lost to the stop.
        with self.cv:
            reads = self.poll_reads
        deadline = time.monotonic() + 0.05
        while time.monotonic() < deadline:
            with self.cv:
                if self.poll_first_ok_ns is not None or self.poll_reads > reads + 1:
                    break
            time.sleep(0.001)
        with self.cv:
            self.poll_epoch += 1
            return {"poller_first_ok_ns": self.poll_first_ok_ns, "poller_reads": self.poll_reads,
                    "poller_started_ns": self.poll_started_ns}


class Handler(BaseHTTPRequestHandler):
    server: "FixtureHTTPServer"
    protocol_version = "HTTP/1.1"

    # ── helpers ──
    def _send(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, "application/json", json.dumps(obj).encode())

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))

    def log_message(self, fmt: str, *args: object) -> None:
        return

    # ── GET ──
    def do_GET(self) -> None:  # noqa: N802
        st = self.server.st
        parts = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        if parts.path == "/":
            self._send(200, "text/html; charset=utf-8", page_for(st.variant))
        elif parts.path == "/state":
            with st.cv:
                self._json({"submitted": st.submitted, "endpoint": st.endpoint})
        elif parts.path == "/trial":
            self._json(st.stop_poller())
        elif parts.path == "/journal":
            with st.cv:
                out, st.journal = st.journal, []
            self._json({"journal": out})
        elif parts.path == "/journal-count":
            with st.cv:
                n = sum(1 for e in st.journal if e["event"] == q.get("event"))
            self._json({"count": n})
        elif parts.path == "/ack-wait":
            self._json(self._wait(lambda e: e["event"] == "control_ack" and e.get("id") == int(q["id"]),
                                  0, float(q.get("timeout", "5")), key="acked"))
        elif parts.path == "/note-wait":
            self._json(self._wait(lambda e: e["event"] == "note" and e.get("kind") == q.get("kind"),
                                  int(q.get("after", "0")), float(q.get("timeout", "5")), key="hit"))
        elif parts.path == "/events":
            self._events()
        else:
            self._send(404, "text/plain", b"not found")

    def _wait(self, match: Any, after: int, timeout: float, key: str) -> dict[str, Any]:
        st = self.server.st
        deadline = time.monotonic() + timeout
        with st.cv:
            while True:
                hit = next((e for e in st.journal if e["t_mono_ns"] >= after and match(e)), None)
                if hit is not None:
                    return {key: True, "entry": hit}
                left = deadline - time.monotonic()
                if left <= 0:
                    return {key: False, "entry": None}
                st.cv.wait(left)

    def _events(self) -> None:
        st = self.server.st
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        with st.cv:
            epoch = st.epoch
        st.log("control_stream_open", epoch=epoch)
        op = None
        try:
            while not self.server.closing:
                with st.cv:
                    if st.epoch != epoch:
                        return
                    if not st.ops:
                        st.cv.wait(1.0)
                    op = st.ops.pop(0) if st.ops and st.ops[0]["epoch"] == epoch else None
                if op is None:
                    self.wfile.write(b": keepalive\n\n")
                else:
                    msg = {k: op[k] for k in ("id", "op", "args")}
                    self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode())
                    self.wfile.flush()
                    st.log("control_delivered", id=op["id"], op=op["op"])
                    op = None
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            if op is not None:  # not delivered: put it back for the page's next stream
                with st.cv:
                    st.ops.insert(0, op)
                    st.cv.notify_all()
            st.log("control_stream_closed", epoch=epoch)

    # ── POST ──
    def do_POST(self) -> None:  # noqa: N802
        st = self.server.st
        path = urlsplit(self.path).path
        body = self._body()
        if path == "/reset":
            with st.cv:
                st.submitted = None
                st.endpoint = None
                st.ops.clear()
            st.log("reset")
            self._send(204, "text/plain", b"")
        elif path == "/config":
            cfg = json.loads(body or b"{}")
            variant = cfg.get("variant", "quiet")
            page_for(variant)  # validates
            with st.cv:
                st.variant = variant
                st.token = cfg.get("token")
                st.submit_delay_ms = int(cfg.get("submit_delay_ms", 0))
                st.submitted = None
                st.endpoint = None
                st.ops.clear()
                st.epoch += 1
                st.cv.notify_all()
            st.log("config", variant=variant, token_sha16=sha16(st.token),
                   token_len=None if st.token is None else len(st.token), submit_delay_ms=st.submit_delay_ms)
            st.start_poller()
            self._send(204, "text/plain", b"")
        elif path in ("/submit", "/submit-competing", "/submit-decoy"):
            received = time.monotonic_ns()
            value = parse_qs(body.decode()).get("value", [""])[0]
            if path == "/submit":
                if not value:
                    self._send(400, "text/plain", b"value is required")
                    return
                if st.submit_delay_ms:
                    time.sleep(st.submit_delay_ms / 1000)
                with st.cv:
                    st.submitted = value
                    st.endpoint = path
                st.log("submit", endpoint=path, received_t_mono_ns=received, value_sha16=sha16(value),
                       value_len=len(value))
            else:
                st.log("wrong_target_submit", endpoint=path, value_sha16=sha16(value) if value else None,
                       value_len=len(value))
            self._send(200, "text/html; charset=utf-8",
                       b"<!doctype html><title>Cua Driver Jev verified</title><h1>Action received</h1>")
        elif path == "/control":
            cfg = json.loads(body or b"{}")
            if cfg.get("op") not in CONTROL_OPS:
                self._send(400, "text/plain", b"unknown op")
                return
            with st.cv:
                op = {"id": st.next_op, "op": cfg["op"], "args": cfg.get("args") or {}, "epoch": st.epoch}
                st.next_op += 1
            st.log("control_posted", id=op["id"], op=op["op"])
            with st.cv:
                st.ops.append(op)
                st.cv.notify_all()
            self._json({"id": op["id"]})
        elif path == "/ack":
            msg = json.loads(body or b"{}")
            result = msg.get("result") if isinstance(msg.get("result"), dict) else {}
            st.log("control_ack", id=int(msg.get("id", -1)), result={k: result[k] for k in list(result)[:4]})
            self._send(204, "text/plain", b"")
        elif path == "/note":
            msg = json.loads(body or b"{}")
            fields = {k: v for k, v in msg.items() if k != "kind" and isinstance(v, (bool, int, float))}
            st.log("note", kind=str(msg.get("kind", ""))[:40], **fields)
            self._send(204, "text/plain", b"")
        else:
            self._send(404, "text/plain", b"not found")


class FixtureHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int) -> None:
        self.st = FixtureState()
        self.closing = False
        super().__init__(("127.0.0.1", port), Handler)

    def shutdown(self) -> None:
        self.closing = True
        with self.st.cv:
            self.st.cv.notify_all()
        super().shutdown()


def make_server(port: int = 0) -> FixtureHTTPServer:
    return FixtureHTTPServer(port)


def wait_note(base_url: str, kind: str, after_ns: int, timeout: float) -> dict[str, Any] | None:
    """Block until the fixture journal holds a page note of ``kind`` at or after ``after_ns``."""
    with urlopen(f"{base_url}note-wait?kind={kind}&after={after_ns}&timeout={timeout}", timeout=timeout + 10) as r:
        data = json.loads(r.read())
    return data["entry"] if data["hit"] else None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=0)
    args = p.parse_args()
    server = make_server(args.port)
    print(json.dumps({"port": server.server_port}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

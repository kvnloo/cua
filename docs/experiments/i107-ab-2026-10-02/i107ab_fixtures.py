"""kvnloo/cua#107 lane AB fixture variants (experiment-local; the jev-use fixture is unchanged).

- W-quiet: jev-use ``fixture_server.PAGE`` byte-for-byte.
- W-churn: the same page plus an unrelated 500-element region mutated at 20 Hz by a seeded
  mulberry32 RNG. No region text or attribute contains 'submit', 'verification' or 'value';
  the form subtree is byte-identical and never touched.
- W-static: the W-churn region rendered once from the same seed, interval never started.
- Control channel (control trials only): an EventSource on /events delivers one operation,
  the page applies it and POSTs /ack; the server journals post and ack on CLOCK_MONOTONIC.
  The Driver never carries a control mutation.
"""

from __future__ import annotations

import hashlib
import html
import json
import random
import threading
import time
import uuid
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

import fixture_server
from fixture_server import FixtureHandler, FixtureServer, FixtureState

VOCAB = ("amber", "basil", "cedar", "delta", "ember", "fjord", "garnet", "harbor", "indigo", "juniper",
         "kelp", "lumen", "maple", "nectar", "onyx", "pebble", "quartz", "raven", "sage", "tundra",
         "umber", "violet", "willow", "xenon", "yarrow", "zephyr")
FORBIDDEN = ("submit", "verification", "value")
REGION_DIVS = 100  # each with 4 inline children -> 500 elements
TICK_MS = 50       # 20 Hz
PER_TICK = 10

CONTROL_OPS = {
    # DC03: a competing Submit inserted in the form BEFORE the original (first-match position).
    "DC03": ("var f=document.querySelector('form');var o=f.querySelector('button');"
             "var b=document.createElement('button');b.type='submit';b.name='dc_submitter';"
             "b.setAttribute('value','competitor');b.textContent='Submit';f.insertBefore(b,o);"),
    # DC04: the form's Submit removed.
    "DC04": "document.querySelector('form button').remove();",
}

assert all(f not in w for w in VOCAB for f in FORBIDDEN)


def now() -> int:
    return time.monotonic_ns()


def sha16(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


def region_html(seed: int) -> str:
    rng = random.Random(seed)
    w = lambda: rng.choice(VOCAB)  # noqa: E731
    parts = ['<section id="i107-churn" aria-label="ambient feed" '
             'style="font-size:12px;max-height:30vh;overflow:hidden;text-align:left">']
    for i in range(REGION_DIVS):
        parts.append(f'<div data-k="{rng.randrange(1000)}">'
                     f'<span>{w()} {w()}</span><em>{w()}</em><span>{w()}</span><em>{w()} {w()}</em></div>')
    parts.append("</section>")
    return "".join(parts)


def churn_script(seed: int, run: bool) -> str:
    vocab = json.dumps(list(VOCAB))
    body = (
        "(function(){var s=%d>>>0;function r(){s=(s+0x6D2B79F5)>>>0;var t=s;"
        "t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296;}"
        "var V=%s;var root=document.getElementById('i107-churn');var leaves=root.querySelectorAll('span,em');"
        "var divs=root.querySelectorAll('div');var extras=[];function w(){return V[Math.floor(r()*V.length)];}"
        "function tick(){for(var i=0;i<%d;i++){var el=leaves[Math.floor(r()*leaves.length)];var op=r();"
        "if(op<1/3){el.textContent=w()+' '+w();}else if(op<2/3){if(r()<0.5){el.setAttribute('data-k',"
        "String(Math.floor(r()*1000)));}else{el.classList.toggle('on');}}else{var n=document.createElement('span');"
        "n.textContent=w();divs[Math.floor(r()*divs.length)].appendChild(n);extras.push(n);"
        "if(extras.length>1){extras.shift().remove();}}}}"
    ) % (seed, vocab, PER_TICK)
    if run:
        body += "setInterval(tick,%d);" % TICK_MS
    return "<script>" + body + "})();</script>"


def control_script() -> str:
    ops = json.dumps(CONTROL_OPS)
    return ("<script>(function(){var OPS=%s;var es=new EventSource('/events');"
            "es.onmessage=function(m){var op=JSON.parse(m.data);try{(new Function(OPS[op.op]))();}catch(e){}"
            "fetch('/ack',{method:'POST',body:op.id});};})();</script>") % ops


def page_for(condition: str, *, seed: int, control: bool) -> bytes:
    page = fixture_server.PAGE
    if condition == "W-quiet" and not control:
        return page
    text = page.decode()
    if condition in ("W-churn", "W-static"):
        cut = text.index("</form>") + len("</form>")
        text = text[:cut] + region_html(seed) + churn_script(seed, run=condition == "W-churn") + text[cut:]
    elif condition != "W-quiet":
        raise ValueError(condition)
    if control:
        cut = text.index("</main>")
        text = text[:cut] + control_script() + text[cut:]
    return text.encode()


class JournalFormState(FixtureState):
    """FixtureState plus a CLOCK_MONOTONIC journal of resets and submits (token hashed only)."""

    def __init__(self) -> None:
        super().__init__()
        self.journal: list[dict[str, Any]] = []
        self._jlock = threading.Lock()
        self._submitter: str | None = None

    def submit_form(self, value: str, *, submitter: str | None) -> None:
        t = now()
        who = submitter or "original"
        super().submit(value)
        with self._jlock:
            self._submitter = who
            self.journal.append({"event": "submit", "t_mono_ns": t, "value_sha16": sha16(value),
                                 "value_len": len(value), "submitter": who})

    def submit(self, value: str) -> None:  # jev-use handler path (not used by I107Handler)
        self.submit_form(value, submitter=None)

    def reset(self) -> None:
        t = now()
        super().reset()
        with self._jlock:
            self._submitter = None
            self.journal.append({"event": "reset", "t_mono_ns": t})

    def snapshot(self) -> dict[str, Any]:
        snap: dict[str, Any] = dict(super().snapshot())
        with self._jlock:
            snap["submitter"] = self._submitter
        return snap

    def add(self, event: dict[str, Any]) -> None:
        with self._jlock:
            self.journal.append(event)

    def drain(self) -> list[dict[str, Any]]:
        with self._jlock:
            out, self.journal = self.journal, []
        return out


def wrong_target_submits(journal: list[dict[str, Any]]) -> int:
    return sum(1 for e in journal if e.get("event") == "submit" and e.get("submitter") != "original")


class ControlBus:
    """One-shot operations for the page's EventSource; only the newest connection receives them."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._queue: list[dict[str, Any]] = []
        self._acks: set[str] = set()
        self.journal: list[dict[str, Any]] = []
        self.latest_conn = 0

    def connect(self) -> int:
        with self._cv:
            self.latest_conn += 1
            return self.latest_conn

    def post(self, op: str) -> str:
        op_id = uuid.uuid4().hex[:12]
        with self._cv:
            self._queue.append({"id": op_id, "op": op})
            self.journal.append({"event": "control_post", "op": op, "id": op_id, "t_mono_ns": now()})
            self._cv.notify_all()
        return op_id

    def next_op(self, timeout: float, conn: int | None = None) -> dict[str, Any] | None:
        with self._cv:
            end = time.monotonic() + timeout
            while not self._queue:
                left = end - time.monotonic()
                if left <= 0 or (conn is not None and conn != self.latest_conn):
                    return None
                self._cv.wait(left)
            if conn is not None and conn != self.latest_conn:
                return None
            return self._queue.pop(0)

    def ack(self, op_id: str) -> None:
        with self._cv:
            self._acks.add(op_id)
            self.journal.append({"event": "control_ack", "id": op_id, "t_mono_ns": now()})
            self._cv.notify_all()

    def wait_ack(self, op_id: str, timeout: float) -> bool:
        with self._cv:
            return self._cv.wait_for(lambda: op_id in self._acks, timeout)

    def drain(self) -> list[dict[str, Any]]:
        with self._cv:
            out, self.journal = self.journal, []
            self._queue.clear()
        return out


class I107Handler(FixtureHandler):
    server: "I107Server"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            srv = self.server
            self._send(HTTPStatus.OK, "text/html; charset=utf-8",
                       page_for(srv.condition, seed=srv.seed, control=srv.control))
        elif self.path == "/events" and self.server.control:
            conn = self.server.bus.connect()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(b": open\n\n")
                self.wfile.flush()
                while not self.server.stopping and conn == self.server.bus.latest_conn:
                    op = self.server.bus.next_op(0.25, conn)
                    if op is None:
                        continue
                    self.wfile.write(f"data: {json.dumps(op)}\n\n".encode())
                    self.wfile.flush()
            except OSError:
                return
        else:
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/ack":
            length = int(self.headers.get("Content-Length", "0"))
            self.server.bus.ack(self.rfile.read(length).decode().strip())
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/submit":
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode())
            value = form.get("value", [""])[0]
            if not value:
                self.send_error(HTTPStatus.BAD_REQUEST, "value is required")
                return
            submitter = form.get("dc_submitter", [None])[0]
            self.server.state.submit_form(value, submitter=submitter)
            body = ("<!doctype html><title>Cua Driver Jev verified</title>"
                    f"<h1>Action received</h1><output>status=submitted:{html.escape(value)}</output>").encode()
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
            return
        super().do_POST()


class I107Server(FixtureServer):
    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address)
        self.RequestHandlerClass = I107Handler
        self.state = JournalFormState()
        self.bus = ControlBus()
        self.condition = "W-quiet"
        self.seed = 0
        self.control = False
        self.stopping = False
        self.daemon_threads = True

    def configure(self, condition: str, seed: int, control: bool) -> None:
        self.condition, self.seed, self.control = condition, seed, control
        self.bus.drain()

"""In-memory stand-in for ``cua-driver mcp`` used ONLY by the harness unit tests.

It never produces evidence: every trial it drives is labelled ``UNIT_FAKE_DRIVER``.
It lets the unit tests exercise the real jev-use ``run.run`` (A and D), the PR 4316
guard, the lane-D stamping/hooks/ledger code, the fixture server, its control
channel and the analysis end to end without a browser.

``FakePage`` models the fixture form (field value, Submit elements with the form
endpoint each posts to, document generation). ``FakePageChannel`` plays the page
side of the control channel: it reads ``/events``, applies the op to the model and
POSTs ``/ack``. ``FakeSession`` answers the Driver tools the caller uses; refs are
minted per snapshot (a new snapshot invalidates older refs, like BrowserStore), a
ref from an older document generation is refused ``browser_ref_stale``, and a ref
to a replaced (detached) element is clicked with no effect, recording the page's
``detached_click`` note (the known Driver gap R2-07 N4a, modelled, not measured).
"""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _post(url: str, body: bytes, ctype: str = "application/json") -> None:
    with urlopen(Request(url, data=body, method="POST", headers={"Content-Type": ctype}), timeout=5):
        pass


class FakePage:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.value = ""
        self.doc = 1
        self.next_el = 1
        self.buttons = [self._el("/submit")]
        self.detached: set[int] = set()
        self.hidden = False

    def _el(self, endpoint: str, name: str = "Submit") -> dict[str, Any]:
        el = {"id": self.next_el, "endpoint": endpoint, "name": name}
        self.next_el += 1
        return el

    def apply(self, op: str, args: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if op == "set_value":
                self.value = str(args.get("value", ""))
            elif op == "insert_competing":
                self.buttons.insert(0, self._el("/submit-competing"))
            elif op == "remove_submit":
                self.buttons = [b for b in self.buttons if b["endpoint"] != "/submit"]
            elif op in ("rerender_submit", "replace_submit_watch"):
                for i, b in enumerate(self.buttons):
                    if b["endpoint"] == "/submit":
                        if op == "replace_submit_watch":
                            self.detached.add(b["id"])
                        self.buttons[i] = self._el("/submit")
            elif op == "relocate_decoy":
                self.buttons = [self._el("/submit-decoy")]
            elif op == "replace_document":
                self.doc += 1
                self.value = ""
                self.buttons = [self._el("/submit")]
            elif op == "hide_submit":
                self.hidden = True
            elif op == "before_name":
                for b in self.buttons:
                    b["name"] = "Do not Submit"
            return {"applied": True}


class FakePageChannel(threading.Thread):
    def __init__(self, base_url: str, page: FakePage) -> None:
        super().__init__(daemon=True)
        self.base_url, self.page = base_url, page
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                with urlopen(self.base_url + "events", timeout=30) as stream:
                    _post(self.base_url + "note", json.dumps({"kind": "control_open"}).encode())
                    for raw in stream:
                        if self.stop.is_set():
                            return
                        line = raw.decode().strip()
                        if not line.startswith("data:"):
                            continue
                        msg = json.loads(line[5:])
                        result = self.page.apply(msg["op"], msg.get("args") or {})
                        _post(self.base_url + "ack", json.dumps({"id": msg["id"], "result": result}).encode())
                        if msg["op"] == "replace_document":
                            break  # the new document opens a new stream
            except OSError:
                if self.stop.wait(0.05):
                    return


class FakeSession:
    TARGET, TAB = "fake-target", "fake-tab"

    def __init__(self, base_url: str, page: FakePage, trace_path: str | None = None, bound: bool = True) -> None:
        self.base_url, self.page, self.trace_path = base_url, page, trace_path
        self.snap = 0
        self.refs: dict[str, tuple[int, int | str]] = {}  # ref -> (doc, element id | "field")
        self.bound = bound
        self.calls: list[str] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None

    async def initialize(self) -> None:
        return None

    async def list_tools(self) -> Any:
        return SimpleNamespace(tools=[])

    def _mark(self, phase: str, **detail: Any) -> None:
        if self.trace_path:
            import time
            with open(self.trace_path, "a") as f:
                f.write(json.dumps({"t_mono_ns": time.monotonic_ns(), "seq": 0, "phase": phase, "session": "",
                                    "detail": detail or None}) + "\n")

    @staticmethod
    def _ok(data: dict[str, Any]) -> Any:
        return SimpleNamespace(isError=False, structuredContent=data, content=[])

    @staticmethod
    def _err(code: str) -> Any:
        return SimpleNamespace(isError=True, structuredContent={"code": code}, content=[{"type": "text", "text": code}])

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        self.calls.append(name)
        if name == "set_agent_cursor_enabled":
            return self._ok({"enabled": bool(args.get("enabled"))})
        if name == "browser_prepare":
            return self._ok({"prepared_pid": 0})
        if name == "list_windows":
            return self._ok({"windows": [{"window_id": 1, "is_on_screen": True, "bounds": {"width": 10, "height": 10}}]})
        if name == "browser_navigate":
            return self._ok({"status": "ok"})
        if name == "get_browser_state" and "snapshot_format" not in args:
            return self._ok({"target_id": self.TARGET, "tabs": [{"tab_id": self.TAB, "active": True}]})
        if not self.bound:
            return self._err("browser_binding_stale")
        if name == "get_browser_state":
            self.snap += 1
            self._mark("cdp.send", id=self.snap, method="DOM.getDocument", on_session=True, bytes=60)
            self._mark("cdp.reply", id=self.snap, bytes=4000, error=False)
            self._mark("snap.acquired_dom", dom_nodes=20, layout_nodes=15)
            self._mark("snap.acquired_ax", ax_nodes=12)
            with self.page.lock:
                self.refs = {f"p{self.snap}:0": (self.page.doc, "field")}
                refs = [{"ref": f"p{self.snap}:0", "role": "textbox", "name": "verification value",
                         "value": self.page.value, "actions": ["type", "click"], "visibility": "in_viewport"}]
                for i, b in enumerate([] if self.page.hidden else self.page.buttons, start=1):
                    ref = f"p{self.snap}:{i}"
                    self.refs[ref] = (self.page.doc, b["id"])
                    refs.append({"ref": ref, "role": "button", "name": b["name"], "value": None,
                                 "actions": ["click"], "visibility": "in_viewport"})
            return self._ok({"status": "ok", "target_id": self.TARGET, "tab_id": self.TAB, "refs": refs,
                             "snapshot": {"id": f"p{self.snap}", "format": "semantic_v2"}})
        ref = args.get("ref")
        if ref not in self.refs:
            return self._err("browser_ref_stale")
        doc, el = self.refs[ref]
        with self.page.lock:
            current_doc = self.page.doc
        if doc != current_doc:
            return self._err("browser_ref_stale")
        if name == "browser_type":
            self._mark("focus.settle_start", settle_ms=100)
            with self.page.lock:
                self.page.value = args.get("text", "")
            return self._ok({"status": "ok", "effect": "unverifiable"})
        if name == "browser_click":
            self._mark("platform.gate", cursor_enabled=False)
            with self.page.lock:
                target = next((b for b in self.page.buttons if b["id"] == el), None)
                detached = el in self.page.detached
                value = self.page.value
            if detached:
                _post(self.base_url + "note", json.dumps({"kind": "detached_click", "connected": False}).encode())
            elif target is not None:
                _post(self.base_url + target["endpoint"].lstrip("/"), urlencode({"value": value}).encode(),
                      "application/x-www-form-urlencoded")
            return self._ok({"status": "ok", "route": "dom_event", "effect": "unverifiable"})
        return self._err("unsupported_tool")

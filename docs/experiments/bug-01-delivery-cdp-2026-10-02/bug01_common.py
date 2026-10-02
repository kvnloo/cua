"""Shared helpers for the BUG-01 probes (measurement only).

Runs INSIDE the isolated X11 session (cua-x11-session.sh) with the jev-use
venv, cwd = <worktree>/libs/cua-driver/examples/jev-use. Every Driver call is
an ordinary public MCP tool call with default safety settings.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.request import Request, urlopen

JEV = Path.cwd()
sys.path.insert(0, str(JEV))
sys.path.insert(0, str(JEV / "python"))

from fixture_server import PAGE, FixtureHandler, FixtureServer  # noqa: E402
from driver_env import driver_environment  # noqa: E402,F401
from mcp import ClientSession  # noqa: E402,F401

# ---------------------------------------------------------------- sanitising
_HOST = socket.gethostname()
_SUBS: list[tuple[str, str]] = []
for env_key, placeholder in (("HOME", "<session-home>"), ("TMPDIR", "<session-tmp>"), ("XDG_RUNTIME_DIR", "<session-xdg-runtime>")):
    value = os.environ.get(env_key)
    if value and len(value) > 4:
        _SUBS.append((value, placeholder))
# Derived roots, no literal local paths: lanes root = worktree parent; lane temp
# root = two levels above the session TMPDIR.
_SUBS.append((str(JEV.parents[3].parent), "<lanes>"))
if os.environ.get("TMPDIR"):
    _SUBS.append((str(Path(os.environ["TMPDIR"]).parents[1]), "<tmp>"))
if _HOST:
    _SUBS.append((_HOST, "<host>"))
_ABS = re.compile(r"(/(?:home|mnt|tmp|root|var/tmp)/[^\s\"']*)")


def sanitize(obj: Any) -> Any:
    if isinstance(obj, str):
        for raw, placeholder in _SUBS:
            obj = obj.replace(raw, placeholder)
        return _ABS.sub("<abs-path>", obj)
    if isinstance(obj, dict):
        return {sanitize(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def require_isolated_session() -> None:
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ) or not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: not inside the isolated X11 session")


# ------------------------------------------------------- instrumented fixture
LISTENER = r"""
<script>
(() => {
  const TRIAL = "__TRIAL__";
  let seq = 0;
  const desc = (el) => {
    if (!el || el === window) return el === window ? "window" : null;
    if (el === document) return "document";
    if (!el.tagName) return String(el.nodeName || "?");
    let d = el.tagName.toLowerCase();
    if (el.type) d += "[type=" + el.type + "]";
    if (el.name) d += "[name=" + el.name + "]";
    if (el.id) d += "#" + el.id;
    const t = (el.textContent || "").trim();
    if (el.tagName === "BUTTON" && t) d += "{" + t.slice(0, 20) + "}";
    return d;
  };
  const post = (kind, e, extra) => {
    const rec = {trial: TRIAL, seq: seq++, kind, t_epoch_ms: performance.timeOrigin + performance.now(),
      has_focus: document.hasFocus(), visibility: document.visibilityState, active: desc(document.activeElement)};
    if (e) { rec.is_trusted = e.isTrusted; rec.target = desc(e.target); if ("pointerType" in e) rec.pointer_type = e.pointerType; }
    if (extra) Object.assign(rec, extra);
    try { navigator.sendBeacon("/events", JSON.stringify(rec)); } catch (_) {}
  };
  const input = () => document.querySelector("input[name=value]");
  for (const type of ["pointerdown", "pointerup", "mousedown", "mouseup", "click"]) window.addEventListener(type, (e) => post(type, e), true);
  for (const type of ["focusin", "focusout"]) window.addEventListener(type, (e) => post(type, e), true);
  window.addEventListener("submit", (e) => post("submit", e, {value_len: (input() || {value: ""}).value.length}), true);
  window.addEventListener("input", (e) => post("input", e, {value_len: (input() || {value: ""}).value.length}), true);
  const ready = () => requestAnimationFrame(() => requestAnimationFrame(() => post("load", null)));
  if (document.readyState === "complete") ready(); else window.addEventListener("load", ready);
})();
</script>"""

NOOP_BUTTON = b'<p><button type="button" id="bug01-noop">No-op</button></p>'


class ProbeHandler(FixtureHandler):
    server: "ProbeServer"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            body = PAGE
            if self.server.noop_button:
                body = body.replace(b"</form>", b"</form>" + NOOP_BUTTON)
            if self.server.instrumented:
                body = body.replace(b"</html>", LISTENER.replace("__TRIAL__", self.server.trial).encode() + b"</html>")
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        recv = time.time()
        if self.path == "/events":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode() or "{}")
            except ValueError:
                payload = {"unparsed": True}
            self.server.journal_add({"source": "page", "recv_epoch_ms": recv * 1000, "server_trial": self.server.trial, **payload})
            self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
            return
        if self.path == "/submit":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            value = parse_qs(raw.decode()).get("value", [""])[0]
            self.server.journal_add({"source": "target", "kind": "submit_post", "recv_epoch_ms": recv * 1000, "server_trial": self.server.trial, "value": value})
            import io
            self.rfile = io.BytesIO(raw)
            super().do_POST()
            return
        super().do_POST()


class ProbeServer(FixtureServer):
    def __init__(self, address: tuple[str, int], *, instrumented: bool = True, noop_button: bool = False) -> None:
        super().__init__(address)
        self.RequestHandlerClass = ProbeHandler
        self.trial = "none"
        self.instrumented = instrumented
        self.noop_button = noop_button
        self._jlock = threading.Lock()
        self.journal: list[dict[str, Any]] = []

    def journal_add(self, rec: dict[str, Any]) -> None:
        with self._jlock:
            self.journal.append(rec)

    def journal_for(self, trial: str) -> list[dict[str, Any]]:
        with self._jlock:
            return [r for r in self.journal if r.get("server_trial") == trial or r.get("trial") == trial]


def sh(cmd: list[str], timeout: float = 3) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def x_focus() -> dict[str, Any]:
    return {
        "active_window": sh(["xdotool", "getactivewindow"]),
        "net_active_window": sh(["xprop", "-root", "_NET_ACTIVE_WINDOW"]),
    }


def oracle(url: str) -> dict[str, Any]:
    with urlopen(url + "state", timeout=2) as response:
        return json.load(response)


def reset(url: str) -> None:
    urlopen(Request(url + "reset", method="POST", data=b""), timeout=2).read()


class Probe:
    """Thin MCP caller; acceptance = no isError and no refusal/effect=refused."""

    def __init__(self, session: Any, label: str) -> None:
        self.session = session
        self.label = label

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        t0 = time.time() * 1000
        p0 = time.perf_counter()
        try:
            res = await self.session.call_tool(name, {**args, "session": self.label})
        except Exception as exc:  # transport failure: outcome unknown
            return {"tool": name, "t_start_ms": t0, "t_end_ms": time.time() * 1000, "elapsed_ms": (time.perf_counter() - p0) * 1000, "transport_error": f"{type(exc).__name__}: {exc}", "accepted": False}
        elapsed = (time.perf_counter() - p0) * 1000
        t1 = time.time() * 1000
        structured = res.structuredContent if isinstance(res.structuredContent, dict) else None
        text = " ".join(getattr(c, "text", "") for c in (res.content or []) if getattr(c, "text", None))
        refusal = None
        if structured:
            refusal = structured.get("refusal") or (structured if structured.get("status") == "refused" else None)
            if structured.get("effect") == "refused" and refusal is None:
                refusal = {"effect": "refused", "error": structured.get("error")}
        accepted = (not res.isError) and refusal is None and bool(structured)
        return {"tool": name, "t_start_ms": t0, "t_end_ms": t1, "elapsed_ms": elapsed, "is_error": bool(res.isError), "refusal": refusal, "accepted": accepted, "structured": structured, "text": text[:400]}


async def wait_for_window(probe: Probe, pid: int) -> dict[str, Any]:
    import asyncio

    for _ in range(60):
        r = await probe.call("list_windows", {"pid": pid})
        windows = (r.get("structured") or {}).get("windows", [])
        visible = [w for w in windows if w.get("is_on_screen")]
        if visible:
            return max(visible, key=lambda w: w["bounds"]["width"] * w["bounds"]["height"])
        await asyncio.sleep(0.25)
    raise RuntimeError("isolated browser window did not become ready")


def find_ref(snapshot: dict[str, Any], role: str, name: str) -> str | None:
    for item in snapshot.get("refs") or []:
        if item.get("role") == role and item.get("name") == name:
            return item.get("ref")
    return None


def driver_version(binary: str) -> str | None:
    return sh([binary, "--version"], timeout=10)


def sha256_file(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

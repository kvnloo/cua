"""R2-06 trusted-input miss diagnosis probe (measurement only).

Runs INSIDE the isolated X11 session (cua-x11-session.sh) with the jev-use
venv. It reuses the jev-use fixture server (subclassed only to add a page
listener journal), the jev-use Driver environment helper and the MCP stdio
client. It does not change Driver behaviour: every Driver call is an ordinary
public MCP tool call with default safety settings.

Per trial it records:
  tool acceptance  -> MCP browser_click result (isError / refusal / structured)
  X input delivery -> `xinput test-xi2 --root` lines stamped while the tool ran
  page event       -> capture-phase DOM listeners posted by sendBeacon to the
                      fixture journal (pointer/mouse/click/focus/invalid/submit)
  handler          -> `submit` event in the page journal
  target journal   -> fixture POST /submit receipt (server side)
  fresh verify     -> independent GET /state immediately and bounded re-reads
plus window focus/activation (xdotool) and target geometry (DOM rect, DPR,
viewport, window offset) per trial.

usage (inside the session):
  probe_trusted_input.py --plan plan.json --out <dir> [--driver-label main]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.request import Request, urlopen

JEV = Path.cwd()
sys.path.insert(0, str(JEV))
sys.path.insert(0, str(JEV / "python"))

from fixture_server import PAGE, FixtureHandler, FixtureServer  # noqa: E402
from driver_env import driver_environment  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

FIELD_NAME = "verification value"
SUBMIT_NAME = "Submit"

# ---------------------------------------------------------------- sanitising
_HOST = socket.gethostname()
_SUBS: list[tuple[str, str]] = []
for env_key, placeholder in (("HOME", "<session-home>"), ("TMPDIR", "<session-tmp>"), ("XDG_RUNTIME_DIR", "<session-xdg-runtime>")):
    value = os.environ.get(env_key)
    if value and len(value) > 4:
        _SUBS.append((value, placeholder))
_SUBS += [
    ("<redacted: lane temp root>", "<tmp>"),
    ("<redacted: lanes root>", "<lanes>"),
    ("<redacted: models mount>", "<mnt>"),
    ("<redacted: user home>", "<home>"),
]
if _HOST:
    _SUBS.append((_HOST, "<host>"))
_ABS = re.compile(r"(/(?:home|mnt|tmp)/[^\s\"']*)")


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
    const t = (el.textContent || "").trim();
    if (el.tagName === "BUTTON" && t) d += "{" + t.slice(0, 20) + "}";
    return d;
  };
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height};
  };
  const geom = () => ({
    dpr: window.devicePixelRatio,
    vv_scale: window.visualViewport ? window.visualViewport.scale : null,
    inner: [window.innerWidth, window.innerHeight],
    outer: [window.outerWidth, window.outerHeight],
    screen_xy: [window.screenX, window.screenY],
    scroll: [window.scrollX, window.scrollY],
    button: rect("button[type=submit]"),
    input: rect("input[name=value]"),
  });
  const post = (kind, e, extra) => {
    const rec = {trial: TRIAL, seq: seq++, kind, t_epoch_ms: performance.timeOrigin + performance.now(),
      has_focus: document.hasFocus(), visibility: document.visibilityState,
      active: desc(document.activeElement)};
    if (e) {
      rec.is_trusted = e.isTrusted;
      rec.target = desc(e.target);
      if ("clientX" in e) {
        rec.client = [e.clientX, e.clientY];
        rec.screen = [e.screenX, e.screenY];
        rec.button_no = e.button; rec.buttons = e.buttons; rec.detail = e.detail;
        if ("pointerType" in e) rec.pointer_type = e.pointerType;
        const hit = document.elementFromPoint(e.clientX, e.clientY);
        rec.hit = desc(hit);
      }
    }
    if (extra) Object.assign(rec, extra);
    try { navigator.sendBeacon("/events", JSON.stringify(rec)); } catch (_) {}
  };
  const input = () => document.querySelector("input[name=value]");
  for (const type of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "pointermove", "mousemove", "contextmenu", "auxclick", "dblclick"]) {
    window.addEventListener(type, (e) => post(type, e, (type === "pointerdown" || type === "mousedown" || type === "click") ? {geom: geom(), value_len: (input() || {value: ""}).value.length} : null), true);
  }
  for (const type of ["focusin", "focusout"]) window.addEventListener(type, (e) => post(type, e), true);
  window.addEventListener("focus", (e) => { if (e.target === window) post("window_focus", null); }, true);
  window.addEventListener("blur", (e) => { if (e.target === window) post("window_blur", null); }, true);
  window.addEventListener("invalid", (e) => post("invalid", e, {value_len: (input() || {value: ""}).value.length}), true);
  window.addEventListener("submit", (e) => post("submit", e, {value_len: (input() || {value: ""}).value.length, valid: e.target.checkValidity ? e.target.checkValidity() : null}), true);
  window.addEventListener("input", (e) => post("input", e, {value_len: (input() || {value: ""}).value.length}), true);
  window.addEventListener("resize", () => post("resize", null, {geom: geom()}), true);
  document.addEventListener("visibilitychange", () => post("visibilitychange", null), true);
  window.addEventListener("pagehide", () => post("pagehide", null), true);
  const ready = () => requestAnimationFrame(() => requestAnimationFrame(() => post("load", null, {geom: geom()})));
  if (document.readyState === "complete") ready(); else window.addEventListener("load", ready);
})();
</script>"""


class ProbeHandler(FixtureHandler):
    server: "ProbeServer"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" and self.server.instrumented:
            body = PAGE.replace(b"</html>", LISTENER.replace("__TRIAL__", self.server.trial).encode() + b"</html>")
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
            # Peek the form body for the journal, then let the unmodified handler run.
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
    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address)
        self.RequestHandlerClass = ProbeHandler
        self.trial = "none"
        self.instrumented = True
        self._jlock = threading.Lock()
        self.journal: list[dict[str, Any]] = []

    def journal_add(self, rec: dict[str, Any]) -> None:
        with self._jlock:
            self.journal.append(rec)

    def journal_for(self, trial: str) -> list[dict[str, Any]]:
        with self._jlock:
            return [r for r in self.journal if r.get("server_trial") == trial or r.get("trial") == trial]


# ------------------------------------------------------------- X11 recorder
class XRecorder:
    """`xinput test-xi2 --root` line logger with wall-clock stamps."""

    def __init__(self) -> None:
        self.lines: list[tuple[float, str]] = []
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[str] | None = None
        self.error: str | None = None

    def start(self) -> None:
        try:
            self.proc = subprocess.Popen(["xinput", "test-xi2", "--root"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            return
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            with self.lock:
                self.lines.append((time.time() * 1000, line.rstrip("\n")))

    def window(self, t0: float, t1: float) -> dict[str, Any]:
        with self.lock:
            sel = [(t, l) for t, l in self.lines if t0 <= t <= t1]
        events: dict[str, int] = {}
        for _, line in sel:
            m = re.match(r"EVENT type \d+ \((\w+)\)", line)
            if m:
                events[m.group(1)] = events.get(m.group(1), 0) + 1
        return {"event_counts": events, "event_lines": [l for _, l in sel if l.startswith("EVENT")][:50], "lines_total": len(sel), "recorder_alive": bool(self.proc and self.proc.poll() is None), "recorder_error": self.error}

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def sh(cmd: list[str]) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def x_focus(window_id: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "active_window": sh(["xdotool", "getactivewindow"]),
        "focus_window": sh(["xdotool", "getwindowfocus", "-f"]),
        "net_active_window": sh(["xprop", "-root", "_NET_ACTIVE_WINDOW"]),
    }
    if window_id is not None:
        out["browser_window_geometry"] = sh(["xdotool", "getwindowgeometry", str(window_id)])
    out["pointer"] = sh(["xdotool", "getmouselocation"])
    return out


# ------------------------------------------------------------------ Driver
class Probe:
    def __init__(self, session: ClientSession, label: str) -> None:
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
        structured = res.structuredContent if isinstance(res.structuredContent, dict) else None
        text = " ".join(getattr(c, "text", "") for c in (res.content or []) if getattr(c, "text", None))
        refusal = None
        if structured:
            refusal = structured.get("refusal") or (structured if structured.get("status") == "refused" else None)
            if structured.get("effect") == "refused" and refusal is None:
                refusal = {"effect": "refused"}
        # Acceptance = the tool returned without error and without a refusal
        # (isError is unset on refusal envelopes, so effect=refused is checked too).
        accepted = (not res.isError) and refusal is None and bool(structured)
        return {"tool": name, "t_start_ms": t0, "t_end_ms": time.time() * 1000, "elapsed_ms": elapsed, "is_error": bool(res.isError), "refusal": refusal, "accepted": accepted, "structured": structured, "text": text[:600]}


def oracle(url: str) -> dict[str, Any]:
    with urlopen(url + "state", timeout=2) as response:
        return json.load(response)


def reset(url: str) -> None:
    urlopen(Request(url + "reset", method="POST", data=b""), timeout=2).read()


async def wait_for_window(probe: Probe, pid: int) -> dict[str, Any]:
    for _ in range(40):
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


async def run_trial(probe: Probe, server: ProbeServer, url: str, xrec: XRecorder, ctx: dict[str, Any], spec: dict[str, Any], out: Path, verify_bound_ms: float) -> dict[str, Any]:
    arm = spec["arm"]
    trial_id = f"{spec['index']:03d}-{arm}-{uuid.uuid4().hex[:6]}"
    token = f"r2-06-{trial_id}"
    server.trial = trial_id
    server.instrumented = spec.get("instrumented", True)
    reset(url)
    rec: dict[str, Any] = {"event": "trial", "trial": trial_id, "index": spec["index"], "block": spec["block"], "pos_in_block": spec["pos"], "arm": arm, "instrumented": server.instrumented, "driver_label": ctx["driver_label"], "loadavg_start": os.getloadavg(), "token": token}
    target, tab = ctx["target_id"], ctx["tab_id"]
    nav = await probe.call("browser_navigate", {"target_id": target, "tab_id": tab, "url": url})
    rec["navigate"] = {k: nav.get(k) for k in ("accepted", "elapsed_ms", "is_error", "refusal")}
    load_rec = None
    if server.instrumented:
        deadline = time.time() + 6
        while time.time() < deadline:
            loads = [r for r in server.journal_for(trial_id) if r.get("kind") == "load"]
            if loads:
                load_rec = loads[0]
                break
            await asyncio.sleep(0.05)
    rec["page_load"] = load_rec
    snap = await probe.call("get_browser_state", {"target_id": target, "tab_id": tab, "snapshot_format": "semantic_v2"})
    snapshot = snap.get("structured") or {}
    field_ref = find_ref(snapshot, "textbox", FIELD_NAME)
    submit_ref = find_ref(snapshot, "button", SUBMIT_NAME)
    rec["snapshot"] = {"accepted": snap.get("accepted"), "elapsed_ms": snap.get("elapsed_ms"), "field_ref": field_ref, "submit_ref": submit_ref, "ref_count": len(snapshot.get("refs") or [])}
    if spec.get("type", True):
        typed = await probe.call("browser_type", {"target_id": target, "tab_id": tab, "ref": field_ref, "text": token, "replace": True})
        rec["type"] = {k: typed.get(k) for k in ("accepted", "elapsed_ms", "is_error", "refusal", "t_start_ms", "t_end_ms")}
        rec["type"]["structured"] = typed.get("structured")
    else:
        rec["type"] = {"skipped": True}
    if spec.get("stale_ref"):
        # Negative control: navigate again so the snapshot ref is stale, then click it.
        nav2 = await probe.call("browser_navigate", {"target_id": target, "tab_id": tab, "url": url})
        rec["stale_navigate"] = {k: nav2.get(k) for k in ("accepted", "elapsed_ms")}
        await asyncio.sleep(0.5)
    rec["focus_pre"] = x_focus(ctx.get("window_id"))
    click_args: dict[str, Any] = {"target_id": target, "tab_id": tab}
    if spec.get("coords"):
        click_args.update({"x": spec["coords"][0], "y": spec["coords"][1]})
    else:
        click_args["ref"] = submit_ref
    click_args.update(spec.get("click_args", {}))
    rec["click_args"] = {k: v for k, v in click_args.items() if k not in ("target_id", "tab_id")}
    click = await probe.call("browser_click", click_args)
    t_click_end = click["t_end_ms"]
    # Fresh, independent verification: one immediate read, then bounded re-reads.
    reads = []
    first_verified_ms = None
    p0 = time.perf_counter()
    while True:
        try:
            state = oracle(url)
        except Exception as exc:  # noqa: BLE001
            state = {"error": type(exc).__name__}
        dt = (time.perf_counter() - p0) * 1000
        reads.append({"after_tool_ms": round(dt, 2), "state": state})
        if state.get("submitted") == token and first_verified_ms is None:
            first_verified_ms = dt
            break
        if dt >= verify_bound_ms:
            break
        await asyncio.sleep(0.05)
    rec["click"] = click
    rec["focus_post"] = x_focus(ctx.get("window_id"))
    rec["oracle"] = {"immediate": reads[0]["state"], "reads": len(reads), "first_verified_after_tool_ms": first_verified_ms, "final": reads[-1]["state"], "bound_ms": verify_bound_ms}
    await asyncio.sleep(0.4)  # let trailing beacons arrive (does not affect the oracle above)
    rec["x11"] = xrec.window(click["t_start_ms"] - 5, t_click_end + 5)
    rec["x11_trial"] = xrec.window(nav["t_start_ms"], time.time() * 1000)
    rec["journal"] = server.journal_for(trial_id)
    rec["loadavg_end"] = os.getloadavg()
    rec["t_trial_end_ms"] = time.time() * 1000
    rec = sanitize(rec)
    with (out / f"{trial_id}.jsonl").open("w") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    v = "V" if first_verified_ms is not None else "-"
    print(json.dumps({"trial": trial_id, "accepted": click.get("accepted"), "verified": v, "first_verified_ms": first_verified_ms, "click_ms": round(click["elapsed_ms"], 1)}), flush=True)
    return rec


async def run_block(block: dict[str, Any], server: ProbeServer, url: str, xrec: XRecorder, out: Path, driver_label: str, verify_bound_ms: float) -> None:
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_environment())
    label = f"r2-06-{uuid.uuid4().hex[:8]}"
    meta: dict[str, Any] = {"event": "block", "block": block["block"], "label": label, "t_start_ms": time.time() * 1000, "loadavg": os.getloadavg()}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            meta["server_info"] = {"name": init.serverInfo.name, "version": init.serverInfo.version}
            probe = Probe(session, label)
            prep = await probe.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            meta["prepare"] = {k: prep.get(k) for k in ("accepted", "elapsed_ms", "is_error", "refusal")}
            pid = int((prep.get("structured") or {})["prepared_pid"])
            window = await wait_for_window(probe, pid)
            bound = await probe.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
            b = bound.get("structured") or {}
            tabs = b.get("tabs") or []
            tab = next((t for t in tabs if t.get("active")), tabs[0])
            ctx = {"target_id": b["target_id"], "tab_id": str(tab["tab_id"]), "window_id": int(window["window_id"]), "driver_label": driver_label}
            meta["window"] = {"window_id": window["window_id"], "bounds": window.get("bounds")}
            meta["focus_at_bind"] = x_focus(ctx["window_id"])
            for spec in block["trials"]:
                try:
                    await run_trial(probe, server, url, xrec, ctx, {**spec, "block": block["block"]}, out, verify_bound_ms)
                except Exception as exc:  # keep the failure in the denominator
                    err = sanitize({"event": "trial_harness_error", "index": spec["index"], "arm": spec["arm"], "block": block["block"], "error": f"{type(exc).__name__}: {exc}"})
                    with (out / f"{spec['index']:03d}-{spec['arm']}-harness-error.jsonl").open("w") as fh:
                        fh.write(json.dumps(err) + "\n")
                    print(json.dumps(err), flush=True)
    meta["t_end_ms"] = time.time() * 1000
    with (out / f"block-{block['block']:02d}.json").open("w") as fh:
        fh.write(json.dumps(sanitize(meta), sort_keys=True, indent=1) + "\n")


async def amain(args: argparse.Namespace) -> None:
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    with ProbeServer(("127.0.0.1", 0)) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/"
        xrec = XRecorder()
        xrec.start()
        # Recorder positive control: two XTest pointer motions on the bare root,
        # outside the browser window, before any block starts.
        await asyncio.sleep(1.0)
        t_self0 = time.time() * 1000
        sh(["xdotool", "mousemove", "1915", "1075"])
        await asyncio.sleep(0.3)
        sh(["xdotool", "mousemove", "1910", "1070"])
        await asyncio.sleep(0.5)
        recorder_selftest = xrec.window(t_self0, time.time() * 1000)
        env = {"xinput_list": sh(["xinput", "list"]), "display": os.environ.get("DISPLAY"), "focus_initial": x_focus(None), "driver_label": args.driver_label, "plan_name": plan.get("name"), "x_recorder_selftest": recorder_selftest}
        (out / "session-env.json").write_text(json.dumps(sanitize(env), indent=1) + "\n")
        try:
            for block in plan["blocks"]:
                if args.only_blocks and block["block"] not in args.only_blocks:
                    continue
                try:
                    await run_block(block, server, url, xrec, out, args.driver_label, args.verify_bound_ms)
                except Exception as exc:  # noqa: BLE001
                    err = sanitize({"event": "block_harness_error", "block": block["block"], "error": f"{type(exc).__name__}: {exc}"})
                    (out / f"block-{block['block']:02d}-harness-error.json").write_text(json.dumps(err) + "\n")
                    print(json.dumps(err), flush=True)
        finally:
            xrec.stop()
            server.shutdown()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--driver-label", default="main")
    p.add_argument("--verify-bound-ms", type=float, default=3000.0)
    p.add_argument("--only-blocks", type=int, nargs="*")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ) or not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: not inside the isolated X11 session")
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()

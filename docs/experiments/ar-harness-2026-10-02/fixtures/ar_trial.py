#!/usr/bin/env python3
"""One AR fixture trial: fixture app + frozen scripted caller + sandboxed Driver +
target-owned oracle + external checks (evaluator side; no model, no provider).

Runs INSIDE the private session (cua-x11-session.sh with a private AT-SPI bus),
under the jev-use venv. ``run_trial`` is the unit the AA/AB harness times:

  T = CLOCK_MONOTONIC from the Driver spawn (bwrap exec) to the frozen caller's
      verified done (the app journal / fixture /state confirms the effect, and the
      journal's own mutation stamp is <= done).

The frozen caller is the R2-04 scripted path: get_window_state (tree +
screenshot) -> jev-use ``eligible_controls`` lookup by label ->
``click(element_token, delivery_mode="background")`` (text: ``set_value`` then the
Save click) -> poll the target-owned oracle. It never retries, never redispatches
and never reads trace marks. The browser spot check follows the jev-use
fill->submit path (browser_prepare isolated_new -> navigate -> semantic_v2 refs
-> browser_type -> trusted browser_click foreground -> poll /state).
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import secrets
import select
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from contextlib import suppress
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ar_external as ext  # noqa: E402
import ar_oracle as orc  # noqa: E402
import ar_sandbox as sbx  # noqa: E402
from ar_layout import layout_for  # noqa: E402

JEV_REL = "libs/cua-driver/examples/jev-use"
APP = HERE / "ar_gtk3_app.py"
SYSTEM_PYTHON = "/usr/bin/python3"  # PyGObject lives in the system interpreter
ORACLE_DEADLINE_S = 3.0
UNKNOWN_DEADLINE_S = 1.5
POLL_S = 0.0005
LINGER_S = 1.0


def mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def loadavg() -> list[float]:
    return [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]


def jev_imports(wt: Path):
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    sys.path.insert(0, str(wt / JEV_REL))
    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402
    from run import Driver, DriverToolError  # noqa: E402
    return driver_environment, NativeObservation, eligible_controls, Driver, DriverToolError


# ------------------------------------------------------------------ fixture app
class App:
    """A fixture app process started with a nonce pipe and a ready pipe."""

    def __init__(self, task: str, seed: int, variant: str, state_dir: Path | None, log: Path,
                 nonce: str | None) -> None:
        self.nonce = nonce or ""
        nr, nw = os.pipe()
        rr, rw = os.pipe()
        self.control, child_control = socket.socketpair()
        argv = [SYSTEM_PYTHON, str(APP), "--task", task, "--seed", str(seed), "--variant", variant,
                "--nonce-fd", str(nr), "--ready-fd", str(rw), "--control-fd", str(child_control.fileno())]
        if state_dir is not None:
            argv += ["--state-dir", str(state_dir)]
        self.log = open(log, "w")
        self.proc = subprocess.Popen(argv, pass_fds=(nr, rw, child_control.fileno()), stdout=self.log,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        os.close(nr)
        os.close(rw)
        child_control.close()
        os.write(nw, self.nonce.encode())
        os.close(nw)
        self.ready = self._read_ready(rr)
        self.pid = self.proc.pid

    def _read_ready(self, fd: int, timeout: float = 20.0) -> dict[str, Any]:
        buf = b""
        end = time.monotonic() + timeout
        try:
            while b"\n" not in buf:
                left = end - time.monotonic()
                if left <= 0 or self.proc.poll() is not None:
                    raise RuntimeError(f"fixture app not ready (rc={self.proc.poll()})")
                r, _, _ = select.select([fd], [], [], left)
                if r:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    buf += chunk
        finally:
            os.close(fd)
        return json.loads(buf.split(b"\n")[0])

    def command(self, text: str, timeout: float = 5.0) -> str:
        """Send a harness command on the control socket and wait for the reply line."""
        self.control.sendall((text + "\n").encode())
        self.control.settimeout(timeout)
        return self.control.recv(256).decode().strip()

    def stop(self) -> None:
        self.control.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()


# ------------------------------------------------------------------- X helpers
def sh(cmd: list[str], timeout: float = 5.0) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()


def active_window() -> int | None:
    out = sh(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    m = re.search(r"#\s*(0x[0-9a-fA-F]+)", out)
    return int(m.group(1), 16) if m else None


def client_titles() -> dict[int, str]:
    out = sh(["xprop", "-root", "_NET_CLIENT_LIST"])
    ids = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", out)]
    titles = {}
    for wid in ids:
        t = sh(["xprop", "-id", hex(wid), "_NET_WM_NAME"])
        m = re.search(r'=\s*"(.*)"', t)
        titles[wid] = m.group(1) if m else ""
    return titles


class FocusJournal:
    """`xprop -root -spy _NET_ACTIVE_WINDOW` with CLOCK_MONOTONIC stamps (external)."""

    def __init__(self) -> None:
        self.events: list[tuple[int, int | None]] = []
        self.proc = subprocess.Popen(["xprop", "-root", "-spy", "_NET_ACTIVE_WINDOW"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            m = re.search(r"#\s*(0x[0-9a-fA-F]+)", line)
            self.events.append((mono_ns(), int(m.group(1), 16) if m else None))

    def stop(self) -> list[tuple[int, int | None]]:
        self.proc.terminate()
        with suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=3)
        return list(self.events)


# ----------------------------------------------------------------- bus monitor
def a11y_address() -> str:
    out = sh(["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
              "--method", "org.a11y.Bus.GetAddress"], timeout=10)
    m = re.search(r"'([^']+)'", out)
    if not m:
        raise RuntimeError("could not read the AT-SPI bus address")
    return m.group(1)


class BusMonitor:
    """dbus-monitor on the private AT-SPI bus; counts Action.DoAction method calls (external)."""

    def __init__(self, address: str, log_path: Path) -> None:
        self.log_path = log_path
        self.stream = open(log_path, "w")
        self.proc = subprocess.Popen(["dbus-monitor", "--address", address, "--monitor"],
                                     stdout=self.stream, stderr=subprocess.STDOUT)
        end = time.monotonic() + 3
        while time.monotonic() < end and log_path.stat().st_size == 0:
            time.sleep(0.005)
        time.sleep(0.03)

    def stop(self) -> dict[str, Any]:
        time.sleep(0.05)
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.stream.close()
        text = self.log_path.read_text(errors="replace")
        calls = re.findall(r"^method call .*member=(\w+)", text, flags=re.M)
        return {"do_action_on_bus": calls.count("DoAction"),
                "set_text_on_bus": calls.count("SetTextContents"),
                "method_calls": len(calls)}


# ------------------------------------------------------------- browser fixture
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
    return d;
  };
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {cx: r.left + r.width / 2, cy: r.top + r.height / 2};
  };
  const post = (kind, e, extra) => {
    const rec = {trial: TRIAL, seq: seq++, kind};
    if (e) {
      rec.is_trusted = e.isTrusted; rec.target = desc(e.target);
      if ("clientX" in e) { rec.client = [e.clientX, e.clientY]; rec.screen = [e.screenX, e.screenY]; }
    }
    if (extra) Object.assign(rec, extra);
    try { navigator.sendBeacon("/events", JSON.stringify(rec)); } catch (_) {}
  };
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"])
    window.addEventListener(type, (e) => post(type, e), true);
  let lastMove = 0;
  window.addEventListener("pointermove", (e) => {
    if (performance.now() - lastMove > 150) { lastMove = performance.now(); post("pointermove", e); }
  }, true);
  window.addEventListener("submit", (e) => post("submit", e), true);
  const auto = new URLSearchParams(location.search).get("auto");
  const ready = () => requestAnimationFrame(() => {
    post("load", null, {input: rect("input[name=value]"), button: rect("button[type=submit]"), dpr: devicePixelRatio});
    if (auto === "js") {
      // Negative control: a page-script fill + synthetic click (isTrusted false).
      document.querySelector("input[name=value]").value = "__TOKEN__";
      document.querySelector("button[type=submit]").click();
    }
  });
  if (document.readyState === "complete") ready(); else window.addEventListener("load", ready);
})();
</script>"""


def make_browser_server(wt: Path):
    sys.path.insert(0, str(wt / JEV_REL))
    from fixture_server import PAGE, FixtureHandler, FixtureServer  # noqa: E402

    class Handler(FixtureHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?")[0] == "/":
                pad = self.server.pad_px
                page = PAGE.replace(b"<main>", f'<main style="padding-top:{pad}px">'.encode())
                script = LISTENER.replace("__TRIAL__", self.server.trial).replace("__TOKEN__", self.server.js_token)
                body = page.replace(b"</html>", script.encode() + b"</html>")
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            recv = mono_ns()
            if self.path == "/events":
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    payload = json.loads(raw.decode() or "{}")
                except ValueError:
                    payload = {"unparsed": True}
                self.server.journal_add({"source": "page", "recv_mono_ns": recv, **payload})
                self._send(HTTPStatus.NO_CONTENT, "text/plain", b"")
                return
            if self.path == "/submit":
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                value = parse_qs(raw.decode()).get("value", [""])[0]
                self.server.journal_add({"source": "target", "kind": "submit_post", "recv_mono_ns": recv,
                                         "value": value})
                self.rfile = io.BytesIO(raw)
            super().do_POST()

    class Server(FixtureServer):
        def __init__(self) -> None:
            super().__init__(("127.0.0.1", 0))
            self.RequestHandlerClass = Handler
            self.trial = "none"
            self.pad_px = 0
            self.js_token = ""
            self._jlock = threading.Lock()
            self.journal: list[dict[str, Any]] = []

        def journal_add(self, rec: dict[str, Any]) -> None:
            with self._jlock:
                self.journal.append({"server_trial": self.trial, **rec})

        def journal_for(self, trial: str) -> list[dict[str, Any]]:
            # Page beacons carry the trial id the page was served with, so a late
            # beacon from an earlier page is never counted in a later trial.
            with self._jlock:
                return [r for r in self.journal if (r.get("trial") or r.get("server_trial")) == trial]

    return Server()


# ------------------------------------------------------------------ the trial
class Harness:
    """Session-level context: worktree, Driver binary, private root, imports."""

    def __init__(self, wt: Path, driver: Path, run_root: Path, *, bus_monitor: bool = True,
                 driver_label: str = "champion") -> None:
        self.wt = wt
        self.driver = driver
        self.driver_label = driver_label
        self.run_root = run_root
        self.private = run_root / "private"   # masked out of the Driver sandbox
        self.homes = run_root / "driver-homes"
        self.private.mkdir(parents=True, exist_ok=True)
        self.homes.mkdir(parents=True, exist_ok=True)
        (self.driver_environment, self.NativeObservation, self.eligible_controls,
         self.Driver, self.DriverToolError) = jev_imports(wt)
        self.session_root = ext.session_root()
        self.runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        self.bus_monitor = bus_monitor
        self.a11y = a11y_address() if bus_monitor else None
        self.browser_server = None

    def ensure_browser_server(self):
        if self.browser_server is None:
            self.browser_server = make_browser_server(self.wt)
            threading.Thread(target=self.browser_server.serve_forever, daemon=True).start()
        return self.browser_server

    def close(self) -> None:
        if self.browser_server is not None:
            self.browser_server.shutdown()
            self.browser_server.server_close()


async def _call(driver, rec_calls: list, name: str, arguments: dict[str, Any], DriverToolError) -> dict[str, Any]:
    t0 = mono_ns()
    entry: dict[str, Any] = {"tool": name, "t0_ns": t0}
    try:
        payload = await driver.call(name, arguments)
        entry["ok"] = True
        return_payload = payload
    except DriverToolError as exc:
        entry["ok"] = False
        entry["error_code"] = exc.code
        entry["error"] = str(exc)[:300]
        entry["t1_ns"] = mono_ns()
        rec_calls.append(entry)
        raise
    entry["t1_ns"] = mono_ns()
    entry["structured"] = {k: return_payload.get(k) for k in ("route", "effect", "path", "verified", "code",
                                                              "focus_outcome") if k in return_payload}
    rec_calls.append(entry)
    return return_payload


async def run_gtk_caller(h: Harness, kind: str, layout: dict, app: App, journal_path: Path,
                         trial_home: Path, errlog) -> dict[str, Any]:
    """The frozen scripted caller for one GTK trial. Returns the caller record."""
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    task = layout["task"]
    argv = sbx.driver_argv(h.driver, trial_home=trial_home, runtime_dir=h.runtime_dir,
                           private_roots=[h.private])
    env = sbx.driver_env(h.driver_environment(), trial_home)
    params = StdioServerParameters(command=argv[0], args=argv[1:], env=env)
    rec: dict[str, Any] = {"calls": [], "dispatch_count": 0, "outcome": None, "error_code": None,
                           "t_done_ns": None, "sandbox": "bwrap"}
    note_value = f"ar-{layout['seed']}-{secrets.token_hex(3)}" if task == "text" else None
    rec["note_value"] = note_value
    E = h.DriverToolError
    rec["t_spawn_ns"] = mono_ns()
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            rec["t_init_ns"] = mono_ns()
            driver = h.Driver(session, f"ar-{uuid.uuid4().hex[:8]}")
            calls = rec["calls"]
            window = None
            for _ in range(300):
                wins = (await _call(driver, calls, "list_windows", {"pid": app.pid}, E)).get("windows", [])
                hits = [w for w in wins if w.get("title") == layout["title"] and w.get("is_on_screen") is not False]
                if hits:
                    window = hits[0]
                    break
                await asyncio.sleep(0.05)
            if window is None:
                rec["outcome"] = "error"
                rec["error"] = "window_not_found"
                return rec
            wid = int(window["window_id"])
            target = {"pid": app.pid, "window_id": wid}

            async def observe():
                return await _call(driver, calls, "get_window_state", {
                    **target, "include_accessibility_tree": True, "include_screenshot": True}, E)

            def lookup(payload, labels):
                obs = h.NativeObservation.from_window_state(payload, expected_pid=app.pid, expected_window_id=wid)
                controls = h.eligible_controls(obs, "linux").controls
                found = {}
                for label in labels:
                    matches = [c for c in controls if c.label == label]
                    found[label] = matches[0] if len(matches) == 1 else None
                return obs, found

            def oracle_poll(deadline_s: float):
                end = time.monotonic() + deadline_s
                while time.monotonic() < end:
                    hit = orc.gtk_confirms(orc.read_journal(journal_path), task=task, nonce=app.nonce,
                                           app_pid=app.pid, initial=app.ready["initial"],
                                           expected_note=note_value)
                    if hit is not None:
                        return mono_ns(), hit
                    time.sleep(POLL_S)
                return None, None

            try:
                payload = await observe()
                if task == "checkbox":
                    labels = [layout["target_label"]]
                else:
                    labels = [layout["note_label"], layout["save_label"]]
                obs, found = lookup(payload, labels)
                if kind == "negative_no_action":
                    rec["outcome"] = "observed_only"
                    rec["t_done_ns"] = mono_ns()
                    return rec
                if kind == "negative_stale_token":
                    old = found[labels[0]]
                    await observe()  # publishes a replacement snapshot
                    rec["dispatch_count"] += 1
                    await _call(driver, calls, "click", {**target, "element_token": old.element_token,
                                                         "delivery_mode": "background"}, E)
                    # Accepted: the oracle decides whether anything happened.
                    t, hit = oracle_poll(UNKNOWN_DEADLINE_S)
                    rec["outcome"] = "verified" if hit else "unknown"
                    rec["t_done_ns"] = t
                    return rec
                if kind == "canary_disabled":
                    # The target was eligible when observed (fresh token); the app now makes
                    # it insensitive, so the dispatch is impossible. The Driver must refuse
                    # or do nothing, and the caller must not claim the effect.
                    if found[labels[0]] is None:
                        rec["outcome"] = "unknown"
                        rec["error"] = "target_not_found"
                        return rec
                    rec["canary_disable_ack"] = app.command("disable")
                    rec["dispatch_count"] += 1
                    await _call(driver, calls, "click", {**target, "element_token": found[labels[0]].element_token,
                                                         "delivery_mode": "background"}, E)
                    t, hit = oracle_poll(UNKNOWN_DEADLINE_S)
                    rec["outcome"] = "verified" if hit else "unknown"
                    rec["t_done_ns"] = t
                    return rec
                if not all(found.values()):
                    rec["outcome"] = "unknown"
                    rec["error"] = "target_not_found"
                    return rec
                if task == "checkbox":
                    rec["dispatch_count"] += 1
                    await _call(driver, calls, "click", {**target, "element_token": found[labels[0]].element_token,
                                                         "delivery_mode": "background"}, E)
                else:
                    rec["dispatch_count"] += 1
                    await _call(driver, calls, "set_value", {**target, "element_token": found[labels[0]].element_token,
                                                             "value": note_value}, E)
                    rec["dispatch_count"] += 1
                    await _call(driver, calls, "click", {**target, "element_token": found[labels[1]].element_token,
                                                         "delivery_mode": "background"}, E)
                rec["t_action_returned_ns"] = mono_ns()
                t, hit = oracle_poll(ORACLE_DEADLINE_S)
                rec["outcome"] = "verified" if hit else "unknown"
                rec["t_done_ns"] = t
            except E as exc:
                rec["outcome"] = "refused"
                rec["error_code"] = exc.code
                rec["error"] = str(exc)[:300]
                rec["t_done_ns"] = mono_ns()
            except Exception as exc:  # retained in the denominator
                rec["outcome"] = "error"
                rec["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            finally:
                # Outside T: one fresh observation for the cross-layer agreement check,
                # then the in-trial external snapshot while the Driver is still alive.
                with suppress(Exception):
                    if rec.get("outcome") in ("verified", "observed_only", "unknown", "refused"):
                        vp = await observe()
                        _, vfound = lookup(vp, labels)
                        if task == "checkbox" and vfound.get(labels[0]) is not None:
                            rec["fresh_observation_checked"] = vfound[labels[0]].selected
                        elif task == "text" and vfound.get(labels[0]) is not None:
                            rec["fresh_observation_value"] = vfound[labels[0]].value
                rec["external_during"] = ext.snapshot(h.session_root, _file_roots(h, trial_home))
    return rec


async def run_browser_caller(h: Harness, seed: int, trial_home: Path, errlog, trial_id: str) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    server = h.ensure_browser_server()
    url = f"http://127.0.0.1:{server.server_port}/?t={trial_id}"
    token = f"ar-{seed}-{secrets.token_hex(4)}"
    # No bwrap here: an unprivileged user namespace shows root-owned files as the
    # overflow uid, and the Driver's isolated launch requires a root-owned,
    # non-writable Chromium, so it refuses (browser_route_unavailable) inside the
    # sandbox. The oracle is the in-process server journal, not a file, so the
    # mask is not needed for provenance; HOME/TMPDIR still move to the trial home
    # so the file diff covers what the Driver and Chromium write there.
    env = sbx.driver_env(h.driver_environment(), trial_home)
    params = StdioServerParameters(command=str(h.driver), args=["mcp"], env=env)
    rec: dict[str, Any] = {"calls": [], "dispatch_count": 0, "outcome": None, "token": token, "t_done_ns": None,
                           "sandbox": "none: trial HOME only (root-owned Chromium check)"}
    E = h.DriverToolError
    rec["t_spawn_ns"] = mono_ns()
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            driver = h.Driver(session, f"ar-{uuid.uuid4().hex[:8]}")
            calls = rec["calls"]
            try:
                prep = await _call(driver, calls, "browser_prepare",
                                   {"allow_launch": True, "profile": {"mode": "isolated_new"}}, E)
                pid = int(prep["prepared_pid"])
                window = None
                for _ in range(200):
                    wins = (await _call(driver, calls, "list_windows", {"pid": pid}, E)).get("windows", [])
                    vis = [w for w in wins if w.get("is_on_screen")]
                    if vis:
                        window = max(vis, key=lambda w: w["bounds"]["width"] * w["bounds"]["height"])
                        break
                    await asyncio.sleep(0.05)
                if window is None:
                    raise RuntimeError("browser window did not appear")
                bound = await _call(driver, calls, "get_browser_state", {"pid": pid, "window_id": window["window_id"]}, E)
                tabs = bound.get("tabs") or []
                tab = next((t for t in tabs if t.get("active")), tabs[0])
                ids = {"target_id": bound["target_id"], "tab_id": str(tab["tab_id"])}
                await _call(driver, calls, "browser_navigate", {**ids, "url": url}, E)
                field_ref = submit_ref = None
                for _ in range(60):
                    snap = await _call(driver, calls, "get_browser_state", {**ids, "snapshot_format": "semantic_v2"}, E)
                    for item in snap.get("refs") or []:
                        if item.get("role") == "textbox" and item.get("name") == "verification value":
                            field_ref = item.get("ref")
                        if item.get("role") == "button" and item.get("name") == "Submit":
                            submit_ref = item.get("ref")
                    if field_ref and submit_ref:
                        break
                    await asyncio.sleep(0.05)
                if not (field_ref and submit_ref):
                    raise RuntimeError("fixture refs not found")
                rec["dispatch_count"] += 1
                await _call(driver, calls, "browser_type", {**ids, "ref": field_ref, "text": token, "replace": True}, E)
                rec["dispatch_count"] += 1
                await _call(driver, calls, "browser_click", {**ids, "ref": submit_ref, "delivery_mode": "foreground"}, E)
                rec["t_action_returned_ns"] = mono_ns()
                end = time.monotonic() + ORACLE_DEADLINE_S
                while time.monotonic() < end:
                    if server.state.snapshot().get("submitted") == token:
                        rec["t_done_ns"] = mono_ns()
                        break
                    time.sleep(POLL_S)
                rec["outcome"] = "verified" if rec["t_done_ns"] else "unknown"
            except E as exc:
                rec["outcome"] = "refused"
                rec["error_code"] = exc.code
                rec["error"] = str(exc)[:300]
            except Exception as exc:
                rec["outcome"] = "error"
                rec["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            finally:
                rec["external_during"] = ext.snapshot(h.session_root, _file_roots(h, trial_home))
    return rec


CHROME = "/opt/google/chrome/chrome"  # the binary the Driver's isolated launch selects here


def run_browser_selfcheck(h: Harness, kind: str, seed: int, trial_id: str, trial_home: Path) -> dict[str, Any]:
    """Driver-free validation of the browser fixture's oracle (no timing, no Driver).

    xdotool_trusted: the harness launches Chrome itself (sandbox on, throwaway
      profile) and fills + submits through XTest pointer/keyboard events, which the
      page sees as trusted. The oracle must verify it.
    js_untrusted: the page fills the field and calls button.click() from script
      (isTrusted false); the POST lands, and the oracle must NOT verify it.
    """
    server = h.ensure_browser_server()
    token = f"ar-{seed}-{secrets.token_hex(4)}"
    server.js_token = token if kind == "js_untrusted" else ""
    url = f"http://127.0.0.1:{server.server_port}/?t={trial_id}" + ("&auto=js" if kind == "js_untrusted" else "")
    rec: dict[str, Any] = {"token": token, "outcome": None, "t_done_ns": None, "dispatch_count": 0}
    rec["t_spawn_ns"] = mono_ns()
    log = open(h.private / "trials" / trial_id / "chrome.log", "w")
    chrome = subprocess.Popen([CHROME, f"--user-data-dir={trial_home / 'chrome'}", "--no-first-run",
                               "--no-default-browser-check", "--password-store=basic", "--disable-gpu",
                               "--window-position=10,10", "--window-size=945,1060", "--new-window", url],
                              stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                              env={**os.environ, "HOME": str(trial_home)}, start_new_session=True)
    try:
        def journal_kind(name: str):
            return [r for r in server.journal_for(trial_id) if r.get("kind") == name]

        end = time.monotonic() + 30
        while not journal_kind("load") and time.monotonic() < end:
            time.sleep(0.05)
        load = journal_kind("load")
        if not load:
            rec["outcome"] = "error"
            rec["error"] = "page did not load"
            return rec
        if kind == "xdotool_trusted":
            time.sleep(0.5)
            wins = sh(["xdotool", "search", "--onlyvisible", "--pid", str(chrome.pid)]).split()
            if not wins:
                wins = sh(["xdotool", "search", "--onlyvisible", "--class", "google-chrome"]).split()
            geo = dict(line.split("=", 1) for line in sh(["xdotool", "getwindowgeometry", "--shell", wins[-1]]).splitlines())
            cx, cy = int(geo["X"]) + int(geo["WIDTH"]) // 2, int(geo["Y"]) + int(geo["HEIGHT"]) // 2
            sh(["xdotool", "mousemove", str(cx), str(cy)])
            end = time.monotonic() + 5
            while not journal_kind("pointermove") and time.monotonic() < end:
                time.sleep(0.02)
                sh(["xdotool", "mousemove_relative", "--", "1", "1"])
            move = journal_kind("pointermove")[-1]
            off_x = move["screen"][0] - move["client"][0]
            off_y = move["screen"][1] - move["client"][1]
            field, button = load[0]["input"], load[0]["button"]
            rec["dispatch_count"] = 2
            sh(["xdotool", "mousemove", str(int(field["cx"] + off_x)), str(int(field["cy"] + off_y)), "click", "1"])
            time.sleep(0.15)
            sh(["xdotool", "type", "--delay", "5", token])
            time.sleep(0.15)
            sh(["xdotool", "mousemove", str(int(button["cx"] + off_x)), str(int(button["cy"] + off_y)), "click", "1"])
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if server.state.snapshot().get("submitted") == token:
                rec["t_done_ns"] = mono_ns()
                break
            time.sleep(POLL_S)
        rec["outcome"] = "submitted" if rec["t_done_ns"] else "unknown"
        time.sleep(LINGER_S)
    finally:
        with suppress(ProcessLookupError):
            os.killpg(chrome.pid, signal.SIGTERM)
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(chrome.pid, signal.SIGKILL)
            chrome.wait()
        log.close()
    return rec


def _file_roots(h: Harness, trial_home: Path) -> dict[str, Path]:
    # The private root is not listed: the sandbox mounts it as an empty read-only
    # tmpfs, so the Driver cannot write there (and the harness itself does).
    roots = {"driver_home": trial_home, "dev_shm": Path("/dev/shm")}
    if h.runtime_dir:
        roots["runtime"] = Path(h.runtime_dir)
    return roots


def run_trial(h: Harness, fixture: str, kind: str, seed: int, index: int, monitor: bool | None = None) -> dict[str, Any]:
    """One trial. ``fixture`` is 'gtk3_checkbox', 'gtk3_text' or 'browser'."""
    trial_id = f"{index:04d}-{fixture}-{kind}-{seed}"
    tdir = h.private / "trials" / trial_id
    tdir.mkdir(parents=True)
    state_dir = tdir / "state"
    state_dir.mkdir()
    trial_home = sbx.prepare_home(h.homes / trial_id)
    errlog = open(tdir / "driver-stderr.txt", "w")
    monitor = h.bus_monitor if monitor is None else monitor
    rec: dict[str, Any] = {"event": "trial", "trial": trial_id, "fixture": fixture, "kind": kind, "seed": seed,
                           "index": index, "driver_label": h.driver_label, "loadavg_start": loadavg()}
    apps: list[App] = []
    focus = None
    bus = None
    try:
        if fixture == "browser_selfcheck":
            server = h.ensure_browser_server()
            server.trial = trial_id
            server.pad_px = (seed * 37) % 240
            server.state.reset()
            caller = run_browser_selfcheck(h, kind, seed, trial_id, trial_home)
            journal = server.journal_for(trial_id)
            oracle = orc.evaluate_browser(journal, server.state.snapshot(), token=caller["token"],
                                          t_spawn_ns=caller["t_spawn_ns"], t_done_ns=caller.get("t_done_ns"))
            if kind == "xdotool_trusted":
                reasons = [] if oracle["verified"] else ["oracle rejected a real trusted fill+submit"]
            else:
                reasons = []
                if oracle["verified"]:
                    reasons.append("oracle accepted a synthetic (untrusted) click")
                if oracle["posts"] != 1 or not oracle["trusted_sequence"]["untrusted_click"]:
                    reasons.append("negative not exercised (no untrusted click + POST)")
            verdict = {"kind": f"browser_selfcheck_{kind}", "passed": not reasons, "reasons": reasons}
            rec["journal_kinds"] = [(r.get("source"), r.get("kind"), r.get("is_trusted")) for r in journal
                                    if r.get("kind") != "pointermove"]
            rec.update({"caller": caller, "oracle": oracle, "verdict": verdict})
            return rec
        if fixture == "browser":
            server = h.ensure_browser_server()
            server.trial = trial_id
            server.pad_px = (seed * 37) % 240
            server.state.reset()
            excluded = []
            pre = ext.snapshot(h.session_root, _file_roots(h, trial_home))
            caller = asyncio.run(run_browser_caller(h, seed, trial_home, errlog, trial_id))
            time.sleep(LINGER_S)
            post = ext.snapshot(h.session_root, _file_roots(h, trial_home))
            journal = server.journal_for(trial_id)
            oracle = orc.evaluate_browser(journal, server.state.snapshot(), token=caller["token"],
                                          t_spawn_ns=caller["t_spawn_ns"], t_done_ns=caller.get("t_done_ns"))
            verdict = orc.browser_control_verdict(caller, oracle)
            rec["journal_kinds"] = [(r.get("source"), r.get("kind"), r.get("is_trusted")) for r in journal]
        else:
            task = "checkbox" if fixture == "gtk3_checkbox" else "text"
            variant = orc.VARIANT_FOR_KIND[kind]
            layout = layout_for(task, seed, variant)
            if kind == "focus_steal":
                user = App("user", seed, "normal", None, tdir / "user-app.log", None)
                apps.append(user)
            nonce = secrets.token_hex(16)
            app = App(task, seed, variant, state_dir, tdir / "app.log", nonce)
            apps.append(app)
            rec["layout"] = app.ready["layout"]
            rec["initial"] = app.ready["initial"]
            rec["app_ready_ns"] = app.ready["t_ready_ns"]
            if kind == "focus_steal":
                sh(["xdotool", "windowactivate", "--sync", str(apps[0].ready["xid"])])
                time.sleep(0.2)
                rec["user_xid"] = apps[0].ready["xid"]
                rec["active_before"] = active_window()
                focus = FocusJournal()
            if monitor:
                bus = BusMonitor(h.a11y, tdir / "bus.log")
            excluded = [a.pid for a in apps] + ([bus.proc.pid] if bus else []) + ([focus.proc.pid] if focus else [])
            pre = ext.snapshot(h.session_root, _file_roots(h, trial_home), exclude_pids=excluded)
            journal_path = state_dir / "journal.jsonl"
            caller = asyncio.run(run_gtk_caller(h, kind, layout, app, journal_path, trial_home, errlog))
            # Linger: late duplicates (redispatch, delayed second effect) and the
            # focus-steal timeline must have played out before the final verdict.
            linger_until = time.monotonic() + LINGER_S
            while time.monotonic() < linger_until:
                time.sleep(0.02)
            post = ext.snapshot(h.session_root, _file_roots(h, trial_home), exclude_pids=excluded)
            extra: dict[str, Any] = {}
            if bus is not None:
                extra.update(bus.stop())
                bus = None
            if focus is not None:
                events = focus.stop()
                focus = None
                titles = client_titles()
                notice = [w for w, t in titles.items() if t == "Notice"]
                user_xid = rec["user_xid"]
                rec["focus_events"] = [((t - caller["t_spawn_ns"]) / 1e6, w) for t, w in events]
                rec["active_after"] = active_window()
                extra["steal_observed"] = any(w in notice for _, w in events)
                extra["focus_back_with_user"] = rec["active_after"] == user_xid
                rec["notice_windows"] = len(notice)
            records = orc.read_journal(journal_path)
            oracle = orc.evaluate_gtk(records, task=task, nonce=nonce, app_pid=app.pid, initial=app.ready["initial"],
                                      t_spawn_ns=caller["t_spawn_ns"], t_done_ns=caller.get("t_done_ns"),
                                      expected_note=caller.get("note_value"))
            verdict = orc.gtk_control_verdict(kind if fixture == "gtk3_checkbox" else "text_save", caller, oracle, extra)
            rec["extra"] = extra
        during = caller.pop("external_during")
        # The Driver root is the harness's own new child (bwrap, or the Driver itself).
        # Harness-owned helpers (fixture apps, bus monitor, focus spy) are not Driver work.
        ignore = sorted({a.pid for a in apps} | set(excluded))
        driver_root = None
        for pid, info in during["procs"].items():
            if int(info["ppid"]) == os.getpid() and pid not in pre["procs"] and pid not in ignore:
                driver_root = pid
        external = {"during": ext.diff(pre, during, ignore), "leftover": ext.diff(pre, post, ignore),
                    "driver_tree": ext.driver_tree(during, driver_root) if driver_root else None}
        external["signature"] = ext.signature(external)
        rec.update({"caller": caller, "oracle": oracle, "verdict": verdict, "external": external})
        done = caller.get("t_done_ns")
        rec["T_ms"] = (done - caller["t_spawn_ns"]) / 1e6 if done and caller.get("outcome") == "verified" else None
    except Exception as exc:
        rec["harness_error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
        rec["verdict"] = {"kind": kind, "passed": False, "reasons": ["harness_error"]}
    finally:
        if bus is not None:
            with suppress(Exception):
                bus.stop()
        if focus is not None:
            with suppress(Exception):
                focus.stop()
        for a in apps:
            a.stop()
        errlog.close()
        rec["loadavg_end"] = loadavg()
    return rec

#!/usr/bin/env python3
"""R2-09: native post-DoAction event wake on Chromium AT-SPI and GTK3 (measurement only).

Derived from the N-01R harness (``exp/n-01r-native-wait-ab-20261002``,
``n01r_harness.py``): one fresh Driver per trial, an independent 2 ms oracle
sampler on a target-owned state file, phase trace on, receipts logged but never
the oracle. Targets:

* ``chrome`` (T1): system Chrome launched by THIS harness with
  ``--force-renderer-accessibility``, a fresh ``--user-data-dir`` under the lane
  tmp dir, after ``org.a11y.Status IsEnabled=true`` is set on the PRIVATE session
  bus. The page is served by ``fixture_server.py``; its journal (state file) is
  the oracle. Actions go through the Driver's native AT-SPI tools
  (``get_window_state`` tree, ``element_token`` click / ``set_value``).
* ``gtk3`` (T2): the canonical GTK3 task fixture, as N-01R, with the delivery
  mode given per trial (FOREGROUND for T2).

Arms: B (defaults), S0 (sleep knob 0), EW (wake knob ``event``), and the
supplementary ``*_F0`` arms (focus-guard settle knob 0 on top) that isolate the
post-DoAction wait as the only post-action wait.

Runs INSIDE hostless + cua-x11-session.sh with a private AT-SPI bus and refuses
to run otherwise. No provider: any non-loopback TCP connect from this process is
refused and counted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xprobe  # noqa: E402

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use"
GTK_TITLE = "CuaTestHarness GTK3 Tasks"
GTK_SCHEMA = "cua.gtk3_task_state_v1"
WEB_SCHEMA = "cua.r209_web_state_v1"
WEB_TITLE = "R2-09 fixture"
CHROME = "/opt/google/chrome/chrome"
SLEEP_ENV = "CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS"
WAKE_ENV = "CUA_DRIVER_EXP_NATIVE_POST_ACTION_WAKE"
SETTLE_ENV = "CUA_DRIVER_EXP_FOCUS_GUARD_SETTLE_MS"
ARMS: dict[str, dict[str, str]] = {
    "B": {},
    "S0": {SLEEP_ENV: "0"},
    "EW": {WAKE_ENV: "event"},
    "B_F0": {SETTLE_ENV: "0"},
    "S0_F0": {SLEEP_ENV: "0", SETTLE_ENV: "0"},
    "EW_F0": {WAKE_ENV: "event", SETTLE_ENV: "0"},
}
STATE_PERIOD_S = 0.002
CONFIRM_DEADLINE_S = 3.0
POST_HOLD_S = 0.3
LABELS = {
    ("chrome", "checkbox"): ["I agree"],
    ("chrome", "text"): ["Note", "Save note"],
    ("chrome", "submit"): ["Save note"],
    ("chrome", "noop"): ["Do nothing"],
    ("gtk3", "checkbox"): ["I agree"],
    ("gtk3", "text"): ["Note", "Save note"],
}

# ----------------------------------------------------------------------------- no provider
NET = {"refused_non_loopback_connects": 0, "targets": []}
_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            NET["refused_non_loopback_connects"] += 1
            NET["targets"].append(str(host)[:64])
            raise ConnectionRefusedError("R2-09: provider cap 0, non-loopback connect refused")
    return _real_connect(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]


def now() -> tuple[int, int]:
    """(monotonic_ns, wall_ns) taken back to back."""
    return time.monotonic_ns(), time.time_ns()


def loadavg() -> list[float]:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return [float(x) for x in stream.read().split()[:3]]


def read_state(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def gdbus(*args: str, timeout: float = 5.0) -> dict[str, Any]:
    proc = subprocess.run(["gdbus", "call", "--session", *args], capture_output=True, text=True,
                          timeout=timeout)
    return {"rc": proc.returncode, "out": proc.stdout.strip()[:300], "err": proc.stderr.strip()[:300]}


def enable_session_a11y() -> dict[str, Any]:
    """org.a11y.Status IsEnabled=true on the PRIVATE session bus (this session's dbus)."""
    base = ["--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus", "--method"]
    set_ = gdbus(*base, "org.freedesktop.DBus.Properties.Set", "org.a11y.Status", "IsEnabled", "<true>")
    get = gdbus(*base, "org.freedesktop.DBus.Properties.Get", "org.a11y.Status", "IsEnabled")
    return {"set": set_, "get": get, "enabled": "true" in get["out"]}


def a11y_bus_daemon_pid() -> int | None:
    """pid of the private AT-SPI bus daemon: the child dbus-daemon of the
    at-spi-bus-launcher that owns org.a11y.Bus on THIS session's private bus."""
    proc = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                           "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.GetConnectionUnixProcessID",
                           "org.a11y.Bus"], capture_output=True, text=True, timeout=5)
    try:
        launcher = int(proc.stdout.strip().strip("()").rstrip(",").split()[-1].rstrip(","))
    except (ValueError, IndexError):
        return None
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except (OSError, ValueError, IndexError):
            continue
        if ppid == launcher and ("dbus-daemon" in cmd or "dbus-broker" in cmd):
            return int(entry.name)
    return None


def registry_pid() -> int | None:
    """pid owning org.a11y.atspi.Registry on THIS session's private AT-SPI bus."""
    addr = gdbus("--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus", "--method",
                 "org.a11y.Bus.GetAddress")
    out = addr["out"]
    if addr["rc"] != 0 or "'" not in out:
        return None
    address = out.split("'")[1]
    proc = subprocess.run(["gdbus", "call", "--address", address, "--dest", "org.freedesktop.DBus",
                           "--object-path", "/org/freedesktop/DBus", "--method",
                           "org.freedesktop.DBus.GetConnectionUnixProcessID", "org.a11y.atspi.Registry"],
                          capture_output=True, text=True, timeout=5)
    try:
        return int(proc.stdout.strip().strip("()").rstrip(",").split()[-1].rstrip(","))
    except (ValueError, IndexError):
        return None


class StateSampler(threading.Thread):
    """Independent oracle: reads the target-owned state file every 2 ms."""

    def __init__(self, path: Path, schema: str) -> None:
        super().__init__(daemon=True)
        self.path = path
        self.schema = schema
        self.stop_flag = threading.Event()
        self.t0: list[int] = []
        self.t1: list[int] = []
        self.idx: list[int] = []
        self.states: list[Any] = []
        self._index: dict[str, int] = {}
        self.expected: dict[str, Any] | None = None
        self.return_ns: int | None = None
        self.confirmed = threading.Event()
        self.on_change = None  # optional callback(state) on every NEW distinct content

    def matches(self, state: Any) -> bool:
        exp = self.expected
        return (isinstance(state, dict) and exp is not None and state.get("schema") == self.schema
                and all(state.get(k) == v for k, v in exp.items()))

    def run(self) -> None:
        start = time.monotonic_ns()
        k = 0
        period = int(STATE_PERIOD_S * 1e9)
        while not self.stop_flag.is_set():
            a = time.monotonic_ns()
            try:
                raw = self.path.read_text(encoding="utf-8")
            except OSError:
                raw = ""
            b = time.monotonic_ns()
            i = self._index.get(raw)
            if i is None:
                try:
                    parsed: Any = json.loads(raw) if raw else None
                except ValueError:
                    parsed = {"unparsable": raw[:80]}
                i = len(self.states)
                self._index[raw] = i
                self.states.append(parsed)
                if self.on_change is not None:
                    try:
                        self.on_change(parsed)
                    except Exception:  # noqa: BLE001 - a perturbation hook must not stop the oracle
                        pass
            self.t0.append(a)
            self.t1.append(b)
            self.idx.append(i)
            ret = self.return_ns
            if ret is not None and a >= ret and not self.confirmed.is_set() and self.matches(self.states[i]):
                self.confirmed.set()
            k += 1
            delay = (start + k * period - time.monotonic_ns()) / 1e9
            if delay > 0:
                time.sleep(delay)

    def stop(self, anchor_ns: int) -> dict[str, Any]:
        self.stop_flag.set()
        self.join(timeout=2)
        return {
            "anchor": "T0 (caller monotonic ns of the first observation send)",
            "anchor_ns": anchor_ns,
            "t0_us": [round((t - anchor_ns) / 1000) for t in self.t0],
            "t1_us": [round((t - anchor_ns) / 1000) for t in self.t1],
            "idx": self.idx,
            "states": self.states,
        }


def kill_group(proc: subprocess.Popen) -> None:
    """Terminate a child this harness started (own process group)."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.wait()


# ----------------------------------------------------------------------------- harness
async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402
    from run import Driver, DriverToolError  # noqa: E402

    sys.setswitchinterval(0.0005)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    block = next(b for b in plan["blocks"] if b["block"] == args.block)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    driver_bin = str(Path(args.driver).resolve())

    pre = xprobe.snapshot()
    a11y = enable_session_a11y()
    chrome_version = subprocess.run([CHROME, "--version"], capture_output=True, text=True,
                                    timeout=20).stdout.strip() if Path(CHROME).exists() else None
    meta = {
        "event": "meta", "block": args.block, "kind": block["kind"], "label": args.label,
        "display": os.environ.get("DISPLAY"), "x_clients_at_start": pre["clients"],
        "display_collision": bool(pre["clients"]), "loadavg": loadavg(), "wall_ns": time.time_ns(),
        "driver_bin_name": Path(driver_bin).name, "plan_sha256": args.plan_sha256,
        "driver_sha256": args.driver_sha256, "pid": os.getpid(), "session_a11y": a11y,
        "chrome_version": chrome_version, "registry_pid_at_start": registry_pid(),
    }
    ledger_path = out / "trials.jsonl"
    ledger = open(ledger_path, "w", encoding="utf-8")
    ledger.write(json.dumps(meta, sort_keys=True) + "\n")
    ledger.flush()
    if meta["display_collision"]:
        for t in block["trials"]:
            ledger.write(json.dumps({"event": "trial", **t, "failure": "display_collision",
                                     "oracle_verified": False}) + "\n")
        ledger.write(json.dumps({"event": "end", "failures": len(block["trials"]), "net": NET}) + "\n")
        ledger.close()
        return 3

    failures = 0

    async def run_trial(t: dict[str, Any]) -> dict[str, Any]:
        target_kind = t["target"]
        task = t["task"]
        kind = t["kind"]
        variant = t.get("variant", "main")
        delivery = t.get("delivery", "background")
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": loadavg(),
                               "display": os.environ.get("DISPLAY"), "w_begin": time.time_ns()}
        tdir = work / t["id"]
        if tdir.exists():
            shutil.rmtree(tdir)
        tdir.mkdir(parents=True)
        state_path = tdir / "state.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        procs: list[subprocess.Popen] = []
        logs = []
        sampler: StateSampler | None = None
        listener: subprocess.Popen | None = None
        anchor = None
        perturb: dict[str, Any] = {}
        token = f"r209-{t['id']}-{uuid.uuid4().hex[:6]}"

        def spawn(cmd: list[str], name: str, env: dict[str, str] | None = None) -> subprocess.Popen:
            log = open(tdir / f"{name}.log", "w", encoding="utf-8")
            logs.append((name, log))
            proc = subprocess.Popen(cmd, env=env or dict(os.environ), stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            procs.append(proc)
            return proc

        def wait_for(pred, what: str, timeout: float, proc: subprocess.Popen | None = None) -> None:
            deadline = time.monotonic() + timeout
            while not pred():
                if time.monotonic() > deadline or (proc is not None and proc.poll() is not None):
                    raise RuntimeError(f"{what} did not happen")
                time.sleep(0.02)

        env = driver_environment()
        for key in list(env):
            if key.startswith("CUA_DRIVER_EXP_") or key == "CUA_DRIVER_PHASE_TRACE_FILE":
                env.pop(key)
        env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
        env["DO_NOT_TRACK"] = "1"
        env.update(ARMS[t["arm"]])
        rec["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
        rec["driver_env_keys"] = sorted(env)
        try:
            if target_kind == "chrome":
                schema, title = WEB_SCHEMA, WEB_TITLE
                port_file = tdir / "port"
                server = spawn(["/usr/bin/python3", str(HERE / "fixture_server.py"), str(state_path),
                                str(port_file)], "server")
                wait_for(port_file.exists, "fixture server port", 10, server)
                port = int(port_file.read_text())
                if variant == "decoy":
                    ready = tdir / "decoy.ready"
                    spawn(["/usr/bin/python3", str(HERE / "decoy_gtk.py"), str(ready)], "decoy")
                    wait_for(ready.exists, "decoy window", 15)
                profile = tdir / "chrome-profile"
                profile.mkdir()
                app = spawn([CHROME, f"--user-data-dir={profile}", "--force-renderer-accessibility",
                             "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                             "--disable-component-update", "--disable-sync", "--disable-default-apps",
                             "--disable-features=Translate,MediaRouter,OptimizationHints",
                             "--password-store=basic", "--disable-gpu", "--window-position=0,0",
                             "--window-size=1200,900", f"http://127.0.0.1:{port}/?v={variant}"
                             + (f"&note={token}" if task == "submit" else "")], "chrome")
                wait_for(lambda: (read_state(state_path) or {}).get("loaded") is True, "page load", 30, app)
            else:
                schema, title = GTK_SCHEMA, GTK_TITLE
                fenv = dict(os.environ)
                fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
                app = spawn(["/usr/bin/python3", str(wt / FIXTURE_REL)], "fixture", fenv)
                wait_for(lambda: read_state(state_path) is not None, "fixture state", 15, app)
                time.sleep(1.0)  # AT-SPI registration settle (as R2-04 / N-01R)
            rec["app_pid"] = app.pid
            before = read_state(state_path) or {}
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    driver = Driver(session, f"r209-{uuid.uuid4().hex[:8]}")

                    async def find_window(pid: int) -> int:
                        for _ in range(120):
                            wins = (await driver.call("list_windows", {"pid": pid})).get("windows", [])
                            hits = [w for w in wins if title in str(w.get("title"))
                                    and w.get("is_on_screen") is not False]
                            if hits:
                                return int(hits[0]["window_id"])
                            await asyncio.sleep(0.25)
                        raise RuntimeError("target window did not appear")

                    window_id = await find_window(app.pid)
                    rec["window_id"] = window_id
                    target = {"pid": app.pid, "window_id": window_id}

                    async def timed(name: str, arguments: dict[str, Any], raw: bool = False) -> dict[str, Any]:
                        m0, w0 = now()
                        error = None
                        payload: dict[str, Any] = {}
                        content_text: list[str] = []
                        try:
                            if raw:
                                res = await session.call_tool(name, {**arguments, "session": driver.label})
                                payload = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                                content_text = [getattr(c, "text", "")[:400] for c in (res.content or [])]
                                if res.isError:
                                    error = {"code": payload.get("code"), "is_error": True}
                            else:
                                payload = await driver.call(name, arguments)
                        except DriverToolError as exc:
                            error = {"code": exc.code, "message": str(exc)[:400]}
                        m1, w1 = now()
                        return {"tool": name, "m0": m0, "w0": w0, "m1": m1, "w1": w1,
                                "wrapper_ms": (m1 - m0) / 1e6, "error": error, "payload": payload,
                                "content_text": content_text}

                    async def observe() -> tuple[dict[str, Any], dict[str, Any]]:
                        call = await timed("get_window_state", {
                            **target, "include_accessibility_tree": True, "include_screenshot": True})
                        p = call.pop("payload")
                        call["summary"] = {k: p.get(k) for k in (
                            "walk_elapsed_ms", "element_count", "nodes_visited", "snapshot_id", "degraded")}
                        call["summary"]["has_screenshot"] = "screenshot_mime_type" in p
                        return call, p

                    def lookup(payload: dict[str, Any], labels: list[str]):
                        m0, w0 = now()
                        found: dict[str, Any] = {}
                        controls: list[Any] = []
                        err = None
                        try:
                            view = payload
                            if target_kind == "chrome":
                                # jev-use rule 5 sends web content to its browser source; T1 acts on
                                # web content through the native AT-SPI tools on purpose, so only that
                                # rule is waived (rules 1-4 and the token requirement still apply).
                                view = dict(payload)
                                view["elements"] = [{k: v for k, v in e.items() if k != "in_web_content"}
                                                    for e in payload.get("elements", [])]
                            obs = NativeObservation.from_window_state(view, expected_pid=app.pid,
                                                                      expected_window_id=window_id)
                            controls = eligible_controls(obs, "linux").controls
                        except Exception as exc:  # noqa: BLE001 - recorded, trial fails
                            err = f"{type(exc).__name__}: {str(exc)[:200]}"
                        for label in labels:
                            matches = [c for c in controls if c.label == label]
                            found[label] = matches[0] if len(matches) == 1 else None
                        m1, w1 = now()
                        return {"m0": m0, "w0": w0, "m1": m1, "w1": w1, "lookup_ms": (m1 - m0) / 1e6,
                                "found": {k: v is not None for k, v in found.items()},
                                "n_controls": len(controls), "error": err,
                                "controls": [{"label": c.label, "role": getattr(c, "role", None)}
                                             for c in controls][:40]}, found

                    def shape(a: dict[str, Any]) -> dict[str, Any]:
                        p = a.pop("payload")
                        a["structured"] = {k: v for k, v in p.items()
                                           if k not in ("screenshot", "image", "tree", "elements")}
                        return a

                    labels = LABELS[(target_kind, task)]
                    # Pre-T readiness: the web content must be exposed (STEP 0 gate); poll the tree.
                    exposure = []
                    ready_by = time.monotonic() + (15 if target_kind == "chrome" else 3)
                    while True:
                        call, payload = await observe()
                        lk, found = lookup(payload, labels)
                        exposure.append({"element_count": call["summary"]["element_count"],
                                         "found": lk["found"], "n_controls": lk["n_controls"],
                                         "error": call["error"]})
                        if all(found.values()) or time.monotonic() > ready_by:
                            break
                        await asyncio.sleep(0.5)
                    rec["pre_exposure"] = exposure
                    if kind == "pilot":
                        rec["pilot_tree_markdown"] = str(payload.get("tree_markdown", ""))[:6000]
                        rec["pilot_controls"] = lk["controls"]
                    if not all(found.values()):
                        rec["failure"] = "target_not_exposed"
                        return rec
                    await asyncio.sleep(0.3)

                    sampler = StateSampler(state_path, schema)
                    if variant == "reconnect":
                        # Control (c): on the page's click report, restart this session's
                        # private at-spi2-registryd (a process this session started).
                        rpid = registry_pid()
                        perturb["registry_pid_before"] = rpid

                        def restart(state: Any) -> None:
                            if perturb.get("restarted") or not isinstance(state, dict) or not state.get("clicks"):
                                return
                            perturb["restarted"] = True
                            perturb["kill_m_ns"] = time.monotonic_ns()
                            if rpid:
                                os.kill(rpid, signal.SIGTERM)
                            new = subprocess.Popen(["/usr/lib/at-spi2-registryd", "--use-gnome-session"],
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                   start_new_session=True)
                            perturb["new_registry_pid"] = new.pid
                            perturb["spawn_m_ns"] = time.monotonic_ns()

                        sampler.on_change = restart
                    if variant == "busdrop":
                        # Control (c2): on the page's click report, terminate this session's
                        # private AT-SPI bus daemon (started by this session's bus launcher).
                        bpid = a11y_bus_daemon_pid()
                        perturb["a11y_bus_pid"] = bpid

                        def drop(state: Any) -> None:
                            if perturb.get("dropped") or not isinstance(state, dict) or not state.get("clicks"):
                                return
                            perturb["dropped"] = True
                            perturb["kill_m_ns"] = time.monotonic_ns()
                            if bpid:
                                os.kill(bpid, signal.SIGTERM)

                        sampler.on_change = drop
                    if kind.startswith("ctl") and variant != "busdrop":
                        lout = tdir / "listener.jsonl"
                        listener = subprocess.Popen(["/usr/bin/python3", str(HERE / "atspi_listener.py"),
                                                     str(lout), "--tag", t["id"]],
                                                    stdout=subprocess.DEVNULL, stderr=open(tdir / "listener.err", "w"),
                                                    start_new_session=True)
                        wait_for(lambda: lout.exists() and '"ready"' in lout.read_text(), "listener", 10, listener)
                    sampler.start()
                    while not sampler.t0:
                        await asyncio.sleep(0.001)
                    if task == "checkbox":
                        expected = {"agreed": not bool(before.get("agreed")), "seq": int(before.get("seq", 0)) + 1}
                    elif task in ("text", "submit"):
                        expected = {"note_saved": token, "seq": int(before.get("seq", 0)) + 1}
                    else:  # noop: the page must not change
                        expected = {"seq": int(before.get("seq", 0)), "agreed": bool(before.get("agreed"))}
                    sampler.expected = expected
                    rec["expected"] = expected
                    rec["before"] = {k: v for k, v in before.items() if k != "journal"}

                    t0m, t0w = now()
                    anchor = t0m
                    rec["T0_m"], rec["T0_w"] = t0m, t0w
                    tree, payload = await observe()
                    rec["tree"] = tree
                    lk, found = lookup(payload, labels)
                    rec["lookup"] = {k: v for k, v in lk.items() if k != "controls"}
                    actions: list[dict[str, Any]] = []
                    deliv = {"delivery_mode": delivery}
                    if tree["error"] or not all(found.values()):
                        rec["failure"] = "observe_error" if tree["error"] else "target_not_found"
                    elif task in ("checkbox", "noop", "submit"):
                        actions.append(shape(await timed("click", {
                            **target, "element_token": found[labels[0]].element_token, **deliv}, raw=True)))
                    else:
                        sv = shape(await timed("set_value", {
                            **target, "element_token": found["Note"].element_token, "value": token, **deliv},
                            raw=True))
                        actions.append(sv)
                        if sv["error"] is None:
                            actions.append(shape(await timed("click", {
                                **target, "element_token": found["Save note"].element_token, **deliv},
                                raw=True)))
                    rec["actions"] = actions
                    if actions:
                        sampler.return_ns = actions[-1]["m1"]
                        await asyncio.to_thread(sampler.confirmed.wait, CONFIRM_DEADLINE_S)
                    await asyncio.sleep(POST_HOLD_S)
                    rec["focus_post"] = {k: v for k, v in xprobe.snapshot().items() if k in ("focus", "active")}
        except Exception as exc:  # retained in the denominator
            rec["failure"] = rec.get("failure") or f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            if sampler is not None and sampler.is_alive():
                rec["state_samples"] = sampler.stop(anchor or time.monotonic_ns())
                rec["confirmed_live"] = sampler.confirmed.is_set()
            if listener is not None:
                listener.send_signal(signal.SIGTERM)
                try:
                    listener.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    listener.kill()
                    listener.wait()
                try:
                    rec["listener"] = [json.loads(x) for x in (tdir / "listener.jsonl").read_text().splitlines()
                                       if x.strip()]
                except (OSError, ValueError) as exc:
                    rec["listener_error"] = str(exc)[:200]
            final = read_state(state_path)
            rec["final_state"] = final
            for proc in reversed(procs):
                kill_group(proc)
            for _, log in logs:
                log.close()
            rec["perturb"] = perturb
            rec["app_logs"] = {name: (tdir / f"{name}.log").read_text(encoding="utf-8", errors="replace")[-1500:]
                               for name, _ in logs}
            try:
                rec["marks"] = [json.loads(x) for x in phase_path.read_text(encoding="utf-8").splitlines()
                                if x.strip()]
            except (OSError, ValueError) as exc:
                rec["marks"] = []
                rec["marks_error"] = str(exc)
            rec["w_end"] = time.time_ns()
            if variant == "reconnect":
                rec["registry_pid_after"] = registry_pid()
            shutil.rmtree(tdir / "chrome-profile", ignore_errors=True)
        return rec

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            r["oracle_verified"] = bool(r.get("confirmed_live")) and "failure" not in r
            failures += 0 if r.get("oracle_verified") else 1
            ledger.write(json.dumps(r, sort_keys=True) + "\n")
            ledger.flush()
    finally:
        ledger.write(json.dumps({"event": "end", "failures": failures, "loadavg": loadavg(),
                                 "wall_ns": time.time_ns(), "net": NET,
                                 "registry_pid_at_end": registry_pid()}, sort_keys=True) + "\n")
        ledger.close()
    print(f"done: {ledger_path} failures={failures} net_refused={NET['refused_non_loopback_connects']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("wt", "driver", "driver-sha256", "plan", "plan-sha256", "block", "label", "out", "work"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY")
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith("/run/user")
            or not os.environ.get("DBUS_SESSION_BUS_ADDRESS")):
        raise SystemExit("refusing: not inside hostless + the isolated X11 session")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

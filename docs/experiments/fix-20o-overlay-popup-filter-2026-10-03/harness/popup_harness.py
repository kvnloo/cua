#!/usr/bin/env python3
"""FIX-20O packet harness: the real-popup negative control and the tools/list integrity read.

Runs INSIDE hostless + cua-x11-session.sh (private Xvfb + openbox + picom, private AT-SPI bus);
refuses otherwise. No provider: non-loopback connects are refused and counted (harness_common).
The X helpers are the original OWN-20P ``xprobe.py`` / ``harness_common.py`` and FRESH-07's
``xtree.py`` (blob-identical under ../orig/), imported, not copied.

kind ``popup`` (row POPUP): a fresh fixture (``popup_fixture.py``: the canonical GTK3 task window plus
"Open menu") and a fresh Driver per trial. The user's focus is placed on a harness-owned decoy
toplevel (xprobe.Decoy); the Driver clicks "Open menu" by element_token with
``delivery_mode: background`` (the guarded AT-SPI route). The fixture presents its toplevel and pops
up a real GtkMenu holding the seat grab. Oracles (never the receipt alone):
  * the fixture's state file (menu_open, menu_window) and its own focus log (focuslog/sitecustomize);
  * an independent observer client: the 2 ms focus sampler (xprobe.FocusSampler) for the final input
    focus / _NET_ACTIVE_WINDOW, xtree.read() for the mapped override-redirect windows, and a core
    XGrabKeyboard probe (AlreadyGrabbed = some client holds the keyboard grab; released at once if
    it succeeded).
kind ``toolslist`` (row INTEGRITY): initialize + tools/list three times per binary; the canonical JSON
of the tool list is hashed.

usage: popup_harness.py --wt WT --plan PLAN --block B --label L --out DIR --work DIR NAME=BIN:SHA256 ...
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "orig" / "own-20p" / "harness"))
sys.path.insert(0, str(HERE.parent / "orig" / "fresh-07"))
import harness_common as hc  # noqa: E402
import xprobe  # noqa: E402
import xtree  # noqa: E402

FIXTURE = HERE / "popup_fixture.py"
CONFIRM_DEADLINE_S = 6.0
POST_HOLD_S = 0.7
SETTLE_QUIET_S = 0.3
SETTLE_CAP_S = 3.0
GUARD_TEXT = "A popup menu is open"

_x11 = ctypes.CDLL("libX11.so.6")
_x11.XOpenDisplay.restype = ctypes.c_void_p
_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_x11.XDefaultRootWindow.restype = ctypes.c_ulong
_x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
_x11.XGrabKeyboard.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_ulong]
_x11.XUngrabKeyboard.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
_x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
GRAB_STATUS = {0: "GrabSuccess", 1: "AlreadyGrabbed", 2: "GrabInvalidTime", 3: "GrabNotViewable", 4: "GrabFrozen"}


def keyboard_grab_probe() -> dict[str, Any]:
    """Independent read: can a fresh client grab the core keyboard? AlreadyGrabbed means another
    client holds it. A successful probe grab is released immediately."""
    dpy = _x11.XOpenDisplay(None)
    if not dpy:
        return {"error": "no display"}
    try:
        root = _x11.XDefaultRootWindow(dpy)
        status = int(_x11.XGrabKeyboard(dpy, root, 0, 1, 1, 0))
        if status == 0:
            _x11.XUngrabKeyboard(dpy, 0)
        _x11.XSync(dpy, 0)
        return {"status": GRAB_STATUS.get(status, str(status)), "held_by_other": status == 1}
    finally:
        _x11.XCloseDisplay(dpy)


def wait_focus_settled(sampler: xprobe.FocusSampler) -> dict[str, Any]:
    t0 = time.monotonic_ns()
    while True:
        changes = list(sampler.changes)
        nowns = time.monotonic_ns()
        if changes and nowns - changes[-1][0] >= SETTLE_QUIET_S * 1e9:
            last = changes[-1]
            return {"ok": True, "ref_ns": last[0], "focus": last[1], "active": last[2],
                    "waited_ms": round((nowns - t0) / 1e6, 3)}
        if nowns - t0 > SETTLE_CAP_S * 1e9:
            last = changes[-1] if changes else [0, 0, 0]
            return {"ok": False, "ref_ns": last[0], "focus": last[1], "active": last[2],
                    "waited_ms": round((nowns - t0) / 1e6, 3)}
        time.sleep(0.01)


def read_focus_log(state_path: Path) -> list[dict[str, Any]]:
    try:
        text = Path(str(state_path) + ".focus.jsonl").read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def canonical_tools(tools: Any) -> str:
    rows = []
    for t in tools:
        d = t.model_dump(mode="json", exclude_none=True) if hasattr(t, "model_dump") else dict(t)
        rows.append(d)
    return json.dumps(sorted(rows, key=lambda r: r.get("name", "")), sort_keys=True, separators=(",", ":"))


async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / hc.JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402

    sys.setswitchinterval(0.0005)
    plan_bytes = Path(args.plan).read_bytes()
    plan = json.loads(plan_bytes)
    block = next(b for b in plan["blocks"] if b["block"] == args.block)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    bins: dict[str, tuple[str, str]] = {}
    for spec in args.binaries:
        name, rest = spec.split("=", 1)
        path, sha = rest.rsplit(":", 1)
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if actual != sha:
            raise SystemExit(f"refusing: driver {name} sha256 {actual} != {sha}")
        bins[name] = (str(Path(path).resolve()), sha)

    pre = xprobe.snapshot()
    meta = {"event": "meta", "block": args.block, "kind": block["kind"], "label": args.label,
            "x_clients_at_start": pre["clients"], "display_collision": bool(pre["clients"]),
            "loadavg": hc.loadavg(), "wall_ns": time.time_ns(),
            "driver_sha256": {k: v[1] for k, v in bins.items()},
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(), "pid": os.getpid(),
            "focus_log_hook": os.environ.get("FIX20O_FOCUS_LOG") == "1"}
    ledger_path = out / "trials.jsonl"
    ledger = open(ledger_path, "w", encoding="utf-8")
    ledger.write(json.dumps(meta, sort_keys=True) + "\n")
    ledger.flush()
    if meta["display_collision"]:
        for t in block["trials"]:
            ledger.write(json.dumps({"event": "trial", **t, "failure": "display_collision",
                                     "oracle_verified": False}) + "\n")
        ledger.write(json.dumps({"event": "end", "failures": len(block["trials"]), "net": hc.NET}) + "\n")
        ledger.close()
        return 3
    decoy = xprobe.Decoy() if block["kind"] == "popup" else None
    failures = 0

    def driver_env_for(phase_path: Path) -> dict[str, str]:
        return hc.driver_env(driver_environment(), phase_path, {})

    async def toolslist_trial(t: dict[str, Any]) -> dict[str, Any]:
        driver_bin, driver_sha = bins[t["binary"]]
        rec: dict[str, Any] = {"event": "trial", **t, "driver_sha256": driver_sha, "loadavg": hc.loadavg()}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        env = driver_env_for(tdir / "phase.jsonl")
        params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
        try:
            with open(tdir / "driver.stderr", "w", encoding="utf-8") as errlog:
                async with stdio_client(params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write) as session:
                        init = await session.initialize()
                        rec["server_info"] = {"name": init.serverInfo.name, "version": init.serverInfo.version}
                        listed = await session.list_tools()
                        text = canonical_tools(listed.tools)
                        rec["tools_count"] = len(listed.tools)
                        rec["tools_sha256"] = hashlib.sha256(text.encode()).hexdigest()
                        rec["tool_names"] = sorted(x.name for x in listed.tools)
            rec["oracle_verified"] = True
        except Exception as exc:  # retained in the denominator
            rec["failure"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            rec["oracle_verified"] = False
        return rec

    async def popup_trial(t: dict[str, Any]) -> dict[str, Any]:
        assert decoy is not None
        driver_bin, driver_sha = bins[t["binary"]]
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": hc.loadavg(), "w_begin": time.time_ns(),
                               "driver_bin": Path(driver_bin).name, "driver_sha256": driver_sha,
                               "decoy_window": decoy.window}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        state_path = tdir / "state.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        fixture = None
        focus: xprobe.FocusSampler | None = None
        env = driver_env_for(phase_path)
        rec["driver_env_exp"] = sorted(k for k in env if k.startswith("CUA_DRIVER_EXP_"))
        try:
            fenv = dict(os.environ)
            fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
            fenv["FIX20O_FIXTURE_MAIN"] = str(wt / hc.FIXTURE_REL)
            flog = open(tdir / "fixture.log", "w", encoding="utf-8")
            fixture = subprocess.Popen(["/usr/bin/python3", str(FIXTURE)], env=fenv, stdout=flog,
                                       stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 15
            while hc.read_state(state_path) is None:
                if time.monotonic() > deadline or fixture.poll() is not None:
                    raise RuntimeError("fixture did not publish its state file")
                time.sleep(0.02)
            time.sleep(1.0)  # AT-SPI registration settle (as OWN-20G / OWN-20Q)
            before = hc.read_state(state_path) or {}
            rec["before"] = before
            rec["fixture_pid"] = fixture.pid
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
                    label = f"fix20o-{uuid.uuid4().hex[:8]}"

                    async def call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
                        res = await session.call_tool(tool, {**arguments, "session": label})
                        sc = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                        return {"is_error": bool(res.isError), "structured": sc,
                                "text": [getattr(c, "text", "")[:900] for c in (res.content or [])]}

                    window_id = None
                    for _ in range(60):
                        wins = (await call("list_windows", {"pid": fixture.pid}))["structured"].get("windows", [])
                        hits = [w for w in wins if w.get("title") == hc.WINDOW_TITLE and w.get("is_on_screen") is not False]
                        if hits:
                            window_id = int(hits[0]["window_id"])
                            break
                        await asyncio.sleep(0.25)
                    if window_id is None:
                        raise RuntimeError("task window did not appear")
                    rec["window_id"] = window_id
                    target = {"pid": fixture.pid, "window_id": window_id}
                    await call("set_agent_cursor_motion", {})
                    # The user works in another application: the decoy holds the focus.
                    rec["focus_placement"] = xprobe.activate_and_wait(decoy.window)
                    focus = xprobe.FocusSampler()
                    focus.start()
                    rec["focus_reference"] = await asyncio.to_thread(wait_focus_settled, focus)
                    rec["x_pre"] = xtree.read()
                    t0 = time.monotonic_ns()
                    rec["T0_m"] = t0
                    ws = await call("get_window_state", {**target, "include_accessibility_tree": True,
                                                         "include_screenshot": True})
                    obs = NativeObservation.from_window_state(ws["structured"], expected_pid=fixture.pid,
                                                              expected_window_id=window_id)
                    hits = [c for c in eligible_controls(obs, "linux").controls if c.label == "Open menu"]
                    if len(hits) != 1:
                        rec["failure"] = "target_not_found"
                    else:
                        m0 = time.monotonic_ns()
                        click = await call("click", {**target, "element_token": hits[0].element_token,
                                                     "delivery_mode": "background"})
                        rec["click"] = {"m0": m0, "m1": time.monotonic_ns(), "is_error": click["is_error"],
                                        "text": click["text"],
                                        "structured": {k: v for k, v in click["structured"].items()
                                                       if k not in ("screenshot", "image", "tree", "elements")}}
                        rec["x_after_reply"] = xtree.read()
                        end = time.monotonic() + CONFIRM_DEADLINE_S
                        state = hc.read_state(state_path) or {}
                        while time.monotonic() < end and not state.get("menu_open"):
                            await asyncio.sleep(0.005)
                            state = hc.read_state(state_path) or {}
                        rec["menu_confirmed_ns"] = time.monotonic_ns() if state.get("menu_open") else None
                        await asyncio.sleep(POST_HOLD_S)
                        rec["state_final"] = hc.read_state(state_path)
                        rec["x_final"] = xtree.read()
                        conn = xprobe.Conn()
                        try:
                            rec["x_final_or_pids"] = {str(w["window"]): conn.window_pid(w["window"])
                                                      for w in rec["x_final"].get("mapped_or", [])}
                        finally:
                            conn.close()
                        rec["grab_probe"] = keyboard_grab_probe()
        except Exception as exc:  # retained in the denominator
            rec["failure"] = rec.get("failure") or f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            if focus is not None:
                rec["focus_samples"] = focus.stop()
            rec["fixture_rc"] = hc.stop_process(fixture)
            rec["focus_log"] = read_focus_log(state_path)
            try:
                rec["fixture_log"] = (tdir / "fixture.log").read_text(encoding="utf-8", errors="replace")[-2000:]
            except OSError:
                rec["fixture_log"] = ""
            rec["marks"] = hc.read_marks(phase_path)
            rec["w_end"] = time.time_ns()
        sf = rec.get("state_final") or {}
        rec["oracle_verified"] = bool("failure" not in rec and sf.get("menu_open") and sf.get("menu_window"))
        return rec

    try:
        for t in block["trials"]:
            r = await (popup_trial(t) if t["kind"] == "popup" else toolslist_trial(t))
            failures += 0 if r.get("oracle_verified") else 1
            ledger.write(json.dumps(r, sort_keys=True) + "\n")
            ledger.flush()
    finally:
        if decoy is not None:
            decoy.close()
        ledger.write(json.dumps({"event": "end", "failures": failures, "loadavg": hc.loadavg(),
                                 "wall_ns": time.time_ns(), "net": hc.NET}, sort_keys=True) + "\n")
        ledger.close()
    print(f"done: {ledger_path} failures={failures} net_refused={hc.NET['refused_non_loopback_connects']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("wt", "plan", "block", "label", "out", "work"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("binaries", nargs="+")
    args = parser.parse_args()
    hc.refuse_outside_session()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

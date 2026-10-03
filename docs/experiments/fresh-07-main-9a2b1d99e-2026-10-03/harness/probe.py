#!/usr/bin/env python3
"""FRESH-07 Phase 1c: X11 agent-cursor overlay map-state probe (FIXTURE fact, not timing).

Runs INSIDE hostless + cua-x11-session.sh (private Xvfb, openbox, picom, private session bus and
AT-SPI bus). Refuses otherwise. No provider: any non-loopback TCP connect is refused and counted.

For each run: a fresh GTK3 task fixture (the repository fixture) and a fresh Driver (`mcp` over
stdio, product defaults, no CUA_DRIVER_EXP_* variable, telemetry off). The independent oracle is
the private X server's window tree (xtree.py, a separate libX11 client). States per run:
  S0  spawn -> overlay transitions (2 ms poller) and the MCP initialize reply time
  S1  idle (after initialize, list_windows, set_agent_cursor_motion {}, 300 ms quiet)
  S2  feedback on: get_window_state, background click on 'I agree' by element_token; tree read
      right after the reply and 1.5 s later
  S3  feedback off: set_agent_cursor_enabled {enabled:false}; tree read; get_window_state; the same
      click; tree read right after the reply and 1.5 s later
usage: probe.py --wt <worktree> --out <dir> --runs 5 NAME=BIN:SHA256 [NAME=BIN:SHA256 ...]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xtree  # noqa: E402

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use"
WINDOW_TITLE = "CuaTestHarness GTK3 Tasks"
NET = {"refused_non_loopback_connects": 0}
_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            NET["refused_non_loopback_connects"] += 1
            raise ConnectionRefusedError("FRESH-07: provider cap 0")
    return _real_connect(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]


def read_state(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


GUARD_KEYS = ("focus_changed", "focus_restored", "focus_outcome", "grab_held_by", "focus_changes",
              "path", "route", "effect", "verified")


async def run_one(wt: Path, name: str, binary: str, rep: int, out: Path) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment
    from native import NativeObservation, eligible_controls

    rid = f"{name}-r{rep}"
    tdir = out / "work" / rid
    tdir.mkdir(parents=True, exist_ok=True)
    state_path = tdir / "state.json"
    rec: dict[str, Any] = {"run": rid, "binary": name, "rep": rep, "loadavg_start": os.getloadavg(),
                           "x_before": xtree.read()}
    fenv = dict(os.environ)
    fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
    flog = open(tdir / "fixture.log", "w", encoding="utf-8")
    fixture = subprocess.Popen(["/usr/bin/python3", str(wt / FIXTURE_REL)], env=fenv, stdout=flog,
                               stderr=subprocess.STDOUT)
    poller = xtree.Poller()
    label = f"fresh07-{uuid.uuid4().hex[:8]}"
    try:
        deadline = time.monotonic() + 15
        while read_state(state_path) is None:
            if time.monotonic() > deadline or fixture.poll() is not None:
                raise RuntimeError("fixture did not publish its state file")
            time.sleep(0.02)
        time.sleep(1.0)
        rec["state_initial"] = read_state(state_path)
        env = driver_environment()
        for key in list(env):
            if key.startswith("CUA_DRIVER_EXP_") or key == "CUA_DRIVER_PHASE_TRACE_FILE":
                env.pop(key)
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
        env["DO_NOT_TRACK"] = "1"
        rec["driver_env_exp"] = sorted(k for k in env if k.startswith("CUA_DRIVER_EXP_"))
        params = StdioServerParameters(command=binary, args=["mcp"], env=env)
        errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
        poller.start()
        t_spawn = time.monotonic_ns()
        rec["t_spawn_ns"] = t_spawn
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                rec["t_init_reply_ns"] = time.monotonic_ns()

                async def call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
                    res = await session.call_tool(tool, {**args, "session": label})
                    sc = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                    return {"is_error": bool(res.isError), "structured": sc,
                            "text": [getattr(c, "text", "")[:600] for c in (res.content or [])]}

                pid = fixture.pid
                window_id = None
                for _ in range(60):
                    wins = (await call("list_windows", {"pid": pid}))["structured"].get("windows", [])
                    hits = [w for w in wins if w.get("title") == WINDOW_TITLE and w.get("is_on_screen") is not False]
                    if hits:
                        window_id = int(hits[0]["window_id"])
                        break
                    await asyncio.sleep(0.25)
                if window_id is None:
                    raise RuntimeError("task window did not appear")
                target = {"pid": pid, "window_id": window_id}
                rec["window_id"] = window_id
                await call("set_agent_cursor_motion", {})
                await asyncio.sleep(0.3)
                rec["S1_idle"] = xtree.read()

                async def token_for(label_text: str) -> str | None:
                    ws = await call("get_window_state", {**target, "include_accessibility_tree": True,
                                                         "include_screenshot": True})
                    obs = NativeObservation.from_window_state(ws["structured"], expected_pid=pid,
                                                              expected_window_id=window_id)
                    hits = [c for c in eligible_controls(obs, "linux").controls if c.label == label_text]
                    return hits[0].element_token if len(hits) == 1 else None

                async def click_phase(prefix: str) -> None:
                    before = read_state(state_path) or {}
                    tok = await token_for("I agree")
                    rec[f"{prefix}_pre"] = xtree.read()
                    if tok is None:
                        rec[f"{prefix}_failure"] = "target_not_found"
                        return
                    c = await call("click", {**target, "element_token": tok, "delivery_mode": "background"})
                    rec[f"{prefix}_after"] = xtree.read()
                    rec[f"{prefix}_click"] = {"is_error": c["is_error"], "text": c["text"],
                                              "guard": {k: c["structured"].get(k) for k in GUARD_KEYS
                                                        if k in c["structured"]}}
                    t_end = time.monotonic() + 3.0
                    after = read_state(state_path) or {}
                    while time.monotonic() < t_end and after.get("seq") == before.get("seq"):
                        await asyncio.sleep(0.01)
                        after = read_state(state_path) or {}
                    rec[f"{prefix}_oracle"] = {
                        "agreed_before": before.get("agreed"), "agreed_after": after.get("agreed"),
                        "seq_before": before.get("seq"), "seq_after": after.get("seq"),
                        "verified": after.get("seq") == (before.get("seq") or 0) + 1
                        and after.get("agreed") == (not bool(before.get("agreed")))}
                    await asyncio.sleep(1.5)
                    rec[f"{prefix}_settled"] = xtree.read()

                await click_phase("S2_on")
                rec["S3_disable"] = await call("set_agent_cursor_enabled", {"enabled": False})
                await asyncio.sleep(0.3)
                rec["S3_disabled_idle"] = xtree.read()
                await click_phase("S3_off")
        rec["x_after_driver_exit"] = xtree.read()
    except Exception as exc:  # retained in the denominator
        rec["failure"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        rec["poller"] = poller.stop() if poller.is_alive() else {"samples": 0, "transitions": []}
        fixture.terminate()
        try:
            fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fixture.kill()
            fixture.wait()
        flog.close()
        rec["loadavg_end"] = os.getloadavg()
    return rec


async def main_async(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bins = []
    for spec in args.binaries:
        name, rest = spec.split("=", 1)
        path, sha = rest.rsplit(":", 1)
        actual = sha256_file(path)
        if actual != sha:
            print(f"refusing: {name} sha256 {actual} != {sha}", file=sys.stderr)
            return 98
        bins.append((name, path, sha))
    versions = {}
    for name, path, _ in bins:
        versions[name] = subprocess.run([path, "--version"], capture_output=True, text=True).stdout.strip()
    meta = {"event": "meta", "display_set": bool(os.environ.get("DISPLAY")),
            "atspi": os.environ.get("CUA_SESSION_ATSPI"), "binaries": {n: s for n, _, s in bins},
            "versions": versions, "runs": args.runs, "start_wall": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ledger = open(out / "probe.jsonl", "w", encoding="utf-8")
    ledger.write(json.dumps(meta, sort_keys=True) + "\n")
    failures = 0
    for rep in range(1, args.runs + 1):
        order = bins[(rep - 1) % len(bins):] + bins[:(rep - 1) % len(bins)]  # rotate the order per rep
        for name, path, _ in order:
            rec = await run_one(wt, name, path, rep, out)
            failures += 1 if "failure" in rec else 0
            ledger.write(json.dumps({"event": "run", **rec}, sort_keys=True) + "\n")
            ledger.flush()
            print(f"[probe] {rec['run']} failure={rec.get('failure')}", flush=True)
    ledger.write(json.dumps({"event": "end", "failures": failures, "net": NET,
                             "end_wall": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
    ledger.close()
    return 0 if failures == 0 else 3


def main() -> None:
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        print("refusing: not inside the isolated X11 session", file=sys.stderr)
        sys.exit(97)
    for v in ("CUA_DRIVER_PERMISSION_MODE", "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
              "CUA_E2E_BROWSER_NO_SANDBOX", "TYPESAFE_API_KEY"):
        if os.environ.get(v):
            print(f"refusing: {v} set", file=sys.stderr)
            sys.exit(96)
    ap = argparse.ArgumentParser()
    ap.add_argument("--wt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("binaries", nargs="+")
    sys.exit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()

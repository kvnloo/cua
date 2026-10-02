#!/usr/bin/env python3
"""R2-10R drift row D1: first-snapshot timeout grace on the canonical GTK3 fixture (measurement only).

trycua/cua PR 4375 (in upstream main 0f1955d2f) gives a Linux window's FIRST get_window_state a
2000 ms walk budget when the caller omits ``timeout_ms`` (``linux_snapshot_timeout_ms`` ->
``tool_schema::resolve_timeout_ms_with_first_snapshot_grace``, keyed on
``SnapshotStore::contains_semantic_window``). An explicit ``timeout_ms`` keeps the shared clamp.

Arms (same binary R', same fixture, phase trace on as in every R2-10 arm):
  G  first get_window_state of a fresh window with timeout_ms OMITTED (grace path, 2000 ms budget)
  E  first get_window_state of a fresh window with explicit timeout_ms=1000

Each trial: fresh GTK3 fixture process (fresh CUA_GTK3_TASK_STATE file), fresh Driver process,
list_windows to find the task window, set_agent_cursor_motion {} (BASE pre-T call), then
T0 = send of the observation; T = its return (caller CLOCK_MONOTONIC). Recorded per trial: the
Driver-reported resolved ``timeout_ms`` (forced-path check: G 2000, E 1000), ``walk_elapsed_ms``,
``truncated``/``truncation_reason``, ``nodes_visited``/``nodes_pending``, ``element_count``,
``elements_complete``, an elements digest (sha256 of the canonical JSON of ``elements`` with every
key naming a token or snapshot removed, those being per-snapshot), a tree_markdown digest with
the same rule applied to element tokens, and the phase-trace marks. A second get_window_state with
``timeout_ms`` omitted follows outside T (control: the grace must not apply to a window that
already has a semantic snapshot, so it must report the 1000 ms default) together with the app's
state file before/after (the observation must not mutate the app).

Reuses the accepted N-01R harness helpers (harness/src/n-01r-native-wait-ab-2026-10-02/n01r_harness.py,
unchanged; importing it installs its non-loopback connect refusal).

usage (inside hostless + hostless-strict + cua-x11-session.sh with AT-SPI, via in_session.sh):
  d1_drift.py --wt <wt> --driver <bin> --driver-sha256 <sha> --block d1|d1k --label <label>
              --out <dir> --work <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src" / "n-01r-native-wait-ab-2026-10-02"))
import n01r_harness as h  # noqa: E402  (socket guard, fixture constants, helpers)

PAIRS = 20
ARM_ARGS = {"G": {}, "E": {"timeout_ms": 1000}}
EXPECTED_TIMEOUT = {"G": 2000, "E": 1000}
VOLATILE = re.compile(r"token|snapshot", re.I)


def plan(block: str) -> list[dict[str, Any]]:
    if block == "d1k":  # shakedown before the PREREG commit (not analysed)
        return [{"id": "d1k-001", "arm": "G", "pair": 0, "pos": 1}, {"id": "d1k-002", "arm": "E", "pair": 0, "pos": 2}]
    out = []
    for p in range(PAIRS):
        order = ["G", "E"] if p % 2 == 0 else ["E", "G"]
        for pos, arm in enumerate(order, start=1):
            out.append({"id": f"{block}-{len(out) + 1:03d}", "arm": arm, "pair": p, "pos": pos,
                        "order": "".join(order)})
    return out


def strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in sorted(value.items()) if not VOLATILE.search(k)}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    keys = ("timeout_ms", "walk_elapsed_ms", "truncated", "truncation_reason", "nodes_visited", "nodes_pending",
            "element_count", "elements_complete", "bounds_complete", "snapshot_id")
    out = {k: payload.get(k) for k in keys}
    elements = payload.get("elements")
    out["elements_n"] = len(elements) if isinstance(elements, list) else None
    out["elements_digest"] = digest(strip_volatile(elements)) if isinstance(elements, list) else None
    md = payload.get("tree_markdown")
    if isinstance(md, str):
        md = re.sub(r"element_token[\"'=: ]+[^\s\"',\]]+", "element_token=<t>", md)
    out["tree_markdown_digest"] = digest(md) if isinstance(md, str) else None
    out["has_screenshot"] = "screenshot_mime_type" in payload
    out["payload_keys"] = sorted(payload)[:60]
    return out


async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / h.JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from run import Driver, DriverToolError  # noqa: E402

    sys.setswitchinterval(0.0005)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    driver_bin = str(Path(args.driver).resolve())
    fixture_path = str(wt / h.FIXTURE_REL)
    ledger = open(out / "trials.jsonl", "w", encoding="utf-8")
    ledger.write(json.dumps({"event": "meta", "block": args.block, "label": args.label,
                             "display": os.environ.get("DISPLAY"), "loadavg": h.loadavg(), "wall_ns": time.time_ns(),
                             "driver_bin_name": Path(driver_bin).name, "driver_sha256": args.driver_sha256,
                             "pairs": PAIRS, "arm_args": ARM_ARGS}, sort_keys=True) + "\n")
    ledger.flush()
    failures = 0

    async def trial(t: dict[str, Any]) -> dict[str, Any]:
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": h.loadavg(), "w_begin": time.time_ns()}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        state_path = tdir / "state.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        fenv = dict(os.environ)
        fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
        fixture_log = open(tdir / "fixture.log", "w", encoding="utf-8")
        proc = subprocess.Popen(["/usr/bin/python3", fixture_path], env=fenv, stdout=fixture_log,
                                stderr=subprocess.STDOUT)
        env = driver_environment()
        for key in list(env):
            if key.startswith("CUA_DRIVER_EXP_") or key == "CUA_DRIVER_PHASE_TRACE_FILE":
                env.pop(key)
        env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
        env["DO_NOT_TRACK"] = "1"
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
        rec["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
        try:
            deadline = time.monotonic() + 15
            while h.read_state(state_path) is None:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise RuntimeError("fixture did not publish its state file")
                time.sleep(0.02)
            time.sleep(1.0)  # AT-SPI registration settle (as R2-04 / N-01R)
            rec["state_before"] = h.read_state(state_path)
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    driver = Driver(session, f"d1-{uuid.uuid4().hex[:8]}")
                    window_id = None
                    for _ in range(60):
                        wins = (await driver.call("list_windows", {"pid": proc.pid})).get("windows", [])
                        hits = [w for w in wins if w.get("title") == h.WINDOW_TITLE and w.get("is_on_screen") is not False]
                        if hits:
                            window_id = int(hits[0]["window_id"])
                            break
                        await asyncio.sleep(0.25)
                    if window_id is None:
                        raise RuntimeError("task window did not appear")
                    rec["window_id"] = window_id
                    target = {"pid": proc.pid, "window_id": window_id}
                    await driver.call("set_agent_cursor_motion", {})

                    async def observe(extra: dict[str, Any]) -> dict[str, Any]:
                        m0 = time.monotonic_ns()
                        error = None
                        payload: dict[str, Any] = {}
                        try:
                            payload = await driver.call("get_window_state", {
                                **target, "include_accessibility_tree": True, "include_screenshot": True, **extra})
                        except DriverToolError as exc:
                            error = {"code": exc.code, "message": str(exc)[:300]}
                        m1 = time.monotonic_ns()
                        return {"m0": m0, "m1": m1, "T_ms": (m1 - m0) / 1e6, "error": error,
                                "args": sorted(extra.items()), "summary": summarize(payload)}

                    rec["T0_m"] = time.monotonic_ns()
                    rec["first"] = await observe(dict(ARM_ARGS[t["arm"]]))
                    rec["second"] = await observe({})
                    rec["state_after"] = h.read_state(state_path)
        except Exception as exc:  # retained in the denominator
            rec["failure"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            fixture_log.close()
            try:
                rec["marks"] = [json.loads(x) for x in phase_path.read_text(encoding="utf-8").splitlines() if x.strip()]
            except (OSError, ValueError) as exc:
                rec["marks"] = []
                rec["marks_error"] = str(exc)
            rec["w_end"] = time.time_ns()
        f = rec.get("first") or {}
        s = f.get("summary") or {}
        rec["forced_path_ok"] = bool(s.get("timeout_ms") == EXPECTED_TIMEOUT[t["arm"]]
                                     and ((rec.get("second") or {}).get("summary") or {}).get("timeout_ms") == 1000)
        rec["valid"] = bool("failure" not in rec and not f.get("error") and rec["forced_path_ok"]
                            and s.get("elements_digest") and rec.get("state_before") == rec.get("state_after"))
        return rec

    try:
        for t in plan(args.block):
            r = await trial(t)
            failures += 0 if r["valid"] else 1
            ledger.write(json.dumps(r, sort_keys=True) + "\n")
            ledger.flush()
    finally:
        ledger.write(json.dumps({"event": "end", "failures": failures, "loadavg": h.loadavg(),
                                 "wall_ns": time.time_ns(), "net": h.NET}, sort_keys=True) + "\n")
        ledger.close()
    print(f"done: block={args.block} failures={failures} net_refused={h.NET['refused_non_loopback_connects']}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wt", required=True)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-sha256", required=True)
    p.add_argument("--block", required=True, choices=("d1", "d1k"))
    p.add_argument("--label", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--work", required=True)
    args = p.parse_args()
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY") or os.environ.get("R2_10_OUTER_HOSTLESS") != "1"
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith("/run/user")):
        raise SystemExit("refusing: not inside hostless + the isolated X11 session")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

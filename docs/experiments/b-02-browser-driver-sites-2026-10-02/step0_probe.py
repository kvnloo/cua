"""B-02 STEP 0: REAL localization of the three B-01 sites (excluded from every gate).

Run inside the isolated X11 session, under quiet-timed (EXCLUSIVE), with the jev-use venv:

    JEV_USE_DIR=<jev-use> <venv>/python step0_probe.py --driver <bin> --out <dir> --per-class 5

One trial = one fresh ``cua-driver mcp`` with the phase trace on and every knob unset:
prepare isolated_new, bind, then on the class page:

  A  navigate -> Driver snapshot A1 -> Driver snapshot A2 (same document)
     -> second OS process (raw CDP client, new connection + new session) on the warm document
  B  re-navigate (new document) -> Driver snapshot B1 -> B2
  C  re-navigate -> second OS process FIRST on the cold document -> Driver snapshot C1
  D  re-navigate -> wait 1000 ms -> Driver snapshot D1
  E  a second ``cua-driver mcp`` process tries to bind the same browser window

Every Driver call carries CLOCK_MONOTONIC marks (endpoint and admission sub-spans
included); the raw client times each CDP call of the snapshot sequence itself.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_critpath as rc  # noqa: E402  (loopback-only socket guard + jev-use imports)
from cdp_raw import devtools_ports_for_pid, http_get_json  # noqa: E402

KNOB_ENVS = ("CUA_DRIVER_EXP_ENDPOINT_REPROOF", "CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE",
             "CUA_DRIVER_EXP_CDP_WARM", rc.KNOB_ENV)
RAW_CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from cdp_raw import CdpClient, page_target, timed_semantic_sequence
c = CdpClient(sys.argv[2])
tid = page_target(c, sys.argv[3])
out = timed_semantic_sequence(c, tid)
c.close()
print(json.dumps(out))
"""


def raw_second_process(ws_url: str, page_url: str) -> dict[str, Any]:
    t = time.monotonic_ns()
    proc = subprocess.run([sys.executable, "-c", RAW_CHILD, str(HERE), ws_url, page_url],
                          capture_output=True, text=True, timeout=30)
    wall = (time.monotonic_ns() - t) / 1e6
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()[-300:], "wall_ms": wall}
    return {**json.loads(proc.stdout), "wall_ms": wall}


async def second_driver_bind(args: argparse.Namespace, env: dict[str, str], pid: int, window_id: int) -> dict[str, Any]:
    params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    async with rc.stdio_client(params) as (read, write):
        async with rc.ClientSession(read, write) as session:
            await session.initialize()
            raw = await session.call_tool("get_browser_state", {"pid": pid, "window_id": window_id,
                                                                "session": f"b02-second-{uuid.uuid4().hex[:6]}"})
            sc = raw.structuredContent if isinstance(raw.structuredContent, dict) else {}
            refusal = sc.get("refusal") if isinstance(sc.get("refusal"), dict) else {}
            return {"is_error": bool(raw.isError), "status": sc.get("status"), "effect": sc.get("effect"),
                    "code": sc.get("code") or refusal.get("code"), "has_target": "target_id" in sc}


async def probe_trial(args: argparse.Namespace, fixtures: Any, cls: str, name: str, out: Path) -> dict[str, Any]:
    rec = rc.Recorder()
    trace_rel = f"trials/{name}.driver-trace.jsonl"
    env = rc.driver_environment()
    for k in KNOB_ENVS:
        env.pop(k, None)
    env[rc.TRACE_ENV] = str(out / trace_rel)
    url = fixtures.page_url(cls)
    res: dict[str, Any] = {"trial": name, "cls": cls, "loadavg_before": rc.loadavg(), "driver_trace": trace_rel}
    label = f"jev-b02s0-{uuid.uuid4().hex[:8]}"
    params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    async with rc.stdio_client(params) as (read, write):
        async with rc.ClientSession(read, write) as session:
            await session.initialize()
            await session.list_tools()
            driver = rc.Driver(session, label)
            await rc.timed_call(rec, driver, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": False})
            prepared = await rc.timed_call(rec, driver, "prepare", "browser_prepare",
                                           {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            window = await rc.wait_for_window(driver, pid)
            bound = await rc.timed_call(rec, driver, "bind", "get_browser_state",
                                        {"pid": pid, "window_id": window["window_id"]})
            target_id, tab_id = bound["target_id"], rc.select_tab_id(bound["tabs"])
            ports = devtools_ports_for_pid(pid)
            ws_url = http_get_json(ports[0], "/json/version")["webSocketDebuggerUrl"] if ports else None
            res["devtools_ports"] = len(ports)
            tgt = {"target_id": target_id, "tab_id": tab_id}

            async def nav(lbl: str) -> None:
                await rc.timed_call(rec, driver, lbl, "browser_navigate", {**tgt, "url": url})

            async def snap(lbl: str) -> None:
                await rc.timed_call(rec, driver, lbl, "get_browser_state", {**tgt, "snapshot_format": "semantic_v2"})

            await nav("navA")
            await snap("snapA1")
            await snap("snapA2")
            rec.add("rawA_start")
            res["rawA_warm_doc_second_process"] = raw_second_process(ws_url, url) if ws_url else None
            rec.add("rawA_end")
            await nav("navB")
            await snap("snapB1")
            await snap("snapB2")
            await nav("navC")
            rec.add("rawC_start")
            res["rawC_cold_doc_second_process"] = raw_second_process(ws_url, url) if ws_url else None
            rec.add("rawC_end")
            await snap("snapC1_after_raw")
            await nav("navD")
            rec.add("delay_start")
            await asyncio.sleep(1.0)
            rec.add("delay_end")
            await snap("snapD1_after_1s")
            res["second_driver_bind"] = await second_driver_bind(args, env | {rc.TRACE_ENV: str(out / f"trials/{name}.second-driver-trace.jsonl")},
                                                                 pid, int(window["window_id"]))
    res["loadavg_after"] = rc.loadavg()
    with (out / f"trials/{name}.jsonl").open("w") as f:
        for ev in rec.events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
        f.write(json.dumps({"event": "summary", **res}, sort_keys=True, default=str) + "\n")
    print(json.dumps({"trial": name, "second": res["second_driver_bind"]}), flush=True)
    return res


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    fixtures = rc.Fixtures()
    manifest = {"plan": "step0", "started_mono_ns": rc.now(), "loadavg_start": rc.loadavg(), "trials": [],
                "display": os.environ.get("DISPLAY")}
    try:
        i = 0
        for k in range(args.per_class):
            for cls in rc.CLASSES[k % 3:] + rc.CLASSES[:k % 3]:
                name = f"s{i:03d}-{cls}-step0"
                i += 1
                try:
                    await asyncio.wait_for(probe_trial(args, fixtures, cls, name, out), timeout=120)
                    manifest["trials"].append({"name": name, "ok": True})
                except BaseException as error:  # kept, never retried
                    leaves = []
                    stack = [error]
                    while stack:
                        e = stack.pop()
                        subs = getattr(e, "exceptions", None)
                        if subs:
                            stack.extend(subs)
                        else:
                            leaves.append(f"{type(e).__name__}: {e}"[:300])
                    manifest["trials"].append({"name": name, "ok": False, "error": leaves})
                    print(json.dumps({"trial": name, "error": leaves}), flush=True)
                    if isinstance(error, (KeyboardInterrupt, SystemExit)):
                        raise
                await asyncio.sleep(0.5)
    finally:
        manifest["ended_mono_ns"] = rc.now()
        manifest["loadavg_end"] = rc.loadavg()
        manifest["network"] = dict(rc.NETWORK)
        (out / "run-manifest-step0.json").write_text(json.dumps(manifest, indent=1))
        fixtures.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--per-class", type=int, default=5)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (rc.TRACE_ENV, *KNOB_ENVS):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

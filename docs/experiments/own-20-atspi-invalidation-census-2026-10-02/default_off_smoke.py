#!/usr/bin/env python3
"""OWN-20 default-off smoke for the test-only fixture control channel (runs inside the isolated session).

Launches the BASE fixture (the file at the tested upstream SHA, extracted by the caller) and the
MODIFIED fixture, without CUA_GTK3_CONTROL_FIFO, in task mode and in the default harness mode, and
compares what the Driver observes (get_window_state element digest over role/label/value/selected/
enabled/frame, element count, window size) and the task state file's keys. Expected: identical.

usage: default_off_smoke.py <worktree> <driver> <base-main.py> <out-dir> <work-dir>
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"


async def main() -> int:
    wt, drv, base, out, work = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(wt / "libs/cua-driver/examples/jev-use/python"))
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment

    results = []
    params = StdioServerParameters(command=drv, args=["mcp"], env=driver_environment())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for mode, title in (("task", "CuaTestHarness GTK3 Tasks"), ("harness", "CuaTestHarness GTK3")):
                for which, path in (("base", base), ("modified", wt / FIXTURE_REL)):
                    env = {k: v for k, v in os.environ.items() if not k.startswith("CUA_GTK3_")}
                    state = work / f"{mode}-{which}.state.json"
                    if mode == "task":
                        env["CUA_GTK3_TASK_STATE"] = str(state)
                    proc = subprocess.Popen(["/usr/bin/python3", str(path)], env=env,
                                            stdout=open(work / f"{mode}-{which}.log", "w"), stderr=subprocess.STDOUT)
                    time.sleep(2.0)
                    wid = None
                    for _ in range(40):
                        res = await session.call_tool("list_windows", {"pid": proc.pid})
                        hits = [w for w in (res.structuredContent or {}).get("windows", []) if w.get("title") == title]
                        if hits:
                            wid, size = hits[0]["window_id"], (hits[0]["width"], hits[0]["height"])
                            break
                        await asyncio.sleep(0.1)
                    res = await session.call_tool("get_window_state", {"pid": proc.pid, "window_id": wid,
                                                                       "include_screenshot": False})
                    sc = res.structuredContent or {}
                    els = sc.get("elements") or []
                    full = [[e.get(k) for k in ("role", "label", "value", "selected", "enabled", "frame")] for e in els]
                    # frames are absolute; compare relative to the window origin
                    wb = sc.get("window_bounds") or {}
                    rel = [[*row[:5], {"x": row[5]["x"] - wb.get("x", 0), "y": row[5]["y"] - wb.get("y", 0),
                                       "w": row[5]["w"], "h": row[5]["h"]} if row[5] else None] for row in full]
                    st = None
                    if mode == "task":
                        st = json.loads(state.read_text()) if state.exists() else None
                    results.append({"mode": mode, "fixture": which, "window_size": size, "element_count": len(els),
                                    "digest_rel": hashlib.sha256(json.dumps(rel).encode()).hexdigest()[:16],
                                    "tree_markdown_sha": hashlib.sha256(str(sc.get("tree_markdown")).encode()).hexdigest()[:16],
                                    "state_keys": sorted(st) if st else None, "is_error": bool(res.isError)})
                    proc.terminate()
                    proc.wait(5)
                    time.sleep(0.5)
    verdict = {}
    for mode in ("task", "harness"):
        b = next(r for r in results if r["mode"] == mode and r["fixture"] == "base")
        m = next(r for r in results if r["mode"] == mode and r["fixture"] == "modified")
        verdict[mode] = {k: b[k] == m[k] for k in ("window_size", "element_count", "digest_rel", "tree_markdown_sha", "state_keys")}
    (out / "default-off-smoke.json").write_text(json.dumps({"results": results, "identical": verdict}, indent=1) + "\n")
    print(json.dumps(verdict))
    return 0 if all(all(v.values()) for v in verdict.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

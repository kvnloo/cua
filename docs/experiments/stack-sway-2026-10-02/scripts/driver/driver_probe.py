#!/usr/bin/env python3
"""driver_probe.py: drive cua-driver over MCP stdio inside the private sway session.

  driver_probe.py tools <out.json>
  driver_probe.py native <outdir>     (CUA_DRIVER_RS_ENABLE_WAYLAND=1 expected in the environment)

Run with the jev-use venv python (it carries the `mcp` package). The Driver environment is jev-use's
driver_environment() plus SWAYSOCK, which the Driver's sway IPC metadata needs and jev-use does not
forward. Oracles are independent of the Driver: seatprobe's per-seat event log, swaymsg get_seats /
get_tree, and grim screenshots.
"""
import asyncio
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.environ["JEV"], "python"))
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from driver_env import driver_environment  # noqa: E402


def env():
    e = driver_environment()
    if os.environ.get("SWAYSOCK") and os.environ.get("PROBE_FORWARD_SWAYSOCK", "1") == "1":
        e["SWAYSOCK"] = os.environ["SWAYSOCK"]
    return e


def swaymsg(kind):
    return json.loads(subprocess.run(["swaymsg", "-t", kind, "-r"], capture_output=True, text=True).stdout)


async def call(session, name, args, label):
    t = time.time()
    try:
        r = await session.call_tool(name, {**args, "session": label})
        sc = r.structuredContent if isinstance(r.structuredContent, dict) else None
        text = " ".join(getattr(c, "text", "") for c in (r.content or []) if getattr(c, "type", "") == "text")
        return {"tool": name, "args": args, "session": label, "is_error": bool(r.isError), "ms": round((time.time() - t) * 1000, 1),
                "structured": {k: v for k, v in (sc or {}).items() if k not in ("screenshot", "tree_markdown", "image")},
                "text": text[:1500]}
    except Exception as e:  # noqa: BLE001
        return {"tool": name, "args": args, "session": label, "exception": repr(e)[:1500]}


async def tools(out):
    p = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=env())
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            lst = await s.list_tools()
            want = {"click", "type_text", "list_windows", "get_window_state", "move_cursor", "press_key",
                    "set_agent_cursor_enabled", "parallel_mouse_drag", "health_report", "get_health_report", "check_permissions"}
            json.dump({"server": getattr(init, "serverInfo", None) and init.serverInfo.model_dump(),
                       "tool_names": sorted(t.name for t in lst.tools),
                       "schemas": {t.name: t.inputSchema for t in lst.tools if t.name in want}},
                      open(out, "w"), indent=1, default=str)
    print("tools:", len(lst.tools))


async def native(outdir):
    os.makedirs(outdir, exist_ok=True)
    log = open(os.path.join(outdir, "probe-T.jsonl"), "w")
    probe = subprocess.Popen(["seatprobe", "T", "90"], stdout=log, stderr=subprocess.DEVNULL)
    for _ in range(50):
        tree = swaymsg("get_tree")
        if '"cua-seatprobe"' in json.dumps(tree):
            break
        time.sleep(0.1)
    rec = {"probe_pid": probe.pid, "steps": []}
    p = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=env())
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            step = lambda x: (rec["steps"].append(x), print(json.dumps({k: x.get(k) for k in ("tool", "session", "is_error", "ms", "exception")})))  # noqa: E731
            step(await call(s, "health_report", {}, "agentA"))
            lw = await call(s, "list_windows", {"pid": probe.pid}, "agentA")
            step(lw)
            wins = (lw.get("structured") or {}).get("windows") or []
            win = next((x for x in wins if x.get("title") == "T"), wins[0] if wins else None)
            rec["window"] = win
            if win:
                wid = int(win["window_id"])
                gs = await call(s, "get_window_state", {"pid": probe.pid, "window_id": wid, "include_screenshot": True,
                                                         "include_accessibility_tree": False}, "agentA")
                step(gs)
                # Default delivery (background) first: expected structured refusal on Wayland without libei.
                step(await call(s, "click", {"pid": probe.pid, "window_id": wid, "x": 100, "y": 80}, "agentA"))
                rec["mark_click_A"] = time.time()
                step(await call(s, "click", {"pid": probe.pid, "window_id": wid, "x": 100, "y": 80, "delivery_mode": "foreground"}, "agentA"))
                time.sleep(0.4)
                rec["seats_after_click_A"] = swaymsg("get_seats")
                step(await call(s, "get_window_state", {"pid": probe.pid, "window_id": wid, "include_screenshot": True,
                                                         "include_accessibility_tree": False}, "agentB"))
                rec["mark_click_B"] = time.time()
                step(await call(s, "click", {"pid": probe.pid, "window_id": wid, "x": 400, "y": 300, "delivery_mode": "foreground"}, "agentB"))
                time.sleep(0.3)
                subprocess.run(["grim", "-c", os.path.join(outdir, "screen-two-agent-sessions.png")])
                rec["mark_type"] = time.time()
                step(await call(s, "type_text", {"pid": probe.pid, "window_id": wid, "text": "cua", "delivery_mode": "foreground"}, "agentA"))
                time.sleep(0.4)
                rec["mark_move_cursor"] = time.time()
                step(await call(s, "move_cursor", {"x": 900, "y": 150, "cursor_id": "third"}, "agentC"))
                time.sleep(0.6)
                subprocess.run(["grim", "-c", os.path.join(outdir, "screen-after-move-cursor.png")])
                time.sleep(1.5)
                subprocess.run(["grim", "-c", os.path.join(outdir, "screen-after-move-cursor-2s.png")])
                rec["seats_end"] = swaymsg("get_seats")
                rec["tree_end"] = swaymsg("get_tree")
    probe.terminate()
    probe.wait()
    json.dump(rec, open(os.path.join(outdir, "driver-native.json"), "w"), indent=1, default=str)


async def gtk(outdir):
    """GTK3 fixture as a native Wayland client: list_windows(pid) + get_window_state with AT-SPI tree."""
    os.makedirs(outdir, exist_ok=True)
    wt = os.environ["WT"]
    app = subprocess.Popen(["/usr/bin/python3", f"{wt}/libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"],
                           stdout=open(os.path.join(outdir, "gtk3.log"), "w"), stderr=subprocess.STDOUT)
    time.sleep(3)
    rec = {"forward_swaysock": os.environ.get("PROBE_FORWARD_SWAYSOCK", "1") == "1", "gtk_pid": app.pid,
           "sway_views": [(n.get("pid"), n.get("shell"), n.get("name")) for n in _walk(swaymsg("get_tree")) if n.get("pid")],
           "steps": []}
    p = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=env())
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            lw = await call(s, "list_windows", {"pid": app.pid}, "gtk")
            rec["steps"].append(lw)
            wins = (lw.get("structured") or {}).get("windows") or []
            if wins:
                gs = await call(s, "get_window_state", {"pid": app.pid, "window_id": int(wins[0]["window_id"]),
                                                        "include_accessibility_tree": True, "include_screenshot": True}, "gtk")
                st = gs.get("structured") or {}
                names = sorted({e.get("name") or e.get("label") or "" for e in (st.get("elements") or [])} - {""})
                gs["structured"] = {k: v for k, v in st.items() if k != "elements"}
                gs["element_names"] = names
                rec["steps"].append(gs)
    app.terminate()
    app.wait()
    json.dump(rec, open(os.path.join(outdir, "driver-gtk.json"), "w"), indent=1, default=str)
    print(json.dumps({"forward_swaysock": rec["forward_swaysock"], "windows": len(wins),
                      "elements": len(rec["steps"][-1].get("element_names", [])) if wins else 0}))


async def gtkinput(outdir):
    """GTK3 task fixture; real pixel input (no element tokens / AT-SPI actions); the fixture's own state
    file is the oracle. DELIVERY env: background|foreground."""
    os.makedirs(outdir, exist_ok=True)
    wt, delivery = os.environ["WT"], os.environ.get("DELIVERY", "foreground")
    state = os.path.join(outdir, "fixture-state.json")
    app = subprocess.Popen(["/usr/bin/python3", f"{wt}/libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"],
                           env={**os.environ, "CUA_GTK3_TASK_STATE": state},
                           stdout=open(os.path.join(outdir, "gtk3.log"), "w"), stderr=subprocess.STDOUT)
    time.sleep(3)
    rec = {"delivery": delivery, "gtk_pid": app.pid, "wayland_display_for_driver": "WAYLAND_DISPLAY" in env(),
           "sway_views": [(n.get("pid"), n.get("shell"), n.get("name")) for n in _walk(swaymsg("get_tree")) if n.get("pid")],
           "steps": []}
    p = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=env())

    def centre(names, label):
        e = names.get(label)
        f = e and (e.get("screenshot_frame") or e.get("frame"))
        return (f["x"] + f["w"] // 2, f["y"] + f["h"] // 2) if f else None

    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            lw = await call(s, "list_windows", {"pid": app.pid}, "gtk")
            rec["steps"].append(lw)
            wins = (lw.get("structured") or {}).get("windows") or []
            if wins:
                wid = int(wins[0]["window_id"])
                async def observe():
                    r_ = await s.call_tool("get_window_state", {"pid": app.pid, "window_id": wid, "include_accessibility_tree": True,
                                                                "include_screenshot": True, "session": "gtk"})
                    els = (r_.structuredContent or {}).get("elements") or []
                    return {(e.get("label") or e.get("name") or ""): e for e in els}
                els = await observe()
                rec["labels"] = sorted(els)
                for label, extra in (("Increment", None), ("Note", "sway"), ("Save note", None)):
                    els = await observe()
                    c = centre(els, label)
                    if not c:
                        rec["steps"].append({"tool": "click", "label": label, "error": "label not in tree"})
                        continue
                    st = await call(s, "click", {"pid": app.pid, "window_id": wid, "x": c[0], "y": c[1], "delivery_mode": delivery}, "gtk")
                    st["label"] = label
                    rec["steps"].append(st)
                    time.sleep(0.3)
                    if extra:
                        st = await call(s, "type_text", {"pid": app.pid, "window_id": wid, "text": extra, "delivery_mode": delivery}, "gtk")
                        rec["steps"].append(st)
                        time.sleep(0.3)
    time.sleep(0.5)
    rec["fixture_state"] = json.load(open(state)) if os.path.exists(state) else None
    fs = rec["fixture_state"] or {}
    rec["oracle"] = {"counter_is_1": fs.get("counter") == 1, "note_saved_is_sway": fs.get("note_saved") == "sway"}
    rec["result"] = "PASS" if all(rec["oracle"].values()) else "FAIL"
    app.terminate()
    app.wait()
    json.dump(rec, open(os.path.join(outdir, "driver-gtkinput.json"), "w"), indent=1, default=str)
    print(json.dumps({"delivery": delivery, "result": rec["result"], "oracle": rec["oracle"], "fixture_state": fs,
                      "errors": [(x.get("tool"), x.get("label"), (x.get("text") or x.get("error") or "")[:160]) for x in rec["steps"] if x.get("is_error") or x.get("error")]}))


def _walk(n):
    yield n
    for k in ("nodes", "floating_nodes"):
        for c in n.get(k, []):
            yield from _walk(c)


if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[2]
    asyncio.run({"tools": tools, "native": native, "gtk": gtk, "gtkinput": gtkinput}[mode](out))

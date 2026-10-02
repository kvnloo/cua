#!/usr/bin/env python3
"""driver_direct.py: scripted (model-free) cua-driver MCP client for the multiseat controls.

  driver_direct.py fill <out.json> <pid> <note-text> <increments> [--window-id N] [--session L] [--fg]
      list_windows(pid) -> get_window_state(ax) -> type <note-text> into the "Note" entry, click
      "Save note", click "Increment" <increments> times. Used for the shakedown and for the deliberate
      mis-target (sensitivity) control, where <pid>/<window-id> is the look-alike window of the OTHER
      instance on purpose.
  driver_direct.py click_xy <out.json> <pid> <session> x,y [x,y ...]
      foreground pixel clicks (multi-seat Driver replicate; MS_DRIVER_WAYLAND=1 selects the native Wayland arm)
  driver_direct.py tools <out.json>

Runs with the lane Hermes venv python (it has the `mcp` package). CUA_DRIVER_BIN names the Driver binary.
The Driver output is recorded but never used as the oracle; fixture journals are.
"""
import asyncio
import json
import os
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def driver_env():
    keep = ("PATH", "HOME", "DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS", "LANG",
            "TMPDIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "CUA_HOSTLESS")
    if os.environ.get("MS_DRIVER_WAYLAND") == "1":  # native Wayland arm (multi-seat Driver replicate)
        keep += ("WAYLAND_DISPLAY", "SWAYSOCK")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
    if os.environ.get("MS_DRIVER_WAYLAND") == "1":
        env["CUA_DRIVER_RS_ENABLE_WAYLAND"] = "1"
    return env


def strip(sc):
    return {k: v for k, v in (sc or {}).items() if k not in ("screenshot", "image", "tree_markdown")}


async def call(s, rec, name, args):
    t = time.time()
    try:
        r = await s.call_tool(name, args)
        sc = getattr(r, "structured_content", None)
        sc = sc if isinstance(sc, dict) else {}
        text = " ".join(getattr(c, "text", "") for c in (r.content or []) if getattr(c, "type", "") == "text")
        row = {"tool": name, "args": args, "is_error": bool(getattr(r, "is_error", False)), "ms": round((time.time() - t) * 1000, 1),
               "structured": strip(sc), "text": text[:1200]}
        rec["steps"].append(row)
        return sc, row
    except Exception as e:  # noqa: BLE001
        row = {"tool": name, "args": args, "exception": repr(e)[:1200]}
        rec["steps"].append(row)
        return {}, row


def find(elements, name, role_hint=None):
    for e in elements or []:
        n = (e.get("name") or e.get("label") or "").strip()
        if n == name and (role_hint is None or role_hint in (e.get("role") or "").lower()):
            return e
    return None


async def fill(out, pid, note, increments, window_id=None, session="ctl", fg=False):
    rec = {"mode": "fill", "pid": pid, "note": note, "increments": increments, "window_id_arg": window_id,
           "session": session, "delivery": "foreground" if fg else "background", "steps": []}
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_env())
    delivery = {"delivery_mode": "foreground"} if fg else {}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            sc, _ = await call(s, rec, "list_windows", {"pid": pid, "session": session})
            wins = sc.get("windows") or []
            win = next((x for x in wins if window_id is None or int(x["window_id"]) == window_id), None)
            rec["window"] = win
            if not win:
                json.dump(rec, open(out, "w"), indent=1, default=str)
                return 2
            wid = int(win["window_id"])

            async def snapshot():
                st, _ = await call(s, rec, "get_window_state", {"pid": pid, "window_id": wid, "session": session,
                                                                 "include_screenshot": False})
                return st.get("elements") or []

            els = await snapshot()
            rec["element_names"] = sorted({(e.get("name") or "") for e in els} - {""})
            target = find(els, "Note")
            if target:
                await call(s, rec, "click", {"pid": pid, "window_id": wid, "session": session,
                                             "element_token": target.get("element_token"), **delivery})
                els = await snapshot()
                target = find(els, "Note")
                await call(s, rec, "type_text", {"pid": pid, "window_id": wid, "session": session, "text": note,
                                                 "element_token": target.get("element_token") if target else None,
                                                 **delivery})
            for label, times in (("Save note", 1), ("Increment", increments)):
                for _ in range(times):
                    els = await snapshot()
                    b = find(els, label)
                    if b:
                        await call(s, rec, "click", {"pid": pid, "window_id": wid, "session": session,
                                                     "element_token": b.get("element_token"), **delivery})
    json.dump(rec, open(out, "w"), indent=1, default=str)
    return 0


async def click_xy(out, pid, points, session="ctl"):
    """list_windows(pid) -> get_window_state(screenshot) -> foreground pixel clicks at window-local points."""
    rec = {"mode": "click_xy", "pid": pid, "points": points, "session": session, "steps": []}
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_env())
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            sc, _ = await call(s, rec, "list_windows", {"pid": pid, "session": session})
            wins = sc.get("windows") or []
            rec["window"] = wins[0] if wins else None
            if wins:
                wid = int(wins[0]["window_id"])
                await call(s, rec, "get_window_state", {"pid": pid, "window_id": wid, "session": session,
                                                         "include_screenshot": True, "include_accessibility_tree": False})
                for x, y in points:
                    rec.setdefault("click_marks", []).append(time.time())
                    await call(s, rec, "click", {"pid": pid, "window_id": wid, "session": session, "x": x, "y": y,
                                                 "delivery_mode": "foreground"})
                    await asyncio.sleep(0.4)
    json.dump(rec, open(out, "w"), indent=1, default=str)
    return 0


async def tools(out):
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_env())
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            lst = await s.list_tools()
            json.dump({"server": getattr(getattr(init, "server_info", None), "model_dump", lambda: None)(),
                       "tool_names": sorted(t.name for t in lst.tools)}, open(out, "w"), indent=1, default=str)
    return 0


def main(argv):
    if argv[1] == "tools":
        return asyncio.run(tools(argv[2]))
    if argv[1] == "click_xy":  # click_xy <out> <pid> <session> x,y [x,y ...]
        pts = [tuple(float(v) for v in a.split(",")) for a in argv[5:]]
        return asyncio.run(click_xy(argv[2], int(argv[3]), pts, argv[4]))
    if argv[1] == "fill":
        out, pid, note, inc = argv[2], int(argv[3]), argv[4], int(argv[5])
        rest = argv[6:]
        wid = int(rest[rest.index("--window-id") + 1]) if "--window-id" in rest else None
        session = rest[rest.index("--session") + 1] if "--session" in rest else "ctl"
        return asyncio.run(fill(out, pid, note, inc, wid, session, "--fg" in rest))
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

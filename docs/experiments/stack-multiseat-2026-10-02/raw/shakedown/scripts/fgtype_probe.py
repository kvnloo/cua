#!/usr/bin/env python3
# shakedown-only: does a foreground coordinate click on the Note entry + foreground type_text (no element token,
# which is what Hermes sends) land text in the GTK3 entry under sway/Xwayland? usage: fgtype_probe.py out.json pid
import asyncio, json, os, sys
sys.path.insert(0, os.environ["MS_H"])
from driver_direct import call, driver_env, find  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def main(out, pid):
    rec = {"steps": []}
    p = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_env())
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            sc, _ = await call(s, rec, "list_windows", {"pid": pid, "session": "p"})
            wid = int(sc["windows"][0]["window_id"])
            st, _ = await call(s, rec, "get_window_state", {"pid": pid, "window_id": wid, "session": "p", "include_screenshot": True})
            note = find(st.get("elements"), "Note")
            f = note.get("frame") or {}
            rec["note_el"] = note
            cx, cy = f.get("x", 0) + f.get("w", 0) / 2, f.get("y", 0) + f.get("h", 0) / 2
            inc = (find(st.get("elements"), "Increment") or {}).get("frame") or {}
            ix, iy = inc.get("x", 0) + inc.get("w", 0) / 2, inc.get("y", 0) + inc.get("h", 0) / 2
            mode = "foreground"
            for i in range(3):
                await call(s, rec, "click", {"pid": pid, "window_id": wid, "session": "p", "x": ix, "y": iy, "delivery_mode": mode})
                await asyncio.sleep(0.7)
            for i in range(2):
                await call(s, rec, "click", {"pid": pid, "window_id": wid, "session": "p", "x": cx, "y": cy, "delivery_mode": mode})
                await asyncio.sleep(0.7)
                await call(s, rec, "type_text", {"pid": pid, "window_id": wid, "session": "p", "text": f"fg{i}", "delivery_mode": mode})
                await asyncio.sleep(0.7)
    json.dump(rec, open(out, "w"), indent=1, default=str)

asyncio.run(main(sys.argv[1], int(sys.argv[2])))

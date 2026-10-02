#!/usr/bin/env python3
"""OWN-20 Chromium gate probe (runs inside the isolated AT-SPI X11 session).

Question gated by the spec: does the Driver-chosen Chrome expose AT-SPI in the private session
WITHOUT any forbidden flag? The Driver launches its own browser (browser_prepare, isolated_new
profile, default safety settings, Chromium sandbox on; no extra flags or env from this script).
Records: which browser the Driver launched, whether any Chrome process owns a name on the private
AT-SPI bus, whether the registry lists it, whether get_window_state on the Chrome window exposes
web content (a labelled checkbox), and how many AT-SPI events Chrome emits around a page mutation.

usage: chrome_atspi_probe.py <worktree> <driver> <out-dir>
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

PAGE = ("<!doctype html><title>own20 probe</title><label><input type=checkbox id=agree>"
        "own20 agree</label><input aria-label='own20 note' id=note>")


def gdbus(address: str, *args: str) -> str:
    try:
        return subprocess.run(["gdbus", "call", "--address", address, *args], capture_output=True, text=True,
                              timeout=10).stdout
    except (subprocess.SubprocessError, OSError) as error:
        return f"error: {error}"


async def main() -> int:
    wt, drv, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    pkt = wt / "docs/experiments/own-20-atspi-invalidation-census-2026-10-02"
    sys.path.insert(0, str(wt / "libs/cua-driver/examples/jev-use/python"))
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment

    events = out / "events.jsonl"
    lst = subprocess.Popen(["/usr/bin/python3", str(pkt / "atspi_listener.py"), str(events), "--tag", "chrome-probe"],
                           stderr=open(out / "listener.err", "w"))
    while not (events.exists() and '"ready"' in events.read_text()):
        time.sleep(0.01)
    addr = subprocess.run(["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
                           "--method", "org.a11y.Bus.GetAddress"], capture_output=True, text=True).stdout
    address = re.search(r"'([^']+)'", addr).group(1)
    rec: dict = {"env_extra": "none (driver_environment() only)"}
    params = StdioServerParameters(command=drv, args=["mcp"], env=driver_environment())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            label = f"own20-chrome-{os.getpid()}"

            async def call(name, args):
                res = await session.call_tool(name, {**args, "session": label})
                sc = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                return res, sc

            res, sc = await call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            rec["browser_prepare"] = {k: (str(v)[:300]) for k, v in sc.items()}
            rec["browser_prepare_is_error"] = bool(res.isError)
            pid = int(sc.get("prepared_pid") or 0)
            try:
                exe = os.readlink(f"/proc/{pid}/exe")
                rec["browser_exe"] = exe
            except OSError:
                rec["browser_exe"] = None
            wid = None
            for _ in range(60):
                _r, lw = await call("list_windows", {"pid": pid})
                wins = lw.get("windows", [])
                if wins:
                    wid = wins[0]["window_id"]
                    break
                await asyncio.sleep(0.25)
            _r, bs = await call("get_browser_state", {"pid": pid, "window_id": wid})
            tab = {"target_id": bs.get("target_id")}
            tabs = bs.get("tabs") or []
            if tabs:
                tab["tab_id"] = tabs[0].get("tab_id") or tabs[0].get("id")
            res, nav = await call("browser_navigate", {**tab, "url": "data:text/html," + urllib.parse.quote(PAGE)})
            rec["navigate_is_error"] = bool(res.isError)
            rec["navigate_text"] = " ".join(getattr(c, "text", "") for c in res.content or [])[:300] if res.isError else None
            await asyncio.sleep(2.0)
            m0 = time.monotonic_ns()
            res, gws = await call("get_window_state", {"pid": pid, "window_id": wid, "include_screenshot": False})
            els = gws.get("elements") or []
            rec["gws"] = {"is_error": bool(res.isError), "element_count": len(els), "degraded": gws.get("degraded"),
                          "degraded_reason": (gws.get("degraded_reason") or "")[:200],
                          "labels_sample": [e.get("label") for e in els][:40],
                          "web_checkbox_exposed": any("own20 agree" in str(e.get("label")) for e in els)}
            _r, snap = await call("get_browser_state", {**tab, "snapshot_format": "semantic_v2"})
            ref = None
            for line in json.dumps(snap).split("\\n"):
                if "own20 agree" in line:
                    found = re.search(r"\b(e\d+|ref[=:]\s*\S+)", line)
                    ref = found.group(1) if found else None
            rec["cdp_ref_for_checkbox"] = ref
            if ref:
                m_click = time.monotonic_ns()
                res, clk = await call("browser_click", {**tab, "ref": ref})
                rec["browser_click"] = {"is_error": bool(res.isError), "m0": m_click, "effect": clk.get("effect"),
                                        "route": clk.get("route")}
                await asyncio.sleep(1.0)
            rec["registry_children"] = gdbus(address, "--dest", "org.a11y.atspi.Registry", "--object-path",
                                             "/org/a11y/atspi/accessible/root", "--method",
                                             "org.a11y.atspi.Accessible.GetChildren")[:600]
            rec["a11y_status_is_enabled"] = subprocess.run(
                ["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus", "--method",
                 "org.freedesktop.DBus.Properties.Get", "org.a11y.Status", "IsEnabled"],
                capture_output=True, text=True).stdout.strip()
            rec["m_gws"] = m0
    lst.terminate()
    lst.wait(5)
    names = {}
    sig = []
    for raw in events.read_text().splitlines():
        e = json.loads(raw)
        if e.get("event") == "name_pid":
            names[e["name"]] = e["pid"]
        elif e.get("event") == "signal":
            sig.append(e)

    def comm(p):
        try:
            return Path(f"/proc/{p}/comm").read_text().strip()
        except OSError:
            return None
    chrome_pids = set()
    for n, p in names.items():
        try:
            exe = os.readlink(f"/proc/{p}/exe")
        except OSError:
            exe = ""
        if "chrome" in exe or "chromium" in exe:
            chrome_pids.add(p)
    chrome_names = {n for n, p in names.items() if p in chrome_pids}
    ev = [e for e in sig if e["sender"] in chrome_names and (e.get("interface") or "").startswith("org.a11y.atspi.Event.")]
    rec["chrome_bus_names"] = sorted(chrome_names)
    rec["chrome_atspi_events_total"] = len(ev)
    rec["chrome_atspi_event_types"] = sorted({f'{e["member"]}:{e.get("detail") or ""}' for e in ev})[:30]
    rec["all_bus_name_pids_comm"] = sorted({(n, comm(p)) for n, p in names.items()}, key=str)
    gate = bool(rec["gws"]["web_checkbox_exposed"]) and bool(chrome_names)
    rec["gate_exposes_atspi_without_forbidden_flag"] = gate
    (out / "chrome-gate.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
    print(json.dumps({k: rec[k] for k in ("browser_exe", "chrome_bus_names", "chrome_atspi_events_total",
                                          "gate_exposes_atspi_without_forbidden_flag")}, default=str))
    print(json.dumps(rec["gws"], default=str)[:600])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

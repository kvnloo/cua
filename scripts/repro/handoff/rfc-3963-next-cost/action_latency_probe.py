#!/usr/bin/env python3
"""Which input variable moves Driver browser-action latency? (controlled fixture, real Driver/Chromium)

Times browser_type at several lengths and browser_click on a non-submitting target vs. Submit, N reps each,
against the owned loopback fixture. Run inside cua-x11-session.sh with an examples dir that has the
verify_session_isolation helpers (#4317 head or the composed worktree).
usage: action_latency_probe.py --examples-dir DIR --out FILE [--reps N] [--env-note TEXT]
"""
import argparse, asyncio, json, os, sys, time, statistics
from pathlib import Path

async def main(a):
    ex = a.examples_dir.resolve(); sys.path[:0] = [str(ex / "python"), str(ex)]
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment
    from run import Driver
    from verify_session_isolation import _prepare, _refresh_refs, _type_args, _click_args
    from verify_setup import fixture
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_environment())
    res = {}
    with fixture() as url:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                d = Driver(s, "probe-a"); b = await _prepare(d, url)
                if a.cursor == "off": res["cursor_setup"] = str(await d.call("set_agent_cursor_enabled", {"enabled": False}))[:200]
                elif a.cursor == "reduced": res["cursor_setup"] = str(await d.call("set_agent_cursor_theme", {"reduced_motion": "on"}))[:200]
                elif a.cursor == "glide1": res["cursor_setup"] = str(await d.call("set_agent_cursor_motion", {"glide_duration_ms": 1, "dwell_after_click_ms": 0}))[:300]
                elif a.cursor == "glide0": res["cursor_setup"] = str(await d.call("set_agent_cursor_motion", {"glide_duration_ms": 0}))[:200]
                async def timed(name, tool, args):
                    t = time.perf_counter(); out = await d.call(tool, args)
                    res.setdefault(name, []).append(round((time.perf_counter() - t) * 1000, 1))
                    return out
                for i in range(a.reps):
                    for n in (1, 14, 28):
                        await _refresh_refs(b)
                        await timed(f"type_{n}chars", "browser_type", _type_args(b, b.field_ref, "x" * n))
                    await _refresh_refs(b)
                    await timed("click_textbox_dom", "browser_click", _click_args(b, b.field_ref))
                    await timed("get_browser_state", "get_browser_state", {"target_id": b.target_id, "tab_id": b.tab_id, "snapshot_format": "semantic_v2"})
                    args = _click_args(b, b.field_ref); args["input_route"] = "trusted"
                    await timed("click_textbox_trusted", "browser_click", args)
                    # Submit: empty field (HTML5 validation blocks the POST) vs filled (real submission)
                    from tasks import reset_fixture
                    reset_fixture(url)
                    await d.call("browser_navigate", {"target_id": b.target_id, "tab_id": b.tab_id, "url": url})
                    await _refresh_refs(b)
                    await timed("submit_click_dom_empty_field", "browser_click", _click_args(b, b.submit_ref))
                    await timed("type_14chars_fresh_field", "browser_type", _type_args(b, b.field_ref, "jev-guide-mock"))
                    await _refresh_refs(b)
                    await timed("submit_click_dom_filled", "browser_click", _click_args(b, b.submit_ref))
                    reset_fixture(url)
                    await d.call("browser_navigate", {"target_id": b.target_id, "tab_id": b.tab_id, "url": url})
                    await _refresh_refs(b)
    out = {"env_note": a.env_note, "reps": a.reps, "ms": res, "cursor": a.cursor, "p50": {k: statistics.median(v) for k, v in res.items() if v and isinstance(v[0], float)}}
    a.out.write_text(json.dumps(out, indent=1) + "\n"); print(json.dumps(out["p50"]))

p = argparse.ArgumentParser(); p.add_argument("--examples-dir", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
p.add_argument("--reps", type=int, default=5); p.add_argument("--cursor", choices=["default","off","glide0","glide1","reduced"], default="default"); p.add_argument("--env-note", default="")
asyncio.run(main(p.parse_args()))

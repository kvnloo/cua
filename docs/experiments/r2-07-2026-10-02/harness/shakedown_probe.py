#!/usr/bin/env python3
"""R2-07 shakedown probe (feasibility only, NOT a measured trial; mock/no provider).

Learns, before PREREG is frozen:
  1. the semantic_v2 ref entry shape (keys only + role/name; values redacted);
  2. whether set_agent_cursor_enabled {enabled:false} is accepted right after initialize;
  3. N4a: what the Driver does with a ref whose DOM node was replaced after the snapshot
     (dom_event route), without a new snapshot;
  4. N4b: a ref from a superseded snapshot namespace (a newer snapshot was taken);
  5. N5: whether a NEW session label in the same Driver can re-bind the same browser
     (browser_prepare pid=<prepared_pid>, get_browser_state pid/window) and whether the old
     target id is refused there.

usage (inside cua-x11-session.sh): <venv-python> shakedown_probe.py <examples-dir> <driver-bin> <out.json>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path


def main() -> None:
    examples = Path(sys.argv[1]).resolve()
    driver_bin = sys.argv[2]
    out = Path(sys.argv[3])
    sys.path.insert(0, str(examples / "python"))
    sys.path.insert(0, str(examples))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["CUA_DRIVER_BIN"] = driver_bin
    import run as runner  # unmodified
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment
    from fixture import JournalFixture

    fixture = JournalFixture()
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    report: dict = {"probe": "r2-07-shakedown"}

    async def go() -> None:
        params = StdioServerParameters(command=driver_bin, args=["mcp"], env=driver_environment())
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("set_agent_cursor_enabled", {"enabled": False})
                report["cursor_off"] = {"is_error": bool(res.isError), "structured": res.structuredContent}
                label = f"r207-probe-{uuid.uuid4().hex[:6]}"
                d = runner.Driver(session, label)
                prepared = await d.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                pid = int(prepared["prepared_pid"])
                window = await runner.wait_for_window(d, pid)
                bound = await d.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
                target_id, tab_id = bound["target_id"], runner.select_tab_id(bound["tabs"])

                async def snap(drv, t=target_id, tb=tab_id):
                    return await drv.call("get_browser_state", {"target_id": t, "tab_id": tb, "snapshot_format": "semantic_v2"})

                # --- N4a: DOM replacement after snapshot ---
                fixture.configure("t-n4a", "tok-n4a", variant="rerender_on_signal")
                await d.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": fixture.url})
                s1 = await snap(d)
                report["snapshot_top_keys"] = sorted(s1)
                report["snapshot_meta"] = {k: s1.get(k) for k in ("snapshot", "mode", "page") if not isinstance(s1.get(k), (list,))}
                report["ref_entries"] = [
                    {"keys": sorted(r), "role": r.get("role"), "name": r.get("name"), "has_value": "value" in r,
                     "ref_shape": "p<snap>:<idx>" if str(r.get("ref", "")).startswith("p") else r.get("ref"),
                     "extra": {k: r[k] for k in r if k not in ("ref", "role", "name", "value")}}
                    for r in (s1.get("refs") or [])
                ]
                field = [r for r in s1["refs"] if r.get("role") == "textbox"][0]
                await d.call("browser_type", {"target_id": target_id, "tab_id": tab_id, "ref": field["ref"], "text": "tok-n4a", "replace": True})
                s2 = await snap(d)
                sub = [r for r in s2["refs"] if r.get("role") == "button" and r.get("name") == "Submit"][0]
                fixture.trigger_rerender()
                ok = await asyncio.to_thread(fixture.wait_rerendered, 5.0)
                report["n4a_rerender_acked"] = ok
                try:
                    r = await d.call("browser_click", {"target_id": target_id, "tab_id": tab_id, "ref": sub["ref"], "input_route": "dom_event"})
                    report["n4a_click"] = {"accepted": True, "effect": r.get("effect"), "route": r.get("route"), "result": {k: v for k, v in r.items() if isinstance(v, (str, int, bool))}}
                    # trusted-route variant on another replaced node
                    fixture.configure("t-n4a2", "tok-n4a2", variant="rerender_on_signal")
                    await d.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": fixture.url})
                    sa = await snap(d)
                    fa = [x for x in sa["refs"] if x.get("role") == "textbox"][0]
                    await d.call("browser_type", {"target_id": target_id, "tab_id": tab_id, "ref": fa["ref"], "text": "tok-n4a2", "replace": True})
                    sb = await snap(d)
                    sub2 = [x for x in sb["refs"] if x.get("role") == "button" and x.get("name") == "Submit"][0]
                    fixture.trigger_rerender(); await asyncio.to_thread(fixture.wait_rerendered, 5.0)
                    try:
                        r2 = await d.call("browser_click", {"target_id": target_id, "tab_id": tab_id, "ref": sub2["ref"]})
                        report["n4a_trusted_click"] = {"accepted": True, "result": {k: v for k, v in r2.items() if isinstance(v, (str, int, bool))}}
                    except Exception as e2:  # noqa: BLE001
                        report["n4a_trusted_click"] = {"accepted": False, "code": getattr(e2, "code", None), "err": str(e2)[:300]}
                    await asyncio.sleep(1.0)
                    report["n4a_trusted_journal"] = {k: v for k, v in fixture.journal.snapshot().items() if k in ("received", "applied")}
                except Exception as e:  # noqa: BLE001
                    report["n4a_click"] = {"accepted": False, "code": getattr(e, "code", None), "err": type(e).__name__}
                await asyncio.sleep(1.0)
                report["n4a_journal"] = {k: v for k, v in fixture.journal.snapshot().items() if k != "events"}

                # --- N4b: superseded snapshot namespace ---
                fixture.configure("t-n4b", "tok-n4b", variant="normal")
                await d.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": fixture.url})
                s3 = await snap(d)
                field = [r for r in s3["refs"] if r.get("role") == "textbox"][0]
                s4 = await snap(d)  # supersedes s3's namespace
                report["n4b_ids"] = {"s3_snapshot": s3["snapshot"]["id"], "s4_snapshot": s4["snapshot"]["id"], "old_ref": field["ref"],
                                     "s4_refs": [r["ref"] for r in s4["refs"]]}
                try:
                    rr = await d.call("browser_type", {"target_id": target_id, "tab_id": tab_id, "ref": field["ref"], "text": "tok-n4b", "replace": True})
                    report["n4b_type"] = {"accepted": True, "result": {k: v for k, v in rr.items() if isinstance(v, (str, int, bool))}}
                except Exception as e:  # noqa: BLE001
                    report["n4b_type"] = {"accepted": False, "code": getattr(e, "code", None)}

                # --- N5: new session label, same Driver + browser ---
                label2 = f"r207-probe2-{uuid.uuid4().hex[:6]}"
                d2 = runner.Driver(session, label2)
                try:
                    await snap(d2)
                    report["n5_old_target_in_new_session"] = {"accepted": True}
                except Exception as e:  # noqa: BLE001
                    report["n5_old_target_in_new_session"] = {"accepted": False, "code": getattr(e, "code", None)}
                try:
                    p2 = await d2.call("browser_prepare", {"pid": pid})
                    report["n5_prepare_pid"] = {"ok": True, "action": p2.get("action"), "prepared": p2.get("prepared")}
                except Exception as e:  # noqa: BLE001
                    report["n5_prepare_pid"] = {"ok": False, "code": getattr(e, "code", None), "err": str(e)[:300]}
                try:
                    b2 = await d2.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
                    t2, tb2 = b2["target_id"], runner.select_tab_id(b2["tabs"])
                    s5 = await snap(d2, t2, tb2)
                    report["n5_rebind"] = {"ok": True, "new_target_differs": t2 != target_id,
                                           "submit_unique": sum(1 for r in s5["refs"] if r.get("role") == "button" and r.get("name") == "Submit") == 1}
                except Exception as e:  # noqa: BLE001
                    report["n5_rebind"] = {"ok": False, "code": getattr(e, "code", None), "err": str(e)[:300]}

                # --- N6: modal dialog opened by typing ---
                fixture.configure("t-n6", "tok-n6", variant="n6_modal")
                await d.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": fixture.url})
                s6 = await snap(d)
                field = [r for r in s6["refs"] if r.get("role") == "textbox"][0]
                await d.call("browser_type", {"target_id": target_id, "tab_id": tab_id, "ref": field["ref"], "text": "tok-n6", "replace": True})
                await asyncio.sleep(0.3)
                s7 = await snap(d)
                report["n6_refs_after_modal"] = [
                    {"role": r.get("role"), "name": r.get("name"),
                     "extra": {k: r[k] for k in r if k not in ("ref", "role", "name", "value")}}
                    for r in s7.get("refs") or []
                ]
                subs = [r for r in s7["refs"] if r.get("role") == "button" and r.get("name") == "Submit"]
                if subs:
                    try:
                        r = await d.call("browser_click", {"target_id": target_id, "tab_id": tab_id, "ref": subs[0]["ref"], "input_route": "dom_event"})
                        report["n6_click_if_present"] = {"accepted": True, "effect": r.get("effect")}
                    except Exception as e:  # noqa: BLE001
                        report["n6_click_if_present"] = {"accepted": False, "code": getattr(e, "code", None)}
                    await asyncio.sleep(1.0)
                report["n6_journal"] = {k: v for k, v in fixture.journal.snapshot().items() if k != "events"}

                # --- N8: toggle page snapshot ---
                fixture.configure("t-n8", "tok-n8", variant="n8_toggle")
                await d.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": fixture.url})
                s8 = await snap(d)
                report["n8_refs"] = [{"role": r.get("role"), "name": r.get("name")} for r in s8.get("refs") or []]
                report["page_field"] = {k: (v if k != "url" else "<loopback>") for k, v in (s8.get("page") or {}).items()} if isinstance(s8.get("page"), dict) else type(s8.get("page")).__name__

    t0 = time.monotonic()
    try:
        asyncio.run(go())
    except BaseException as e:  # noqa: BLE001
        report["exception"] = f"{type(e).__name__}: {e}"[:500]
    report["wall_s"] = round(time.monotonic() - t0, 2)
    out.write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps(report, indent=1, sort_keys=True, default=str))
    fixture.shutdown()


if __name__ == "__main__":
    main()

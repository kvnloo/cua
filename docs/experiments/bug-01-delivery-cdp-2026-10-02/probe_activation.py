"""BUG-01 part A decoy-window control: does a Linux trusted foreground browser_click
actually activate the browser window? (REAL, isolated session only.)

Designed by the round-1 fresh verifier and adopted unchanged in logic as a
disclosed extension (not in PREREG.json). It discriminates T from D, which the
single-window matrix cannot (README deviation A4).

A Tk decoy window holds X11 focus before every click. Arm T = browser_click
{ref: Submit, delivery_mode: foreground} (trusted route). Arm D = browser_click
{ref: Submit, input_route: dom_event} (control). Records the receipt, the X11
active window before/after (sampled for 1.5 s), the page journal and the
fixture /state oracle.

usage (cwd = <wt>/libs/cua-driver/examples/jev-use, inside cua-x11-session.sh):
  .venv/bin/python probe_activation.py --out <dir> --blocks 2
  (or via run_in_session.sh <wt> <bin> probe_activation.py --out <dir> --blocks 2)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bug01_common import (  # noqa: E402
    Probe, ProbeServer, driver_environment, driver_version, find_ref, oracle,
    require_isolated_session, reset, sanitize, sh, sha256_file, wait_for_window, x_focus,
)
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

DECOY = "bug01-verifier-decoy"
TK = (
    "import tkinter as tk; r=tk.Tk(); r.title('%s'); r.geometry('320x200+1200+120'); "
    "tk.Label(r,text='decoy').pack(); r.mainloop()" % DECOY
)


def active() -> str | None:
    return sh(["xdotool", "getactivewindow"])


def decoy_id() -> str | None:
    out = sh(["xdotool", "search", "--name", f"^{DECOY}$"])
    return out.split()[0] if out else None


def activate(win: str) -> str | None:
    sh(["xdotool", "windowactivate", "--sync", win], timeout=5)
    time.sleep(0.15)
    return active()


async def trial(probe, server, url, ctx, arm, idx, out, decoy) -> dict:
    tid = f"act-{idx:02d}-{arm}-{uuid.uuid4().hex[:6]}"
    token = f"bug01v-{uuid.uuid4().hex[:8]}"
    server.trial = tid
    reset(url)
    rec = {"trial": tid, "arm": arm, "token": token, "browser_window_id": str(ctx["window_id"]), "decoy_window_id": decoy}
    target, tab = ctx["target_id"], ctx["tab_id"]
    await probe.call("browser_navigate", {"target_id": target, "tab_id": tab, "url": url})
    t_end = time.time() + 6
    while time.time() < t_end and not [r for r in server.journal_for(tid) if r.get("kind") == "load"]:
        await asyncio.sleep(0.05)
    snap = (await probe.call("get_browser_state", {"target_id": target, "tab_id": tab, "snapshot_format": "semantic_v2"})).get("structured") or {}
    field, submit = find_ref(snap, "textbox", "verification value"), find_ref(snap, "button", "Submit")
    typed = await probe.call("browser_type", {"target_id": target, "tab_id": tab, "ref": field, "text": token, "replace": True})
    rec["type"] = {"accepted": typed.get("accepted"), "structured": typed.get("structured")}
    rec["active_after_type"] = active()
    rec["active_after_decoy_activate"] = activate(decoy)
    rec["focus_pre"] = x_focus()
    args = {"target_id": target, "tab_id": tab, "ref": submit}
    args.update({"delivery_mode": "foreground"} if arm == "T" else {"input_route": "dom_event"})
    click = await probe.call("browser_click", args)
    rec["click"] = {k: click.get(k) for k in ("accepted", "is_error", "refusal", "structured", "elapsed_ms")}
    samples = []
    p0 = time.perf_counter()
    verified = None
    while (time.perf_counter() - p0) < 1.5:
        samples.append([round((time.perf_counter() - p0) * 1000), active()])
        st = oracle(url)
        if st.get("submitted") == token and verified is None:
            verified = round((time.perf_counter() - p0) * 1000, 1)
        await asyncio.sleep(0.1)
    rec["active_samples_after_click"] = samples
    rec["focus_post"] = x_focus()
    rec["verified_ms"] = verified
    rec["final_state"] = oracle(url)
    await asyncio.sleep(0.3)
    rec["journal"] = [{k: e.get(k) for k in ("kind", "target", "is_trusted", "has_focus", "visibility")} for e in server.journal_for(tid) if e.get("source") == "page"]
    rec = sanitize(rec)
    (out / f"{tid}.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    cs = rec["click"].get("structured") or {}
    print(json.dumps({"trial": tid, "receipt_delivery": (cs.get("delivery") or {}).get("mode"), "route": cs.get("route"),
                      "decoy_active_pre": rec["focus_pre"]["active_window"] == decoy,
                      "active_post_is_browser": rec["focus_post"]["active_window"] == str(ctx["window_id"]),
                      "active_post_is_decoy": rec["focus_post"]["active_window"] == decoy,
                      "verified": verified is not None}), flush=True)
    return rec


async def block(bi, server, url, out, arms):
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_environment())
    label = f"bug01v-{uuid.uuid4().hex[:8]}"
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            probe = Probe(session, label)
            prep = await probe.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int((prep.get("structured") or {})["prepared_pid"])
            window = await wait_for_window(probe, pid)
            bound = (await probe.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})).get("structured") or {}
            tabs = bound.get("tabs") or []
            tab = next((t for t in tabs if t.get("active")), tabs[0])
            ctx = {"target_id": bound["target_id"], "tab_id": str(tab["tab_id"]), "window_id": int(window["window_id"])}
            decoy_proc = subprocess.Popen([sys.executable, "-c", TK], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                decoy = None
                for _ in range(50):
                    decoy = decoy_id()
                    if decoy:
                        break
                    time.sleep(0.1)
                if not decoy:
                    raise RuntimeError("decoy window did not appear")
                (out / f"block-{bi:02d}.json").write_text(json.dumps(sanitize({"block": bi, "browser_window_id": ctx["window_id"], "decoy": decoy, "active_at_start": active()}), indent=1) + "\n")
                for i, arm in enumerate(arms):
                    try:
                        await trial(probe, server, url, ctx, arm, bi * 100 + i, out, decoy)
                    except Exception as exc:  # keep in denominator
                        (out / f"act-{bi * 100 + i:02d}-{arm}-harness-error.json").write_text(json.dumps(sanitize({"error": f"{type(exc).__name__}: {exc}"})) + "\n")
                        print(json.dumps({"harness_error": f"{type(exc).__name__}: {exc}", "arm": arm}), flush=True)
            finally:
                decoy_proc.terminate()
                try:
                    decoy_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    decoy_proc.kill()


async def amain(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    binary = os.environ["CUA_DRIVER_BIN"]
    env = {"driver_sha256": sha256_file(binary), "driver_version_in_session": driver_version(binary),
           "chrome": sh(["/opt/google/chrome/chrome", "--version"], timeout=20), "display": os.environ.get("DISPLAY"),
           "counter_env_set": bool(os.environ.get("CUA_DRIVER_EXP_CDP_COUNTER_FILE")), "t_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    patterns = ["TDTDTD", "DTDTDT"]
    with ProbeServer(("127.0.0.1", 0), instrumented=True) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            for bi in range(a.blocks):
                await block(bi + 1, server, url, out, list(patterns[bi % 2]))
        finally:
            server.shutdown()
    env["t_end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "session-env.json").write_text(json.dumps(sanitize(env), indent=1) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--blocks", type=int, default=2)
    a = p.parse_args()
    require_isolated_session()
    if os.environ.get("CUA_DRIVER_EXP_CDP_COUNTER_FILE"):
        raise SystemExit("refusing: counter variable must be unset")
    asyncio.run(amain(a))

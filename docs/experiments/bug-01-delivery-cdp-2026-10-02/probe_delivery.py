"""BUG-01 part A: receipt delivery attribution vs page-side evidence (REAL).

Runs INSIDE the isolated X11 session with the jev-use venv (see run_in_session.sh).
Per trial: reset -> browser_navigate -> wait page load beacon -> semantic_v2
snapshot -> browser_type token -> (arm) browser_click -> fixture /state reads.
Records full public receipts, the page journal (isTrusted, hasFocus,
visibility), X11 active window pre/post and the fixture journal.

usage: probe_delivery.py --out <dir> --driver-label <label> [--blocks 1 2 ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from bug01_common import (
    Probe,
    ProbeServer,
    driver_environment,
    driver_version,
    find_ref,
    oracle,
    require_isolated_session,
    reset,
    sanitize,
    sh,
    sha256_file,
    wait_for_window,
    x_focus,
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

FIELD_NAME = "verification value"
SUBMIT_NAME = "Submit"
PATTERNS = ["TDYYDTDYTY", "DYTTYDYTDT", "YTDDTYTDYD"]


def plan() -> list[dict[str, Any]]:
    blocks = []
    index = 0
    for b in range(6):
        trials = []
        for pos, arm in enumerate(PATTERNS[b % 3]):
            index += 1
            trials.append({"index": index, "arm": arm, "pos": pos})
        blocks.append({"block": b + 1, "trials": trials})
    trials = []
    for pos in range(10):
        index += 1
        trials.append({"index": index, "arm": "N_bg" if pos % 2 == 0 else "N_domfg", "pos": pos})
    blocks.append({"block": 7, "trials": trials})
    return blocks


CLICK_ARGS = {
    "T": {"delivery_mode": "foreground"},
    "D": {"input_route": "dom_event"},
    "N_bg": {},
    "N_domfg": {"input_route": "dom_event", "delivery_mode": "foreground"},
}


async def run_trial(probe: Probe, server: ProbeServer, url: str, ctx: dict[str, Any], spec: dict[str, Any], out: Path) -> None:
    arm = spec["arm"]
    trial_id = f"{ctx['driver_label']}-{spec['index']:03d}-{arm}-{uuid.uuid4().hex[:6]}"
    token = f"bug01-{uuid.uuid4().hex[:10]}"
    server.trial = trial_id
    reset(url)
    rec: dict[str, Any] = {"event": "trial", "trial": trial_id, "index": spec["index"], "block": spec["block"], "pos_in_block": spec["pos"], "arm": arm, "driver_label": ctx["driver_label"], "loadavg_start": os.getloadavg(), "token": token, "browser_window_id": ctx["window_id"]}
    target, tab = ctx["target_id"], ctx["tab_id"]
    nav = await probe.call("browser_navigate", {"target_id": target, "tab_id": tab, "url": url})
    rec["navigate"] = {k: nav.get(k) for k in ("accepted", "elapsed_ms", "is_error", "refusal")}
    load_rec = None
    deadline = time.time() + 6
    while time.time() < deadline:
        loads = [r for r in server.journal_for(trial_id) if r.get("kind") == "load"]
        if loads:
            load_rec = loads[0]
            break
        await asyncio.sleep(0.05)
    rec["page_load"] = load_rec
    snap = await probe.call("get_browser_state", {"target_id": target, "tab_id": tab, "snapshot_format": "semantic_v2"})
    snapshot = snap.get("structured") or {}
    field_ref = find_ref(snapshot, "textbox", FIELD_NAME)
    submit_ref = find_ref(snapshot, "button", SUBMIT_NAME)
    rec["snapshot"] = {"accepted": snap.get("accepted"), "elapsed_ms": snap.get("elapsed_ms"), "field_ref_found": field_ref is not None, "submit_ref_found": submit_ref is not None}
    typed = await probe.call("browser_type", {"target_id": target, "tab_id": tab, "ref": field_ref, "text": token, "replace": True})
    rec["type"] = {k: typed.get(k) for k in ("accepted", "elapsed_ms", "is_error", "refusal", "t_start_ms", "t_end_ms", "structured")}
    rec["focus_pre"] = x_focus()
    if arm == "Y":
        rec["click"] = {"skipped": True}
        await asyncio.sleep(1.0)
        reads = [{"after_tool_ms": 1000.0, "state": oracle(url)}]
        first_verified_ms = None
    else:
        click_args: dict[str, Any] = {"target_id": target, "tab_id": tab, "ref": submit_ref, **CLICK_ARGS[arm]}
        rec["click_args"] = {k: v for k, v in click_args.items() if k not in ("target_id", "tab_id", "ref")}
        click = await probe.call("browser_click", click_args)
        rec["click"] = click
        reads = []
        first_verified_ms = None
        p0 = time.perf_counter()
        bound = 3000.0 if arm in ("T", "D", "N_domfg") else 1000.0
        while True:
            try:
                state = oracle(url)
            except Exception as exc:  # noqa: BLE001
                state = {"error": type(exc).__name__}
            dt = (time.perf_counter() - p0) * 1000
            reads.append({"after_tool_ms": round(dt, 2), "state": state})
            if state.get("submitted") == token and first_verified_ms is None:
                first_verified_ms = dt
                break
            if dt >= bound:
                break
            await asyncio.sleep(0.05)
    rec["focus_post"] = x_focus()
    rec["oracle"] = {"immediate": reads[0]["state"], "reads": len(reads), "first_verified_after_tool_ms": first_verified_ms, "final": reads[-1]["state"]}
    await asyncio.sleep(0.4)  # trailing beacons; does not affect the oracle above
    rec["journal"] = server.journal_for(trial_id)
    rec["loadavg_end"] = os.getloadavg()
    rec = sanitize(rec)
    with (out / f"{trial_id}.jsonl").open("w") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    click_s = (rec.get("click") or {}).get("structured") or {}
    print(json.dumps({"trial": trial_id, "click_delivery": (click_s.get("delivery") or {}).get("mode"), "click_route": click_s.get("route"), "type_delivery": ((rec["type"].get("structured") or {}).get("delivery") or {}).get("mode"), "verified": first_verified_ms is not None}), flush=True)


async def run_block(block: dict[str, Any], server: ProbeServer, url: str, out: Path, driver_label: str) -> None:
    params = StdioServerParameters(command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_environment())
    label = f"bug01a-{uuid.uuid4().hex[:8]}"
    meta: dict[str, Any] = {"event": "block", "block": block["block"], "label": label, "t_start_ms": time.time() * 1000, "loadavg": os.getloadavg()}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            meta["server_info"] = {"name": init.serverInfo.name, "version": init.serverInfo.version}
            probe = Probe(session, label)
            prep = await probe.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            meta["prepare"] = {k: prep.get(k) for k in ("accepted", "elapsed_ms", "is_error", "refusal")}
            pid = int((prep.get("structured") or {})["prepared_pid"])
            window = await wait_for_window(probe, pid)
            bound = await probe.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
            b = bound.get("structured") or {}
            tabs = b.get("tabs") or []
            tab = next((t for t in tabs if t.get("active")), tabs[0])
            ctx = {"target_id": b["target_id"], "tab_id": str(tab["tab_id"]), "window_id": int(window["window_id"]), "driver_label": driver_label}
            meta["window"] = {"window_id": window["window_id"], "bounds": window.get("bounds")}
            meta["focus_at_bind"] = x_focus()
            for spec in block["trials"]:
                try:
                    await run_trial(probe, server, url, ctx, {**spec, "block": block["block"]}, out)
                except Exception as exc:  # keep the failure in the denominator
                    err = sanitize({"event": "trial_harness_error", "index": spec["index"], "arm": spec["arm"], "block": block["block"], "driver_label": driver_label, "error": f"{type(exc).__name__}: {exc}"})
                    with (out / f"{driver_label}-{spec['index']:03d}-{spec['arm']}-harness-error.jsonl").open("w") as fh:
                        fh.write(json.dumps(err) + "\n")
                    print(json.dumps(err), flush=True)
    meta["t_end_ms"] = time.time() * 1000
    with (out / f"{driver_label}-block-{block['block']:02d}.json").open("w") as fh:
        fh.write(json.dumps(sanitize(meta), sort_keys=True, indent=1) + "\n")


async def amain(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    binary = os.environ["CUA_DRIVER_BIN"]
    env = {"driver_label": args.driver_label, "driver_sha256": sha256_file(binary), "driver_version_in_session": driver_version(binary), "chrome_version_in_session": sh(["/opt/google/chrome/chrome", "--version"], timeout=20), "display": os.environ.get("DISPLAY"), "focus_initial": x_focus(), "counter_env_set": bool(os.environ.get("CUA_DRIVER_EXP_CDP_COUNTER_FILE")), "t_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with ProbeServer(("127.0.0.1", 0), instrumented=True) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            for block in plan():
                if args.blocks and block["block"] not in args.blocks:
                    continue
                try:
                    await run_block(block, server, url, out, args.driver_label)
                except Exception as exc:  # noqa: BLE001
                    err = sanitize({"event": "block_harness_error", "block": block["block"], "error": f"{type(exc).__name__}: {exc}"})
                    (out / f"{args.driver_label}-block-{block['block']:02d}-harness-error.json").write_text(json.dumps(err) + "\n")
                    print(json.dumps(err), flush=True)
        finally:
            server.shutdown()
    env["t_end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / f"{args.driver_label}-session-env.json").write_text(json.dumps(sanitize(env), indent=1, sort_keys=True) + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--driver-label", required=True)
    p.add_argument("--blocks", type=int, nargs="*")
    args = p.parse_args()
    require_isolated_session()
    if os.environ.get("CUA_DRIVER_EXP_CDP_COUNTER_FILE"):
        raise SystemExit("refusing: part A runs with the counter variable unset")
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()

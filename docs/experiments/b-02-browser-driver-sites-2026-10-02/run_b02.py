"""B-02 runner: causal A/B of the three B-01 Driver sites (mock chooser, 0 provider HTTP).

Run inside the isolated X11 session with the jev-use virtualenv:

    JEV_USE_DIR=<jev-use> <venv>/python run_b02.py --driver <bin> --out <dir> \
        --plan {measured|controls|smoke} [--arms K5,K5E,K5V,K5EV] [--lock <quiet-lane.lock>]

measured: run it under ``quiet-timed`` (the EXCLUSIVE quiet-lane lock is held by the
caller before this process opens any Driver session); the runner takes no lock.
controls/smoke: the runner takes the quiet-lane lock SHARED for at most 10 trials per
acquisition and appends a receipt per acquisition to ``<out>/lock-receipts.jsonl``.

Every arm is B-01's K5 (feedback OFF, focus settle 0 on fill, 10 ms completion poll,
caller-compiled output-schema validators, trycua/cua PR 4316 guarded completion on
fill) plus the B-02 knobs named by the arm. Measured and stale-ref trials run B-01's
``run_critpath.run_trial`` verbatim (copied file, blob recorded in provenance); the
knobs reach the Driver through the environment only. Controls (N-E1, N-E2, N-W2,
N-V) are separate trial functions below. Output paths are relative to --out.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_critpath as rc  # noqa: E402  (loopback-only guard, client validator patch, jev-use imports)
from cdp_raw import CdpClient, Decoy, devtools_ports_for_pid, evaluate, http_get_json, page_target  # noqa: E402

E_ENV = "CUA_DRIVER_EXP_ENDPOINT_REPROOF"
V_ENV = "CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE"
W_ENV = "CUA_DRIVER_EXP_CDP_WARM"
KNOB_ENVS = (E_ENV, V_ENV, W_ENV)
ARM_KNOBS: dict[str, dict[str, str]] = {
    "K5": {},
    "K5E": {E_ENV: "bound"},
    "K5V": {V_ENV: "1"},
    "K5EV": {E_ENV: "bound", V_ENV: "1"},
}
for _arm in ARM_KNOBS:
    rc.ARMS[_arm] = rc.ARMS["K5"]

_BASE_ENV = rc.driver_environment
CURRENT = {"knobs": {}}


def _env_with_knobs(source: Any = None) -> dict[str, str]:
    env = _BASE_ENV() if source is None else _BASE_ENV(source)
    for name in KNOB_ENVS:
        env.pop(name, None)
    env.update(CURRENT["knobs"])
    return env


rc.driver_environment = _env_with_knobs  # run_critpath.run_trial reads it once per trial


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def williams_any(n: int) -> list[list[int]]:
    """Williams rows: n rows for even n; 2n rows (square + mirror) for odd n."""
    if n % 2 == 0:
        return rc.williams(n)
    first = [0]
    lo, hi, take_lo = 1, n - 1, True
    while len(first) < n:
        first.append(lo if take_lo else hi)
        lo, hi = (lo + 1, hi) if take_lo else (lo, hi - 1)
        take_lo = not take_lo
    rows = [[(x + i) % n for x in first] for i in range(n)]
    return rows + [list(reversed(r)) for r in rows]


# ── controls ──────────────────────────────────────────────────────────────────

def kill_lane_browser(pid: int) -> bool:
    """Stop the lane-started (Driver-launched) browser; returns True once it is gone."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    for _ in range(100):
        if not rc.pid_alive(pid):
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    for _ in range(100):
        if not rc.pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


def envelope(raw: Any) -> dict[str, Any]:
    sc = raw.structuredContent if isinstance(raw.structuredContent, dict) else {}
    refusal = sc.get("refusal") if isinstance(sc.get("refusal"), dict) else {}
    err = sc.get("error") if isinstance(sc.get("error"), dict) else {}
    return {"is_error": bool(raw.isError), "status": sc.get("status"), "effect": sc.get("effect"),
            "code": sc.get("code") or refusal.get("code") or err.get("code")}


DOM_REPLACE = {
    "fill": "button[type=submit]",
    "toggle": "#go",
    "modal": "#ok",
}


def dom_replace_js(cls: str, marker: str) -> str:
    sel = DOM_REPLACE[cls]
    return ("(() => { const o = document.querySelector(%s); if (!o) return 'missing';"
            " const n = o.cloneNode(true); n.onclick = o.onclick; o.replaceWith(n);"
            " const p = document.createElement('p'); p.textContent = %s; document.body.appendChild(p);"
            " return o.isConnected ? 'still-connected' : 'replaced'; })()") % (json.dumps(sel), json.dumps(marker))


async def control_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, trace_path: Path,
                        rec: Any, result: dict[str, Any]) -> None:
    """N-E1 / N-E2 / N-W2: B-01's step loop with the control's intervention before action 2."""
    cls, kind, arm = spec["cls"], spec["kind"], rc.ARMS[spec["arm"]]
    token = f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-b02-{uuid.uuid4().hex[:8]}"
    task = rc.make_task(cls, token, fixtures)
    result.update({"token_sha16": rc.sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "routes": [], "tools": [], "input_routes": [], "candidates": []})
    task.reset()
    fixtures.state(cls).drain()
    poller = rc.OraclePoller(fixtures, cls, token)
    result["_poller"] = poller
    env = rc.driver_environment()
    env.pop(rc.TRACE_ENV, None)
    env.pop(rc.KNOB_ENV, None)
    env[rc.TRACE_ENV] = str(trace_path)
    if arm.knob_zero and cls == "fill":
        env[rc.KNOB_ENV] = "0"
    result["driver_env_knobs"] = {k: env[k] for k in KNOB_ENVS if k in env}
    rec.add("trial_start", cls=cls, arm=spec["arm"], kind=kind)
    rc.CLIENT["rec"] = rec
    rc.CLIENT["compiled"] = None
    params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    async with rc.stdio_client(params) as (read, write):
        async with rc.ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            result["compiled_validators"] = rc.compile_output_validators(session)
            available = {tool.name for tool in tools}
            capture_bound = rc.supports_capture_bound_click(tools)
            driver = rc.Driver(session, label)
            await rc.timed_call(rec, driver, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm.cursor})
            await rc.timed_call(rec, driver, "cursor_motion", "set_agent_cursor_motion", rc.DEFAULT_MOTION)

            async def setup_browser(tag: str) -> tuple[int, dict[str, Any], str, str]:
                prepared = await rc.timed_call(rec, driver, f"prepare{tag}", "browser_prepare",
                                               {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                pid = int(prepared["prepared_pid"])
                window = await rc.wait_for_window(driver, pid)
                bound = await rc.timed_call(rec, driver, f"bind{tag}", "get_browser_state",
                                            {"pid": pid, "window_id": window["window_id"]})
                target_id, tab_id = bound["target_id"], rc.select_tab_id(bound["tabs"])
                await rc.timed_call(rec, driver, f"navigate{tag}", "browser_navigate",
                                    {"target_id": target_id, "tab_id": tab_id, "url": fixtures.page_url(cls)})
                return pid, window, target_id, tab_id

            pid, window, target_id, tab_id = await setup_browser("")
            result["prepared_pid"] = pid
            result["pids"] = [pid]
            poller.start()
            history: list[dict[str, Any]] = []
            pending = None
            step = 0
            while step < task.max_steps:
                step += 1
                current = rc.oracle_read(rec, task, f"pre_step{step}", step - 1)
                if current in {"verified", "refuted"}:
                    result["outcome"] = current
                    return
                snap = await rc.timed_call(rec, driver, f"snapshot{step}", "get_browser_state",
                                           {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                if kind == "nw2" and step == 2:
                    # Same-document DOM replacement between the snapshot and the action.
                    marker = f"b02 marker {uuid.uuid4().hex[:8]}"
                    ports = devtools_ports_for_pid(pid)
                    client = CdpClient(http_get_json(ports[0], "/json/version")["webSocketDebuggerUrl"])
                    try:
                        replaced = evaluate(client, page_target(client, fixtures.page_url(cls)),
                                            dom_replace_js(cls, marker))
                    finally:
                        client.close()
                    rec.add("dom_replaced", result=replaced)
                    result["dom_replace"] = replaced
                    old_text = json.dumps(snap)
                    snap = await rc.timed_call(rec, driver, "snapshot2_fresh", "get_browser_state",
                                               {"target_id": target_id, "tab_id": tab_id,
                                                "snapshot_format": "semantic_v2"})
                    result["marker_in_stale_snapshot"] = marker in old_text
                    result["marker_in_fresh_snapshot"] = marker in json.dumps(snap)
                    pending = None  # re-derive the action from the fresh snapshot (provider route)
                rec.add("cand_start", step=step)
                candidates, sources, _visual = await rc.task_candidates_for_step(
                    driver, task, snap, pid, int(window["window_id"]), available, capture_bound, visual_mode="auto")
                rec.add("cand_done", step=step, ids=[c.id for c in candidates])
                candidate = None
                if arm.guard and pending is not None:
                    resolution = rc.resolve_guarded_completion(pending, task, sources, candidates, session=label)
                    candidate = resolution.candidate
                    pending = None
                if candidate is not None:
                    route = "guarded-completion"
                else:
                    rec.add("decide_start", step=step)
                    choice, _c, _p = rc.choose_mock_for_task(task, sources, candidates, history)
                    rec.add("decided", step=step, choice=choice)
                    if choice is None:
                        result["outcome"] = "abstained"
                        return
                    candidate = rc.validate_choice(choice, candidates, current_capture_id=None)
                    route = "provider"
                next_plan = (rc.plan_guarded_completion(task, sources, candidate, session=label)
                             if arm.guard and route == "provider" else None)
                result["routes"].append(route)
                result["candidates"].append(candidate.id)
                result["tools"].append(candidate.tool)
                result["input_routes"].append((candidate.arguments or {}).get("input_route"))
                if candidate.id in ("reobserve", "abstain"):
                    result["outcome"] = "abstained" if candidate.id == "abstain" else result["outcome"]
                    if candidate.id == "abstain":
                        return
                    history.append(task.history_entry(step, candidate.id))
                    continue
                if kind == "ne1" and step == 2:
                    ports = devtools_ports_for_pid(pid)
                    result["takeover_port_found"] = bool(ports)
                    gone = kill_lane_browser(pid)
                    decoy = Decoy(ports[0]) if (ports and gone) else None
                    rec.add("takeover_ready", browser_gone=gone, decoy=decoy is not None)
                    rec.add("call_send", label="takeover_action", tool=candidate.tool)
                    raw = await session.call_tool(candidate.tool, {**candidate.arguments, "session": label})
                    rec.add("call_return", label="takeover_action", tool=candidate.tool, **envelope(raw))
                    result["takeover_envelope"] = envelope(raw)
                    await asyncio.sleep(0.5)
                    result["decoy_connections"] = None if decoy is None else decoy.connections
                    result["decoy_requests"] = None if decoy is None else list(decoy.requests)
                    if decoy is not None:
                        decoy.close()
                    result["outcome"] = rc.oracle_read(rec, task, "takeover_check", step)
                    return
                if kind == "ne2" and step == 2:
                    gone = kill_lane_browser(pid)
                    rec.add("browser_stopped", gone=gone)
                    rec.add("call_send", label="old_binding_action", tool=candidate.tool)
                    raw = await session.call_tool(candidate.tool, {**candidate.arguments, "session": label})
                    rec.add("call_return", label="old_binding_action", tool=candidate.tool, **envelope(raw))
                    result["old_binding_envelope"] = envelope(raw)
                    # Restart through the Driver, then run the task from step 1 on the new browser.
                    pid, window, target_id, tab_id = await setup_browser("_restart")
                    result["pids"].append(pid)
                    result["restart_new_pid"] = pid != result["pids"][0]
                    history, pending, step = [], None, 0
                    task.reset()
                    rec.add("restart_ready")
                    continue
                await rc.timed_call(rec, driver, f"action{step}", candidate.tool, dict(candidate.arguments))
                pending = next_plan
                history.append(task.history_entry(step, candidate.id))
                if candidate.id in task.completion_candidate_ids:
                    polls = int(round(rc.POLL_DEADLINE_S * 1000 / arm.poll_ms))
                    for i in range(polls):
                        outcome = rc.oracle_read(rec, task, f"verify{i}", step)
                        if outcome in {"verified", "refuted"}:
                            result["outcome"] = outcome
                            result["poll_reads"] = i + 1
                            return
                        rec.add("sleep_start", poll_ms=arm.poll_ms)
                        await asyncio.sleep(arm.poll_ms / 1000)
                        rec.add("sleep_end")
            result["outcome"] = task.classify(task.read_oracle(), steps=task.max_steps)


async def control_one(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, out: Path) -> dict[str, Any]:
    """rc.one's bookkeeping around control_trial (same summary fields)."""
    name = spec["name"]
    trace_rel = f"trials/{name}.driver-trace.jsonl"
    rec = rc.Recorder()
    record: dict[str, Any] = {"trial": name, **{k: spec[k] for k in ("cls", "arm", "kind", "block")},
                              "round": spec.get("round"), "loadavg_before": rc.loadavg(), "driver_trace": trace_rel,
                              "lock_mode": spec.get("lock_mode")}
    res: dict[str, Any] = {}
    t0 = rc.now()
    try:
        await asyncio.wait_for(control_trial(spec, args, fixtures, out / trace_rel, rec, res), timeout=180)
    except Exception as error:
        res["outcome"] = "error"
        res["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    record["trial_wall_ns"] = rc.now() - t0
    rc.CLIENT["rec"] = None
    rc.CLIENT["compiled"] = None
    poller = res.pop("_poller", None)
    if poller is not None:
        deadline = time.monotonic() + 2.5
        while poller.first_ok_ns is None and time.monotonic() < deadline and poller._thread.is_alive():
            await asyncio.sleep(0.01)
        poller.stop()
        record["poller_first_ok_ns"] = poller.first_ok_ns
    pids = res.pop("pids", [])
    res.pop("prepared_pid", None)
    for _ in range(50):
        if not any(rc.pid_alive(p) for p in pids):
            break
        await asyncio.sleep(0.1)
    record["browsers_alive_after_close"] = [bool(rc.pid_alive(p)) for p in pids]
    await asyncio.sleep(0.3)
    cls = spec["cls"]
    final_state = fixtures.state(cls).snapshot()
    journal = fixtures.state(cls).drain()
    record.update(res)
    record["journal"] = journal
    if cls == "fill":
        record["oracle_exact_match"] = final_state.get("submitted") is not None and \
            rc.sha16(final_state["submitted"]) == res.get("token_sha16")
    else:
        record["final_state"] = {k: final_state.get(k) for k in ("checked", "opened", "modal")}
        record["oracle_exact_match"] = rc.oracle_ok("toggle-confirm" if cls == "toggle" else "modal", final_state, "")
    record["completion_mutations"] = len(rc.completion_mutations(cls, journal))
    record["network"] = dict(rc.NETWORK)
    record["loadavg_after"] = rc.loadavg()
    with (out / f"trials/{name}.jsonl").open("w") as f:
        for ev in rec.events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: record.get(k) for k in ("trial", "outcome", "oracle_exact_match", "completion_mutations",
                                                  "takeover_envelope", "old_binding_envelope", "decoy_connections",
                                                  "marker_in_fresh_snapshot", "error")}), flush=True)
    return record


# ── N-V: raw JSON-RPC envelopes for invalid calls ────────────────────────────

MODERN_META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
               "io.modelcontextprotocol/clientCapabilities": {}}
NV_CASES = {
    "V1_wrong_type": ("browser_navigate", {"session": "b02-nv", "target_id": 123, "tab_id": "t1",
                                            "url": "http://127.0.0.1:9/"}),
    "V2_missing_required": ("browser_navigate", {"session": "b02-nv"}),
    "V3_unknown_tool": ("b02_no_such_tool", {"session": "b02-nv"}),
    "V4_arguments_not_object": ("browser_navigate", ["b02"]),
}


async def nv_one(spec: dict[str, Any], args: argparse.Namespace, out: Path) -> dict[str, Any]:
    name = spec["name"]
    env = rc.driver_environment()
    env.pop(rc.TRACE_ENV, None)
    env[rc.TRACE_ENV] = str(out / f"trials/{name}.driver-trace.jsonl")
    proc = await asyncio.create_subprocess_exec(args.driver, "mcp", env=env, stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=64 * 1024 * 1024)

    async def rpc(msg: dict[str, Any], expect_reply: bool = True) -> str | None:
        proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
        await proc.stdin.drain()
        if not expect_reply:
            return None
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=20)
        return line.decode().rstrip("\n")

    replies: dict[str, str | None] = {}
    try:
        await rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "b02-nv", "version": "0"}}})
        await rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)
        rid = 10
        for era in ("legacy", "modern"):
            for case, (tool, arguments) in NV_CASES.items():
                rid += 1
                params: dict[str, Any] = {"name": tool, "arguments": arguments}
                if era == "modern":
                    params["_meta"] = MODERN_META
                replies[f"{era}:{case}"] = await rpc({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                                      "params": params})
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=20)
        except asyncio.TimeoutError:
            proc.kill()
    record = {"trial": name, "cls": "none", "arm": spec["arm"], "kind": "nv", "block": spec["block"],
              "lock_mode": spec.get("lock_mode"), "replies": replies, "loadavg_before": rc.loadavg(),
              "driver_env_knobs": {k: env[k] for k in KNOB_ENVS if k in env},
              "driver_trace": f"trials/{name}.driver-trace.jsonl"}
    with (out / f"trials/{name}.jsonl").open("w") as f:
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True) + "\n")
    print(json.dumps({"trial": name, "n_replies": len(replies)}), flush=True)
    return record


# ── plans ─────────────────────────────────────────────────────────────────────

def build_plan(kind: str, arms: list[str], rounds: int) -> list[list[dict[str, Any]]]:
    if kind == "measured":
        rows = williams_any(len(arms))
        trials = []
        for r in range(rounds):
            for cls in rc.CLASSES[r % 3:] + rc.CLASSES[:r % 3]:
                for j in rows[r % len(rows)]:
                    trials.append({"cls": cls, "arm": arms[j], "kind": "measured", "block": "m", "round": r,
                                   "lock_mode": "exclusive_external"})
        return [trials]
    if kind == "smoke":
        return [[{"cls": "fill", "arm": "K5", "kind": "measured", "block": "smoke", "lock_mode": "shared"}
                 for _ in range(5)]]
    if kind == "controls":
        with_e = [a for a in arms if "E" in a[2:]]
        with_v = [a for a in arms if "V" in a[2:]]
        trials: list[dict[str, Any]] = []
        for k in range(10):  # N-E1 takeover, 10 per arm
            for arm in ["K5", *with_e]:
                trials.append({"cls": rc.CLASSES[k % 3], "arm": arm, "kind": "ne1"})
        for k in range(5):  # N-E2 restart through the Driver, 5 per arm
            for arm in ["K5", *with_e]:
                trials.append({"cls": rc.CLASSES[k % 3], "arm": arm, "kind": "ne2"})
        for k in range(5):  # N-W1 stale ref after re-navigation, 5 per arm per class
            for cls in rc.CLASSES:
                for arm in arms:
                    trials.append({"cls": cls, "arm": arm, "kind": "stale_ref"})
        for k in range(5):  # N-W2 same-document DOM replacement, 5 per arm
            for arm in arms:
                trials.append({"cls": rc.CLASSES[k % 3], "arm": arm, "kind": "nw2"})
        for k in range(5):  # N-V invalid-call envelopes, 5 per arm
            for arm in ["K5", *with_v]:
                trials.append({"cls": "none", "arm": arm, "kind": "nv"})
        trials = trials[0::3] + trials[1::3] + trials[2::3]
        blocks = []
        for i in range(0, len(trials), 10):
            chunk = trials[i:i + 10]
            for t in chunk:
                t.update({"block": f"c{i // 10:02d}", "lock_mode": "shared"})
            blocks.append(chunk)
        return blocks
    raise ValueError(kind)


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    arms = args.arms.split(",")
    for arm in arms:
        if arm not in ARM_KNOBS:
            raise SystemExit(f"unknown arm {arm}")
    fixtures = rc.Fixtures()
    blocks = build_plan(args.plan_kind, arms, args.rounds)
    idx = 0
    for block in blocks:
        for spec in block:
            spec["name"] = f"{spec['block']}{idx:03d}-{spec['cls']}-{spec['arm']}-{spec['kind']}"
            idx += 1
    manifest: dict[str, Any] = {"plan_kind": args.plan_kind, "arms": arms, "arm_knobs": {a: ARM_KNOBS[a] for a in arms},
                                "blocks": [[s["name"] for s in b] for b in blocks], "started_mono_ns": rc.now(),
                                "started_utc": utc(), "loadavg_start": rc.loadavg(), "locks": [], "provider": "mock",
                                "rounds": args.rounds, "display": os.environ.get("DISPLAY")}
    args.save_snapshots = False
    try:
        for block in blocks:
            mode = block[0]["lock_mode"]
            fd = None
            if mode == "shared":
                if not args.lock:
                    raise SystemExit("refusing: this plan needs --lock")
                fd = os.open(args.lock, os.O_RDONLY | os.O_CREAT, 0o644)
                t_req, u_req = rc.now(), utc()
                fcntl.flock(fd, fcntl.LOCK_SH)
                lock_rec = {"mode": "shared", "requested_utc": u_req, "acquired_utc": utc(), "t_request_ns": t_req,
                            "t_acquired_ns": rc.now(), "first": block[0]["name"], "last": block[-1]["name"],
                            "trials": len(block)}
            elif mode != "exclusive_external":
                raise SystemExit(f"unknown lock mode {mode}")
            try:
                for spec in block:
                    CURRENT["knobs"] = dict(ARM_KNOBS[spec["arm"]])
                    if spec["kind"] in ("measured", "stale_ref"):
                        await rc.one(spec, args, fixtures, out)
                    elif spec["kind"] == "nv":
                        await nv_one(spec, args, out)
                    else:
                        await control_one(spec, args, fixtures, out)
                    CURRENT["knobs"] = {}
            finally:
                if fd is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    lock_rec.update({"released_utc": utc(), "t_released_ns": rc.now()})
                    manifest["locks"].append(lock_rec)
                    with (out / "lock-receipts.jsonl").open("a") as f:
                        f.write(json.dumps(lock_rec, sort_keys=True) + "\n")
    finally:
        manifest["ended_mono_ns"] = rc.now()
        manifest["ended_utc"] = utc()
        manifest["loadavg_end"] = rc.loadavg()
        manifest["network"] = dict(rc.NETWORK)
        (out / f"run-manifest-{args.plan_kind}.json").write_text(json.dumps(manifest, indent=1))
        fixtures.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", choices=("measured", "controls", "smoke"), required=True)
    p.add_argument("--arms", default="K5,K5E,K5V,K5EV")
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--lock")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (rc.TRACE_ENV, rc.KNOB_ENV, *KNOB_ENVS):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    # rc.one turns the Driver trace off only for plan == "smoke"; B-02 traces every trial
    # (the default-off smoke must show that no knob mark appears).
    args.plan_kind, args.plan = args.plan, f"b02-{args.plan}"
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

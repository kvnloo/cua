"""B-03 runner: decisive per-process vs per-document probe of the toggle cold first snapshot.

Run inside the isolated X11 session with the jev-use virtualenv:

    JEV_USE_DIR=<jev-use> <venv>/python run_b03.py --driver <bin> --out <dir> \
        --plan {measured|shakedown} [--rounds-from 0 --rounds-to 20] [--lock <quiet-lane.lock>]

measured: run under ``quiet-timed`` (the caller holds the EXCLUSIVE quiet-lane lock before
this process opens any Driver session); the runner takes no lock.
shakedown: the runner takes the quiet-lane lock SHARED (at most 10 trials per acquisition)
and appends a receipt to ``<out>/lock-receipts.jsonl``. Shakedown trials are excluded.

Every trial is B-01's K5 step loop (``run_critpath.run_trial``, reproduced below with three
measurement-only insertions, each marked ``B-03``) with one fresh ``cua-driver mcp`` and one
fresh Driver-launched browser (isolated_new profile):

- P=warm: after bind and before the task navigate, one throwaway ``browser_navigate`` to a
  different document on the same owned fixture origin plus one ``semantic_v2`` snapshot of it
  (labels ``warm_navigate`` / ``warm_snapshot``; both before task start).
- D=80: after the step-1 pre-observation oracle read, the harness sleeps 80 ms before the
  first observation send. ``task_start`` is stamped immediately before that sleep (D=0: an
  immediate ``task_start`` / ``delay_end`` pair), so T_oracle(D=80) includes the wait.
- variant=nc (negative control): one extra ``semantic_v2`` snapshot of the task document
  right after the task navigate (label ``nc_presnapshot``), so the task's first snapshot is a
  re-snapshot of the same document with no navigation in between.

Knobs reach the Driver through the environment only (``run_b02.ARM_KNOBS``: K5V, K5EV).
Output paths are relative to --out.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
B02 = HERE.parent / "b-02-browser-driver-sites-2026-10-02"
sys.path.insert(0, str(B02))

import run_b02 as R2  # noqa: E402  (patches rc.driver_environment with the per-trial knobs)
import run_critpath as rc  # noqa: E402

KNOB_ENVS = R2.KNOB_ENVS
TOGGLE_CELLS = [(k, p, d) for k in ("K5V", "K5EV") for p in ("cold", "warm") for d in (0, 80)]
FILL_CELLS = [(p, d) for p in ("cold", "warm") for d in (0, 80)]


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def warm_url(fixtures: Any, cls: str) -> str:
    """A different document on the same owned fixture origin (both return 200, no mutation)."""
    return fixtures.fill_url + "state" if cls == "fill" else fixtures.i24_origin + "modal"


async def b03_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, trace_path: Path | None,
                    rec: Any, result: dict[str, Any]) -> None:
    """rc.run_trial with the B-03 insertions (P warm-up, D delay, nc pre-snapshot)."""
    cls, kind, arm = spec["cls"], spec["kind"], rc.ARMS[spec["arm"]]
    P, D, variant = spec["P"], int(spec["D"]), spec["variant"]
    token = f"jev-{rc.uuid.uuid4().hex[:10]}"
    label = f"jev-b03-{rc.uuid.uuid4().hex[:8]}"
    task = rc.make_task(cls, token, fixtures)
    result.update({"token_sha16": rc.sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "routes": [], "tools": [], "input_routes": [], "candidates": [],
                   "P": P, "D": D, "variant": variant})
    task.reset()
    fixtures.state(cls).drain()
    poller = rc.OraclePoller(fixtures, cls, token)
    result["_poller"] = poller
    env = rc.driver_environment()
    env.pop(rc.TRACE_ENV, None)
    env.pop(rc.KNOB_ENV, None)
    if trace_path is not None:
        env[rc.TRACE_ENV] = str(trace_path)
    if arm.knob_zero and cls == "fill":
        env[rc.KNOB_ENV] = "0"
    result["driver_env_trace_set"] = rc.TRACE_ENV in env
    result["driver_env_knob"] = env.get(rc.KNOB_ENV)
    result["driver_env_knobs"] = {k: env[k] for k in KNOB_ENVS if k in env}
    result["driver_env_telemetry"] = env.get("CUA_DRIVER_RS_TELEMETRY_ENABLED")
    rec.add("trial_start", cls=cls, arm=spec["arm"], kind=kind, P=P, D=D, variant=variant)
    rc.CLIENT["rec"] = rec
    rc.CLIENT["compiled"] = None
    params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    async with rc.stdio_client(params) as (read, write):
        async with rc.ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            if arm.compiled_validator:
                rec.add("compile_validators_start")
                result["compiled_validators"] = rc.compile_output_validators(session)
                rec.add("compile_validators_end")
            available = {tool.name for tool in tools}
            capture_bound = rc.supports_capture_bound_click(tools)
            driver = rc.Driver(session, label)
            await rc.timed_call(rec, driver, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm.cursor})
            motion = await rc.timed_call(rec, driver, "cursor_motion", "set_agent_cursor_motion",
                                         rc.FAST_MOTION if arm.fast_glide else rc.DEFAULT_MOTION)
            result["motion_ack"] = {k: motion.get(k) for k in ("glide_duration_ms", "dwell_after_click_ms")
                                    if isinstance(motion, dict)}
            prepared = await rc.timed_call(rec, driver, "prepare", "browser_prepare",
                                           {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            result["prepared_pid"] = pid
            window = await rc.wait_for_window(driver, pid)
            rec.add("window_ready")
            bound = await rc.timed_call(rec, driver, "bind", "get_browser_state",
                                        {"pid": pid, "window_id": window["window_id"]})
            target_id = bound["target_id"]
            tab_id = rc.select_tab_id(bound["tabs"])
            tgt = {"target_id": target_id, "tab_id": tab_id}
            if P == "warm":  # B-03: throwaway navigate + snapshot of a different document, before task start
                await rc.timed_call(rec, driver, "warm_navigate", "browser_navigate", {**tgt, "url": warm_url(fixtures, cls)})
                await rc.timed_call(rec, driver, "warm_snapshot", "get_browser_state", {**tgt, "snapshot_format": "semantic_v2"})
            await rc.timed_call(rec, driver, "navigate", "browser_navigate", {**tgt, "url": fixtures.page_url(cls)})
            if variant == "nc":  # B-03: same-document re-snapshot control (no navigation after this)
                await rc.timed_call(rec, driver, "nc_presnapshot", "get_browser_state",
                                    {**tgt, "snapshot_format": "semantic_v2"})
            poller.start()
            history: list[dict[str, Any]] = []
            pending = None
            for step in range(1, task.max_steps + 1):
                current = rc.oracle_read(rec, task, f"pre_step{step}", step - 1)
                if current in {"verified", "refuted"}:
                    result["outcome"] = current
                    return
                if step == 1:  # B-03: task start; D=80 waits before the first observation send
                    rec.add("task_start", D=D)
                    if D:
                        await asyncio.sleep(D / 1000)
                    rec.add("delay_end", D=D)
                snap = await rc.timed_call(rec, driver, f"snapshot{step}", "get_browser_state",
                                           {**tgt, "snapshot_format": "semantic_v2"})
                rec.add("cand_start", step=step)
                candidates, sources, visual_record = await rc.task_candidates_for_step(
                    driver, task, snap, pid, int(window["window_id"]), available, capture_bound,
                    visual_mode="auto")
                rec.add("cand_done", step=step, ids=[c.id for c in candidates],
                        visual=visual_record.get("status") if isinstance(visual_record, dict) else None)
                candidate = None
                guard_tel = None
                if arm.guard and pending is not None:
                    rec.add("guard_start", step=step)
                    resolution = rc.resolve_guarded_completion(pending, task, sources, candidates, session=label)
                    candidate, guard_tel = resolution.candidate, resolution.telemetry
                    pending = None
                    rec.add("guard_done", step=step, status=guard_tel.get("status"), reason=guard_tel.get("reason"))
                if candidate is not None:
                    route = "guarded-completion"
                else:
                    rec.add("decide_start", step=step)
                    choice, _confidence, _probabilities = rc.choose_mock_for_task(task, sources, candidates, history)
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
                result.setdefault("guard", []).append(guard_tel)
                result.setdefault("guard_plan_bound", []).append(next_plan is not None)
                rec.add("routed", step=step, route=route, candidate=candidate.id, tool=candidate.tool,
                        plan_bound=next_plan is not None)
                if candidate.id == "reobserve":
                    history.append(task.history_entry(step, candidate.id))
                    continue
                if candidate.id == "abstain":
                    result["outcome"] = "abstained"
                    return
                try:
                    action = await rc.timed_call(rec, driver, f"action{step}", candidate.tool, dict(candidate.arguments))
                except Exception as error:
                    result["outcome"] = "unknown"
                    result["action_error"] = {"type": type(error).__name__, "code": getattr(error, "code", None)}
                    return
                result.setdefault("action_effects", []).append(action.get("effect") if isinstance(action, dict) else None)
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


rc.run_trial = b03_trial  # rc.one (bookkeeping, poller, journal, summary) looks run_trial up at call time


def build_plan(kind: str, r_from: int, r_to: int) -> list[list[dict[str, Any]]]:
    if kind == "shakedown":
        specs = [("toggle", "K5V", "cold", 0, "task"), ("toggle", "K5EV", "warm", 80, "task"),
                 ("toggle", "K5V", "warm", 0, "task"), ("toggle", "K5EV", "cold", 80, "task"),
                 ("fill", "K5V", "warm", 80, "task"), ("fill", "K5V", "cold", 0, "task"),
                 ("toggle", "K5V", "cold", 0, "nc")]
        return [[{"cls": c, "arm": a, "P": p, "D": d, "variant": v, "kind": "measured", "block": "shake",
                  "round": None, "lock_mode": "shared"} for c, a, p, d, v in specs]]
    if kind != "measured":
        raise ValueError(kind)
    w8, w4 = rc.williams(8), rc.williams(4)
    trials: list[dict[str, Any]] = []
    for r in range(r_from, r_to):
        tog = [dict(zip(("arm", "P", "D"), TOGGLE_CELLS[j]), cls="toggle", variant="task") for j in w8[r % 8]]
        fill = ([dict(P=FILL_CELLS[j][0], D=FILL_CELLS[j][1], arm="K5V", cls="fill", variant="task")
                 for j in w4[(r // 2) % 4]] if r % 2 == 0 else [])
        nc = [dict(arm="K5V", P="cold", D=0, cls="toggle", variant="nc")]
        seq = tog[:4] + fill[:2] + nc + tog[4:] + fill[2:]
        for s in seq:
            trials.append({**s, "kind": "measured", "block": "m", "round": r, "lock_mode": "exclusive_external"})
    return [trials]


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    fixtures = rc.Fixtures()
    blocks = build_plan(args.plan_kind, args.rounds_from, args.rounds_to)
    for block in blocks:
        for spec in block:
            rtag = "x" if spec["round"] is None else f"{spec['round']:02d}"
            spec["name"] = (f"{spec['block']}{rtag}-{spec['cls']}-{spec['arm']}-{spec['P']}-D{spec['D']}"
                            f"-{spec['variant']}")
    names = [s["name"] for b in blocks for s in b]
    if len(set(names)) != len(names):
        raise SystemExit("refusing: duplicate trial names in plan")
    manifest: dict[str, Any] = {"plan_kind": args.plan_kind, "rounds": [args.rounds_from, args.rounds_to],
                                "arm_knobs": {a: R2.ARM_KNOBS[a] for a in ("K5V", "K5EV")},
                                "blocks": [[s["name"] for s in b] for b in blocks], "started_mono_ns": rc.now(),
                                "started_utc": utc(), "loadavg_start": rc.loadavg(), "locks": [], "provider": "mock",
                                "display": os.environ.get("DISPLAY")}
    args.save_snapshots = False
    try:
        for block in blocks:
            mode = block[0]["lock_mode"]
            chunks = [block] if mode == "exclusive_external" else [block[i:i + 10] for i in range(0, len(block), 10)]
            for chunk in chunks:
                fd = None
                if mode == "shared":
                    if not args.lock:
                        raise SystemExit("refusing: this plan needs --lock")
                    fd = os.open(args.lock, os.O_RDONLY | os.O_CREAT, 0o644)
                    u_req = utc()
                    fcntl.flock(fd, fcntl.LOCK_SH)
                    lock_rec = {"mode": "shared", "requested_utc": u_req, "acquired_utc": utc(),
                                "first": chunk[0]["name"], "last": chunk[-1]["name"], "trials": len(chunk)}
                elif mode != "exclusive_external":
                    raise SystemExit(f"unknown lock mode {mode}")
                try:
                    for spec in chunk:
                        R2.CURRENT["knobs"] = dict(R2.ARM_KNOBS[spec["arm"]])
                        await rc.one(spec, args, fixtures, out)
                        R2.CURRENT["knobs"] = {}
                finally:
                    if fd is not None:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                        os.close(fd)
                        lock_rec["released_utc"] = utc()
                        manifest["locks"].append(lock_rec)
                        with (out / "lock-receipts.jsonl").open("a") as f:
                            f.write(json.dumps(lock_rec, sort_keys=True) + "\n")
    finally:
        manifest["ended_mono_ns"] = rc.now()
        manifest["ended_utc"] = utc()
        manifest["loadavg_end"] = rc.loadavg()
        manifest["network"] = dict(rc.NETWORK)
        tag = f"{args.plan_kind}-r{args.rounds_from:02d}-{args.rounds_to:02d}"
        (out / f"run-manifest-{tag}.json").write_text(json.dumps(manifest, indent=1))
        fixtures.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", choices=("measured", "shakedown"), required=True)
    p.add_argument("--rounds-from", type=int, default=0)
    p.add_argument("--rounds-to", type=int, default=20)
    p.add_argument("--lock")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (rc.TRACE_ENV, rc.KNOB_ENV, *KNOB_ENVS):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    args.plan_kind, args.plan = args.plan, f"b03-{args.plan}"
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

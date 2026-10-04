"""R2-07c harness: compiled fresh-bound routine for #24 toggle->confirm and modal->act on binary R.

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``run_chunk.sh`` -> ``in_session.sh``; the quiet-lane lock (EXCLUSIVE via bin/quiet-timed, or SHARED
for controls) is taken OUTSIDE, before the session opens. Output paths are relative to --out.

Reuses, by import and unchanged, the R2-10 browser harness (harness/src/r2-10-composition-2026-10-02/
harness/r2_10_browser.py, copied by path from exp/r2-10-composition-2026-10-02 030f6bdbf): arm
configuration (``ARMS["COMP"]``), Driver environment, the 2 ms independent oracle sampler,
the recording Driver proxy and its freshness receipts, the per-trial record (``finish_record``),
the DOM replacement used by N4a, the B-02 N-W2 control and R2-10's own COMP trial (``one``) for the
timing comparison. New here: the toggle/modal compiled routine (``compiled_routine_tm``), the
variant/hold fixture (``fixture_tm``), the action-2 fault seam (``fault_transport_tm``) and the
guarded continuation (the fallback point) with a role+name uniqueness filter.

Arms (same binary, same Driver environment, phase trace on in every arm):
  COMP     R2-10 COMP for toggle/modal: feedback OFF, 10 ms completion poll, compiled validators,
           admission tools-list cache; the step loop decides each click (scripted or TypeSafe).
  COMP_CR  COMP + compiled replay: warm invocations replay the admitted artifact with a fresh
           observation before every click and 0 decisions; any failed precondition hands the
           current state to the guarded continuation (decisions counted).

Plans: shakedown, traingate (G1+G2), timing (COMP vs COMP_CR, AB/BA), costs (G6 fallback / wrong
match cells), negatives (G4), nw2 (G4 N-W2), reconcile (G5), live_shake, live (Phase L).
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
R210 = HERE / "src" / "r2-10-composition-2026-10-02" / "harness"
sys.path[:0] = [str(HERE), str(R210)]

import r2_10_browser as rb10  # noqa: E402  (sets sys.path for the B-02 and R2-07 sources)

rc, rb, cr = rb10.rc, rb10.rb, rb10.cr
import compiled_routine_tm as crt  # noqa: E402
import fault_transport_tm as ftt  # noqa: E402
import fixture_tm as fx  # noqa: E402
from run import DriverToolError  # noqa: E402
import jev_adapter  # noqa: E402

CLASSES = ["toggle", "modal"]
NEG_KINDS = {"n1": "n1_renamed", "n2": "n2_missing", "n3": "n3_duplicate", "n4a": "normal", "n4b": "normal",
             "n5": "normal", "n6": "n6_dialog", "n7": "n7_presat"}
OOD = [("toggle", "fill"), ("toggle", "modal"), ("modal", "toggle")]
G5_ROWS = {
    "applied_ack_lost": {"hold": "immediate", "barrier": "applied", "reps": 5},
    "delayed_after_first_unchanged_read": {"hold": "after_unchanged:1", "barrier": "received", "reps": 5},
    "withheld_unresolved": {"hold": "withheld", "barrier": "received", "reps": 3},
}
LIVE_RESERVE = 4  # a live invocation can need at most task.max_steps (4) decisions
LEDGER: dict[str, Any] = {"path": None, "attempts": 0, "reached": 0, "blocked": 0, "cap_reached": 0,
                          "cap_attempts": 0}
DRIVER_ID: dict[str, Any] = {}
now, utc, sha16, loadavg = rb10.now, rb10.utc, rb10.sha16, rb10.loadavg


# ── provider ledger with a hard cap (live plans only) ────────────────────────

def install_provider_ledger_c(path: Path, cap_reached: int, cap_attempts: int) -> None:
    """One line per provider HTTP attempt (host, path, status, request-id presence + sha256/16,
    latency, trial). No headers, bodies or credentials. Refuses BEFORE sending once either lane
    cap would be exceeded (a refused send is not an attempt; it is logged as blocked_by_cap)."""
    import httpx2
    from urllib.parse import urlsplit

    LEDGER.update({"path": path, "cap_reached": cap_reached, "cap_attempts": cap_attempts})
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("kind") == "attempt":
                    LEDGER["attempts"] += 1
                    LEDGER["reached"] += 1 if rec.get("reached") else 0
    original = httpx2.Client.request

    def write(rec: dict[str, Any]) -> None:
        with path.open("a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    @functools.wraps(original)
    def request(self: Any, method: Any, url: Any, *args: Any, **kwargs: Any) -> Any:
        parts = urlsplit(str(url))
        base = {"utc": utc(), "host": parts.hostname, "path": parts.path, "trial": rb10.CTX["trial"],
                "class": rb10.CTX["cls"], "arm": rb10.CTX["arm"], "layer": rb10.CTX["layer"]}
        if LEDGER["attempts"] + 1 > cap_attempts or LEDGER["reached"] + 1 > cap_reached:
            LEDGER["blocked"] += 1
            write({"kind": "blocked_by_cap", **base, "attempts": LEDGER["attempts"], "reached": LEDGER["reached"]})
            raise RuntimeError("lane provider cap: request not sent")
        LEDGER["attempts"] += 1
        rec = {"kind": "attempt", "attempt": LEDGER["attempts"], **base}
        t0 = now()
        try:
            response = original(self, method, url, *args, **kwargs)
        except BaseException as error:
            rec.update({"reached": False, "latency_ms": round((now() - t0) / 1e6, 3), "error": type(error).__name__})
            write(rec)
            raise
        LEDGER["reached"] += 1
        rid = response.headers.get("x-typesafe-request-id")
        rec.update({"reached": True, "latency_ms": round((now() - t0) / 1e6, 3), "status": response.status_code,
                    "request_id_present": bool(rid),
                    "request_id_sha256_16": hashlib.sha256(rid.encode()).hexdigest()[:16] if rid else None})
        write(rec)
        return response

    httpx2.Client.request = request


# ── recording proxy: R2-10 RecDriver + checked_state in the snapshot receipts ─

class RecDriverC(rb10.RecDriver):
    async def call(self, name: str, arguments: dict[str, Any], label: str | None = None) -> dict[str, Any]:
        data = await super().call(name, arguments, label)
        if self.receipts is not None and name == "get_browser_state" and arguments.get("snapshot_format"):
            refs = [r for r in (data.get("refs") or []) if isinstance(r, dict)]
            for entry, ref in zip(self.receipts[-1].get("refs_logical") or [], refs):
                entry["checked_state"] = crt.checked_state(ref)
        return data


# ── the guarded continuation (fallback point; also the training run) ─────────

async def continuation(*, rec: Any, drv: RecDriverC, task: Any, target_id: str, tab_id: str, pid: int,
                       window: dict[str, Any], available: set[str], capture_bound: bool, poll_ms: int,
                       provider: str, result: dict[str, Any], route_prefix: str = "") -> str:
    """R2-10 ``step_loop`` rules (run.py incl. FIX-01 Part B) from the CURRENT state, plus a
    role+name uniqueness filter: a page candidate whose target is not unique in the fresh
    observation is dropped, so the continuation can never make an ambiguous dispatch. Guarded
    completion binds nothing for toggle/modal (trycua/cua PR 4316 plans fill only), so every
    click is a decision. Visual parsing is off (the #24 tasks only use the page source)."""
    history: list[dict[str, Any]] = []
    dispatched: set[str] = set()
    refusal_retried = False
    for step in range(1, task.max_steps + 1):
        current = rc.oracle_read(rec, task, f"pre_step{route_prefix}{step}", step - 1)
        if current in {"verified", "refuted"}:
            return current
        snap = await drv.call("get_browser_state", {"target_id": target_id, "tab_id": tab_id,
                                                    "snapshot_format": "semantic_v2"})
        rec.add("cand_start", step=step)
        candidates, sources, _visual = await rc.task_candidates_for_step(
            drv.inner, task, snap, pid, int(window["window_id"]), available, capture_bound, visual_mode="off")
        refs = [r for r in snap.get("refs") or [] if isinstance(r, dict)]
        safe, dropped = [], []
        for cand in candidates:
            ref = (cand.arguments or {}).get("ref")
            entry = next((r for r in refs if r.get("ref") == ref), None) if ref else None
            n = sum(1 for r in refs if entry is not None and r.get("role") == entry.get("role")
                    and r.get("name") == entry.get("name"))
            (safe if ref is None or n == 1 else dropped).append(cand)
        if dropped:
            result.setdefault("dropped_not_unique", []).append([c.id for c in dropped])
        rec.add("cand_done", step=step, ids=[c.id for c in safe], dropped=[c.id for c in dropped])
        rec.add("decide_start", step=step, provider=provider)
        try:
            if provider == "live":
                choice, _conf, _probs = await asyncio.to_thread(jev_adapter.choose_live_for_task, task, sources,
                                                                safe, history)
            else:
                choice, _conf, _probs = rc.choose_mock_for_task(task, sources, safe, history)
        except Exception as error:  # provider failure: retained, never retried here
            rec.add("decided", step=step, choice=None, error=type(error).__name__)
            result["provider_error"] = type(error).__name__
            return "unknown"
        rec.add("decided", step=step, choice=choice)
        result.setdefault("decisions", []).append({"step": f"{route_prefix}{step}", "choice": choice,
                                                   "provider": provider})
        if drv.receipts is not None:
            drv.receipts.append({"kind": "provider_response", "ok": choice is not None, "backend": provider,
                                 "selected_id": choice})
        if choice is None:
            return "abstained"
        candidate = rc.validate_choice(choice, safe, current_capture_id=None)
        result["routes"].append(route_prefix + "provider")
        result["candidates"].append(candidate.id)
        result["tools"].append(candidate.tool)
        result["input_routes"].append((candidate.arguments or {}).get("input_route"))
        rec.add("routed", step=step, route="provider", candidate=candidate.id, tool=candidate.tool)
        if candidate.id == "reobserve":
            history.append(task.history_entry(step, candidate.id))
            continue
        if candidate.id == "abstain":
            return "abstained"
        if candidate.id in dispatched:
            result["stop"] = "redispatch_blocked"
            return "unknown"
        try:
            await drv.call(candidate.tool, dict(candidate.arguments))
            dispatched.add(candidate.id)
        except Exception as error:
            if isinstance(error, DriverToolError) and error.refused:
                code = error.code or "refused"
                result.setdefault("refusals", []).append({"step": step, "candidate": candidate.id, "code": code})
                if refusal_retried:
                    result["stop"] = f"second_refusal:{code}"
                    return "unknown"
                refusal_retried = True
                history.append({"step": step, "selected_id": candidate.id,
                                "outcome": f"Driver refused the action ({code}); nothing was dispatched"})
                continue
            result["action_error"] = {"type": type(error).__name__, "code": getattr(error, "code", None)}
            return "unknown"
        history.append(task.history_entry(step, candidate.id))
        if candidate.id in task.completion_candidate_ids:
            for i in range(int(round(rb10.POLL_DEADLINE_S * 1000 / poll_ms))):
                outcome = rc.oracle_read(rec, task, f"verify{route_prefix}{i}", step)
                if outcome in {"verified", "refuted"}:
                    result["poll_reads"] = i + 1
                    return outcome
                rec.add("sleep_start", poll_ms=poll_ms)
                await asyncio.sleep(poll_ms / 1000)
                rec.add("sleep_end")
            result["stop"] = "reconcile_unconfirmed"
            return "unknown"
    return task.classify(task.read_oracle(), steps=task.max_steps)


# ── routine store ────────────────────────────────────────────────────────────

class Store:
    def __init__(self, root: Path) -> None:
        self.dir = root / "routines"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, layer: str, cls: str) -> Path:
        return self.dir / f"{layer}-{cls}.json"

    def get(self, layer: str, cls: str) -> dict[str, Any] | None:
        p = self.path(layer, cls)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, layer: str, cls: str, state: dict[str, Any]) -> None:
        self.path(layer, cls).write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


# ── one COMP_CR trial ────────────────────────────────────────────────────────

async def run_trial_c(spec: dict[str, Any], args: argparse.Namespace, fixtures: fx.FixturesC, store: Store,
                      trace_path: Path, rec: Any, result: dict[str, Any]) -> None:
    cls, kind, layer = spec["cls"], spec["kind"], spec["layer"]
    page_cls = spec.get("page_cls", cls)
    arm = rb10.ARMS["COMP"]
    provider = "live" if layer.startswith("live") else "mock"
    token = f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-r207c-{uuid.uuid4().hex[:8]}"
    fixtures.configure(spec.get("variant", "normal"), spec.get("hold", "immediate"))
    page_task = rc.make_task(page_cls, token, fixtures)
    task_c = rc.make_task(cls, token, fixtures)
    task_class = crt.CLASS_OF[cls]
    result.update({"token_sha16": sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "routes": [], "tools": [], "input_routes": [], "candidates": [],
                   "page_cls": page_cls, "variant": spec.get("variant", "normal"), "hold": spec.get("hold", "immediate")})
    page_task.reset()
    if page_cls != cls and page_cls == "fill":
        task_c.reset()
    fixtures.state(page_cls).drain()
    sampler = rb10.Sampler(fixtures, page_cls, token)
    result["_sampler"] = sampler
    env = rb10.driver_env_for(arm, cls, trace_path)
    result["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
    result["driver_env_trace_set"] = rb10.TRACE_ENV in env
    mode = {"train": "train", "admission": "admission"}.get(kind, "replay")
    result["mode"] = mode
    receipts: list[dict[str, Any]] | None = [] if mode == "train" else None
    artifact = None
    if mode == "admission":
        artifact = spec["_artifact"]
    elif mode == "replay":
        state = store.get(spec["store_layer"], cls)
        if not (state and state.get("admitted") and state.get("artifact")):
            raise RuntimeError(f"no admitted routine for {spec['store_layer']}/{cls}")
        artifact = state["artifact"]
    transport = rc.stdio_client
    plan = None
    if kind == "g5":
        plan = ftt.FaultPlan(mode="ack_lost", barrier_kind=spec["barrier"], barrier_wait=fixtures.i24.state.wait_for)
        transport = functools.partial(ftt.fault_stdio_client, plan=plan)
        result["_plan"] = plan
    rec.add("trial_start", cls=cls, arm="COMP_CR", kind=kind, layer=layer, mode=mode)
    rc.CLIENT["rec"] = rec
    rb10.CTX_REC["rec"] = rec
    rc.CLIENT["compiled"] = None
    params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    async with transport(params) as (read, write):
        async with rc.ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            rec.add("compile_validators_start")
            result["compiled_validators"] = rc.compile_output_validators(session)
            rec.add("compile_validators_end")
            available = {tool.name for tool in tools}
            capture_bound = rc.supports_capture_bound_click(tools)
            inner = rc.Driver(session, label)
            drv = RecDriverC(inner, rec, token, receipts)
            result["_drv"] = drv
            await rc.timed_call(rec, inner, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm["cursor"]})
            motion = await rc.timed_call(rec, inner, "cursor_motion", "set_agent_cursor_motion", rb10.DEFAULT_MOTION)
            result["motion_ack"] = {k: motion.get(k) for k in ("glide_duration_ms", "dwell_after_click_ms")
                                    if isinstance(motion, dict)}
            prepared = await rc.timed_call(rec, inner, "prepare", "browser_prepare",
                                           {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            result["prepared_pid"] = pid
            window = await rc.wait_for_window(inner, pid)
            rec.add("window_ready")
            bound = await rc.timed_call(rec, inner, "bind", "get_browser_state",
                                        {"pid": pid, "window_id": window["window_id"]})
            target_id = bound["target_id"]
            tab_id = rc.select_tab_id(bound["tabs"])
            url = fixtures.page_url(page_cls)
            await rc.timed_call(rec, inner, "navigate", "browser_navigate",
                                {"target_id": target_id, "tab_id": tab_id, "url": url})
            sampler.start()
            loop_kw = dict(rec=rec, drv=drv, task=task_c, target_id=target_id, tab_id=tab_id, pid=pid, window=window,
                           available=available, capture_bound=capture_bound, poll_ms=arm["poll_ms"],
                           provider=provider, result=result)
            if mode == "train":
                result["outcome"] = await continuation(**loop_kw)
                result["t_end_ns"] = now()
                return

            async def fallback(ctx: Any, rrec: Any, index: int, reason: str) -> str:
                rec.add("fallback_start", index=index, reason=reason)
                result["fallback"] = {"index": index, "reason": reason}
                out = await continuation(**{**loop_kw, "target_id": ctx.target_id, "tab_id": ctx.tab_id},
                                         route_prefix="fallback:")
                return "fallback_verified" if out == "verified" else out

            async def hook(where: str, index: int, ctx: Any, rrec: Any) -> None:
                if kind == "n4a" and where == "before_dispatch" and index == 1 and not result.get("dom_replace"):
                    result["dom_replace"] = await asyncio.to_thread(rb10.dom_replace, pid, url, page_cls)
                    rec.add("dom_replaced", result=result["dom_replace"])
                elif kind == "n4b" and where == "before_dispatch" and index == 1 and not result.get("superseded"):
                    snap = await ctx.driver.call("get_browser_state", {"target_id": ctx.target_id, "tab_id": ctx.tab_id,
                                                                       "snapshot_format": "semantic_v2"},
                                                 label="supersede_snapshot")
                    result["superseded"] = {"by_snapshot": (snap.get("snapshot") or {}).get("id")}
                    rec.add("superseded")
                elif kind == "n5" and where == "before_step" and index == 1 and not result.get("session_replaced"):
                    old_target, old_tab = ctx.target_id, ctx.tab_id
                    new_label = f"jev-r207c-{uuid.uuid4().hex[:8]}"
                    drv.inner = rc.Driver(drv.inner.session, new_label)
                    drv.label = new_label
                    ctx.target_id = ctx.tab_id = None
                    probe: dict[str, Any] = {"session_replaced": True}
                    try:  # discriminating control: the OLD target capability must not resolve in the new session
                        await drv.inner.call("get_browser_state", {"target_id": old_target, "tab_id": old_tab,
                                                                   "snapshot_format": "semantic_v2"})
                        probe["old_target_in_new_session"] = "accepted"
                    except Exception as error:  # noqa: BLE001
                        probe["old_target_in_new_session"] = "refused"
                        probe["old_target_refusal_code"] = getattr(error, "code", None)
                    result["session_replaced"] = probe
                    rec.add("session_replaced", **probe)

            async def rebind(ctx: Any) -> None:
                await drv.call("set_agent_cursor_enabled", {"enabled": False}, label="rebind_cursor_off")
                await drv.call("browser_prepare", {"pid": ctx.pid}, label="rebind_prepare")
                bound2 = await drv.call("get_browser_state", {"pid": ctx.pid, "window_id": ctx.window_id},
                                        label="rebind_bind")
                ctx.target_id, ctx.tab_id = bound2["target_id"], rc.select_tab_id(bound2["tabs"])

            def read_oracle() -> dict[str, Any]:
                rec.add("oracle_send", label="routine_read")
                state = task_c.read_oracle()
                rec.add("oracle_return", label="routine_read", outcome=crt.verdict(task_class, state)
                        if crt.verdict(task_class, state) != "pending" else "unknown")
                return dict(state)

            routine = crt.RoutineTM(artifact, fallback=None if mode == "admission" else fallback, hook=hook)
            ctx = cr.ReplayContext(driver=drv, target_id=target_id, tab_id=tab_id, pid=pid,
                                   window_id=int(window["window_id"]), fixture_url=url, token=token,
                                   read_oracle=read_oracle, rebind=rebind)
            rrec = cr.ReplayRecord()
            result["_rrec"] = rrec
            rrec.t0_ns = now()
            await routine.replay(ctx, rrec)
            if (mode != "admission" and rrec.outcome == "stopped" and str(rrec.stop_reason or "") == "refused:browser_ref_stale"
                    and not result.get("fallback")):
                # Second pre-dispatch refusal: nothing landed; the guarded continuation takes the current state.
                rrec.outcome = await fallback(ctx, rrec, -1, "refused:browser_ref_stale")
            result["t_end_ns"] = now()


def routine_fields(result: dict[str, Any], record: dict[str, Any]) -> None:
    rrec = result.get("_rrec")
    if rrec is None:
        return
    record["routine"] = {k: v for k, v in rrec.as_dict().items() if k != "events"}
    record["routine_events"] = rrec.events
    record["routine_outcome"] = rrec.outcome
    record["routes"] = ["compiled"] + list(record.get("routes") or [])
    if record.get("outcome") not in ("error",):
        record["outcome"] = {"fallback_verified": "verified", "verified_by_reconcile": "verified"}.get(
            rrec.outcome, rrec.outcome)


async def one_c(spec: dict[str, Any], args: argparse.Namespace, fixtures: fx.FixturesC, store: Store,
                out: Path) -> dict[str, Any]:
    name = spec["name"]
    trace_rel = f"trials/{name}.driver-trace.jsonl"
    rec = rc.Recorder()
    record: dict[str, Any] = {"trial": name, "arm": "COMP_CR",
                              **{k: spec.get(k) for k in ("cls", "kind", "block", "layer", "round", "order", "page_cls",
                                                          "variant", "hold", "barrier", "g5_row", "store_layer")},
                              "loadavg_before": loadavg(), "driver_trace": trace_rel, "utc_start": utc(), **DRIVER_ID}
    rb10.CTX.update({"trial": name, "cls": spec["cls"], "arm": "COMP_CR", "layer": spec["layer"]})
    res: dict[str, Any] = {}
    t0 = now()
    try:
        await asyncio.wait_for(run_trial_c(spec, args, fixtures, store, out / trace_rel, rec, res), timeout=180)
    except Exception as error:  # every failure is kept
        rrec = res.get("_rrec")
        leaves, stack = [], [error]
        while stack:
            e = stack.pop()
            subs = getattr(e, "exceptions", None)
            if subs:
                stack.extend(subs)
            else:
                leaves.append(f"{type(e).__name__}: {e}"[:300])
        if rrec is not None and rrec.outcome != "running" and spec["kind"] == "g5":
            res["context_exit_error"] = leaves  # expected after the seam's EOF; the routine had finished
        else:
            res["outcome"] = "error"
            res["error"] = f"{type(error).__name__}: {str(error)[:300]}"
            res["error_leaves"] = leaves
            if rrec is not None and rrec.outcome == "running":
                rrec.outcome = "error"
    rc.CLIENT["rec"] = None
    rb10.CTX_REC["rec"] = None
    rc.CLIENT["compiled"] = None
    sampler = res.pop("_sampler", None)
    drv = res.pop("_drv", None)
    receipts = drv.receipts if (drv is not None and spec["kind"] == "train") else None
    plan = res.pop("_plan", None)
    page_cls = spec.get("page_cls", spec["cls"])
    if plan is not None:
        record["seam_events"] = plan.events
        record["fault_fired"] = plan.fired
    if spec["kind"] == "g5":
        st = fixtures.i24.state
        record["journal_before_release"] = {
            "received": sum(1 for e in st.journal if e["event"] == "received"),
            "applied": sum(1 for e in st.journal if e["event"] == "applied"),
            "caller_state_reads": sum(1 for e in st.journal if e["event"] == "state_read")}
        st.release_all("harness_release_after_caller_finished")
        record["journal_quiescent"] = st.wait_quiescent(15)
    if sampler is None:
        sampler = rb10.Sampler(fixtures, page_cls, "")
        sampler._thread = threading.Thread(target=lambda: None)
        sampler._thread.start()
    t_end = res.pop("t_end_ns", None)
    record = await rb10.finish_record(record, res, sampler, rec, fixtures, page_cls, t0, drv)
    routine_fields(res, record)
    record["t_end_ns"] = t_end
    record["provider_decisions"] = sum(1 for e in rec.events if e["event"] == "decided" and e.get("choice") is not None)
    rb10.CTX.update({"trial": None})
    if receipts is not None:
        learning_verified = bool(record.get("outcome") == "verified" and record.get("oracle_exact_match")
                                 and record.get("completion_mutations") == 1)
        c0 = time.perf_counter_ns()
        try:
            artifact = crt.compile_trace_tm(receipts, learning_verified=learning_verified,
                                            routine_id=f"r2-07c-{spec['cls']}-{spec['layer']}",
                                            task_class=crt.CLASS_OF[spec["cls"]])
            compile_error = None
        except Exception as error:  # noqa: BLE001
            artifact, compile_error = None, f"{type(error).__name__}: {error}"
        compile_ms = (time.perf_counter_ns() - c0) / 1e6
        record["training"] = {"learning_verified": learning_verified, "compile_ms": compile_ms,
                              "compile_error": compile_error, "receipts": len(receipts),
                              "authority_problems": crt.check_artifact_authority_tm(artifact) if artifact else None}
        state: dict[str, Any] = {"trained_by": name, "learning_verified": learning_verified, "compile_ms": compile_ms,
                                 "compile_error": compile_error, "artifact": artifact, "admitted": False}
        write_trial(out, name, rec, record)
        if artifact is not None:
            (out / f"artifact-{spec['layer']}-{spec['cls']}.json").write_text(crt.dumps(artifact))
            adm_spec = {**spec, "name": f"{name}-admission", "kind": "admission", "_artifact": artifact}
            adm = await one_c(adm_spec, args, fixtures, store, out)
            admitted = bool(adm.get("routine_outcome") == "verified" and adm.get("oracle_exact_match")
                            and adm.get("completion_mutations") == 1
                            and all(m.get("fresh") for m in adm.get("mutations") or [])
                            and adm.get("provider_decisions") == 0 and not adm.get("fallback"))
            state.update({"admission_trial": adm["trial"], "admitted": admitted})
            record["training"].update({"admission_trial": adm["trial"], "admitted": admitted})
        store.put(spec["layer"], spec["cls"], state)
    write_trial(out, name, rec, record)
    print(json.dumps({k: record.get(k) for k in ("trial", "kind", "outcome", "routine_outcome", "oracle_exact_match",
                                                  "completion_mutations", "routes", "error")}
                     | {"la": record["loadavg_before"].split()[0], "dec": record["provider_decisions"],
                        "prov": record.get("provider_ledger_after")}), flush=True)
    return record


def write_trial(out: Path, name: str, rec: Any, record: dict[str, Any]) -> None:
    rb10.write_trial(out, name, rec, record)


async def one_comp(spec: dict[str, Any], args: argparse.Namespace, fixtures: fx.FixturesC, out: Path) -> dict[str, Any]:
    """R2-10's own COMP trial, unchanged (rb10.one), on the same fixture server (normal page)."""
    fixtures.configure("normal", "immediate")
    store = rb10.RoutineStore(out / "unused-r210-store")
    record = await rb10.one({**spec, "arm": "COMP", "kind": "measured"}, args, fixtures, store, out)
    return record


# ── plans ────────────────────────────────────────────────────────────────────

def build_plan(kind: str, start: int, rounds: int) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    if kind == "shakedown":
        for cls in CLASSES:
            trials.append({"cls": cls, "kind": "train", "layer": "shake", "round": 0})
        for cls in CLASSES:
            trials.append({"cls": cls, "kind": "warm", "layer": "shake", "store_layer": "shake", "round": 0})
            trials.append({"cls": cls, "arm": "COMP", "kind": "measured", "layer": "shake", "round": 0})
            for k, variant in NEG_KINDS.items():
                trials.append({"cls": cls, "kind": k, "variant": variant, "layer": "shake", "store_layer": "shake",
                               "round": 0})
            for row, g in G5_ROWS.items():
                trials.append({"cls": cls, "kind": "g5", "g5_row": row, "hold": g["hold"], "barrier": g["barrier"],
                               "layer": "shake", "store_layer": "shake", "round": 0})
        for cls, page in OOD:
            trials.append({"cls": cls, "page_cls": page, "kind": "n8", "layer": "shake", "store_layer": "shake",
                           "round": 0})
        trials.append({"cls": "toggle", "kind": "nw2", "layer": "shake", "round": 0})
        return trials
    if kind == "traingate":
        return [{"cls": cls, "kind": "train", "layer": "scripted", "round": 0, "block": "G"} for cls in CLASSES]
    if kind == "timing":
        for r in range(start, start + rounds):
            classes = CLASSES if (r // 2) % 2 == 0 else CLASSES[::-1]
            order = ["COMP", "COMP_CR"] if r % 2 == 0 else ["COMP_CR", "COMP"]
            for cls in classes:
                for arm in order:
                    t = {"cls": cls, "kind": "measured" if arm == "COMP" else "warm", "arm": arm, "layer": "scripted",
                         "round": r, "order": "AB" if r % 2 == 0 else "BA", "block": "T"}
                    if arm == "COMP_CR":
                        t["store_layer"] = "scripted"
                    trials.append(t)
        return trials
    if kind == "costs":
        for k in range(5):
            for cls in CLASSES:
                trials.append({"cls": cls, "kind": "n7", "variant": "n7_presat", "layer": "scripted",
                               "store_layer": "scripted", "round": k, "block": "C6"})
            for cls, page in (("toggle", "modal"), ("modal", "toggle")):
                trials.append({"cls": cls, "page_cls": page, "kind": "n8", "layer": "scripted",
                               "store_layer": "scripted", "round": k, "block": "C6"})
        return trials
    if kind == "negatives":
        for k in range(5):
            for nk, variant in NEG_KINDS.items():
                for cls in CLASSES:
                    trials.append({"cls": cls, "kind": nk, "variant": variant, "layer": "scripted",
                                   "store_layer": "scripted", "round": k, "block": "N"})
            for cls, page in OOD:
                trials.append({"cls": cls, "page_cls": page, "kind": "n8", "layer": "scripted",
                               "store_layer": "scripted", "round": k, "block": "N"})
        return trials
    if kind == "nw2":
        return [{"cls": CLASSES[k % 2], "kind": "nw2", "layer": "scripted", "round": k // 2, "block": "W"}
                for k in range(10)]
    if kind == "reconcile":
        for k in range(5):
            for row, g in G5_ROWS.items():
                if k >= g["reps"]:
                    continue
                for cls in CLASSES:
                    trials.append({"cls": cls, "kind": "g5", "g5_row": row, "hold": g["hold"], "barrier": g["barrier"],
                                   "layer": "scripted", "store_layer": "scripted", "round": k, "block": "R"})
        return trials
    if kind == "live_shake":
        return [{"cls": "toggle", "kind": "train", "layer": "live_shake", "round": 0, "block": "LK"}]
    if kind == "live":
        for r in range(start, start + rounds):
            for cls in (CLASSES if r % 2 == 0 else CLASSES[::-1]):
                trials.append({"cls": cls, "kind": "train" if r == 0 else "warm", "layer": "live",
                               "store_layer": "live", "round": r, "block": "L"})
        return trials
    raise ValueError(kind)


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    store = Store(Path(args.routines) if args.routines else out)
    fixtures = fx.FixturesC()
    trials = build_plan(args.plan, args.start_round, args.rounds)
    for i, spec in enumerate(trials):
        spec.setdefault("arm", "COMP_CR")
        spec.setdefault("block", spec["layer"])
        page = f"-on-{spec['page_cls']}" if spec.get("page_cls") else ""
        extra = f"-{spec['g5_row']}" if spec.get("g5_row") else ""
        spec["name"] = f"{args.prefix}{i:03d}-{spec['cls']}{page}-{spec['arm']}-{spec['kind']}{extra}-r{spec['round']:02d}"
    sel = trials[args.offset: args.offset + args.count] if args.count else trials[args.offset:]
    manifest: dict[str, Any] = {"plan": args.plan, "start_round": args.start_round, "rounds": args.rounds,
                                "offset": args.offset, "count": args.count, "trials": [s["name"] for s in sel],
                                "plan_size": len(trials), "started_utc": utc(), "loadavg_start": loadavg(),
                                "display": os.environ.get("DISPLAY"), "provider_mode": rb10.NET["provider_mode"],
                                "provider_caps": {"reached": args.cap_reached, "attempts": args.cap_attempts},
                                "ledger_start": {k: LEDGER[k] for k in ("attempts", "reached", "blocked")},
                                **DRIVER_ID}
    not_run: list[str] = []
    try:
        for idx, spec in enumerate(sel):
            if spec["layer"].startswith("live"):
                if (LEDGER["reached"] + LIVE_RESERVE > args.cap_reached
                        or LEDGER["attempts"] + LIVE_RESERVE > args.cap_attempts):
                    not_run = [s["name"] for s in sel[idx:]]
                    manifest["stopped_for_budget"] = {"at": spec["name"],
                                                      "ledger": {k: LEDGER[k] for k in ("attempts", "reached")}}
                    break
            if spec["kind"] == "nw2":
                fixtures.configure("normal", "immediate")
                await rb10.nw2_one({**spec, "arm": "K5"}, args, fixtures, out)
            elif spec["arm"] == "COMP":
                await one_comp(spec, args, fixtures, out)
            else:
                await one_c(spec, args, fixtures, store, out)
    finally:
        manifest.update({"ended_utc": utc(), "loadavg_end": loadavg(), "network": dict(rb10.NET), "not_run": not_run,
                         "ledger_end": {k: LEDGER[k] for k in ("attempts", "reached", "blocked")}})
        (out / f"run-manifest-{args.prefix}{args.offset:03d}.json").write_text(json.dumps(manifest, indent=1))
        fixtures.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", required=True, choices=("shakedown", "traingate", "timing", "costs", "negatives", "nw2",
                                                     "reconcile", "live_shake", "live"))
    p.add_argument("--start-round", type=int, default=0)
    p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--prefix", required=True)
    p.add_argument("--routines", help="directory holding routines/ (defaults to --out)")
    p.add_argument("--provider-ledger")
    p.add_argument("--cap-reached", type=int, default=0)
    p.add_argument("--cap-attempts", type=int, default=0)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or os.environ.get("R2_07C_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless + cua-x11-session.sh (in_session.sh)")
    for name in (rb10.TRACE_ENV, rb10.SETTLE_ENV, rb10.E_ENV, rb10.V_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    digest = hashlib.sha256(Path(args.driver).read_bytes()).hexdigest()
    if digest != args.driver_sha256:
        raise SystemExit("refusing: Driver binary sha256 mismatch")
    import subprocess

    version = subprocess.run([args.driver, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    DRIVER_ID.update({"driver_name": Path(args.driver).name, "driver_sha256": digest, "driver_version": version})
    live = args.plan in ("live", "live_shake")
    if live:
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            raise SystemExit("blocked: provider key not forwarded into the session")
        if not args.provider_ledger or args.cap_reached <= 0 or args.cap_attempts <= 0:
            raise SystemExit("refusing: live plans need --provider-ledger and both caps")
        rb10.enable_live_network()
        install_provider_ledger_c(Path(args.provider_ledger), args.cap_reached, args.cap_attempts)
    else:
        os.environ.pop("TYPESAFE_API_KEY", None)
    args.plan_kind = args.plan
    args.save_snapshots = False
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

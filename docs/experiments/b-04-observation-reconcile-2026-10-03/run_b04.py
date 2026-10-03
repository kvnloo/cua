"""B-04 runner: browser cold-first-snapshot reconciliation on R2-10's binary R (measurement only).

Run inside hostless + cua-x11-session.sh with the jev-use virtualenv of the tested source:

    JEV_USE_DIR=<jev-use> <venv>/python run_b04.py --driver <bin> --out <dir> \
        --plan {pilot|measured} [--rounds-from 0 --rounds-to 30] --inject-mode tail

The runner takes no lock itself. The caller takes the quiet-lane lock OUTSIDE the session, before
any Driver opens, and says which lock it holds through B04_LOCK (forwarded into the session):
measured = ``quiet-timed`` (EXCLUSIVE, receipt line in the quiet-lane ledger); pilot =
``lane-scripts/shared-locked.sh`` (SHARED flock, receipt line with lane/label/mode/pid/acquired/
released/rc/loadavg_at_acquire in the same ledger). The runner refuses a measured plan unless
B04_LOCK=exclusive and a pilot plan unless B04_LOCK is set. Pilot trials are excluded from every
analysis.

Attempt 2 (wave 4) changes against attempt 1's uncommitted draft: in-runner shared locking removed
(external wrapper above); the oracle sampler is R2-10's ``Sampler`` (keeps every expected-state
sample time after the first, for the caller-side T_oracle rule) instead of B-01's first-hit
poller; the Driver binary name + sha256 and the browser executable basename are recorded.

Derived from B-03's ``run_b03.py`` (copied verbatim to harness/run_b03.py): B-01's
``run_critpath.one`` bookkeeping (fresh ``cua-driver mcp`` and fresh Driver-launched browser per
trial, 2 ms independent oracle poller, server journal, loadavg before/after) with the trial body
replaced by R2-10's COMP configuration and the B-04 insertions. Differences from run_b03.py:

- fresh fixture servers per trial (B-03 kept one per run);
- configuration COMP (R2-10): feedback off, focus settle 0 on fill, 10 ms completion poll, caller-
  compiled output validators, CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1, guarded completion on fill,
  compiled replay on fill (R2-07 ``compiled_routine``, the R2-10 scripted COMP artifact, guarded step
  loop as fallback); toggle/modal run R2-10's step loop (run.py rules incl. FIX-01 Part B);
- DEFAULT (smoke only): R2-10 BASE (feedback on, default glide, no guard, 100 ms poll, library
  validation, no CUA_DRIVER_EXP_* variable), step loop for every class;
- P=warm: before the task navigate, ``browser_navigate`` to a matched-content sibling page served by
  the same fixture (same DOM structure and roles, different text/tokens) plus one semantic_v2
  snapshot of it (labels warm_navigate / warm_snapshot);
- variant ``presnap``: one semantic_v2 snapshot right after the task navigate (label presnap), so the
  task's first observation is a re-snapshot of the same document;
- ``resnap``: the task's first observation is taken twice back to back (labels snapshot1 and
  resnap1, no call in between); the routine / step loop uses resnap1's refs;
- D: the first task observation is sent D ms after the task navigate returned (harness sleep);
- inject: the fixture delays its first response for the task document by ``inject_ms``
  (mode per PREREG: ``hdr`` = before the status line, ``tail`` = all but the last byte, then the
  delay, then the last byte).

``task_start`` is stamped immediately after the task navigate returns (before ``presnap`` and the
D wait). Knobs reach the Driver through its environment only. Output paths are relative to --out.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import threading
import json
import os
import sys
import time
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness"))

import run_b02 as R2  # noqa: E402  (knob names; imports run_critpath)
import run_critpath as rc  # noqa: E402
import b01_fixtures as bf  # noqa: E402
import compiled_routine as cr  # noqa: E402
import driver_env as jev_driver_env  # noqa: E402
import fixture_server as jev_fs  # noqa: E402
from run import DriverToolError  # noqa: E402

V_ENV = R2.V_ENV
SETTLE_ENV = rc.KNOB_ENV
TRACE_ENV = rc.TRACE_ENV
POLL_DEADLINE_S = 2.0
cr.Routine.VERIFY_DEADLINE_S = POLL_DEADLINE_S  # R2-10: same 2.0 s deadline as the step loop
cr.Routine.VERIFY_INTERVAL_S = 0.010
ROUTINE = json.loads((HERE / "harness" / "r2-10-scripted-COMP-routine.json").read_text())["artifact"]
cr.require_clean(ROUTINE)

ARMS: dict[str, dict[str, Any]] = {
    "COMP": {"cursor": False, "guard": True, "settle0": True, "poll_ms": 10, "compiled_validator": True,
             "knobs": {V_ENV: "1"}, "replay": True},
    "DEFAULT": {"cursor": True, "guard": False, "settle0": False, "poll_ms": 100, "compiled_validator": False,
                "knobs": {}, "replay": False},
}
for _a in ARMS:
    rc.ARMS[_a] = rc.ARMS["K5"]  # rc.one only reads spec keys; the arm table above drives the trial

# ── matched-content sibling pages (same DOM structure and roles; different text and tokens) ──
SIBLING_PATH = {"fill": "/sibling", "toggle": "/toggle-sibling", "modal": "/modal-sibling"}
FILL_SIBLING = (jev_fs.PAGE
                .replace(b"<title>Cua Driver Jev fixture</title>", b"<title>Cua Driver Jev sibling</title>")
                .replace(b"<h1>Cua Driver + TypeSafe Jev fixture</h1>", b"<h1>Cua Driver + TypeSafe Jev sibling</h1>")
                .replace(b"<p>Enter the verification value and submit it.</p>",
                         b"<p>Type the confirmation code and send it.</p>")
                .replace(b'action="/submit"', b'action="/sibling-send"')
                .replace(b'<input name="value" required aria-label="verification value">',
                         b'<input name="code" required aria-label="confirmation code">')
                .replace(b'<button type="submit">Submit</button>', b'<button type="submit">Send</button>')
                .replace(b"<output>status=waiting</output>", b"<output>status=idle</output>"))
I24_SIBLING = {
    "/toggle-sibling": bf.PAGES["toggle-confirm"]
    .replace("<title>toggle</title>", "<title>switch</title>")
    .replace('aria-label="feature"', 'aria-label="option"')
    .replace(">Confirm</button>", ">Apply</button>")
    .replace("[aria-label=feature]", "[aria-label=option]")
    .replace('"/event/toggle"', '"/sibling/toggle"'),
    "/modal-sibling": bf.PAGES["modal"]
    .replace("<title>modal</title>", "<title>panel</title>")
    .replace(">Open dialog</button>", ">Show panel</button>")
    .replace(">Confirm choice</button>", ">Accept item</button>")
    .replace('"/event/opened"', '"/sibling/opened"')
    .replace('"/event/modal"', '"/sibling/modal"'),
}
assert FILL_SIBLING.count(b"<input") == jev_fs.PAGE.count(b"<input") and FILL_SIBLING != jev_fs.PAGE
assert all(I24_SIBLING[p] != bf.PAGES[k] for p, k in (("/toggle-sibling", "toggle-confirm"), ("/modal-sibling", "modal")))


def _send_with_injection(handler: Any, status: HTTPStatus, content_type: str, body: bytes) -> None:
    """Send ``body``; the first task-document response of the trial is delayed per the server's mode."""
    server = handler.server
    delay = 0.0
    if server.inject_ms and not server.injected:
        server.injected = True
        delay = server.inject_ms / 1000
        server.inject_record = {"mode": server.inject_mode, "path": handler.path, "t_start_ns": rc.now()}
    if delay and server.inject_mode == "hdr":
        time.sleep(delay)
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if delay and server.inject_mode == "tail":
        handler.wfile.write(body[:-1])
        handler.wfile.flush()
        time.sleep(delay)
        handler.wfile.write(body[-1:])
    else:
        handler.wfile.write(body)
    if delay:
        server.inject_record["t_end_ns"] = rc.now()


class I24Handler(bf.Handler):
    def do_GET(self) -> None:  # noqa: N802
        page = I24_SIBLING.get(self.path)
        if page is not None:
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", page.encode())
            return
        task_page = bf.PAGES.get(self.path.removeprefix("/"))
        if task_page is not None:
            _send_with_injection(self, HTTPStatus.OK, "text/html; charset=utf-8", task_page.encode())
            return
        super().do_GET()


class FillHandler(jev_fs.FixtureHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == SIBLING_PATH["fill"]:
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", FILL_SIBLING)
            return
        if self.path == "/":
            _send_with_injection(self, HTTPStatus.OK, "text/html; charset=utf-8", jev_fs.PAGE)
            return
        super().do_GET()


class B04Fixtures(rc.Fixtures):
    """rc.Fixtures (fill FixtureServer + i24 JournalServer, server journals) with the sibling pages
    and the injection switch; one instance per trial."""

    def __init__(self, inject_ms: int = 0, inject_mode: str = "hdr") -> None:
        super().__init__()
        self.fill.RequestHandlerClass = FillHandler
        self.i24.RequestHandlerClass = I24Handler
        for server in (self.fill, self.i24):
            server.inject_ms, server.inject_mode, server.injected, server.inject_record = inject_ms, inject_mode, False, None

    def sibling_url(self, cls: str) -> str:
        return (self.fill_url if cls == "fill" else self.i24_origin).rstrip("/") + SIBLING_PATH[cls]

    def inject_record(self) -> dict[str, Any] | None:
        return self.fill.inject_record or self.i24.inject_record


class Sampler:
    """R2-10's independent 2 ms re-read of the server state (verbatim logic from R2-10
    harness/r2_10_browser.py ``Sampler`` @ 030f6bdbf): keeps the first expected-state sample and every
    sample time after it (cap 4000). B-04 addition: ``stop`` copies the sample list into the trial
    result so the caller-side T_oracle rule can be applied offline."""

    def __init__(self, fixtures: Any, cls: str, token: str, result: dict[str, Any]) -> None:
        self.fixtures, self.cls, self.token, self.result = fixtures, cls, token, result
        self.first_ok_ns: int | None = None
        self.ok_samples: list[int] = []
        self.reverted_after_ok = 0
        self.reads = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        start = rc.now()
        k = 0
        period = int(0.002 * 1e9)
        while not self._stop.is_set():
            t = rc.now()
            ok = self.fixtures.oracle_ok_direct(self.cls, self.token)
            self.reads += 1
            if ok:
                if self.first_ok_ns is None:
                    self.first_ok_ns = t
                if len(self.ok_samples) < 4000:
                    self.ok_samples.append(t)
            elif self.first_ok_ns is not None:
                self.reverted_after_ok += 1
            k += 1
            delay = (start + k * period - rc.now()) / 1e9
            if delay > 0:
                time.sleep(delay)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=2)
        self.result["oracle_ok_samples_ns"] = self.ok_samples[:400]
        self.result["oracle_reverted_after_ok"] = self.reverted_after_ok


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ── recording Driver proxy: labels, first-observation D wait and matched re-snapshot ──────────

class ObsDriver:
    """Wraps run.Driver. semantic_v2 observations are labelled snapshotN, actions actionN. Before the
    FIRST task observation it waits until navigate return + D; with ``resnap`` the first observation
    is sent twice back to back (snapshot1, resnap1) and resnap1's result is returned."""

    def __init__(self, inner: Any, rec: Any, *, nav_return_ns: int, D: int, resnap: bool) -> None:
        self.inner, self.rec = inner, rec
        self.label, self.session = inner.label, inner.session
        self.nav_return_ns, self.D, self.resnap = nav_return_ns, D, resnap
        self.n_snap = self.n_act = 0
        self.first_done = False

    async def _timed(self, label: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.rec.add("call_send", label=label, tool=name)
        try:
            data = await self.inner.call(name, arguments)
        except Exception as error:
            self.rec.add("call_return", label=label, tool=name, ok=False, error=type(error).__name__,
                         code=getattr(error, "code", None), refused=bool(getattr(error, "refused", False)))
            raise
        snap = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else {}
        refs = data.get("refs") if isinstance(data.get("refs"), list) else None
        self.rec.add("call_return", label=label, tool=name, ok=True, route=data.get("route"),
                     effect=data.get("effect"), status=data.get("status"), snapshot_id=snap.get("id"),
                     n_refs=None if refs is None else len(refs))
        return data

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_browser_state" and arguments.get("snapshot_format") == "semantic_v2":
            self.n_snap += 1
            if not self.first_done:
                self.first_done = True
                wait_s = (self.nav_return_ns + self.D * 1_000_000 - rc.now()) / 1e9 if self.D else 0.0
                self.rec.add("delay_start", D=self.D)
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
                self.rec.add("delay_end", D=self.D)
                first = await self._timed("snapshot1", name, arguments)
                if not self.resnap:
                    return first
                return await self._timed("resnap1", name, arguments)
            return await self._timed(f"snapshot{self.n_snap}", name, arguments)
        if name in ("browser_type", "browser_click"):
            self.n_act += 1
            return await self._timed(f"action{self.n_act}", name, arguments)
        return await self._timed(f"call-{name}", name, arguments)


# ── R2-10 step loop (run.py rules incl. FIX-01 Part B: a refusal is refused, never re-dispatched) ──

async def step_loop(*, rec: Any, drv: ObsDriver, task: Any, pid: int, window: dict[str, Any], available: set[str],
                    capture_bound: bool, guard: bool, poll_ms: int, result: dict[str, Any], prefix: str = "") -> str:
    history: list[dict[str, Any]] = []
    pending = None
    dispatched: set[str] = set()
    refusal_retried = False
    for step in range(1, task.max_steps + 1):
        current = rc.oracle_read(rec, task, f"pre_step{prefix}{step}", step - 1)
        if current in {"verified", "refuted"}:
            return current
        snap = await drv.call("get_browser_state", {"target_id": result["_tgt"]["target_id"],
                                                    "tab_id": result["_tgt"]["tab_id"], "snapshot_format": "semantic_v2"})
        rec.add("cand_start", step=step)
        candidates, sources, visual_record = await rc.task_candidates_for_step(
            drv.inner, task, snap, pid, int(window["window_id"]), available, capture_bound, visual_mode="auto")
        rec.add("cand_done", step=step, ids=[c.id for c in candidates],
                visual=visual_record.get("status") if isinstance(visual_record, dict) else None)
        if not candidates:
            result["stop"] = "no_candidates"
            return "abstained"
        candidate = None
        guard_tel = None
        if guard and pending is not None:
            rec.add("guard_start", step=step)
            resolution = rc.resolve_guarded_completion(pending, task, sources, candidates, session=drv.label)
            candidate, guard_tel = resolution.candidate, resolution.telemetry
            pending = None
            rec.add("guard_done", step=step, status=guard_tel.get("status"), reason=guard_tel.get("reason"))
        if candidate is not None:
            route = "guarded-completion"
        else:
            rec.add("decide_start", step=step)
            choice, _c, _p = rc.choose_mock_for_task(task, sources, candidates, history)
            rec.add("decided", step=step, choice=choice)
            if choice is None:
                return "abstained"
            candidate = rc.validate_choice(choice, candidates, current_capture_id=None)
            route = "provider"
        next_plan = (rc.plan_guarded_completion(task, sources, candidate, session=drv.label)
                     if guard and route == "provider" else None)
        result["routes"].append(prefix + route)
        result["candidates"].append(candidate.id)
        result["tools"].append(candidate.tool)
        result["input_routes"].append((candidate.arguments or {}).get("input_route"))
        rec.add("routed", step=step, route=route, candidate=candidate.id, tool=candidate.tool,
                plan_bound=next_plan is not None)
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
        pending = next_plan
        history.append(task.history_entry(step, candidate.id))
        if candidate.id in task.completion_candidate_ids:
            for i in range(int(round(POLL_DEADLINE_S * 1000 / poll_ms))):
                outcome = rc.oracle_read(rec, task, f"verify{prefix}{i}", step)
                if outcome in {"verified", "refuted"}:
                    result["poll_reads"] = i + 1
                    return outcome
                rec.add("sleep_start", poll_ms=poll_ms)
                await asyncio.sleep(poll_ms / 1000)
                rec.add("sleep_end")
            result["stop"] = "reconcile_unconfirmed"
            return "unknown"
    return task.classify(task.read_oracle(), steps=task.max_steps)


def driver_env_for(arm: dict[str, Any], cls: str, trace_path: Path | None) -> dict[str, str]:
    env = jev_driver_env.driver_environment()
    for key in list(env):
        if key.startswith("CUA_DRIVER_EXP_") or key == TRACE_ENV:
            env.pop(key)
    if trace_path is not None:
        env[TRACE_ENV] = str(trace_path)
    env.update(arm["knobs"])
    if arm["settle0"] and cls == "fill":
        env[SETTLE_ENV] = "0"
    env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
    env["DO_NOT_TRACK"] = "1"
    return env


async def b04_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: B04Fixtures, trace_path: Path | None,
                    rec: Any, result: dict[str, Any]) -> None:
    cls, arm_name = spec["cls"], spec["arm"]
    arm = ARMS[arm_name]
    P, D, variant = spec["P"], int(spec["D"]), spec["variant"]
    token = f"jev-{rc.uuid.uuid4().hex[:10]}"
    label = f"jev-b04-{rc.uuid.uuid4().hex[:8]}"
    task = rc.make_task(cls, token, fixtures)
    result.update({"token_sha16": rc.sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "routes": [], "tools": [], "input_routes": [], "candidates": [],
                   "probe": spec["probe"], "P": P, "D": D, "variant": variant, "resnap": spec["resnap"],
                   "inject_ms": spec["inject_ms"], "inject_mode": spec.get("inject_mode"),
                   "driver_name": Path(args.driver).name, "driver_sha256": spec.get("driver_sha256")})
    task.reset()
    fixtures.state(cls).drain()
    poller = Sampler(fixtures, cls, token, result)
    result["_poller"] = poller
    env = driver_env_for(arm, cls, trace_path)
    result["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
    result["driver_env_trace_set"] = TRACE_ENV in env
    result["driver_env_telemetry"] = env.get("CUA_DRIVER_RS_TELEMETRY_ENABLED")
    mode = "replay" if (arm["replay"] and cls == "fill") else "step"
    result["mode"] = mode
    rec.add("trial_start", cls=cls, arm=arm_name, probe=spec["probe"], P=P, D=D, variant=variant, mode=mode)
    rc.CLIENT["rec"] = rec
    rc.CLIENT["compiled"] = None
    params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    async with rc.stdio_client(params) as (read, write):
        async with rc.ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            if arm["compiled_validator"]:
                rec.add("compile_validators_start")
                result["compiled_validators"] = rc.compile_output_validators(session)
                rec.add("compile_validators_end")
            available = {tool.name for tool in tools}
            capture_bound = rc.supports_capture_bound_click(tools)
            inner = rc.Driver(session, label)
            await rc.timed_call(rec, inner, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm["cursor"]})
            motion = await rc.timed_call(rec, inner, "cursor_motion", "set_agent_cursor_motion", rc.DEFAULT_MOTION)
            result["motion_ack"] = {k: motion.get(k) for k in ("glide_duration_ms", "dwell_after_click_ms")
                                    if isinstance(motion, dict)}
            prepared = await rc.timed_call(rec, inner, "prepare", "browser_prepare",
                                           {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            result["prepared_pid"] = pid
            try:
                result["browser_exe"] = os.path.basename(os.readlink(f"/proc/{pid}/exe"))
            except OSError as error:
                result["browser_exe"] = f"unreadable:{type(error).__name__}"
            window = await rc.wait_for_window(inner, pid)
            rec.add("window_ready")
            bound = await rc.timed_call(rec, inner, "bind", "get_browser_state",
                                        {"pid": pid, "window_id": window["window_id"]})
            tgt = {"target_id": bound["target_id"], "tab_id": rc.select_tab_id(bound["tabs"])}
            result["_tgt"] = tgt
            if P == "warm":  # B-04: matched-content sibling page on the same fixture origin, then a snapshot
                await rc.timed_call(rec, inner, "warm_navigate", "browser_navigate", {**tgt, "url": fixtures.sibling_url(cls)})
                await rc.timed_call(rec, inner, "warm_snapshot", "get_browser_state", {**tgt, "snapshot_format": "semantic_v2"})
            url = fixtures.page_url(cls)
            await rc.timed_call(rec, inner, "navigate", "browser_navigate", {**tgt, "url": url})
            nav_return = rc.now()
            rec.add("task_start", D=D)
            poller.start()
            if variant == "presnap":  # B-04 P3 arm B: the task document is snapshotted once before the task
                await rc.timed_call(rec, inner, "presnap", "get_browser_state", {**tgt, "snapshot_format": "semantic_v2"})
            drv = ObsDriver(inner, rec, nav_return_ns=nav_return, D=D, resnap=bool(spec["resnap"]))
            loop_kw = dict(rec=rec, drv=drv, task=task, pid=pid, window=window, available=available,
                           capture_bound=capture_bound, guard=arm["guard"] and cls == "fill", poll_ms=arm["poll_ms"],
                           result=result)
            if mode == "replay":
                async def fallback(ctx: Any, rrec: Any, index: int, reason: str) -> str:
                    rec.add("fallback_start", index=index, reason=reason)
                    result["fallback"] = {"index": index, "reason": reason}
                    out = await step_loop(**loop_kw, prefix="fallback:")
                    return "fallback_verified" if out == "verified" else out

                def read_oracle() -> dict[str, Any]:
                    rec.add("oracle_send", label="routine_read")
                    state = task.read_oracle()
                    rec.add("oracle_return", label="routine_read",
                            outcome="verified" if state.get("submitted") == token else "unknown")
                    return dict(state)

                routine = cr.Routine(ROUTINE, fallback=fallback)
                ctx = cr.ReplayContext(driver=drv, target_id=tgt["target_id"], tab_id=tgt["tab_id"], pid=pid,
                                       window_id=int(window["window_id"]), fixture_url=url, token=token,
                                       read_oracle=read_oracle, rebind=None)
                rrec = cr.ReplayRecord()
                rrec.t0_ns = rc.now()
                await routine.replay(ctx, rrec)
                if rrec.outcome == "stopped" and str(rrec.stop_reason or "") == "refused:browser_ref_stale" \
                        and not result.get("fallback"):
                    rrec.outcome = await fallback(ctx, rrec, -1, "refused:browser_ref_stale")
                result["routine"] = {k: v for k, v in rrec.as_dict().items() if k != "events"}
                result["routine_events"] = rrec.events
                result["routes"] = ["compiled"] + result["routes"]
                out = rrec.outcome
                result["outcome"] = {"fallback_verified": "verified", "verified_by_reconcile": "verified"}.get(out, out)
            else:
                result["outcome"] = await step_loop(**loop_kw)
    result.pop("_tgt", None)
    result["inject_record"] = fixtures.inject_record()


rc.run_trial = b04_trial  # rc.one looks run_trial up at call time


# ── plan ─────────────────────────────────────────────────────────────────────

def T(cls: str, probe: str, *, P: str = "cold", D: int = 0, variant: str = "task", resnap: bool = True,
      inject_ms: int = 0, arm: str = "COMP", cell: str) -> dict[str, Any]:
    return {"cls": cls, "probe": probe, "P": P, "D": D, "variant": variant, "resnap": resnap, "inject_ms": inject_ms,
            "arm": arm, "cell": cell, "kind": "measured"}


def round_trials(r: int, inject_mode: str) -> list[dict[str, Any]]:
    """One round: P1 pair per class, P2/P3 AB/BA pairs, P4 Williams row, POS pair (r < 10), smoke (r < 5)."""
    ab = r % 2 == 0
    seq: list[dict[str, Any]] = []
    for cls in (("fill", "toggle") if ab else ("toggle", "fill")):
        p1 = [T(cls, "P1", D=80, cell="D80"), T(cls, "P1", D=160, cell="D160")]
        seq += p1 if ab else p1[::-1]
    for cls in (("fill", "toggle", "modal") if ab else ("modal", "toggle", "fill")):
        p2 = [T(cls, "P2", P="cold", cell="cold"), T(cls, "P2", P="warm", cell="warm")]
        seq += p2 if ab else p2[::-1]
    for cls in (("toggle", "fill") if ab else ("fill", "toggle")):
        p3 = [T(cls, "P3", P="warm", cell="newdoc"), T(cls, "P3", P="warm", variant="presnap", cell="samedoc")]
        seq += p3 if ab else p3[::-1]
    w = R2.williams_any(3)  # 6 rows: square + mirror
    arms4 = [dict(cell="W0"), dict(cell="W80", D=80), dict(cell="PREWARM", P="warm")]
    for k, cls in enumerate(("fill", "toggle") if ab else ("toggle", "fill")):
        row = w[(r + 3 * k) % 6]
        for j in row:
            a = arms4[j]
            seq.append(T(cls, "P4", resnap=False, **a))
    if r < 10:
        for cls in (("toggle", "fill") if ab else ("fill", "toggle")):
            pos = [T(cls, "POS", inject_ms=20, cell="inject20"), T(cls, "POS", inject_ms=0, cell="inject0")]
            seq += pos if ab else pos[::-1]
    if r < 5:
        for cls in ("fill", "toggle", "modal"):
            seq.append(T(cls, "SMOKE", resnap=False, arm="DEFAULT", cell="default"))
    for s in seq:
        s["inject_mode"] = inject_mode if s["inject_ms"] else None
    return seq


P4X_CLASS_INDEX = {"fill": 0, "toggle": 1}


def p4x_round_trials(r: int) -> list[dict[str, Any]]:
    """Extension block (added after the measured run, disclosed): P4 only, in true Williams order.

    round_trials() above picks row w[(r + 3k) % 6] with k = position of the class in an order that
    flips with round parity, so fill only ever got rows {0,2,4} and toggle rows {1,3,5}: neither is a
    Latin square and W80 vs W0 had a fixed order within each class. Here k is a fixed class index, so
    each class cycles through all 6 rows of williams_any(3) every 6 rounds (30 rounds = 5 x each row:
    each arm 10 x in each position, each ordered arm pair 15/30). Class order still alternates.
    """
    w = R2.williams_any(3)
    arms4 = [dict(cell="W0"), dict(cell="W80", D=80), dict(cell="PREWARM", P="warm")]
    seq: list[dict[str, Any]] = []
    for cls in (("fill", "toggle") if r % 2 == 0 else ("toggle", "fill")):
        row = w[(r + 3 * P4X_CLASS_INDEX[cls]) % 6]
        for j in row:
            seq.append(T(cls, "P4", resnap=False, **arms4[j]))
    for s in seq:
        s["inject_mode"] = None
    return seq


def build_plan(kind: str, r_from: int, r_to: int, inject_mode: str, pilot_set: int = 1,
               block: str = "m") -> list[dict[str, Any]]:
    if kind == "p4x":
        return [{**s, "block": block, "round": r, "lock_mode": "exclusive_external", "williams_row_pos": i}
                for r in range(r_from, r_to) for i, s in enumerate(p4x_round_trials(r))]
    if kind == "pilot":
        specs = [T("toggle", "PILOT", cell="cold-D0"), T("toggle", "PILOT", inject_ms=20, cell="inj-hdr"),
                 T("toggle", "PILOT", inject_ms=20, cell="inj-tail"), T("fill", "PILOT", cell="cold-D0"),
                 T("fill", "PILOT", inject_ms=20, cell="inj-hdr"), T("fill", "PILOT", inject_ms=20, cell="inj-tail"),
                 T("toggle", "PILOT", P="warm", cell="warm"), T("fill", "PILOT", P="warm", variant="presnap", cell="presnap"),
                 T("modal", "PILOT", P="warm", cell="warm"), T("fill", "PILOT", D=80, cell="D80"),
                 T("toggle", "PILOT", resnap=False, arm="DEFAULT", cell="default"),
                 T("fill", "PILOT", resnap=False, arm="DEFAULT", cell="default"),
                 T("toggle", "PILOT", P="warm", resnap=False, cell="prewarm")]
        if pilot_set == 2:  # P1 cells and the tail-mode positive control
            specs = [T(c, "PILOT", D=d, cell=f"D{d}") for c in ("toggle", "fill") for d in (80, 160)] + \
                    [T(c, "PILOT", inject_ms=20, cell="inj-tail") for c in ("toggle", "fill")]
        if pilot_set == 3:  # shakedown: the measured plan's round(s), shared lock, block "shake" (excluded)
            return [{**s, "block": "shake", "round": r, "lock_mode": "shared"}
                    for r in range(r_from, r_to) for s in round_trials(r, inject_mode)]
        out = []
        for i, s in enumerate(specs * max(1, r_to - r_from)):
            s = dict(s)
            s["inject_mode"] = ("tail" if s["cell"] == "inj-tail" else "hdr") if s["inject_ms"] else None
            s.update({"block": "pilot", "round": i, "lock_mode": "shared"})
            out.append(s)
        return out
    if kind != "measured":
        raise ValueError(kind)
    out = []
    for r in range(r_from, r_to):
        for s in round_trials(r, inject_mode):
            out.append({**s, "block": block, "round": r, "lock_mode": "exclusive_external"})
    return out


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    plan = build_plan(args.plan_kind, args.rounds_from, args.rounds_to, args.inject_mode, args.pilot_set,
                      args.block)
    seen: dict[str, int] = {}
    for i, spec in enumerate(plan):
        base = (f"{spec['block']}{spec['round']:02d}-{spec['probe']}-{spec['cls']}-{spec['cell']}")
        seen[base] = seen.get(base, 0) + 1
        spec["name"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
        spec["seq"] = i
    if len({s["name"] for s in plan}) != len(plan):
        raise SystemExit("refusing: duplicate trial names in plan")
    lock = os.environ.get("B04_LOCK")
    if args.plan_kind in ("measured", "p4x") and lock != "exclusive":
        raise SystemExit("refusing: measured plan needs B04_LOCK=exclusive (run under quiet-timed)")
    if args.plan_kind == "pilot" and lock not in ("shared", "exclusive"):
        raise SystemExit("refusing: pilot plan needs B04_LOCK (run under shared-locked.sh)")
    for s in plan:
        s["lock_mode"] = lock
    drv_bytes = Path(args.driver).read_bytes()
    manifest: dict[str, Any] = {"plan_kind": args.plan_kind, "rounds": [args.rounds_from, args.rounds_to],
                                "inject_mode": args.inject_mode, "arms": ARMS, "trials": [s["name"] for s in plan],
                                "started_mono_ns": rc.now(), "started_utc": utc(), "loadavg_start": rc.loadavg(),
                                "lock_mode": lock, "lock_label": os.environ.get("B04_LOCK_LABEL"),
                                "provider": "mock", "display": os.environ.get("DISPLAY"), "hostless": os.environ.get("B04_HOSTLESS"),
                                "driver_name": Path(args.driver).name,
                                "driver_sha256": hashlib.sha256(drv_bytes).hexdigest()}
    del drv_bytes
    args.save_snapshots = False
    try:
        for spec in plan:
            spec["driver_sha256"] = manifest["driver_sha256"]
            fixtures = B04Fixtures(spec["inject_ms"], spec.get("inject_mode") or "hdr")
            try:
                await rc.one(spec, args, fixtures, out)
            finally:
                fixtures.close()
    finally:
        manifest["ended_mono_ns"] = rc.now()
        manifest["ended_utc"] = utc()
        manifest["loadavg_end"] = rc.loadavg()
        manifest["network"] = dict(rc.NETWORK)
        tag = f"{args.plan_kind}-{args.block}-r{args.rounds_from:02d}-{args.rounds_to:02d}"
        (out / f"run-manifest-{tag}.json").write_text(json.dumps(manifest, indent=1, default=str))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", choices=("measured", "pilot", "p4x"), required=True)
    p.add_argument("--rounds-from", type=int, default=0)
    p.add_argument("--rounds-to", type=int, default=30)
    p.add_argument("--inject-mode", choices=("hdr", "tail"), default="hdr")
    p.add_argument("--pilot-set", type=int, default=1)
    p.add_argument("--block", default="m", help="measured block tag; a re-run of a failed session-start block uses a new tag")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (TRACE_ENV, SETTLE_ENV, *R2.KNOB_ENVS):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    args.plan_kind, args.plan = args.plan, f"b04-{args.plan}"
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

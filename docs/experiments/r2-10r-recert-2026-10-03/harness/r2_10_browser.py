"""R2-10 browser composition harness: BASE vs composed surviving deletions on one binary.

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``in_session.sh``; the quiet-lane lock (quiet-timed, EXCLUSIVE) and the cargo-build lock are
taken OUTSIDE, before the session opens. Output paths are relative to --out.

Reuses, unchanged and by path (harness/src/...):
* B-01/B-02 ``run_critpath`` (loopback guard, caller-compiled MCP output validators, Recorder,
  fixtures with server journals, task specs) and ``run_b02`` (knob names, N-W2 control trial);
* R2-07 ``compiled_routine`` (authority-free artifact, fresh-bound replay, reconcile);
* the tested jev-use ``run.py`` Driver wrapper, candidate building, guarded completion and the
  provider adapters (``choose_mock_for_task`` = scripted chooser, ``choose_live_for_task`` = TypeSafe).

Arms (the Driver binary is the same in every arm; the phase trace is on in every arm):
  BASE    product default: feedback ON (cursor enabled, default glide), ordinary runner,
          100 ms completion poll, library MCP output validation, no CUA_DRIVER_EXP_* variable.
  COMP    feedback OFF, focus settle 0 (fill), 10 ms poll, compiled validators, admission
          tools-list cache, guarded completion (fill), compiled replay (fill) with the guarded
          continuation as fallback.
  COMP_E  COMP + endpoint re-proof bound check (scripted layer only).
  COMP_K  COMP minus the OWNER_DECISION knobs: feedback default ON, focus settle default.

Each trial: fresh Driver process, fresh isolated browser, fresh token (B-02 lifecycle).
T0 = send of the first observation (label snapshot1). The oracle is the fixture server's state,
re-read every 2 ms by an independent harness thread; every sample time after the first
expected-state sample is kept so T_oracle (first expected-state sample at/after the return of
the last accepted mutation) and T_land (first expected-state sample) can both be computed.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import hashlib
import json
import os
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
B02 = SRC / "b-02-browser-driver-sites-2026-10-02"
R207 = SRC / "r2-07-2026-10-02" / "harness"
sys.path[:0] = [str(B02), str(R207)]

_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex

import run_critpath as rc  # noqa: E402  (loopback guard, validator patch, jev-use imports)
import run_b02 as rb  # noqa: E402  (knob names, N-W2 control)
import compiled_routine as cr  # noqa: E402
from cdp_raw import CdpClient, devtools_ports_for_pid, evaluate, http_get_json, page_target  # noqa: E402
import driver_env as jev_driver_env  # noqa: E402
from run import DriverToolError  # noqa: E402
import jev_adapter  # noqa: E402

E_ENV, V_ENV = rb.E_ENV, rb.V_ENV
SETTLE_ENV = rc.KNOB_ENV
TRACE_ENV = rc.TRACE_ENV
POLL_DEADLINE_S = 2.0
STATE_PERIOD_S = 0.002
cr.Routine.VERIFY_DEADLINE_S = POLL_DEADLINE_S  # same 2.0 s completion deadline as the step loop
cr.Routine.VERIFY_INTERVAL_S = 0.010


class _RoutineAsyncio:
    """compiled_routine's ``asyncio`` name: identical calls, plus sleep_start/sleep_end events so the
    decomposition attributes the routine's bounded-read sleeps to sleeps_polls (as in the step loop)."""

    to_thread = staticmethod(asyncio.to_thread)

    @staticmethod
    async def sleep(seconds: float) -> None:
        rec = CTX_REC.get("rec")
        if rec is not None:
            rec.add("sleep_start", poll_ms=int(round(seconds * 1000)))
        await asyncio.sleep(seconds)
        if rec is not None:
            rec.add("sleep_end")


CTX_REC: dict[str, Any] = {"rec": None}
cr.asyncio = _RoutineAsyncio  # type: ignore[attr-defined]

ARMS: dict[str, dict[str, Any]] = {
    "BASE": {"cursor": True, "guard": False, "settle0": False, "poll_ms": 100, "compiled_validator": False,
             "knobs": {}, "replay": False},
    "COMP": {"cursor": False, "guard": True, "settle0": True, "poll_ms": 10, "compiled_validator": True,
             "knobs": {V_ENV: "1"}, "replay": True},
    "COMP_E": {"cursor": False, "guard": True, "settle0": True, "poll_ms": 10, "compiled_validator": True,
               "knobs": {V_ENV: "1", E_ENV: "bound"}, "replay": True},
    "COMP_K": {"cursor": True, "guard": True, "settle0": False, "poll_ms": 10, "compiled_validator": True,
               "knobs": {V_ENV: "1"}, "replay": True},
}
CLASSES = ["fill", "toggle", "modal"]
DEFAULT_MOTION = rc.DEFAULT_MOTION
NET = {"non_loopback_connects": 0, "provider_mode": "mock"}
CTX: dict[str, Any] = {"trial": None, "cls": None, "arm": None, "layer": None}
LEDGER: dict[str, Any] = {"path": None, "attempts": 0, "reached": 0}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def now() -> int:
    return time.monotonic_ns()


def sha16(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


def loadavg() -> str:
    return Path("/proc/loadavg").read_text().strip()


# ── network: scripted = loopback only (run_critpath guard); live = counted, TypeSafe allowed ──

def enable_live_network() -> None:
    def _counted(self: socket.socket, address: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0] if isinstance(address, tuple) and address else None
            if host not in ("127.0.0.1", "::1", "localhost"):
                NET["non_loopback_connects"] += 1
        return _REAL_CONNECT(self, address)

    def _counted_ex(self: socket.socket, address: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0] if isinstance(address, tuple) and address else None
            if host not in ("127.0.0.1", "::1", "localhost"):
                NET["non_loopback_connects"] += 1
        return _REAL_CONNECT_EX(self, address)

    socket.socket.connect = _counted  # type: ignore[method-assign]
    socket.socket.connect_ex = _counted_ex  # type: ignore[method-assign]
    NET["provider_mode"] = "live"


def install_provider_ledger(path: Path) -> None:
    """One line per provider HTTP attempt: reached (a response arrived) or not, latency, status.
    No headers, bodies, request ids or credentials are recorded."""
    import httpx2

    LEDGER["path"] = path
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                LEDGER["attempts"] += 1
                LEDGER["reached"] += 1 if rec.get("reached") else 0
    original = httpx2.Client.request

    @functools.wraps(original)
    def request(self: Any, method: Any, url: Any, *args: Any, **kwargs: Any) -> Any:
        from urllib.parse import urlsplit

        parts = urlsplit(str(url))
        t0 = now()
        rec = {"attempt": LEDGER["attempts"] + 1, "utc": utc(), "host_is_loopback": parts.hostname in ("127.0.0.1", "localhost"),
               "path": parts.path, "trial": CTX["trial"], "class": CTX["cls"], "arm": CTX["arm"], "layer": CTX["layer"]}
        LEDGER["attempts"] += 1
        try:
            response = original(self, method, url, *args, **kwargs)
        except BaseException as error:
            rec.update({"reached": False, "latency_ms": round((now() - t0) / 1e6, 3), "error": type(error).__name__})
            with path.open("a") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            raise
        LEDGER["reached"] += 1
        rec.update({"reached": True, "latency_ms": round((now() - t0) / 1e6, 3), "status": response.status_code})
        with path.open("a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        return response

    httpx2.Client.request = request


# R2-10R attempt 2: run_critpath.OraclePoller.stop joined a thread that run_b02.control_trial never started
# when a trial failed during setup; the RuntimeError ("cannot join thread before it is started") replaced
# the real error in the row (attempt-1 p0c-nw2-U). Same guard as Sampler.stop below; a started poller
# behaves exactly as before.
def _oracle_poller_stop(self: Any) -> None:
    self._stop.set()
    if self._thread.ident is not None:
        self._thread.join(timeout=2)


rc.OraclePoller.stop = _oracle_poller_stop


# ── oracle sampler ───────────────────────────────────────────────────────────

class Sampler:
    """Independent 2 ms re-read of the server state (no HTTP, no runner involvement). Keeps the
    first expected-state sample and every sample time after it (for the at/after-return rule)."""

    def __init__(self, fixtures: Any, cls: str, token: str) -> None:
        self.fixtures, self.cls, self.token = fixtures, cls, token
        self.first_ok_ns: int | None = None
        self.ok_samples: list[int] = []
        self.reverted_after_ok = 0
        self.reads = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        start = now()
        k = 0
        period = int(STATE_PERIOD_S * 1e9)
        while not self._stop.is_set():
            t = now()
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
            delay = (start + k * period - now()) / 1e9
            if delay > 0:
                time.sleep(delay)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=2)


# ── recording Driver proxy (labels, receipts, refs) ──────────────────────────

class RecDriver:
    """Wraps run.Driver: every call is recorded (call_send/call_return with a unique label) and,
    when ``receipts`` is set, an R2-07-format receipt is kept for compile_trace."""

    def __init__(self, inner: Any, rec: Any, token: str, receipts: list[dict[str, Any]] | None = None) -> None:
        self.inner, self.rec, self.token, self.receipts = inner, rec, token, receipts
        self.label = inner.label
        self.session = inner.session
        self.n_snap = 0
        self.n_act = 0
        self.mutations: list[dict[str, Any]] = []
        self.last_snapshot_id: str | None = None
        self.mutations_since_snapshot = 0

    def _label(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "get_browser_state" and arguments.get("snapshot_format") == "semantic_v2":
            self.n_snap += 1
            return f"snapshot{self.n_snap}"
        if name in ("browser_type", "browser_click"):
            self.n_act += 1
            return f"action{self.n_act}"
        return f"call-{name}-{uuid.uuid4().hex[:6]}"

    async def call(self, name: str, arguments: dict[str, Any], label: str | None = None) -> dict[str, Any]:
        label = label or self._label(name, arguments)
        mutation = name in ("browser_type", "browser_click")
        ref = arguments.get("ref") if isinstance(arguments.get("ref"), str) else None
        receipt: dict[str, Any] = {"kind": "driver_call", "tool": name, "t_start_ns": now()}
        for key in ("ref", "input_route", "snapshot_format"):
            if isinstance(arguments.get(key), str):
                receipt[f"arg_{key}"] = arguments[key]
        if name == "browser_type":
            receipt["arg_text_is_token"] = arguments.get("text") == self.token
            receipt["arg_replace"] = arguments.get("replace")
        mrec = None
        if mutation:
            mrec = {"label": label, "tool": name, "ref_snapshot": None if ref is None else ref.split(":")[0],
                    "latest_snapshot": self.last_snapshot_id,
                    "fresh": ref is not None and ref.split(":")[0] == self.last_snapshot_id
                    and self.mutations_since_snapshot == 0,
                    "input_route": arguments.get("input_route")}
        self.rec.add("call_send", label=label, tool=name)
        try:
            data = await self.inner.call(name, arguments)
        except Exception as error:
            code = getattr(error, "code", None)
            refused = bool(getattr(error, "refused", False))
            self.rec.add("call_return", label=label, tool=name, ok=False, error=type(error).__name__, code=code,
                         refused=refused)
            receipt.update({"t_end_ns": now(), "ok": False, "error": type(error).__name__, "error_code": code})
            if mrec is not None:
                mrec.update({"result": "refused" if refused else "error", "code": code, "t_return_ns": now()})
                self.mutations.append(mrec)
            if self.receipts is not None:
                self.receipts.append(receipt)
            raise
        t_ret = now()
        self.rec.add("call_return", label=label, tool=name, ok=True, route=data.get("route"),
                     effect=data.get("effect"), status=data.get("status"),
                     delivery=data.get("delivery"), input_route=data.get("input_route"),
                     verification=data.get("verification"),
                     result_keys=sorted(data.keys()) if mutation else None)
        receipt.update({"t_end_ns": t_ret, "ok": True,
                        "result": {k: v for k, v in data.items() if k in cr_result_keys()
                                   and (v is None or isinstance(v, (str, int, bool)))}})
        if name == "get_browser_state" and arguments.get("snapshot_format"):
            snap = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else {}
            page = data.get("page") if isinstance(data.get("page"), dict) else {}
            self.last_snapshot_id = snap.get("id")
            self.mutations_since_snapshot = 0
            from urllib.parse import urlsplit

            parts = urlsplit(page.get("url") or "")
            receipt["snapshot_id"] = snap.get("id")
            receipt["page_url"] = (f"{parts.scheme}://{parts.hostname}:{parts.port}{parts.path}"
                                   if parts.hostname in {"127.0.0.1", "localhost"} else "<non-loopback>")
            refs = data.get("refs") if isinstance(data.get("refs"), list) else []
            receipt["refs_logical"] = [
                {"ref": r.get("ref"), "role": r.get("role"), "name": r.get("name"),
                 "value_state": "empty" if r.get("value") in (None, "") else ("param" if r.get("value") == self.token else "other")}
                for r in refs if isinstance(r, dict)]
        if mrec is not None:
            mrec.update({"result": "accepted", "effect": data.get("effect"), "route": data.get("route"),
                         "t_return_ns": t_ret})
            self.mutations.append(mrec)
            self.mutations_since_snapshot += 1
        if self.receipts is not None:
            self.receipts.append(receipt)
        return data


def cr_result_keys() -> frozenset[str]:
    return frozenset({"effect", "route", "input_route", "status", "delivery", "delivery_mode", "verification",
                      "action", "format", "snapshot_format", "prepared", "launched", "reused", "profile_mode",
                      "code", "enabled"})


# ── the ordinary / guarded step loop (run.py rules incl. FIX-01 Part B) ───────

async def step_loop(*, rec: Any, drv: RecDriver, task: Any, pid: int, window: dict[str, Any], target_id: str,
                    tab_id: str, available: set[str], capture_bound: bool, guard: bool, poll_ms: int,
                    provider: str, result: dict[str, Any], inject: Any = None,
                    route_prefix: str = "") -> str:
    history: list[dict[str, Any]] = []
    pending = None
    dispatched: set[str] = set()
    refusal_retried = False
    label = drv.label
    for step in range(1, task.max_steps + 1):
        current = rc.oracle_read(rec, task, f"pre_step{route_prefix}{step}", step - 1)
        if current in {"verified", "refuted"}:
            return current
        snap = await drv.call("get_browser_state", {"target_id": target_id, "tab_id": tab_id,
                                                    "snapshot_format": "semantic_v2"})
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
            resolution = rc.resolve_guarded_completion(pending, task, sources, candidates, session=label)
            candidate, guard_tel = resolution.candidate, resolution.telemetry
            pending = None
            rec.add("guard_done", step=step, status=guard_tel.get("status"), reason=guard_tel.get("reason"))
        if candidate is not None:
            route = "guarded-completion"
        else:
            rec.add("decide_start", step=step, provider=provider)
            try:
                if provider == "live":
                    choice, _conf, _probs = await asyncio.to_thread(jev_adapter.choose_live_for_task, task, sources,
                                                                    candidates, history)
                else:
                    choice, _conf, _probs = rc.choose_mock_for_task(task, sources, candidates, history)
            except Exception as error:  # provider failure: retained, never retried here
                rec.add("decided", step=step, choice=None, error=type(error).__name__)
                result["provider_error"] = type(error).__name__
                return "unknown"
            rec.add("decided", step=step, choice=choice)
            result.setdefault("decisions", []).append({"step": step, "choice": choice, "provider": provider})
            if drv.receipts is not None:
                drv.receipts.append({"kind": "provider_response", "ok": choice is not None, "backend": provider,
                                     "selected_id": choice})
            if choice is None:
                return "abstained"
            candidate = rc.validate_choice(choice, candidates, current_capture_id=None)
            route = "provider"
        next_plan = (rc.plan_guarded_completion(task, sources, candidate, session=label)
                     if guard and route == "provider" else None)
        result["routes"].append(route_prefix + route)
        result["candidates"].append(candidate.id)
        result["tools"].append(candidate.tool)
        result["input_routes"].append((candidate.arguments or {}).get("input_route"))
        result.setdefault("guard", []).append(guard_tel)
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
        if inject is not None:
            await inject(step, candidate, snap)
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
            polls = int(round(POLL_DEADLINE_S * 1000 / poll_ms))
            for i in range(polls):
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


# ── DOM replacement (N4a / OOD controls) through an independent CDP client ───

def dom_replace(pid: int, url: str, cls: str) -> str:
    marker = f"r2-10 marker {uuid.uuid4().hex[:8]}"
    ports = devtools_ports_for_pid(pid)
    client = CdpClient(http_get_json(ports[0], "/json/version")["webSocketDebuggerUrl"])
    try:
        return evaluate(client, page_target(client, url), rb.dom_replace_js(cls, marker))
    finally:
        client.close()


# ── one trial ────────────────────────────────────────────────────────────────

class RoutineStore:
    """Per (layer, arm) compiled-routine state, persisted so chunks continue."""

    def __init__(self, out: Path) -> None:
        self.dir = out / "routines"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, layer: str, arm: str) -> Path:
        return self.dir / f"{layer}-{arm}.json"

    def get(self, layer: str, arm: str) -> dict[str, Any] | None:
        p = self.path(layer, arm)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, layer: str, arm: str, state: dict[str, Any]) -> None:
        self.path(layer, arm).write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


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


async def run_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, store: RoutineStore,
                    trace_path: Path | None, rec: Any, result: dict[str, Any]) -> None:
    cls, kind, arm_name, layer = spec["cls"], spec["kind"], spec["arm"], spec["layer"]
    arm = ARMS[arm_name]
    page_cls = spec.get("page_cls", cls)  # OOD control: fill routine applied on another page
    token = f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-r210-{uuid.uuid4().hex[:8]}"
    task = rc.make_task(page_cls, token, fixtures)
    result.update({"token_sha16": sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "routes": [], "tools": [], "input_routes": [], "candidates": [],
                   "page_cls": page_cls})
    task.reset()
    fixtures.state(page_cls).drain()
    sampler = Sampler(fixtures, page_cls, token)
    result["_sampler"] = sampler
    env = driver_env_for(arm, cls, trace_path)
    result["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
    result["driver_env_trace_set"] = TRACE_ENV in env
    provider = "live" if layer in ("live", "live_shake") else "mock"
    replay_state = store.get(layer, arm_name) if (arm["replay"] and cls == "fill") else None
    mode = "step"
    if arm["replay"] and cls == "fill" and kind == "measured":
        mode = "replay" if (replay_state and replay_state.get("admitted")) else (
            "train" if replay_state is None else "step_after_failed_admission")
    if kind in ("n4a", "ood") and cls == "fill":
        mode = "replay"
    result["mode"] = mode
    receipts: list[dict[str, Any]] | None = [] if mode == "train" else None
    rec.add("trial_start", cls=cls, arm=arm_name, kind=kind, layer=layer, mode=mode)
    rc.CLIENT["rec"] = rec
    CTX_REC["rec"] = rec
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
            drv = RecDriver(inner, rec, token, receipts)
            result["_drv"] = drv
            await rc.timed_call(rec, inner, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm["cursor"]})
            motion = await rc.timed_call(rec, inner, "cursor_motion", "set_agent_cursor_motion", DEFAULT_MOTION)
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
            loop_kw = dict(rec=rec, drv=drv, task=task, pid=pid, window=window, target_id=target_id, tab_id=tab_id,
                           available=available, capture_bound=capture_bound,
                           guard=arm["guard"] and page_cls == "fill", poll_ms=arm["poll_ms"], provider=provider,
                           result=result)

            inject = None
            if kind == "n4a":
                async def inject_step(step: int, candidate: Any, snap: dict[str, Any]) -> None:
                    if step == 2 and not result.get("dom_replace"):
                        result["dom_replace"] = await asyncio.to_thread(dom_replace, pid, url, page_cls)
                        rec.add("dom_replaced", result=result["dom_replace"])
                inject = inject_step

            if mode in ("replay",):
                art_state = replay_state if (replay_state and replay_state.get("admitted")) else None
                if art_state is None or not art_state.get("artifact"):
                    raise RuntimeError(f"no admitted routine for {layer}/{arm_name} (controls run after training)")
                artifact = art_state["artifact"]

                async def fallback(ctx: Any, rrec: Any, index: int, reason: str) -> str:
                    rec.add("fallback_start", index=index, reason=reason)
                    result["fallback"] = {"index": index, "reason": reason}
                    out = await step_loop(**loop_kw, route_prefix="fallback:")
                    return "fallback_verified" if out == "verified" else out

                async def hook(where: str, index: int, ctx: Any, rrec: Any) -> None:
                    if kind == "n4a" and where == "before_dispatch" and index == 1 and not result.get("dom_replace"):
                        result["dom_replace"] = await asyncio.to_thread(dom_replace, pid, url, "fill")
                        rec.add("dom_replaced", result=result["dom_replace"])

                def read_oracle() -> dict[str, Any]:
                    rec.add("oracle_send", label="routine_read")
                    state = task.read_oracle()
                    rec.add("oracle_return", label="routine_read",
                            outcome="verified" if state.get("submitted") == token else "unknown")
                    return dict(state)

                routine = cr.Routine(artifact, fallback=fallback, hook=hook)
                ctx = cr.ReplayContext(driver=drv, target_id=target_id, tab_id=tab_id, pid=pid,
                                       window_id=int(window["window_id"]), fixture_url=url, token=token,
                                       read_oracle=read_oracle, rebind=None)
                rrec = cr.ReplayRecord()
                rrec.t0_ns = now()
                await routine.replay(ctx, rrec)
                if rrec.outcome == "stopped" and str(rrec.stop_reason or "") == "refused:browser_ref_stale" \
                        and not result.get("fallback"):
                    # Compiled replay refused twice with a pre-dispatch code: nothing landed; the
                    # guarded continuation takes the current state.
                    rrec.outcome = await fallback(ctx, rrec, -1, "refused:browser_ref_stale")
                result["routine"] = {k: v for k, v in rrec.as_dict().items() if k != "events"}
                result["routine_events"] = rrec.events
                result["routes"] = ["compiled"] + result["routes"]
                out = rrec.outcome
                result["outcome"] = {"fallback_verified": "verified", "verified_by_reconcile": "verified"}.get(out, out)
                result["routine_outcome"] = out
            else:
                result["outcome"] = await step_loop(**loop_kw, inject=inject)
    if mode == "train":
        result["_receipts"] = receipts


async def admission_cell(args: argparse.Namespace, fixtures: Any, artifact: dict[str, Any], arm_name: str,
                         out: Path, name: str) -> dict[str, Any]:
    """Clean-reset admission replay: fresh fixture state, Driver and browser, compiled replay, NO fallback."""
    rec = rc.Recorder()
    res: dict[str, Any] = {}
    spec = {"cls": "fill", "kind": "admission", "arm": arm_name, "layer": "admission"}
    trace_rel = f"trials/{name}.driver-trace.jsonl"
    arm = ARMS[arm_name]
    token = f"jev-{uuid.uuid4().hex[:10]}"
    task = rc.make_task("fill", token, fixtures)
    task.reset()
    fixtures.state("fill").drain()
    sampler = Sampler(fixtures, "fill", token)
    env = driver_env_for(arm, "fill", out / trace_rel)
    t0 = now()
    rrec = cr.ReplayRecord()
    drv_holder: dict[str, Any] = {}
    try:
        rc.CLIENT["rec"] = rec
        CTX_REC["rec"] = rec
        params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
        async with rc.stdio_client(params) as (read, write):
            async with rc.ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                if arm["compiled_validator"]:
                    rc.compile_output_validators(session)
                inner = rc.Driver(session, f"jev-r210-{uuid.uuid4().hex[:8]}")
                drv = RecDriver(inner, rec, token, None)
                drv_holder["drv"] = drv
                await rc.timed_call(rec, inner, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm["cursor"]})
                await rc.timed_call(rec, inner, "cursor_motion", "set_agent_cursor_motion", DEFAULT_MOTION)
                prepared = await rc.timed_call(rec, inner, "prepare", "browser_prepare",
                                               {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                pid = int(prepared["prepared_pid"])
                res["prepared_pid"] = pid
                res["token_sha16"] = sha16(token)
                window = await rc.wait_for_window(inner, pid)
                bound = await rc.timed_call(rec, inner, "bind", "get_browser_state",
                                            {"pid": pid, "window_id": window["window_id"]})
                target_id, tab_id = bound["target_id"], rc.select_tab_id(bound["tabs"])
                url = fixtures.page_url("fill")
                await rc.timed_call(rec, inner, "navigate", "browser_navigate",
                                    {"target_id": target_id, "tab_id": tab_id, "url": url})
                sampler.start()

                def read_oracle() -> dict[str, Any]:
                    rec.add("oracle_send", label="routine_read")
                    state = task.read_oracle()
                    rec.add("oracle_return", label="routine_read",
                            outcome="verified" if state.get("submitted") == token else "unknown")
                    return dict(state)

                routine = cr.Routine(artifact, fallback=None)
                ctx = cr.ReplayContext(driver=drv, target_id=target_id, tab_id=tab_id, pid=pid,
                                       window_id=int(window["window_id"]), fixture_url=url, token=token,
                                       read_oracle=read_oracle)
                rrec.t0_ns = now()
                await routine.replay(ctx, rrec)
    except Exception as error:  # every failure is kept
        res["error"] = f"{type(error).__name__}: {str(error)[:300]}"
        if rrec.outcome == "running":
            rrec.outcome = "error"
    rc.CLIENT["rec"] = None
    CTX_REC["rec"] = None
    rc.CLIENT["compiled"] = None
    record = await finish_record({"trial": name, **spec, "round": None, "loadavg_before": loadavg(),
                                  "driver_trace": trace_rel}, res, sampler, rec, fixtures, "fill", t0,
                                 drv_holder.get("drv"))
    record["routine"] = {k: v for k, v in rrec.as_dict().items() if k != "events"}
    record["routine_events"] = rrec.events
    record["outcome"] = rrec.outcome
    record["admitted"] = bool(rrec.outcome == "verified" and record["oracle_exact_match"]
                              and record["completion_mutations"] == 1
                              and all(m.get("fresh") for m in record["mutations"]))
    write_trial(out, name, rec, record)
    return record


async def finish_record(record: dict[str, Any], res: dict[str, Any], sampler: Sampler, rec: Any, fixtures: Any,
                        page_cls: str, t0: int, drv: RecDriver | None) -> dict[str, Any]:
    record["trial_wall_ns"] = now() - t0
    deadline = time.monotonic() + 2.5
    while sampler.first_ok_ns is None and time.monotonic() < deadline and sampler._thread.is_alive():
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    sampler.stop()
    pid = res.pop("prepared_pid", None)
    for _ in range(50):
        if pid is None or rb.browser_gone(pid):
            break
        await asyncio.sleep(0.1)
    record["browser_alive_after_close"] = None if pid is None else not rb.browser_gone(pid)
    await asyncio.sleep(0.3)
    final_state = fixtures.state(page_cls).snapshot()
    journal = fixtures.state(page_cls).drain()
    record.update({k: v for k, v in res.items() if not k.startswith("_")})
    record["journal"] = journal
    if page_cls == "fill":
        record["final_state"] = {"submitted_sha16": sha16(final_state.get("submitted"))}
        record["oracle_exact_match"] = final_state.get("submitted") is not None and \
            sha16(final_state["submitted"]) == res.get("token_sha16")
    else:
        record["final_state"] = {k: final_state.get(k) for k in ("checked", "opened", "modal")}
        record["oracle_exact_match"] = rc.oracle_ok("toggle-confirm" if page_cls == "toggle" else "modal", final_state, "")
    record["completion_mutations"] = len(rc.completion_mutations(page_cls, journal))
    record["poller_first_ok_ns"] = sampler.first_ok_ns
    record["poller_ok_samples_ns"] = sampler.ok_samples
    record["poller_reads"] = sampler.reads
    record["poller_reverted_after_ok"] = sampler.reverted_after_ok
    record["mutations"] = drv.mutations if drv is not None else []
    record["network"] = dict(NET)
    record["provider_ledger_after"] = {"attempts": LEDGER["attempts"], "reached": LEDGER["reached"]}
    record["loadavg_after"] = loadavg()
    return record


def write_trial(out: Path, name: str, rec: Any, record: dict[str, Any]) -> None:
    with (out / f"trials/{name}.jsonl").open("w") as f:
        for ev in rec.events:
            f.write(json.dumps(ev, sort_keys=True, default=str) + "\n")
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True, default=str) + "\n")


async def one(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, store: RoutineStore,
              out: Path) -> dict[str, Any]:
    name = spec["name"]
    trace_rel = None if spec["kind"] == "smoke" else f"trials/{name}.driver-trace.jsonl"
    trace_path = None if trace_rel is None else out / trace_rel
    rec = rc.Recorder()
    record: dict[str, Any] = {"trial": name, **{k: spec.get(k) for k in ("cls", "arm", "kind", "block", "layer",
                                                                          "round", "order", "page_cls")},
                              "loadavg_before": loadavg(), "driver_trace": trace_rel, "utc_start": utc()}
    CTX.update({"trial": name, "cls": spec["cls"], "arm": spec["arm"], "layer": spec["layer"]})
    res: dict[str, Any] = {}
    t0 = now()
    try:
        await asyncio.wait_for(run_trial(spec, args, fixtures, store, trace_path, rec, res), timeout=180)
    except Exception as error:
        res["outcome"] = "error"
        res["error"] = f"{type(error).__name__}: {str(error)[:300]}"
        leaves, stack = [], [error]
        while stack:
            e = stack.pop()
            subs = getattr(e, "exceptions", None)
            if subs:
                stack.extend(subs)
            else:
                leaves.append(f"{type(e).__name__}: {e}"[:300])
        res["error_leaves"] = leaves
    rc.CLIENT["rec"] = None
    CTX_REC["rec"] = None
    rc.CLIENT["compiled"] = None
    sampler = res.pop("_sampler", None)
    drv = res.pop("_drv", None)
    receipts = res.pop("_receipts", None)
    if sampler is None:
        sampler = Sampler(fixtures, spec.get("page_cls", spec["cls"]), "")
        sampler._thread = threading.Thread(target=lambda: None)
        sampler._thread.start()
    record = await finish_record(record, res, sampler, rec, fixtures, spec.get("page_cls", spec["cls"]), t0, drv)
    CTX.update({"trial": None})
    if receipts is not None:
        # Training invocation: compile from its receipts (timed, outside T), then the clean-reset
        # admission replay. Both are charged to this (first) invocation in the amortized analysis.
        learning_verified = bool(record.get("outcome") == "verified" and record.get("oracle_exact_match")
                                 and record.get("completion_mutations") == 1)
        c0 = time.perf_counter_ns()
        try:
            artifact = cr.compile_trace(receipts, learning_verified=learning_verified,
                                        routine_id=f"r2-10-fill-submit-{spec['layer']}-{spec['arm']}")
            compile_error = None
        except Exception as error:  # noqa: BLE001
            artifact, compile_error = None, f"{type(error).__name__}: {error}"
        compile_ms = (time.perf_counter_ns() - c0) / 1e6
        record["training"] = {"learning_verified": learning_verified, "compile_ms": compile_ms,
                              "compile_error": compile_error,
                              "authority_problems": cr.check_artifact_authority(artifact) if artifact else None,
                              "receipts": len(receipts)}
        state: dict[str, Any] = {"trained_by": name, "learning_verified": learning_verified, "compile_ms": compile_ms,
                                 "compile_error": compile_error, "artifact": artifact, "admitted": False}
        if artifact is not None:
            adm = await admission_cell(args, fixtures, artifact, spec["arm"], out, f"{name}-admission")
            state.update({"admission_trial": adm["trial"], "admitted": adm["admitted"]})
            record["training"]["admission_trial"] = adm["trial"]
            record["training"]["admitted"] = adm["admitted"]
        store.put(spec["layer"], spec["arm"], state)
    write_trial(out, name, rec, record)
    print(json.dumps({k: record.get(k) for k in ("trial", "mode", "outcome", "oracle_exact_match", "completion_mutations",
                                                  "routes", "error")} | {"la": record["loadavg_before"].split()[0],
                                                                         "prov": record["provider_ledger_after"]}),
          flush=True)
    return record


# ── plans ────────────────────────────────────────────────────────────────────

def build_plan(kind: str, start: int, rounds: int, arms: list[str]) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    if kind == "live":
        for r in range(start, start + rounds):
            for cls in CLASSES[r % 3:] + CLASSES[:r % 3]:
                order = ["BASE", "COMP"] if r % 2 == 0 else ["COMP", "BASE"]
                for pos, arm in enumerate(order):
                    trials.append({"cls": cls, "arm": arm, "kind": "measured", "layer": "live", "round": r,
                                   "order": "AB" if r % 2 == 0 else "BA", "block": "L"})
        return trials
    if kind == "scripted":
        rows = rb.williams_any(len(arms))
        for r in range(start, start + rounds):
            for cls in CLASSES[r % 3:] + CLASSES[:r % 3]:
                row = rows[r % len(rows)]
                for j in row:
                    trials.append({"cls": cls, "arm": arms[j], "kind": "measured", "layer": "scripted", "round": r,
                                   "order": "".join(arms[k][0] if arms[k] == "BASE" else arms[k][-1] for k in row),
                                   "block": "S"})
        return trials
    if kind == "controls":
        for k in range(5):
            for cls in CLASSES:
                trials.append({"cls": cls, "arm": "COMP", "kind": "n4a", "layer": "scripted", "round": k, "block": "N"})
        for k in range(5):
            trials.append({"cls": "fill", "arm": "COMP", "kind": "ood", "layer": "scripted", "round": k, "block": "N",
                           "page_cls": "toggle" if k % 2 == 0 else "modal"})
        for k in range(5):
            trials.append({"cls": CLASSES[k % 3], "arm": "COMP", "kind": "nw2", "layer": "scripted", "round": k,
                           "block": "N"})
        return trials
    if kind == "smoke":
        for cls in CLASSES:
            for k in range(5):
                trials.append({"cls": cls, "arm": "BASE", "kind": "smoke", "layer": "smoke", "round": k, "block": "D"})
        return trials
    if kind == "shakedown":
        for cls in CLASSES:
            for arm in arms:
                trials.append({"cls": cls, "arm": arm, "kind": "measured", "layer": "shake", "round": 0, "block": "K"})
        for cls in CLASSES:
            trials.append({"cls": cls, "arm": "COMP", "kind": "n4a", "layer": "shake", "round": 0, "block": "K"})
        trials.append({"cls": "fill", "arm": "COMP", "kind": "ood", "layer": "shake", "round": 0, "block": "K",
                       "page_cls": "toggle"})
        trials.append({"cls": "toggle", "arm": "COMP", "kind": "nw2", "layer": "shake", "round": 0, "block": "K"})
        return trials
    if kind == "traingate":
        # Phase 0 (e): n training invocations, each in its own routine scope: verified training
        # execution -> compile -> clean-reset admission replay (fresh binding checked per mutation).
        for k in range(start, start + rounds):
            trials.append({"cls": "fill", "arm": "COMP", "kind": "measured", "layer": f"gate{k}", "round": k,
                           "block": "G"})
        return trials
    if kind == "nw2gate":
        # Phase 0 (c): B-02 N-W2 at the default path (no knobs), toggle and modal interleaved.
        for k in range(start, start + rounds):
            for cls in ("toggle", "modal"):
                trials.append({"cls": cls, "arm": "K5", "kind": "nw2gate", "layer": "gate", "round": k,
                               "block": "C"})
        return trials
    if kind == "live_shake":
        for cls in CLASSES:
            trials.append({"cls": cls, "arm": "COMP" if cls == "fill" else "BASE", "kind": "measured",
                           "layer": "live_shake", "round": 0, "block": "LK"})
        return trials
    raise ValueError(kind)


_RB_BASE_ENV = rb._BASE_ENV


def _rb_env(source: Any = None) -> dict[str, str]:
    env = _RB_BASE_ENV() if source is None else _RB_BASE_ENV(source)
    env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
    env["DO_NOT_TRACK"] = "1"
    return env


rb._BASE_ENV = _rb_env


async def toolslist_raw(driver: str, out: Path, name: str, env: dict[str, str]) -> dict[str, Any]:
    """Raw MCP stdio: initialize + tools/list; the reply line is kept byte for byte."""
    proc = await asyncio.create_subprocess_exec(driver, "mcp", env=env, stdin=asyncio.subprocess.PIPE,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                                                limit=64 * 1024 * 1024)

    async def rpc(msg: dict[str, Any], reply: bool = True) -> bytes | None:
        proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
        await proc.stdin.drain()
        return (await asyncio.wait_for(proc.stdout.readline(), timeout=20)) if reply else None

    try:
        await rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "r2-10-toolslist", "version": "0"}}})
        await rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, reply=False)
        line = await rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=20)
        except asyncio.TimeoutError:
            proc.kill()
    (out / f"{name}.json").write_bytes(line or b"")
    return {"name": name, "bytes": len(line or b""), "sha256": hashlib.sha256(line or b"").hexdigest()}


def session_files() -> list[str]:
    """Every file under the private session HOME and TMPDIR (default-off smoke: no trace file may appear)."""
    roots = [Path(os.environ.get("HOME", "/nonexistent")), Path(os.environ.get("TMPDIR", "/nonexistent"))]
    found = []
    for root in roots:
        if root.is_dir():
            for p in root.rglob("*"):
                try:
                    if p.is_file():
                        found.append(str(p.relative_to(root.parent)))
                except OSError:
                    continue
    return sorted(found)


async def nw2_one(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, out: Path) -> dict[str, Any]:
    """B-02 N-W2 control (run_b02.control_one, unchanged) with the COMP admission knob."""
    rb.CURRENT["knobs"] = dict(ARMS["COMP"]["knobs"]) if spec["kind"] == "nw2" else {}
    try:
        return await rb.control_one({**spec, "arm": "K5", "kind": "nw2"}, args, fixtures, out)
    except Exception as error:  # run_b02.control_one cannot stop a poller it never started: keep the row
        record = {"trial": spec["name"], "cls": spec["cls"], "arm": "K5", "kind": "nw2", "block": spec.get("block"),
                  "outcome": "error", "error": f"{type(error).__name__}: {str(error)[:300]}",
                  "harness_note": "control_one raised after a failed setup", "loadavg_before": loadavg()}
        with (out / f"trials/{spec['name']}.jsonl").open("w") as f:
            f.write(json.dumps({"event": "summary", **record}, sort_keys=True) + "\n")
        print(json.dumps({"trial": spec["name"], "outcome": "error", "error": record["error"]}), flush=True)
        return record
    finally:
        rb.CURRENT["knobs"] = {}


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    arms = args.arms.split(",")
    if args.plan == "toolslist":
        env = driver_env_for(ARMS["BASE"], "none", None)
        rows = [await toolslist_raw(args.driver, out, f"{args.prefix}-toolslist-{k}", env) for k in range(3)]
        (out / f"{args.prefix}-toolslist.json").write_text(json.dumps(
            {"rows": rows, "driver_env_exp": {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")},
             "trace_env_set": TRACE_ENV in env}, indent=1))
        print(json.dumps(rows), flush=True)
        return
    files_before = session_files() if args.plan == "smoke" else None
    store = RoutineStore(Path(args.routines) if args.routines else out)
    fixtures = rc.Fixtures()
    trials = build_plan(args.plan, args.start_round, args.rounds, arms)
    for i, spec in enumerate(trials):
        spec["name"] = (f"{args.prefix}{i:03d}-{spec['cls']}-{spec['arm']}-{spec['kind']}"
                        f"-r{spec['round']:02d}")
    manifest: dict[str, Any] = {"plan": args.plan, "arms": arms, "start_round": args.start_round, "rounds": args.rounds,
                                "trials": [s["name"] for s in trials], "started_utc": utc(),
                                "loadavg_start": loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": NET["provider_mode"], "provider_caps": {"reached": args.cap_reached,
                                                                                          "attempts": args.cap_attempts},
                                "ledger_start": {"attempts": LEDGER["attempts"], "reached": LEDGER["reached"]}}
    not_run: list[str] = []
    try:
        for idx, spec in enumerate(trials):
            if spec["layer"] in ("live", "live_shake"):
                # A pair needs at most 4 decisions (+2 for a fallback or reobserve): stop before a cap could be hit.
                need = 3
                if LEDGER["reached"] + need > args.cap_reached or LEDGER["attempts"] + need > args.cap_attempts:
                    not_run = [s["name"] for s in trials[idx:]]
                    manifest["stopped_for_budget"] = {"at": spec["name"], "ledger": dict(LEDGER) | {"path": None}}
                    break
            if spec["kind"] in ("nw2", "nw2gate"):
                await nw2_one(spec, args, fixtures, out)
            else:
                await one(spec, args, fixtures, store, out)
    finally:
        manifest.update({"ended_utc": utc(), "loadavg_end": loadavg(), "network": dict(NET), "not_run": not_run,
                         "ledger_end": {"attempts": LEDGER["attempts"], "reached": LEDGER["reached"]}})
        if files_before is not None:
            after = session_files()
            new = [f for f in after if f not in set(files_before)]
            manifest["smoke_new_session_files"] = new
            manifest["smoke_trace_like_files"] = [f for f in new if "trace" in f.lower() or "phase" in f.lower()]
        (out / f"run-manifest-{args.prefix}.json").write_text(json.dumps(manifest, indent=1))
        fixtures.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", required=True,
                   choices=("live", "scripted", "controls", "smoke", "shakedown", "live_shake", "toolslist",
                            "traingate", "nw2gate"))
    p.add_argument("--arms", default="BASE,COMP,COMP_K,COMP_E")
    p.add_argument("--start-round", type=int, default=0)
    p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--prefix", required=True)
    p.add_argument("--routines", help="directory holding routines/ (defaults to --out)")
    p.add_argument("--provider-ledger", help="raw/provider-ledger.jsonl (live plans)")
    p.add_argument("--cap-reached", type=int, default=0)
    p.add_argument("--cap-attempts", type=int, default=0)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or os.environ.get("R2_10_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless + cua-x11-session.sh (in_session.sh)")
    for name in (TRACE_ENV, SETTLE_ENV, E_ENV, V_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    live = args.plan in ("live", "live_shake")
    if live:
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            raise SystemExit("blocked: provider key not forwarded into the session")
        if not args.provider_ledger or args.cap_reached <= 0:
            raise SystemExit("refusing: live plans need --provider-ledger and caps")
        enable_live_network()
        install_provider_ledger(Path(args.provider_ledger))
    else:
        os.environ.pop("TYPESAFE_API_KEY", None)
    args.plan_kind = args.plan  # run_b02.control_one reads args.driver only
    args.save_snapshots = False
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

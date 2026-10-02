"""B-01 browser critical-path runner (measurement only, mock chooser, 0 provider HTTP).

Run inside the isolated X11 session with the jev-use virtualenv:

    JEV_USE_DIR=<jev-use> <jev-use>/.venv/bin/python run_critpath.py --driver <bin> \
        --out <dir> --plan {shakedown|measured|controls|smoke} [--lock <quiet-lane.lock>]

Each trial mirrors jev-use ``python/run.py`` (mock provider, ``--guarded-completion``
where the arm says so) and reuses its functions: a fresh ``cua-driver mcp``
process, the arm's cursor settings, ``browser_prepare`` isolated_new,
``wait_for_window``, bind, navigate, then the run.py step loop (oracle read,
semantic_v2 snapshot, ``task_candidates_for_step``, guarded resolve or
``choose_mock_for_task``, action) and the completion poll. Every caller phase is
stamped with ``time.monotonic_ns()``; the Driver writes CLOCK_MONOTONIC marks
through CUA_DRIVER_PHASE_TRACE_FILE; the fixture servers journal every
mutation on the same clock; an independent harness thread re-reads the server
state every 2 ms. The server state is the oracle; the runner's outcome is
logged but is not the oracle. Output paths are relative to --out.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import socket
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("JEV_USE_DIR", "")).resolve()
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(JEV))
sys.path.insert(0, str(JEV / "python"))

# ── 0 provider HTTP: the runner process may only open loopback sockets ─────────
NETWORK = {"non_loopback_connect_attempts": 0}
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex


def _check_address(sock: socket.socket, address: Any) -> None:
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) and address else None
        if host not in _LOOPBACK:
            NETWORK["non_loopback_connect_attempts"] += 1
            raise ConnectionRefusedError("B-01 runner: non-loopback network is disabled (mock chooser)")


def _guarded_connect(self: socket.socket, address: Any) -> None:
    _check_address(self, address)
    return _orig_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
    _check_address(self, address)
    return _orig_connect_ex(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from mcp.client.session import ClientSession as _McpClientSession  # noqa: E402

import fixture_server as jev_fixture_server  # noqa: E402
from b01_fixtures import JournalServer, oracle_ok  # noqa: E402
from b01_tasks import ModalTask, ToggleConfirmTask  # noqa: E402
from core import validate_choice  # noqa: E402
from driver_env import driver_environment  # noqa: E402
from fixture_server import FixtureServer, FixtureState  # noqa: E402
from guarded_completion import plan_guarded_completion, resolve_guarded_completion  # noqa: E402
from jev_adapter import choose_mock_for_task  # noqa: E402
from run import (  # noqa: E402
    Driver,
    select_tab_id,
    supports_capture_bound_click,
    task_candidates_for_step,
    wait_for_window,
)
from tasks import FixtureFormTask  # noqa: E402
from verify_setup import DUPLICATE_SUBMIT_ON_INPUT  # noqa: E402

# ── MCP client output-schema validation: timed in every arm; K5 compiles once ──
# mcp 1.30 ClientSession._validate_tool_result calls jsonschema.validate() on
# every tools/call result, which re-checks the schema against its metaschema
# and builds a new validator each time. Every arm records its start/end; arm
# K5 (caller-side, product code untouched) compiles one validator per output
# schema at tools/list time (outside T) and validates each result with it,
# with the same acceptance rule (validator_for + check_schema + best_match).
CLIENT = {"rec": None, "compiled": None}
_orig_validate_tool_result = _McpClientSession._validate_tool_result


def _schema_key(schema: Any) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compile_output_validators(session: Any) -> int:
    from jsonschema.validators import validator_for
    from referencing import Registry

    compiled: dict[str, Any] = {}
    for schema in getattr(session, "_tool_output_schemas", {}).values():
        if schema is None:
            continue
        key = _schema_key(schema)
        if key not in compiled:
            cls = validator_for(schema)
            cls.check_schema(schema)
            compiled[key] = cls(schema, registry=Registry())
    CLIENT["compiled"] = compiled
    return len(compiled)


async def _compiled_validate(self: Any, name: str, result: Any) -> None:
    from jsonschema.exceptions import best_match

    if name not in self._tool_output_schemas:
        await self.list_tools()
    schema = self._tool_output_schemas.get(name)
    if schema is None:
        return
    if result.structuredContent is None:
        raise RuntimeError(f"Tool {name} has an output schema but did not return structured content")
    validator = CLIENT["compiled"].get(_schema_key(schema))
    if validator is None:  # not compiled at tools/list: fall back to the library path
        await _orig_validate_tool_result(self, name, result)
        return
    error = best_match(validator.iter_errors(result.structuredContent))
    if error is not None:
        raise RuntimeError(f"Invalid structured content returned by tool {name}: {error}")


async def _timed_validate_tool_result(self: Any, name: str, result: Any) -> None:
    rec = CLIENT["rec"]
    if rec is not None:
        rec.add("client_validate_start", tool=name)
    try:
        if CLIENT["compiled"] is not None:
            await _compiled_validate(self, name, result)
        else:
            await _orig_validate_tool_result(self, name, result)
    finally:
        if rec is not None:
            rec.add("client_validate_end", tool=name)


_McpClientSession._validate_tool_result = _timed_validate_tool_result  # type: ignore[method-assign]

TRACE_ENV = "CUA_DRIVER_PHASE_TRACE_FILE"
KNOB_ENV = "CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS"
POLL_DEADLINE_S = 2.0  # run.py: 20 x 0.1 s


@dataclass(frozen=True)
class Arm:
    cursor: bool
    fast_glide: bool
    guard: bool
    knob_zero: bool
    poll_ms: int
    compiled_validator: bool = False


ARMS: dict[str, Arm] = {
    "K0n": Arm(cursor=True, fast_glide=False, guard=False, knob_zero=False, poll_ms=100),
    "K0": Arm(cursor=True, fast_glide=False, guard=True, knob_zero=False, poll_ms=100),
    "K1": Arm(cursor=True, fast_glide=True, guard=True, knob_zero=False, poll_ms=100),
    "K2": Arm(cursor=False, fast_glide=False, guard=True, knob_zero=False, poll_ms=100),
    "K3": Arm(cursor=False, fast_glide=False, guard=True, knob_zero=True, poll_ms=100),
    "K4": Arm(cursor=False, fast_glide=False, guard=True, knob_zero=True, poll_ms=10),
    "K5": Arm(cursor=False, fast_glide=False, guard=True, knob_zero=True, poll_ms=10, compiled_validator=True),
}
CLASS_ARMS = {
    "fill": ["K0n", "K0", "K1", "K2", "K3", "K4"],
    "toggle": ["K0", "K1", "K2", "K4"],
    "modal": ["K0", "K1", "K2", "K4"],
}
CLASSES = ["fill", "toggle", "modal"]
EXPECTED_TOOLS = {"fill": ["browser_type", "browser_click"], "toggle": ["browser_click", "browser_click"],
                  "modal": ["browser_click", "browser_click"]}
DEFAULT_MOTION = {"glide_duration_ms": 0, "dwell_after_click_ms": 80}
FAST_MOTION = {"glide_duration_ms": 1, "dwell_after_click_ms": 0}


def now() -> int:
    return time.monotonic_ns()


def sha16(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


def loadavg() -> str:
    try:
        return Path("/proc/loadavg").read_text().strip()
    except OSError:
        return "unavailable"


def williams(n: int) -> list[list[int]]:
    """Williams design for even n: n sequences, first-order carryover balanced."""
    first = [0]
    lo, hi = 1, n - 1
    take_lo = True
    while len(first) < n:
        first.append(lo if take_lo else hi)
        if take_lo:
            lo += 1
        else:
            hi -= 1
        take_lo = not take_lo
    return [[(x + i) % n for x in first] for i in range(n)]


# ── fixtures with server-side journals ─────────────────────────────────────────

class FillJournalState(FixtureState):
    """jev-use FixtureState plus a CLOCK_MONOTONIC submit journal."""

    def __init__(self) -> None:
        super().__init__()
        self.journal: list[dict[str, Any]] = []
        self._jlock = threading.Lock()
        self.expected_sha16: str | None = None

    def submit(self, value: str) -> None:
        t = now()
        super().submit(value)
        with self._jlock:
            self.journal.append({"event": "submit", "t_mono_ns": t, "value_sha16": sha16(value),
                                 "value_len": len(value)})

    def reset(self) -> None:
        t = now()
        super().reset()
        with self._jlock:
            self.journal.append({"event": "reset", "t_mono_ns": t})

    def drain(self) -> list[dict[str, Any]]:
        with self._jlock:
            out, self.journal = self.journal, []
        return out


class Fixtures:
    def __init__(self) -> None:
        self.fill = FixtureServer(("127.0.0.1", 0))
        self.fill.state = FillJournalState()
        self.i24 = JournalServer()
        for server in (self.fill, self.i24):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.fill_url = f"http://127.0.0.1:{self.fill.server_port}/"
        self.i24_origin = f"http://127.0.0.1:{self.i24.server_port}/"

    def state(self, cls: str) -> Any:
        return self.fill.state if cls == "fill" else self.i24.state

    def page_url(self, cls: str) -> str:
        return self.fill_url if cls == "fill" else self.i24_origin + ("toggle-confirm" if cls == "toggle" else "modal")

    def oracle_ok_direct(self, cls: str, token: str) -> bool:
        snap = self.state(cls).snapshot()
        if cls == "fill":
            return snap.get("submitted") == token
        return oracle_ok("toggle-confirm" if cls == "toggle" else "modal", snap, token)

    def close(self) -> None:
        for server in (self.fill, self.i24):
            server.shutdown()
            server.server_close()


@contextmanager
def duplicate_submit_page(enabled: bool):
    if not enabled:
        yield
        return
    with patch.object(jev_fixture_server, "PAGE", jev_fixture_server.PAGE + DUPLICATE_SUBMIT_ON_INPUT):
        yield


class OraclePoller:
    """Independent 2 ms re-read of the server state (no HTTP, no runner involvement)."""

    def __init__(self, fixtures: Fixtures, cls: str, token: str) -> None:
        self.fixtures, self.cls, self.token = fixtures, cls, token
        self.first_ok_ns: int | None = None
        self.reads = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            ok = self.fixtures.oracle_ok_direct(self.cls, self.token)
            t = now()
            self.reads += 1
            if ok:
                self.first_ok_ns = t
                return
            self._stop.wait(0.002)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


class Recorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, name: str, **fields: Any) -> None:
        self.events.append({"event": name, "t_mono_ns": now(), **fields})


async def timed_call(rec: Recorder, driver: Driver, label: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    rec.add("call_send", label=label, tool=tool)
    try:
        result = await driver.call(tool, args)
    except Exception as error:  # retained, never retried
        rec.add("call_return", label=label, tool=tool, ok=False, error=type(error).__name__,
                code=getattr(error, "code", None))
        raise
    rec.add("call_return", label=label, tool=tool, ok=True, route=result.get("route"),
            effect=result.get("effect"), status=result.get("status"))
    return result


def oracle_read(rec: Recorder, task: Any, label: str, steps: int) -> str:
    rec.add("oracle_send", label=label)
    outcome = task.classify(task.read_oracle(), steps=steps)
    rec.add("oracle_return", label=label, outcome=outcome)
    return outcome


def make_task(cls: str, token: str, fixtures: Fixtures) -> Any:
    if cls == "fill":
        return FixtureFormTask(token, fixtures.fill_url, 4)
    if cls == "toggle":
        return ToggleConfirmTask(token, fixtures.i24_origin, 4)
    return ModalTask(token, fixtures.i24_origin, 4)


def completion_mutations(cls: str, journal: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if cls == "fill":
        return [e for e in journal if e["event"] == "submit"]
    key = "checked" if cls == "toggle" else "modal"
    return [e for e in journal if e["event"] == "update" and key in e.get("fields", {})]


async def run_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Fixtures, trace_path: Path | None,
                    rec: Recorder, result: dict[str, Any]) -> None:
    cls, kind, arm = spec["cls"], spec["kind"], ARMS[spec["arm"]]
    token = f"jev-{uuid.uuid4().hex}{uuid.uuid4().hex}"[:64] if kind == "t0_stress" else f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-b01-{uuid.uuid4().hex[:8]}"
    task = make_task(cls, token, fixtures)
    result.update({"token_sha16": sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "routes": [], "tools": [], "input_routes": [], "candidates": []})
    task.reset()
    fixtures.state(cls).drain()
    poller = OraclePoller(fixtures, cls, token)
    result["_poller"] = poller
    env = driver_environment()
    env.pop(TRACE_ENV, None)
    env.pop(KNOB_ENV, None)
    if trace_path is not None:
        env[TRACE_ENV] = str(trace_path)
    if arm.knob_zero and cls == "fill":
        env[KNOB_ENV] = "0"
    result["driver_env_trace_set"] = TRACE_ENV in env
    result["driver_env_knob"] = env.get(KNOB_ENV)
    rec.add("trial_start", cls=cls, arm=spec["arm"], kind=kind)
    CLIENT["rec"] = rec
    CLIENT["compiled"] = None
    params = StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            if arm.compiled_validator:
                rec.add("compile_validators_start")
                result["compiled_validators"] = compile_output_validators(session)
                rec.add("compile_validators_end")
            available = {tool.name for tool in tools}
            capture_bound = supports_capture_bound_click(tools)
            driver = Driver(session, label)
            await timed_call(rec, driver, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm.cursor})
            motion = await timed_call(rec, driver, "cursor_motion", "set_agent_cursor_motion",
                                      FAST_MOTION if arm.fast_glide else DEFAULT_MOTION)
            result["motion_ack"] = {k: motion.get(k) for k in ("glide_duration_ms", "dwell_after_click_ms")
                                    if isinstance(motion, dict)}
            prepared = await timed_call(rec, driver, "prepare", "browser_prepare",
                                        {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            result["prepared_pid"] = pid
            window = await wait_for_window(driver, pid)
            rec.add("window_ready")
            bound = await timed_call(rec, driver, "bind", "get_browser_state",
                                     {"pid": pid, "window_id": window["window_id"]})
            target_id = bound["target_id"]
            tab_id = select_tab_id(bound["tabs"])
            await timed_call(rec, driver, "navigate", "browser_navigate",
                             {"target_id": target_id, "tab_id": tab_id, "url": fixtures.page_url(cls)})
            poller.start()
            history: list[dict[str, Any]] = []
            pending = None
            for step in range(1, task.max_steps + 1):
                current = oracle_read(rec, task, f"pre_step{step}", step - 1)
                if current in {"verified", "refuted"}:
                    result["outcome"] = current
                    return
                snap = await timed_call(rec, driver, f"snapshot{step}", "get_browser_state",
                                        {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                if args.save_snapshots and cls != "fill":
                    out = Path(args.out) / "snapshots"
                    out.mkdir(parents=True, exist_ok=True)
                    (out / f"{cls}-step{step}.json").write_text(json.dumps(snap, indent=1, sort_keys=True))
                rec.add("cand_start", step=step)
                candidates, sources, visual_record = await task_candidates_for_step(
                    driver, task, snap, pid, int(window["window_id"]), available, capture_bound,
                    visual_mode="auto")
                rec.add("cand_done", step=step, ids=[c.id for c in candidates],
                        visual=visual_record.get("status") if isinstance(visual_record, dict) else None)
                candidate = None
                guard_tel = None
                if arm.guard and pending is not None:
                    rec.add("guard_start", step=step)
                    resolution = resolve_guarded_completion(pending, task, sources, candidates, session=label)
                    candidate, guard_tel = resolution.candidate, resolution.telemetry
                    pending = None
                    rec.add("guard_done", step=step, status=guard_tel.get("status"), reason=guard_tel.get("reason"))
                if candidate is not None:
                    route = "guarded-completion"
                else:
                    rec.add("decide_start", step=step)
                    choice, _confidence, _probabilities = choose_mock_for_task(task, sources, candidates, history)
                    rec.add("decided", step=step, choice=choice)
                    if choice is None:
                        result["outcome"] = "abstained"
                        return
                    candidate = validate_choice(choice, candidates, current_capture_id=None)
                    route = "provider"
                next_plan = (plan_guarded_completion(task, sources, candidate, session=label)
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
                if kind == "stale_ref" and step == 2:
                    await timed_call(rec, driver, "renavigate", "browser_navigate",
                                     {"target_id": target_id, "tab_id": tab_id, "url": fixtures.page_url(cls)})
                    rec.add("call_send", label="stale_click", tool=candidate.tool)
                    raw = await session.call_tool(candidate.tool, {**candidate.arguments, "session": label})
                    structured = raw.structuredContent if isinstance(raw.structuredContent, dict) else {}
                    rec.add("call_return", label="stale_click", tool=candidate.tool, is_error=bool(raw.isError),
                            status=structured.get("status"), effect=structured.get("effect"))
                    result["stale_envelope"] = structured
                    result["stale_is_error"] = bool(raw.isError)
                    await asyncio.sleep(1.0)
                    result["outcome"] = oracle_read(rec, task, "stale_check", step)
                    return
                try:
                    await timed_call(rec, driver, f"action{step}", candidate.tool, dict(candidate.arguments))
                except Exception as error:
                    result["outcome"] = "unknown"
                    result["action_error"] = {"type": type(error).__name__, "code": getattr(error, "code", None)}
                    return
                pending = next_plan
                history.append(task.history_entry(step, candidate.id))
                if kind == "first_only" and step == 1:
                    await asyncio.sleep(1.0)
                    result["outcome"] = oracle_read(rec, task, "first_only_check", step)
                    return
                if candidate.id in task.completion_candidate_ids:
                    polls = int(round(POLL_DEADLINE_S * 1000 / arm.poll_ms))
                    for i in range(polls):
                        outcome = oracle_read(rec, task, f"verify{i}", step)
                        if outcome in {"verified", "refuted"}:
                            result["outcome"] = outcome
                            result["poll_reads"] = i + 1
                            return
                        rec.add("sleep_start", poll_ms=arm.poll_ms)
                        await asyncio.sleep(arm.poll_ms / 1000)
                        rec.add("sleep_end")
            result["outcome"] = task.classify(task.read_oracle(), steps=task.max_steps)


def pid_alive(pid: int | None) -> bool | None:
    if not pid:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def one(spec: dict[str, Any], args: argparse.Namespace, fixtures: Fixtures, out: Path) -> dict[str, Any]:
    name = spec["name"]
    trace_rel = None if args.plan == "smoke" else f"trials/{name}.driver-trace.jsonl"
    trace_path = None if trace_rel is None else out / trace_rel
    (out / "trials").mkdir(parents=True, exist_ok=True)
    rec = Recorder()
    record: dict[str, Any] = {"trial": name, **{k: spec[k] for k in ("cls", "arm", "kind", "block")},
                              "round": spec.get("round"), "loadavg_before": loadavg(), "driver_trace": trace_rel,
                              "lock_mode": spec.get("lock_mode")}
    res: dict[str, Any] = {}
    t0 = now()
    with duplicate_submit_page(spec["kind"] == "guard_decline"):
        try:
            await asyncio.wait_for(run_trial(spec, args, fixtures, trace_path, rec, res), timeout=180)
        except Exception as error:
            res["outcome"] = "error"
            res["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    record["trial_wall_ns"] = now() - t0
    CLIENT["rec"] = None
    CLIENT["compiled"] = None
    poller = res.pop("_poller", None)
    if poller is not None:
        # Let a late effect land before the independent read loop gives up.
        deadline = time.monotonic() + 2.5
        while poller.first_ok_ns is None and time.monotonic() < deadline and poller._thread.is_alive():
            await asyncio.sleep(0.01)
        poller.stop()
        record["poller_first_ok_ns"] = poller.first_ok_ns
        record["poller_reads"] = poller.reads
    pid = res.pop("prepared_pid", None)
    alive = pid_alive(pid)
    for _ in range(50):
        if not alive:
            break
        await asyncio.sleep(0.1)
        alive = pid_alive(pid)
    record["browser_alive_after_close"] = alive
    await asyncio.sleep(0.3)
    cls = spec["cls"]
    final_state = fixtures.state(cls).snapshot()
    journal = fixtures.state(cls).drain()
    record.update(res)
    record["journal"] = journal
    if cls == "fill":
        record["final_state"] = {"submitted_sha16": sha16(final_state.get("submitted")),
                                 "submitted_len": None if final_state.get("submitted") is None
                                 else len(final_state["submitted"])}
        record["oracle_exact_match"] = final_state.get("submitted") is not None and \
            sha16(final_state["submitted"]) == res.get("token_sha16") and \
            len(final_state["submitted"]) == res.get("token_len")
    else:
        record["final_state"] = {k: final_state.get(k) for k in ("checked", "opened", "modal")}
        record["oracle_exact_match"] = oracle_ok("toggle-confirm" if cls == "toggle" else "modal", final_state, "")
    record["completion_mutations"] = len(completion_mutations(cls, journal))
    record["network"] = dict(NETWORK)
    record["loadavg_after"] = loadavg()
    with (out / f"trials/{name}.jsonl").open("w") as f:
        for ev in rec.events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: record.get(k) for k in ("trial", "outcome", "oracle_exact_match", "completion_mutations",
                                                  "routes", "loadavg_before")}), flush=True)
    return record


def build_plan(kind: str, rounds: int, t0_pairs: int) -> list[list[dict[str, Any]]]:
    """Return blocks: list of (lock_mode, trials)."""
    blocks: list[list[dict[str, Any]]] = []
    if kind == "smoke":
        return [[{"cls": "fill", "arm": "K0", "kind": "measured", "block": "smoke", "lock_mode": "none"}
                 for _ in range(5)]]
    if kind == "shakedown":
        trials = []
        for cls in CLASSES:
            for arm in CLASS_ARMS[cls]:
                trials.append({"cls": cls, "arm": arm, "kind": "measured", "block": "shake", "lock_mode": "none"})
        trials.append({"cls": "fill", "arm": "K2", "kind": "stale_ref", "block": "shake", "lock_mode": "none"})
        trials.append({"cls": "toggle", "arm": "K2", "kind": "stale_ref", "block": "shake", "lock_mode": "none"})
        trials.append({"cls": "modal", "arm": "K2", "kind": "first_only", "block": "shake", "lock_mode": "none"})
        trials.append({"cls": "fill", "arm": "K3", "kind": "t0_stress", "block": "shake", "lock_mode": "none"})
        trials.append({"cls": "fill", "arm": "K0", "kind": "guard_decline", "block": "shake", "lock_mode": "none"})
        trials.append({"cls": "toggle", "arm": "K5", "kind": "measured", "block": "shake", "lock_mode": "none"})
        trials.append({"cls": "fill", "arm": "K5", "kind": "measured", "block": "shake", "lock_mode": "none"})
        return [trials]
    if kind == "measured":
        squares = {cls: williams(len(CLASS_ARMS[cls])) for cls in CLASSES}
        trials = []
        for r in range(rounds):
            order = CLASSES[r % 3:] + CLASSES[:r % 3]
            for cls in order:
                row = squares[cls][r % len(squares[cls])]
                for j in row:
                    trials.append({"cls": cls, "arm": CLASS_ARMS[cls][j], "kind": "measured", "block": "m",
                                   "round": r, "lock_mode": "exclusive"})
        for k in range(rounds):
            for cls in CLASSES[k % 3:] + CLASSES[:k % 3]:
                for arm in (("K4", "K5") if k % 2 == 0 else ("K5", "K4")):
                    trials.append({"cls": cls, "arm": arm, "kind": "measured", "block": "v", "round": k,
                                   "lock_mode": "exclusive"})
        for k in range(t0_pairs):
            pair = ("K3", "K2") if k % 2 == 0 else ("K2", "K3")
            for arm in pair:
                trials.append({"cls": "fill", "arm": arm, "kind": "t0_stress", "block": "t", "round": k,
                               "lock_mode": "exclusive"})
        blocks.append(trials)
        return blocks
    if kind == "controls":
        trials = []
        for cls in CLASSES:
            for arm in CLASS_ARMS[cls]:
                for _ in range(2):
                    trials.append({"cls": cls, "arm": arm, "kind": "stale_ref"})
        for cls in CLASSES:
            for arm in ("K0", "K4"):
                trials.append({"cls": cls, "arm": arm, "kind": "first_only"})
        for arm in ("K0", "K4", "K0", "K4", "K0", "K4"):
            trials.append({"cls": "fill", "arm": arm, "kind": "guard_decline"})
        # Interleave kinds/classes deterministically, then cut into shared-lock blocks of <= 10.
        trials = trials[0::3] + trials[1::3] + trials[2::3]
        for i in range(0, len(trials), 10):
            chunk = trials[i:i + 10]
            for t in chunk:
                t.update({"block": f"c{i // 10}", "lock_mode": "shared"})
            blocks.append(chunk)
        return blocks
    raise ValueError(kind)


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    fixtures = Fixtures()
    blocks = build_plan(args.plan, args.rounds, args.t0_pairs)
    idx = 0
    for block in blocks:
        for spec in block:
            spec["name"] = f"{spec['block']}{idx:03d}-{spec['cls']}-{spec['arm']}-{spec['kind']}"
            idx += 1
    manifest: dict[str, Any] = {"plan_kind": args.plan, "blocks": [[s["name"] for s in b] for b in blocks],
                                "started_mono_ns": now(), "loadavg_start": loadavg(), "locks": [],
                                "provider": "mock", "rounds": args.rounds, "t0_pairs": args.t0_pairs}
    try:
        for block in blocks:
            mode = block[0]["lock_mode"]
            fd = None
            if mode in ("exclusive", "shared") and args.lock:
                fd = os.open(args.lock, os.O_RDONLY | os.O_CREAT, 0o644)
                t_req = now()
                fcntl.flock(fd, fcntl.LOCK_EX if mode == "exclusive" else fcntl.LOCK_SH)
                manifest["locks"].append({"event": "lock_acquired", "mode": mode, "t_request_ns": t_req,
                                          "t_mono_ns": now(), "first": block[0]["name"]})
                print(json.dumps({"event": "lock_acquired", "mode": mode}), flush=True)
            elif mode in ("exclusive", "shared"):
                raise SystemExit("refusing: this plan needs --lock")
            try:
                for spec in block:
                    await one(spec, args, fixtures, out)
            finally:
                if fd is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    manifest["locks"].append({"event": "lock_released", "mode": mode, "t_mono_ns": now(),
                                              "last": block[-1]["name"]})
                    print(json.dumps({"event": "lock_released", "mode": mode}), flush=True)
    finally:
        manifest["ended_mono_ns"] = now()
        manifest["loadavg_end"] = loadavg()
        manifest["network"] = dict(NETWORK)
        (out / f"run-manifest-{args.plan}.json").write_text(json.dumps(manifest, indent=1))
        fixtures.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", choices=("shakedown", "measured", "controls", "smoke"), required=True)
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--t0-pairs", type=int, default=20)
    p.add_argument("--lock")
    p.add_argument("--save-snapshots", action="store_true")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (TRACE_ENV, KNOB_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

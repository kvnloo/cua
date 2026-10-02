"""kvnloo/cua#107 lane CSHADOW runner (measurement only, mock chooser, 0 provider HTTP).

Run one block per invocation, inside the private X11 session, under hostless,
under the quiet-lane lock:

    quiet-timed <label> hostless cua-x11-session.sh \\
        <jev-use>/.venv/bin/python run_cshadow.py --driver <bin> --out <dir> \\
        --plan {smoke|overhead|idle|fidelity|controls|resident} [--condition W-...] [--pairs N] ...

Each trial mirrors jev-use ``python/run.py`` and reuses its functions (as B-01
did): a fresh ``cua-driver mcp`` process, ``set_agent_cursor_enabled
{enabled:false}`` (feedback OFF in every arm), ``browser_prepare``
isolated_new, ``wait_for_window``, bind, navigate, then the run.py step loop
(oracle read, one full ``semantic_v2`` snapshot, ``task_candidates_for_step``,
``choose_mock_for_task``, ``validate_choice``, action) and the 20 x 100 ms
completion poll. No ``--guarded-completion`` (arm D is lane AB's). Both sides
of every comparison use this lane's one binary; the arms differ only in
``CUA_DRIVER_EXP_I107_MIRROR`` (unset = A, ``shadow`` = C_shadow_M,
``shadow_audit`` = C_shadow_audit), which the jev-use environment forwarding
passes because of its ``CUA_DRIVER_`` prefix. The phase trace is ON in every
arm. An independent thread re-reads the fixture state every 2 ms; the fixture
journals mutations on CLOCK_MONOTONIC. The runner's outcome is logged but is
not the oracle. Output paths are relative to --out.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("JEV_USE_DIR") or HERE.parents[2] / "libs/cua-driver/examples/jev-use").resolve()
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
            raise ConnectionRefusedError("CSHADOW runner: non-loopback network is disabled (mock chooser)")


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

from core import validate_choice  # noqa: E402
from cshadow_fixture import CshadowServer  # noqa: E402
from driver_env import driver_environment  # noqa: E402
from jev_adapter import choose_mock_for_task  # noqa: E402
from run import (  # noqa: E402
    Driver,
    select_tab_id,
    supports_capture_bound_click,
    task_candidates_for_step,
    wait_for_window,
)
from tasks import FixtureFormTask  # noqa: E402

TRACE_ENV = "CUA_DRIVER_PHASE_TRACE_FILE"
MIRROR_ENV = "CUA_DRIVER_EXP_I107_MIRROR"
FAULT_ENV = "CUA_DRIVER_EXP_I107_MIRROR_FAULT"
KNOB_ENV = "CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS"
ARMS = {"A": None, "C_shadow_M": "shadow", "C_shadow_audit": "shadow_audit"}
SEED = 20261002
CONDITIONS = {
    "W-quiet": ("quiet", ""),
    "W-churn": ("churn", f"?seed={SEED}"),
    "W-static": ("static", f"?seed={SEED}&churn=0"),
    "W-idle-quiet": ("quiet", ""),
    "W-idle-churn": ("churn", f"?seed={SEED}"),
}
IDLE_S = 20.0
POLL_READS, POLL_MS = 20, 100  # run.py completion poll
CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")

# Dependency controls for this lane (PREREG dependency_controls; arms A + C_shadow_audit
# on the lane binary; D belongs to lane AB). point: after_type | check_to_dispatch |
# during_bootstrap | during_audit | special.
CONTROLS: dict[str, dict[str, Any]] = {
    "DC01": {"variant": "control", "op": {"kind": "set_value", "value": "other-value"}, "point": "after_type"},
    "DC02": {"variant": "churn", "op": None, "point": None},
    "DC03": {"variant": "control", "op": {"kind": "insert_competing_submit"}, "point": "after_type"},
    "DC04": {"variant": "control", "op": {"kind": "remove_submit"}, "point": "after_type"},
    "DC05a": {"variant": "control", "op": {"kind": "replace_submit_same_form"}, "point": "after_type"},
    "DC07": {"variant": "control", "op": {"kind": "location_replace"}, "point": "check_to_dispatch"},
    "DC10": {"variant": "control", "op": None, "point": "special"},
    "DC11": {"variant": "control", "op": None, "point": "special"},
    "DC12": {"variant": "control", "op": {"kind": "hide_submit_ancestor"}, "point": "after_type"},
    "DC13": {"variant": "control", "op": {"kind": "move_submit_offscreen"}, "point": "after_type"},
    "DC14a": {"variant": "control", "op": {"kind": "overlay_submit"}, "point": "after_type"},
    "DC14b": {"variant": "control", "op": {"kind": "overlay_submit"}, "point": "check_to_dispatch"},
    "DC15": {"variant": "control", "op": {"kind": "blur_field"}, "point": "after_type"},
    "DC16a": {"variant": "control", "op": {"kind": "disable_fieldset"}, "point": "after_type"},
    "DC16b": {"variant": "control", "op": {"kind": "aria_disable_submit"}, "point": "after_type"},
    "DC17a": {"variant": "control", "op": {"kind": "set_value", "value": "property-only"}, "point": "after_type"},
    "DC17b": {"variant": "control", "op": {"kind": "css_before_name"}, "point": "after_type"},
    "DC19a": {"variant": "churn_control", "op": {"kind": "burst", "count": 400}, "point": "during_bootstrap"},
    "DC19b": {"variant": "churn_control", "op": {"kind": "burst", "count": 400}, "point": "during_audit"},
}
DC18_FAULTS = ["drop:7", "dup:7", "delay:7:200", "swap:7", "early", "foreign:7", "stale:7",
               "overflow:50", "reconnect:50"]


def now() -> int:
    return time.monotonic_ns()


def sha16(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


def read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def pressure() -> dict[str, Any]:
    return {"loadavg": read("/proc/loadavg").strip(), "psi_cpu": read("/proc/pressure/cpu").strip(),
            "psi_memory": read("/proc/pressure/memory").strip()}


# ── process accounting (only this runner's own descendants) ────────────────────

def proc_table() -> dict[int, tuple[int, str]]:
    table: dict[int, tuple[int, str]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        stat = read(f"/proc/{entry}/stat")
        if not stat:
            continue
        rest = stat[stat.rindex(")") + 2:].split()
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        table[int(entry)] = (int(rest[1]), comm)
    return table


def descendants(root: int, table: dict[int, tuple[int, str]]) -> list[int]:
    out, frontier = [], [root]
    while frontier:
        parent = frontier.pop()
        for pid, (ppid, _) in table.items():
            if ppid == parent:
                out.append(pid)
                frontier.append(pid)
    return out


def cpu_s(pid: int) -> float:
    stat = read(f"/proc/{pid}/stat")
    if not stat:
        return 0.0
    rest = stat[stat.rindex(")") + 2:].split()
    return (int(rest[11]) + int(rest[12])) / CLK_TCK


def status_kib(pid: int, key: str) -> int:
    for line in read(f"/proc/{pid}/status").splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1])
    return 0


def resources(driver_pid: int | None, browser_pid: int | None) -> dict[str, Any]:
    table = proc_table()
    out: dict[str, Any] = {"t_mono_ns": now()}
    if driver_pid:
        out["driver_pid"] = driver_pid
        out["driver_cpu_s"] = cpu_s(driver_pid)
        out["driver_vmhwm_kib"] = status_kib(driver_pid, "VmHWM")
        out["driver_vmrss_kib"] = status_kib(driver_pid, "VmRSS")
        out["driver_vmswap_kib"] = status_kib(driver_pid, "VmSwap")  # reclaim under host memory pressure
    if browser_pid:
        tree = [browser_pid] + descendants(browser_pid, table)
        out["browser_tree_pids"] = len(tree)
        out["browser_tree_cpu_s"] = sum(cpu_s(p) for p in tree)
        out["browser_tree_rss_kib"] = sum(status_kib(p, "VmRSS") for p in tree)
        out["browser_tree_swap_kib"] = sum(status_kib(p, "VmSwap") for p in tree)
    return out


def own_driver_pid(driver_bin: str) -> int | None:
    me = os.getpid()
    table = proc_table()
    target = os.path.realpath(driver_bin)
    # The MCP server is this runner's direct child; helper processes re-exec the same binary.
    for pid in sorted(p for p in descendants(me, table) if table[p][0] == me):
        try:
            if os.path.realpath(f"/proc/{pid}/exe") == target:
                return pid
        except OSError:
            continue
    return None


def kill_own_renderers(browser_pid: int, driver_pid: int) -> dict[str, Any]:
    """DC11: SIGKILL renderer processes only after proving descent from this runner."""
    table = proc_table()
    me = os.getpid()
    killed, proofs = [], []
    for pid in descendants(browser_pid, table):
        if "--type=renderer" not in read(f"/proc/{pid}/cmdline").replace("\0", " "):
            continue
        chain, cursor = [], pid
        while cursor and cursor != 1 and len(chain) < 64:
            chain.append(cursor)
            if cursor == me:
                break
            cursor = table.get(cursor, (0, ""))[0]
        proven = me in chain and driver_pid in chain and browser_pid in chain
        proofs.append({"pid": pid, "chain_len": len(chain), "proven": proven})
        if proven:
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
    return {"killed": len(killed), "proofs": proofs, "proven_all": all(p["proven"] for p in proofs) and bool(proofs)}


class OraclePoller:
    """Independent 2 ms re-read of the fixture state (no HTTP, no runner involvement)."""

    def __init__(self, server: CshadowServer, token: str) -> None:
        self.server, self.token = server, token
        self.first_ok_ns: int | None = None
        self.reads = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            snap = self.server.state.snapshot()
            t = now()
            self.reads += 1
            if snap.get("submitted") == self.token and snap.get("form") == "main":
                self.first_ok_ns = t
                return
            self._stop.wait(0.002)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:  # idle/resident trials never start the poller
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


async def send_op(rec: Recorder, server: CshadowServer, op: dict[str, Any], wait_ack: bool = True) -> dict[str, Any]:
    op = {"id": f"op-{uuid.uuid4().hex[:10]}", **op}
    rec.add("op_send", op_id=op["id"], kind=op["kind"])
    listeners = server.state.send_op(op)
    ack = None
    if wait_ack:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and ack is None:
            with server.state._lock:
                ack = next((e for e in server.state.journal if e.get("event") == "ack" and e.get("id") == op["id"]), None)
            if ack is None:
                await asyncio.sleep(0.002)
    rec.add("op_ack", op_id=op["id"], listeners=listeners, acked=ack is not None, ok=None if ack is None else ack.get("ok"))
    return op


async def run_task(driver: Driver, session: ClientSession, rec: Recorder, server: CshadowServer, task: Any,
                   target_id: str, tab_id: str, pid: int, window: dict[str, Any], available: set[str],
                   capture_bound: bool, result: dict[str, Any], control: dict[str, Any] | None,
                   label: str, driver_pid: int | None) -> None:
    """The run.py step loop (unguarded, mock), with optional control-op injection points."""
    history: list[dict[str, Any]] = []
    for step in range(1, task.max_steps + 1):
        current = oracle_read(rec, task, f"pre_step{step}", step - 1)
        if current in {"verified", "refuted"}:
            result["outcome"] = current
            return
        point = control and control.get("point")
        concurrent = None
        if control and control.get("op") and ((point == "during_bootstrap" and step == 1)
                                              or (point == "during_audit" and step == 2)):
            concurrent = asyncio.create_task(send_op(rec, server, control["op"], wait_ack=False))
        try:
            snap = await timed_call(rec, driver, f"snapshot{step}", "get_browser_state",
                                    {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
        except Exception as error:  # a refused fresh read ends the trial; never retried or bypassed
            result["outcome"] = "unknown"
            result["snapshot_error"] = {"step": step, "type": type(error).__name__,
                                        "code": getattr(error, "code", None)}
            if concurrent is not None:
                await concurrent
            return
        if concurrent is not None:
            await concurrent
        rec.add("cand_start", step=step)
        candidates, sources, visual_record = await task_candidates_for_step(
            driver, task, snap, pid, int(window["window_id"]), available, capture_bound, visual_mode="auto")
        rec.add("cand_done", step=step, ids=[c.id for c in candidates],
                visual=visual_record.get("status") if isinstance(visual_record, dict) else None)
        if not candidates:
            result["outcome"] = "abstained"
            return
        rec.add("decide_start", step=step)
        choice, _confidence, _probabilities = choose_mock_for_task(task, sources, candidates, history)
        rec.add("decided", step=step, choice=choice)
        if choice is None:
            result["outcome"] = "abstained"
            return
        candidate = validate_choice(choice, candidates, current_capture_id=None)
        result["candidates"].append(candidate.id)
        result["tools"].append(candidate.tool)
        if candidate.id == "reobserve":
            history.append(task.history_entry(step, candidate.id))
            continue
        if candidate.id == "abstain":
            result["outcome"] = "abstained"
            return
        if control and step == 2 and point == "check_to_dispatch" and control.get("op"):
            await send_op(rec, server, control["op"])
        try:
            await timed_call(rec, driver, f"action{step}", candidate.tool, dict(candidate.arguments))
        except Exception as error:
            result["outcome"] = "unknown"
            result["action_error"] = {"type": type(error).__name__, "code": getattr(error, "code", None)}
            return
        history.append(task.history_entry(step, candidate.id))
        if control and step == 1 and point == "after_type" and control.get("op"):
            await send_op(rec, server, control["op"])
        if control and step == 1 and control.get("id") == "DC11" and driver_pid:
            result["dc11"] = kill_own_renderers(pid, driver_pid)
            rec.add("dc11_kill", **{k: v for k, v in result["dc11"].items() if k != "proofs"})
            if not result["dc11"]["proven_all"]:
                result["outcome"] = "not_run_descent_unproven"
                return
            await asyncio.sleep(0.5)
        if control and step == 1 and control.get("id") == "DC10":
            new_label = f"{label}-replaced"
            other = Driver(session, new_label)
            refusals = {}
            for tool, args in (("get_browser_state", {"target_id": target_id, "tab_id": tab_id,
                                                       "snapshot_format": "semantic_v2"}),
                               ("browser_click", {"target_id": target_id, "tab_id": tab_id,
                                                  "ref": (candidate.arguments or {}).get("ref", "p0:0"),
                                                  "input_route": "dom_event"})):
                try:
                    await other.call(tool, args)
                    refusals[tool] = "accepted"
                except Exception as error:  # expected: binding/ref stale in the new session
                    refusals[tool] = getattr(error, "code", None) or type(error).__name__
            result["dc10"] = refusals
            rec.add("dc10_done", **refusals)
        if candidate.id in task.completion_candidate_ids:
            for i in range(POLL_READS):
                outcome = oracle_read(rec, task, f"verify{i}", step)
                if outcome in {"verified", "refuted"}:
                    result["outcome"] = outcome
                    result["poll_reads"] = i + 1
                    return
                rec.add("sleep_start", poll_ms=POLL_MS)
                await asyncio.sleep(POLL_MS / 1000)
                rec.add("sleep_end")
    result["outcome"] = task.classify(task.read_oracle(), steps=task.max_steps)


async def run_trial(spec: dict[str, Any], args: argparse.Namespace, server: CshadowServer, trace_path: Path,
                    rec: Recorder, result: dict[str, Any]) -> None:
    variant, query = CONDITIONS.get(spec["condition"], (None, ""))
    control = CONTROLS.get(spec.get("control") or "")
    if control:
        variant = control["variant"]
        query = f"?seed={SEED}" if "churn" in variant else ""
        control = {**control, "id": spec["control"]}
    token = f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-cshadow-{uuid.uuid4().hex[:8]}"
    server.state.configure(variant)
    origin = server.url()
    task = FixtureFormTask(token, origin, 4)
    result.update({"token_sha16": sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "candidates": [], "tools": [], "variant": variant})
    task.reset()
    server.state.drain()
    poller = OraclePoller(server, token)
    result["_poller"] = poller
    env = driver_environment()
    for name in (TRACE_ENV, MIRROR_ENV, FAULT_ENV, KNOB_ENV):
        env.pop(name, None)
    env[TRACE_ENV] = str(trace_path)
    mirror = ARMS[spec["arm"]]
    if mirror:
        env[MIRROR_ENV] = mirror
    if spec.get("fault"):
        env[FAULT_ENV] = spec["fault"]
    result["driver_env"] = {k: env.get(k) for k in (MIRROR_ENV, FAULT_ENV, KNOB_ENV)}
    result["driver_env_trace_set"] = TRACE_ENV in env
    rec.add("trial_start", arm=spec["arm"], condition=spec["condition"], control=spec.get("control"))
    driver_bin = args.ref_driver if spec.get("driver") == "ref" else args.driver
    result["driver_kind"] = spec.get("driver") or "lane"
    params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            rec.add("driver_ready")
            driver_pid = own_driver_pid(driver_bin)
            result["driver_pid_found"] = driver_pid is not None
            tools = (await session.list_tools()).tools
            available = {tool.name for tool in tools}
            capture_bound = supports_capture_bound_click(tools)
            driver = Driver(session, label)
            await timed_call(rec, driver, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": False})
            prepared = await timed_call(rec, driver, "prepare", "browser_prepare",
                                        {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            result["prepared_pid"] = pid
            if spec["plan"] == "smoke" and args.protocol_out:
                result["protocol"] = read_endpoint_protocol(pid, Path(args.protocol_out))
            window = await wait_for_window(driver, pid)
            rec.add("window_ready")
            bound = await timed_call(rec, driver, "bind", "get_browser_state",
                                     {"pid": pid, "window_id": window["window_id"]})
            target_id = bound["target_id"]
            tab_id = select_tab_id(bound["tabs"])
            await timed_call(rec, driver, "navigate", "browser_navigate",
                             {"target_id": target_id, "tab_id": tab_id, "url": origin + query})
            rec.add("navigate_done")
            result["resources_start"] = resources(driver_pid, pid)
            if spec["plan"] == "idle":
                # One snapshot creates the mirror (C), then a 20 s interval with no tool calls.
                await timed_call(rec, driver, "idle_snapshot0", "get_browser_state",
                                 {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                await asyncio.sleep(1.0)
                result["idle_start"] = resources(driver_pid, pid)
                rec.add("idle_start")
                await asyncio.sleep(IDLE_S)
                rec.add("idle_end")
                result["idle_end"] = resources(driver_pid, pid)
                await timed_call(rec, driver, "idle_snapshot1", "get_browser_state",
                                 {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
                result["outcome"] = "idle_complete"
            elif spec["plan"] == "resident":
                outcomes = []
                for k in range(args.resident_tasks):
                    token_k = f"jev-{uuid.uuid4().hex[:10]}"
                    task_k = FixtureFormTask(token_k, origin, 4)
                    task_k.reset()
                    if k:
                        await timed_call(rec, driver, f"renavigate{k}", "browser_navigate",
                                         {"target_id": target_id, "tab_id": tab_id, "url": origin + query})
                    rec.add("resident_task_start", k=k)
                    sub: dict[str, Any] = {"candidates": [], "tools": []}
                    await run_task(driver, session, rec, server, task_k, target_id, tab_id, pid, window,
                                   available, capture_bound, sub, None, label, driver_pid)
                    rec.add("resident_task_end", k=k, outcome=sub.get("outcome"))
                    outcomes.append({"k": k, "outcome": sub.get("outcome"), "token_sha16": sha16(token_k),
                                     "oracle": server.state.snapshot().get("submitted") == token_k})
                result["resident"] = outcomes
                result["outcome"] = "resident_complete"
            else:
                poller.start()
                await run_task(driver, session, rec, server, task, target_id, tab_id, pid, window,
                               available, capture_bound, result, control, label, driver_pid)
            result["resources_end"] = resources(driver_pid, pid)


async def one(spec: dict[str, Any], args: argparse.Namespace, server: CshadowServer, out: Path) -> dict[str, Any]:
    name = spec["name"]
    (out / "trials").mkdir(parents=True, exist_ok=True)
    trace_rel = f"trials/{name}.driver-trace.jsonl"
    rec = Recorder()
    record: dict[str, Any] = {"trial": name, **{k: spec.get(k) for k in (
        "plan", "comparison", "condition", "arm", "pair", "order", "control", "fault", "block")},
        "pressure_before": pressure(), "driver_trace": trace_rel}
    res: dict[str, Any] = {}
    t0 = now()
    try:
        await asyncio.wait_for(run_trial(spec, args, server, out / trace_rel, rec, res),
                               timeout=240 if spec["plan"] in ("idle", "resident") else 120)
    except Exception as error:
        res["outcome"] = res.get("outcome") if res.get("outcome") not in (None, "unknown") else "error"
        res["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    record["lifetime_ns"] = now() - t0  # runner lifetime through stdio client exit
    poller = res.pop("_poller", None)
    if poller is not None:
        deadline = time.monotonic() + 2.5
        while poller.first_ok_ns is None and time.monotonic() < deadline and poller._thread.is_alive():
            await asyncio.sleep(0.01)
        poller.stop()
        record["poller_first_ok_ns"] = poller.first_ok_ns
        record["poller_reads"] = poller.reads
    pid = res.pop("prepared_pid", None)
    for _ in range(50):
        if not pid or not Path(f"/proc/{pid}").exists():
            break
        await asyncio.sleep(0.1)
    record["browser_alive_after_close"] = bool(pid and Path(f"/proc/{pid}").exists())
    await asyncio.sleep(0.3)
    final = server.state.snapshot()
    journal = server.state.drain()
    record.update(res)
    record["journal"] = journal
    record["final_state"] = {"submitted_sha16": sha16(final.get("submitted")), "form": final.get("form")}
    record["oracle_verified"] = final.get("submitted") is not None and sha16(final["submitted"]) == res.get(
        "token_sha16") and final.get("form") == "main"
    record["submits_main"] = sum(1 for e in journal if e["event"] == "submit" and e.get("form") == "main")
    record["submits_decoy"] = sum(1 for e in journal if e["event"] == "submit" and e.get("form") == "decoy")
    record["network"] = dict(NETWORK)
    record["pressure_after"] = pressure()
    with (out / f"trials/{name}.jsonl").open("w") as f:
        for ev in rec.events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: record.get(k) for k in ("trial", "arm", "outcome", "oracle_verified", "submits_main",
                                                  "error")}), flush=True)
    return record


def abba(arms: tuple[str, str], pairs: int, offset: int = 0) -> list[tuple[int, int, str]]:
    """Local pair indices; the AB/BA order follows the global pair id (offset + p)."""
    out = []
    for p in range(pairs):
        order = arms if (offset + p) % 2 == 0 else arms[::-1]
        for position, arm in enumerate(order):
            out.append((p, position, arm))
    return out


def build_plan(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if args.plan == "smoke":
        specs = [{"plan": "smoke", "condition": c, "arm": arm}
                 for c in ("W-quiet", "W-churn") for arm in ("A", "C_shadow_audit")]
    elif args.plan == "defaultoff":
        # Structural default-off check: the lane binary with the mirror unset vs the map binary
        # (no mirror code) vs the lane binary with the mirror on; CDP methods compared per trial.
        for r in range(args.trials):
            order = [("A", "lane"), ("A", "ref"), ("C_shadow_M", "lane")]
            for arm, drv in (order if r % 2 == 0 else order[::-1]):
                specs.append({"plan": "defaultoff", "condition": "W-quiet", "arm": arm, "driver": drv, "pair": r})
    elif args.plan in ("overhead", "idle"):
        comparison = "CMP-C-overhead" if args.plan == "overhead" else "CMP-C-idle"
        for p, position, arm in abba(("A", "C_shadow_M"), args.pairs, args.pair_offset):
            specs.append({"plan": args.plan, "comparison": comparison, "condition": args.condition,
                          "arm": arm, "pair": p + args.pair_offset, "order": position})
    elif args.plan == "fidelity":
        specs = [{"plan": "fidelity", "comparison": "CMP-C-fidelity", "condition": args.condition,
                  "arm": "C_shadow_audit", "pair": i + args.pair_offset} for i in range(args.trials)]
    elif args.plan == "controls":
        ids = args.controls.split(",") if args.controls else list(CONTROLS)
        rounds = range(args.pair_offset, args.pair_offset + args.trials)  # one round per block
        for round_ in rounds:
            for cid in ids:
                for arm in (("A", "C_shadow_audit") if round_ % 2 == 0 else ("C_shadow_audit", "A")):
                    specs.append({"plan": "controls", "control": cid, "condition": "control", "arm": arm,
                                  "pair": round_})
        if not args.controls or "DC18" in ids:
            for round_ in rounds:
                for fault in DC18_FAULTS:
                    specs.append({"plan": "controls", "control": "DC18", "fault": fault, "condition": "W-churn",
                                  "arm": "C_shadow_audit", "pair": round_})
        specs = [s for s in specs if s.get("control") != "DC18" or s.get("fault")]
    elif args.plan == "resident":
        for p, position, arm in abba(("A", "C_shadow_M"), args.pairs, args.pair_offset):
            specs.append({"plan": "resident", "comparison": "CMP-C-resident", "condition": "W-churn",
                          "arm": arm, "pair": p + args.pair_offset, "order": position})
    for i, spec in enumerate(specs):
        spec["block"] = args.block
        suffix = "-ref" if spec.get("driver") == "ref" else ""
        spec["name"] = f"{args.block}-{i:03d}-{spec['plan']}-{spec.get('control') or spec['condition']}-{spec['arm']}{suffix}"
    return specs


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    server = CshadowServer()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    specs = build_plan(args)
    manifest: dict[str, Any] = {"plan": args.plan, "block": args.block, "trials": [s["name"] for s in specs],
                                "started_mono_ns": now(), "pressure_start": pressure(), "provider": "mock",
                                "driver_sha256": sha256_file(args.driver),
                                "ref_driver_sha256": sha256_file(args.ref_driver) if args.ref_driver else None,
                                "harness_sha256": sha256_file(__file__),
                                "fixture_sha256": sha256_file(HERE / "cshadow_fixture.py"),
                                "isolation": args.preflight}
    try:
        for spec in specs:
            await one(spec, args, server, out)
    finally:
        manifest["ended_mono_ns"] = now()
        manifest["pressure_end"] = pressure()
        manifest["network"] = dict(NETWORK)
        (out / f"run-manifest-{args.block}.json").write_text(json.dumps(manifest, indent=1))
        server.close()


LANES = HERE.parents[3]  # <lanes>/<worktree>/docs/experiments/<packet>


def landlock_scope_path() -> str:
    """The landlock-scope binary hostless v2 execs (its LS= line); the path is never recorded."""
    for line in read(str(LANES / "bin/hostless")).splitlines():
        if line.startswith("LS="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""
HOST_RUNTIME_PREFIXES = ("/run/user/",)


def sha256_file(path: Any) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_endpoint_protocol(browser_pid: int, out_path: Path) -> dict[str, Any]:
    """Read /json/version and /json/protocol from this trial's own Driver-launched browser
    (loopback DevTools port from the profile's DevToolsActivePort), inside the session."""
    import http.client

    # Chrome rewrites its process title on Linux, joining argv with spaces into one string.
    args = read(f"/proc/{browser_pid}/cmdline").replace("\0", " ").split()
    profile = next((a.split("=", 1)[1] for a in args if a.startswith("--user-data-dir=")), None)
    info: dict[str, Any] = {"profile_found": profile is not None}
    if not profile:
        return info
    deadline = time.monotonic() + 5
    port_text = ""
    while time.monotonic() < deadline and not port_text:
        port_text = read(f"{profile}/DevToolsActivePort").split("\n")[0].strip()
        if not port_text:
            time.sleep(0.05)
    if not port_text.isdigit():
        info["port_found"] = False
        return info
    out: dict[str, Any] = {}
    for path in ("/json/version", "/json/protocol"):
        conn = http.client.HTTPConnection("127.0.0.1", int(port_text), timeout=5)
        conn.request("GET", path)
        out[path] = conn.getresponse().read()
        conn.close()
    version = json.loads(out["/json/version"])
    out_path.write_bytes(out["/json/protocol"])
    info.update({"port_found": True, "browser": version.get("Browser"),
                 "protocol_version": version.get("Protocol-Version"),
                 "protocol_sha256": hashlib.sha256(out["/json/protocol"]).hexdigest(),
                 "protocol_bytes": len(out["/json/protocol"])})
    return info


def ancestors(pid: int, table: dict[int, tuple[int, str]]) -> list[int]:
    chain = []
    while pid and pid != 1 and len(chain) < 128:
        chain.append(pid)
        pid = table.get(pid, (0, ""))[0]
    return chain


def socket_inodes(pid: int) -> set[str]:
    out = set()
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                link = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if link.startswith("socket:["):
                out.add(link[8:-1])
    except OSError:
        pass
    return out


def preflight() -> dict[str, Any]:
    """Orchestrator condition 2: the inner env has no host DISPLAY/WAYLAND_DISPLAY and the X
    socket in use belongs to this session's own Xvfb. Paths are reduced to placeholders."""
    env = os.environ
    table = proc_table()
    mine = set(ancestors(os.getpid(), table))
    display = env.get("DISPLAY", "")
    number = display[1:] if display.startswith(":") and display[1:].isdigit() else None
    xvfb = [pid for pid, (ppid, comm) in table.items() if comm == "Xvfb"
            and f":{number}" in read(f"/proc/{pid}/cmdline").split("\0") and ppid in mine]
    sock_path = f"/tmp/.X11-unix/X{number}"
    listening = {line.split()[6] for line in read("/proc/net/unix").splitlines()[1:]
                 if len(line.split()) >= 8 and line.split()[7] in (sock_path, "@" + sock_path)}
    owned = bool(xvfb) and bool(listening) and listening <= socket_inodes(xvfb[0])
    run_dir = Path(env.get("HOME", "")).parent
    runtime = env.get("XDG_RUNTIME_DIR", "")
    dbus = env.get("DBUS_SESSION_BUS_ADDRESS", "")
    dbus_daemons = [pid for pid, (ppid, comm) in table.items() if comm == "dbus-daemon" and ppid in mine]
    nnp = any(line.split()[-1] == "1" for line in read("/proc/self/status").splitlines()
              if line.startswith("NoNewPrivs:"))
    checks = {
        "display_is_private_number": number is not None,
        "display_not_host_x0_x2": number is not None and int(number) > 2,
        "no_wayland_vars": not any(k in env for k in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET", "SWAYSOCK", "I3SOCK"))
        and not any(k.startswith("HYPRLAND") for k in env),
        "x_socket_owned_by_session_xvfb": owned,
        "xdg_runtime_dir_in_session_run_dir": runtime.startswith(str(run_dir) + "/")
        and not runtime.startswith(HOST_RUNTIME_PREFIXES),
        "dbus_daemon_is_session_child": bool(dbus_daemons) and "/run/user/" not in dbus,
        # xvfb-run writes its own cookie file under the session's TMPDIR; a host cookie is refused.
        "xauthority_absent_or_session_own": env.get("XAUTHORITY", str(run_dir) + "/").startswith(str(run_dir) + "/"),
        "no_host_atspi_bus": "AT_SPI_BUS_ADDRESS" not in env,
        "landlock_no_new_privs": nnp,
    }
    return {
        "wrapper": "hostless v2 (<lanes>/bin/hostless)",
        "hostless_sha256": sha256_file(LANES / "bin/hostless"),
        "landlock_scope_sha256": sha256_file(landlock_scope_path()) if landlock_scope_path() else None,
        "session_script_sha256": sha256_file(LANES / "cua-x11-session.sh"),
        "session_run_dir": "<lane-tmp>/" + run_dir.name,
        "inner_display": display,
        "x_socket": f"/tmp/.X11-unix/X{number} (listening inodes owned by session Xvfb: {owned})",
        "checks": checks,
        "ok": all(checks.values()),
    }


def inside_hostless() -> bool:
    """hostless v2 runs every command under landlock-scope (no_new_privs, inherited across
    cua-x11-session.sh's env -i); hostless v1/strict runs it in a bwrap user namespace."""
    nnp = any(line.split()[-1] == "1" for line in read("/proc/self/status").splitlines()
              if line.startswith("NoNewPrivs:"))
    uid_map = read("/proc/self/uid_map").split()
    return nnp or uid_map[:3] != ["0", "0", "4294967295"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", choices=("smoke", "defaultoff", "overhead", "idle", "fidelity", "controls", "resident"),
                   required=True)
    p.add_argument("--ref-driver", default="")
    p.add_argument("--protocol-out", default="")
    p.add_argument("--block", required=True)
    p.add_argument("--condition", default="W-quiet", choices=sorted(CONDITIONS))
    p.add_argument("--pairs", type=int, default=30)
    p.add_argument("--pair-offset", type=int, default=0)
    p.add_argument("--trials", type=int, default=30)
    p.add_argument("--controls", default="")
    p.add_argument("--resident-tasks", type=int, default=10)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or not inside_hostless():
        raise SystemExit("refusing: run under hostless inside cua-x11-session.sh")
    for name in (TRACE_ENV, MIRROR_ENV, FAULT_ENV, KNOB_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    args.preflight = preflight()
    print("preflight " + json.dumps({"ok": args.preflight["ok"], "display": args.preflight["inner_display"],
                                     "run_dir": args.preflight["session_run_dir"],
                                     "checks": args.preflight["checks"]}, sort_keys=True), flush=True)
    if not args.preflight["ok"]:
        raise SystemExit("refusing: isolation pre-flight failed")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

"""kvnloo/cua#107 lane AB runner: arm A vs B_proj (measurement only, scripted chooser, 0 provider HTTP).

Adapted from B-01's run_critpath.py (kvnloo/cua 6689610d5, see the previous commit for the
verbatim copy). Kept: a fresh ``cua-driver mcp`` process + isolated_new browser per trial,
caller phases stamped with ``time.monotonic_ns()``, CUA_DRIVER_PHASE_TRACE_FILE per trial,
the 2 ms independent oracle reader, the server-side fixture journal, timed client
output-schema validation and the loopback-only socket guard. Added: set_agent_cursor_enabled
(false) before browser_prepare in every arm, arm B_proj (query on every semantic_v2 call),
wire capture (MCP line bytes + client parse time), per-step semantic facts, the W-churn /
W-static fixture variants and the DC03 / DC04 control channel, a cleanup span and cold
startup kept separate, per-trial loadavg / PSI / Driver CPU+VmHWM / browser-tree CPU+RSS
(read-only /proc), and a preflight that refuses before any Driver spawn when the Driver's
isolated-launch precondition cannot hold under the current wrapper.

Run inside the approved isolation wrapper + private X11 session + quiet-timed lock:

    JEV_USE_DIR=<jev-use> <jev-use>/.venv/bin/python run_critpath.py --driver <i107 bin> \\
        [--ref-driver <reference bin>] --out <dir> --plan <plan> --lock-label <quiet-timed label>

Output paths are relative to --out. The fixture's /state is the oracle; the runner's own
outcome is logged but is not the oracle.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
            raise ConnectionRefusedError("i107 AB runner: non-loopback network is disabled (scripted chooser)")


def _guarded_connect(self: socket.socket, address: Any) -> None:
    _check_address(self, address)
    return _orig_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
    _check_address(self, address)
    return _orig_connect_ex(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]

import mcp.client.stdio as _mcp_stdio  # noqa: E402
import mcp.types as _mcp_types  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.session import ClientSession as _McpClientSession  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

import i107ab_ledger as L  # noqa: E402
from core import validate_choice  # noqa: E402
from driver_env import driver_environment  # noqa: E402
from i107ab_fixtures import I107Server, sha16, wrong_target_submits  # noqa: E402
from jev_adapter import choose_mock_for_task  # noqa: E402
from run import Driver, select_tab_id, supports_capture_bound_click, task_candidates_for_step, wait_for_window  # noqa: E402
from tasks import FIELD_NAME, SUBMIT_NAME, FixtureFormTask  # noqa: E402

CLIENT: dict[str, Any] = {"rec": None}
_orig_validate_tool_result = _McpClientSession._validate_tool_result


async def _timed_validate_tool_result(self: Any, name: str, result: Any) -> None:
    rec = CLIENT["rec"]
    if rec is not None:
        rec.add("client_validate_start", tool=name)
    try:
        await _orig_validate_tool_result(self, name, result)
    finally:
        if rec is not None:
            rec.add("client_validate_end", tool=name)


_McpClientSession._validate_tool_result = _timed_validate_tool_result  # type: ignore[method-assign]


# ── wire capture: bytes and parse time of every MCP line the stdio client receives ──
def _record_wire(t0: int, t1: int, bytes: int) -> None:  # noqa: A002
    rec = CLIENT["rec"]
    if rec is not None:
        rec.add_at("parse_start", t0)
        rec.add_at("parse_end", t1, bytes=bytes)


class _TypesProxy:
    """mcp.types for the stdio reader only, with a recording JSONRPCMessage.model_validate_json."""

    class JSONRPCMessage:  # noqa: D106
        model_validate_json = staticmethod(L.recording_parser(_mcp_types.JSONRPCMessage.model_validate_json, _record_wire))

    def __getattr__(self, name: str) -> Any:
        return getattr(_mcp_types, name)


_mcp_stdio.types = _TypesProxy()  # type: ignore[assignment]

TRACE_ENV = "CUA_DRIVER_PHASE_TRACE_FILE"
KNOB_ENV = "CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS"
POLL_READS, POLL_MS = 20, 100  # run.py: 20 x 0.1 s
QUERY = f"{FIELD_NAME} {SUBMIT_NAME}".lower()  # 'verification value submit' from task-spec constants
PINNED = {"i107": "f3a5c01a2c1b5bce75ccb611d0bacd491a7c3b1a8c3fac65889a1fc9d6977aed",
          "ref": "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3"}
SEED_BASE = 20261002


@dataclass(frozen=True)
class Arm:
    binary: str        # "i107" | "ref"
    query: str | None
    trace: bool


# A_off: arm A on the i107 binary with the trace unset (default-off check only).
ARMS = {"A": Arm("i107", None, True), "B_proj": Arm("i107", QUERY, True), "A_ref": Arm("ref", None, False),
        "A_off": Arm("i107", None, False)}


def now() -> int:
    return time.monotonic_ns()


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def loadavg() -> str:
    try:
        return Path("/proc/loadavg").read_text().strip()
    except OSError:
        return "unavailable"


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pid_gone(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    return state[state.rindex(")") + 2:].split()[0] in ("Z", "X")


class Recorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, name: str, **fields: Any) -> None:
        self.events.append({"event": name, "t_mono_ns": now(), **fields})

    def add_at(self, name: str, t: int, **fields: Any) -> None:
        self.events.append({"event": name, "t_mono_ns": t, **fields})


class OraclePoller:
    """Independent 2 ms re-read of the server state (no HTTP, no runner involvement)."""

    def __init__(self, server: I107Server, token: str) -> None:
        self.server, self.token = server, token
        self.first_ok_ns: int | None = None
        self.reads = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            ok = self.server.state.snapshot().get("submitted") == self.token
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


def snapshot_facts(snap: dict[str, Any], token: str) -> dict[str, Any]:
    meta = snap.get("snapshot") or {}
    return {"scope": meta.get("scope"), "selected_nodes": meta.get("selected_nodes"),
            "total_nodes": meta.get("total_nodes"), "omitted": meta.get("omitted"),
            "refs": len(snap.get("refs") or []), "content_refs": len(snap.get("content_refs") or []),
            "outline_chars": len(snap.get("outline") or ""), "controls": L.logical_controls(snap, token)}


class IsolationAbort(RuntimeError):
    """The Driver-launched browser is not confined to the private session: stop the whole run."""


def browser_isolation(pid: int) -> dict[str, Any]:
    """Read-only check of the launched browser's environment against this private session."""
    try:
        env = dict(kv.split("=", 1) for kv in Path(f"/proc/{pid}/environ").read_bytes().decode("utf-8", "replace").split("\0") if "=" in kv)
    except OSError as error:
        return {"ok": False, "reason": f"environ unreadable: {type(error).__name__}"}
    checks = {"display_matches_session": env.get("DISPLAY") == os.environ.get("DISPLAY"),
              "display_not_host_0": env.get("DISPLAY") not in (":0", ":0.0", None),
              "wayland_display_absent": "WAYLAND_DISPLAY" not in env and "WAYLAND_SOCKET" not in env,
              "hyprland_absent": not any(k.startswith("HYPRLAND") for k in env),
              "runtime_dir_not_host": not str(env.get("XDG_RUNTIME_DIR", "")).startswith("/run/user/")}
    return {"ok": all(checks.values()), **checks}


def sample_resources(driver_pid: int | None, browser_pid: int | None) -> dict[str, Any]:
    out: dict[str, Any] = {"clk_tck": L.clk_tck(), "t_mono_ns": now()}
    if driver_pid:
        out["driver_cpu_ticks"] = L.cpu_ticks(driver_pid)
        out["driver_status_kb"] = L.status_kb(driver_pid)
    if browser_pid:
        out["browser_tree"] = L.tree_usage(browser_pid)
        out["browser_pids"] = sorted({browser_pid} | L.descendants(browser_pid))
    return out


async def run_trial(spec: dict[str, Any], args: argparse.Namespace, server: I107Server, trace_path: Path | None,
                    rec: Recorder, result: dict[str, Any]) -> None:
    arm = ARMS[spec["arm"]]
    control = spec.get("control")
    token = f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-i107ab-{uuid.uuid4().hex[:8]}"
    server.configure(spec["condition"], spec["seed"], control in ("DC03", "DC04"))
    fixture_url = f"http://127.0.0.1:{server.server_port}/"
    task = FixtureFormTask(token, fixture_url, 4)
    result.update({"token_sha16": sha16(token), "token_len": len(token), "outcome": "unknown", "routes": [],
                   "tools": [], "input_routes": [], "candidates": [], "steps": []})
    task.reset()
    server.state.drain()
    poller = OraclePoller(server, token)
    result["_poller"] = poller
    env = driver_environment()
    env.pop(TRACE_ENV, None)
    env.pop(KNOB_ENV, None)
    if trace_path is not None:
        env[TRACE_ENV] = str(trace_path)
    result["driver_env_trace_set"] = TRACE_ENV in env
    result["driver_env_knob"] = env.get(KNOB_ENV)
    driver_bin = args.driver if arm.binary == "i107" else args.ref_driver
    rec.add("trial_start", arm=spec["arm"], condition=spec["condition"], control=control)
    CLIENT["rec"] = rec
    params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
    rec.add("driver_spawn")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            driver_pids = L.children_with_argv0(os.getpid(), driver_bin)
            result["_driver_pid"] = driver_pids[-1] if driver_pids else None
            result["driver_pid_found"] = bool(driver_pids)
            tools = (await session.list_tools()).tools
            available = {tool.name for tool in tools}
            capture_bound = supports_capture_bound_click(tools)
            driver = Driver(session, label)
            try:
                await timed_call(rec, driver, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": False})
                prepared = await timed_call(rec, driver, "prepare", "browser_prepare",
                                            {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                pid = int(prepared["prepared_pid"])
                result["_browser_pid"] = pid
                iso = browser_isolation(pid)
                result["browser_isolation"] = iso
                if not iso["ok"]:
                    raise IsolationAbort(json.dumps(iso))
                window = await wait_for_window(driver, pid)
                rec.add("window_ready")
                bound = await timed_call(rec, driver, "bind", "get_browser_state",
                                         {"pid": pid, "window_id": window["window_id"]})
                target_id = bound["target_id"]
                tab_id = select_tab_id(bound["tabs"])
                await timed_call(rec, driver, "navigate", "browser_navigate",
                                 {"target_id": target_id, "tab_id": tab_id, "url": fixture_url})
                rec.add("startup_done")
                poller.start()
                await step_loop(spec, arm, server, task, driver, session, rec, result, label, pid, window,
                                target_id, tab_id, fixture_url, available, capture_bound)
            finally:
                rec.add("outcome_decided", outcome=result.get("outcome"))
                result["resources_at_outcome"] = sample_resources(result.get("_driver_pid"), result.get("_browser_pid"))
    rec.add("client_exited")


async def step_loop(spec: dict[str, Any], arm: Arm, server: I107Server, task: Any, driver: Driver, session: Any,
                    rec: Recorder, result: dict[str, Any], label: str, pid: int, window: dict[str, Any],
                    target_id: str, tab_id: str, fixture_url: str, available: set[str], capture_bound: bool) -> None:
    control = spec.get("control")
    history: list[dict[str, Any]] = []
    snap_args: dict[str, Any] = {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"}
    if arm.query is not None:
        snap_args["query"] = arm.query
    for step in range(1, task.max_steps + 1):
        current = oracle_read(rec, task, f"pre_step{step}", step - 1)
        if current in {"verified", "refuted"}:
            result["outcome"] = current
            return
        snap = await timed_call(rec, driver, f"snapshot{step}", "get_browser_state", dict(snap_args))
        rec.add("cand_start", step=step)
        candidates, sources, visual_record = await task_candidates_for_step(
            driver, task, snap, pid, int(window["window_id"]), available, capture_bound, visual_mode="auto")
        rec.add("cand_done", step=step, ids=[c.id for c in candidates],
                visual=visual_record.get("status") if isinstance(visual_record, dict) else None)
        result["steps"].append({"step": step, "candidates": [c.id for c in candidates],
                                **snapshot_facts(snap, task.token)})
        rec.add("decide_start", step=step)
        choice, _confidence, _probabilities = choose_mock_for_task(task, sources, candidates, history)
        rec.add("decided", step=step, choice=choice)
        if choice is None:
            result["outcome"] = "abstained"
            return
        candidate = validate_choice(choice, candidates, current_capture_id=None)
        result["routes"].append("provider")
        result["candidates"].append(candidate.id)
        result["tools"].append(candidate.tool)
        result["input_routes"].append((candidate.arguments or {}).get("input_route"))
        rec.add("routed", step=step, candidate=candidate.id, tool=candidate.tool)
        if candidate.id == "reobserve":
            history.append(task.history_entry(step, candidate.id))
            continue
        if candidate.id == "abstain":
            result["outcome"] = "abstained"
            return
        if control == "stale_ref" and step == 2:
            await timed_call(rec, driver, "renavigate", "browser_navigate",
                             {"target_id": target_id, "tab_id": tab_id, "url": fixture_url})
            rec.add("call_send", label="stale_click", tool=candidate.tool)
            raw = await session.call_tool(candidate.tool, {**candidate.arguments, "session": label})
            structured = raw.structuredContent if isinstance(raw.structuredContent, dict) else {}
            rec.add("call_return", label="stale_click", tool=candidate.tool, is_error=bool(raw.isError),
                    status=structured.get("status"), effect=structured.get("effect"))
            refusal = structured.get("refusal") if isinstance(structured.get("refusal"), dict) else {}
            result["stale_envelope"] = {"status": structured.get("status"), "code": refusal.get("code"),
                                        "is_error": bool(raw.isError)}
            await asyncio.sleep(1.0)
            result["outcome"] = oracle_read(rec, task, "stale_check", step)
            return
        try:
            await timed_call(rec, driver, f"action{step}", candidate.tool, dict(candidate.arguments))
        except Exception as error:
            result["outcome"] = "unknown"
            result["action_error"] = {"type": type(error).__name__, "code": getattr(error, "code", None)}
            return
        history.append(task.history_entry(step, candidate.id))
        if control in ("DC03", "DC04") and step == 1:
            op_id = server.bus.post(control)
            rec.add("control_post", op=control)
            acked = await asyncio.to_thread(server.bus.wait_ack, op_id, 2.0)
            rec.add("control_ack" if acked else "control_ack_missing", op=control)
            result["control_applied"] = acked
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


async def one(spec: dict[str, Any], args: argparse.Namespace, server: I107Server, out: Path) -> dict[str, Any]:
    name = spec["name"]
    arm = ARMS[spec["arm"]]
    trace_rel = f"trials/{name}.driver-trace.jsonl" if arm.trace else None
    trace_path = None if trace_rel is None else out / trace_rel
    rec = Recorder()
    record: dict[str, Any] = {"trial": name, **{k: spec.get(k) for k in (
        "plan", "arm", "condition", "pair", "order", "control", "seed", "excluded", "block")},
        "cohort": "K1", "regime": "fresh-per-trial", "binary": arm.binary,
        "binary_sha256": args.shas[arm.binary], "query": arm.query, "lock_label": args.lock_label,
        "loadavg_before": loadavg(), "psi_before": L.pressure(), "utc_start": utc(), "driver_trace": trace_rel}
    res: dict[str, Any] = {}
    t0 = now()
    try:
        await asyncio.wait_for(run_trial(spec, args, server, trace_path, rec, res), timeout=180)
    except asyncio.TimeoutError:
        res["outcome"] = "timeout"
    except IsolationAbort as error:
        res["outcome"] = "error"
        res["error"] = f"IsolationAbort: {error}"
        res["isolation_abort"] = True
    except Exception as error:
        res["outcome"] = res.get("outcome") if res.get("outcome") not in (None, "unknown") else "error"
        res["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    CLIENT["rec"] = None
    # Cleanup span end: every process of the Driver-launched browser tree gone (20 ms polls, <= 10 s).
    pids = (res.get("resources_at_outcome") or {}).get("browser_pids") or (
        [res["_browser_pid"]] if res.get("_browser_pid") else [])
    deadline = time.monotonic() + 10
    while pids and not all(pid_gone(p) for p in pids) and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    rec.add("browser_gone", ok=all(pid_gone(p) for p in pids) if pids else None, pids=len(pids))
    record["trial_wall_ns"] = now() - t0
    poller = res.pop("_poller", None)
    if poller is not None:
        deadline = time.monotonic() + 2.5
        while poller.first_ok_ns is None and time.monotonic() < deadline and poller._thread.is_alive():
            await asyncio.sleep(0.01)
        poller.stop()
        record["poller_first_ok_ns"] = poller.first_ok_ns
        record["poller_reads"] = poller.reads
    res.pop("_driver_pid", None)
    res.pop("_browser_pid", None)
    if isinstance(res.get("resources_at_outcome"), dict):
        res["resources_at_outcome"]["browser_pids"] = len(res["resources_at_outcome"].get("browser_pids") or [])
    await asyncio.sleep(0.3)
    final_state = server.state.snapshot()
    journal = server.state.drain() + server.bus.drain()
    record.update(res)
    record["journal"] = journal
    record["final_state"] = {"submitted_sha16": sha16(final_state.get("submitted")),
                             "submitted_len": None if final_state.get("submitted") is None else len(final_state["submitted"]),
                             "submitter": final_state.get("submitter")}
    record["oracle_exact_match"] = final_state.get("submitted") is not None and \
        sha16(final_state["submitted"]) == res.get("token_sha16") and len(final_state["submitted"]) == res.get("token_len")
    record["completion_mutations"] = sum(1 for e in journal if e.get("event") == "submit")
    record["wrong_target_submits"] = wrong_target_submits(journal)
    record["trace_file_exists"] = bool(trace_path and trace_path.exists())
    record["network"] = dict(NETWORK)
    record["loadavg_after"] = loadavg()
    record["psi_after"] = L.pressure()
    record["utc_end"] = utc()
    with (out / f"trials/{name}.jsonl").open("w") as f:
        for ev in rec.events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: record.get(k) for k in ("trial", "outcome", "oracle_exact_match", "completion_mutations",
                                                  "wrong_target_submits", "loadavg_before")}), flush=True)
    return record


def build_plan(plan: str, pairs: int, conditions: list[str]) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []

    def add(arm: str, cond: str, **kw: Any) -> None:
        trials.append({"plan": plan, "arm": arm, "condition": cond, "excluded": False, **kw})

    if plan == "shakedown":
        add("A", "W-quiet", excluded=True)
        add("B_proj", "W-churn", excluded=True)
        add("A", "W-quiet", control="DC03", excluded=True)
        add("B_proj", "W-quiet", control="stale_ref", excluded=True)
    elif plan == "default_off":
        for _ in range(5):
            add("A_off", "W-quiet")
    elif plan == "distortion":
        for i, order in enumerate(L.abba_pairs("A", "A_ref", 10)):
            for arm in order:
                add(arm, "W-quiet", pair=f"dist-p{i:02d}", order="AR" if order[0] == "A" else "RA")
    elif plan in ("ab", "static"):
        for cond in (["W-static"] if plan == "static" else conditions):
            for i, order in enumerate(L.abba_pairs("A", "B_proj", pairs)):
                for arm in order:
                    add(arm, cond, pair=f"{cond}-p{i:02d}", order="AB" if order[0] == "A" else "BA")
    elif plan == "controls":
        for i in range(5):
            for j, ctl in enumerate(("DC03", "DC04", "stale_ref")):
                order = ("A", "B_proj") if (i + j) % 2 == 0 else ("B_proj", "A")
                for arm in order:
                    add(arm, "W-quiet", control=ctl, pair=f"{ctl}-p{i:02d}", order="AB" if order[0] == "A" else "BA")
    else:
        raise ValueError(plan)
    for idx, t in enumerate(trials):
        t["seed"] = SEED_BASE + idx
        t["block"] = plan
        t["name"] = f"{plan}{idx:03d}-{t['condition']}-{t['arm']}-{t.get('control') or 'none'}"
    return trials


def lock_fd_inherited() -> bool:
    for fd in Path("/proc/self/fd").iterdir():
        try:
            if os.readlink(fd).endswith("/locks/quiet-lane.lock"):
                return True
        except OSError:
            continue
    return False


async def main_async(args: argparse.Namespace) -> int:
    """Run each requested plan in order inside this one session (one quiet-lane lock acquisition)."""
    rc = 0
    for plan in args.plan:
        rc = await run_plan(args, plan)
        if rc != 0:
            break
    return rc


async def run_plan(args: argparse.Namespace, plan: str) -> int:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"plan_kind": plan, "lock_label": args.lock_label, "utc_start": utc(),
                                "started_mono_ns": now(), "loadavg_start": loadavg(), "psi_start": L.pressure(),
                                "lock_fd_inherited": lock_fd_inherited(), "provider": "mock",
                                "chooser": "choose_mock_for_task", "binaries": args.shas, "pairs": args.pairs,
                                "conditions": args.conditions}
    pre = L.trust_precondition()
    manifest["preflight"] = pre
    if not pre["ok"] or plan == "preflight":
        manifest["status"] = "infrastructure_blocked" if not pre["ok"] else "preflight_ok"
        manifest["utc_end"] = utc()
        manifest["network"] = dict(NETWORK)
        (out / f"run-manifest-{plan}.json").write_text(json.dumps(manifest, indent=1))
        print(json.dumps({"event": manifest["status"], "preflight": pre}), flush=True)
        return 3 if not pre["ok"] else 0
    server = I107Server(("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    trials = build_plan(plan, args.pairs, args.conditions)
    manifest["trials"] = [t["name"] for t in trials]
    records = []
    try:
        for spec in trials:
            rec = await one(spec, args, server, out)
            records.append(rec)
            if rec.get("isolation_abort"):
                manifest["aborted"] = "isolation"
                break
    finally:
        server.stopping = True
        manifest["ended_mono_ns"] = now()
        manifest["utc_end"] = utc()
        manifest["loadavg_end"] = loadavg()
        manifest["network"] = dict(NETWORK)
        manifest["status"] = "ran" if not manifest.get("aborted") else "aborted"
        (out / f"run-manifest-{plan}.json").write_text(json.dumps(manifest, indent=1))
        server.shutdown()
        server.server_close()
    if manifest.get("aborted"):
        return 5
    if plan == "shakedown" and any(r.get("outcome") != "verified" for r in records
                                   if not r.get("control") and r.get("condition") in ("W-quiet", "W-churn")):
        print(json.dumps({"event": "shakedown_failed", "next_plans": "not run"}), flush=True)
        return 4
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--driver", required=True)
    p.add_argument("--ref-driver")
    p.add_argument("--out", required=True)
    p.add_argument("--plan", nargs="+", required=True,
                   choices=("preflight", "shakedown", "default_off", "distortion", "ab", "static", "controls"))
    p.add_argument("--pairs", type=int, default=30)
    p.add_argument("--conditions", nargs="+", default=["W-quiet", "W-churn"])
    p.add_argument("--lock-label", required=True)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (TRACE_ENV, KNOB_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    args.shas = {"i107": file_sha256(args.driver)}
    if args.shas["i107"] != PINNED["i107"]:
        raise SystemExit("refusing: --driver is not the pinned i107 binary")
    if args.ref_driver:
        args.shas["ref"] = file_sha256(args.ref_driver)
        if args.shas["ref"] != PINNED["ref"]:
            raise SystemExit("refusing: --ref-driver is not the pinned reference binary")
    elif "distortion" in args.plan:
        raise SystemExit("refusing: distortion needs --ref-driver")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

"""Lane-D trial runner: the real jev-use caller, arm A vs arm D, measurement only.

Each trial runs the UNMODIFIED jev-use ``python/run.py`` ``run()`` coroutine at the
tested source (jev-use tree 72bf8156, byte-identical to trycua/cua PR 4316 head
a0bca7440), with ``--provider mock --visual-observation auto`` and, for arm D only,
``--guarded-completion``. Nothing in run.py is edited. Measurement is added by
patching the module-level names run.py looks up at call time (the OWN-105 /
R2-05 pattern, which patched ``run.stdio_client``):

* ``stdio_client``      wraps the SDK's real stdio client (or the OWN-105 fault seam
                         for DC20a) and stamps the cleanup span + resource sample;
* ``ClientSession``     wraps the real SDK session: every ``tools/call`` is stamped
                         (label, tool, bytes, error code); the fixed setting
                         ``set_agent_cursor_enabled(enabled=false)`` is sent once
                         before ``browser_prepare`` in both arms; control hooks run
                         after the first ``browser_type`` / before the first
                         ``browser_click``;
* ``FixtureFormTask``   subclass whose ``read_oracle`` is stamped (the runner's own
                         oracle reads; the independent oracle is the fixture process);
* ``choose_mock_for_task``, ``plan_guarded_completion``, ``resolve_guarded_completion``,
  ``task_candidates_for_step``: stamped pass-throughs (decision, program creation,
  program verification, candidate building);
* ``asyncio``           proxy whose ``sleep`` is stamped (completion-poll sleeps);
* ``driver_environment`` the real function, then the trial's trace file is set
                         (``CUA_DRIVER_PHASE_TRACE_FILE``) and the focus-settle knob
                         removed.

Usage (inside cua-x11-session.sh, under hostless, under quiet-timed):

    JEV_USE_DIR=<jev-use> <jev-use>/.venv/bin/python run_d.py --driver <bin> --out <dir> \\
        --block <name> --binary-sha256 <sha> --caller-tree <tree> --lock-label <quiet-timed label>
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("JEV_USE_DIR", HERE.parents[3] / "libs/cua-driver/examples/jev-use")).resolve()
for _p in (str(HERE), str(JEV), str(JEV / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── 0 provider HTTP: the runner process may only open loopback sockets (from B-01 run_critpath.py) ──
NETWORK = {"non_loopback_connect_attempts": 0}
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex


def _check_address(sock: socket.socket, address: Any) -> None:
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) and address else None
        if host not in _LOOPBACK:
            NETWORK["non_loopback_connect_attempts"] += 1
            raise ConnectionRefusedError("i107-d runner: non-loopback network is disabled (mock chooser)")


def _guarded_connect(self: socket.socket, address: Any) -> None:
    _check_address(self, address)
    return _orig_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
    _check_address(self, address)
    return _orig_connect_ex(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]

from mcp import ClientSession as RealClientSession, StdioServerParameters  # noqa: E402
from mcp.client.session import ClientSession as _McpClientSession  # noqa: E402
from mcp.client.stdio import stdio_client as real_stdio_client  # noqa: E402

import d_plan  # noqa: E402
import fault_transport as ft  # noqa: E402
import run as jev_run  # noqa: E402  (jev-use python/run.py, the caller under test)
import tasks as jev_tasks  # noqa: E402

TRACE_ENV = "CUA_DRIVER_PHASE_TRACE_FILE"
KNOB_ENV = "CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS"
TRIAL_TIMEOUT_S = 180
LATE_EFFECT_WAIT_S = 2.5
CLK_TCK = os.sysconf("SC_CLK_TCK")
MUTATION_TOOLS = {"browser_type", "browser_click", "click"}
CHOOSER = "choose_mock_for_task (scripted mock; FIXTURE/BENCHMARK, never LIVE_PROVIDER)"


def now() -> int:
    return time.monotonic_ns()


def utc_now() -> str:
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}Z"


def sha16(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


# ── MCP client output-schema validation timing (B-01 run_critpath.py, library path only) ──
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


# ── host readings (measurement only) ─────────────────────────────────────────

def read_text(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except OSError:
        return None


def loadavg() -> str:
    return (read_text("/proc/loadavg") or "unavailable").strip()


def psi() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for res in ("cpu", "memory", "io"):
        text = read_text(f"/proc/pressure/{res}")
        if text is None:
            out[res] = None
            continue
        out[res] = {}
        for line in text.strip().splitlines():
            kind, *fields = line.split()
            out[res][kind] = {k: float(v) for k, v in (f.split("=") for f in fields)}
    return out


def _stat(pid: int) -> tuple[int, float] | None:
    text = read_text(f"/proc/{pid}/stat")
    if not text:
        return None
    rest = text[text.rindex(")") + 2:].split()
    return int(rest[1]), (int(rest[11]) + int(rest[12])) / CLK_TCK  # ppid, utime+stime (s)


def _status_kib(pid: int, key: str) -> int | None:
    text = read_text(f"/proc/{pid}/status") or ""
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1])
    return None


def descendants(root: int) -> list[int]:
    children: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            st = _stat(int(entry))
            if st:
                children.setdefault(st[0], []).append(int(entry))
    out, stack = [], [root]
    while stack:
        pid = stack.pop()
        out.append(pid)
        stack.extend(children.get(pid, []))
    return out


def child_pids_named(name: str) -> list[int]:
    me = os.getpid()
    out = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            st = _stat(int(entry))
            if st and st[0] == me:
                try:
                    if Path(os.readlink(f"/proc/{entry}/exe")).name == name:
                        out.append(int(entry))
                except OSError:
                    continue
    return out


def sample_resources(driver_pid: int | None, browser_pid: int | None) -> dict[str, Any]:
    res: dict[str, Any] = {"driver_pid_found": driver_pid is not None, "browser_pid_found": bool(browser_pid)}
    if driver_pid:
        st = _stat(driver_pid)
        res.update(driver_cpu_s=None if st is None else st[1], driver_vmhwm_kib=_status_kib(driver_pid, "VmHWM"),
                   driver_vmrss_kib=_status_kib(driver_pid, "VmRSS"))
    if browser_pid:
        tree = [p for p in descendants(browser_pid) if _stat(p)]
        res.update(browser_procs=len(tree), browser_cpu_s=sum(_stat(p)[1] for p in tree if _stat(p)),
                   browser_rss_kib=sum(_status_kib(p, "VmRSS") or 0 for p in tree))
    return res


def pid_alive(pid: int | None) -> bool | None:
    if not pid:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    st = read_text(f"/proc/{pid}/stat")
    return bool(st) and ") Z " not in st


# ── fixture client ────────────────────────────────────────────────────────────

class FixtureClient:
    def __init__(self, url: str) -> None:
        self.url = url

    def _get(self, path: str, timeout: float = 10) -> Any:
        with urlopen(self.url + path, timeout=timeout) as r:
            return json.loads(r.read())

    def _post(self, path: str, obj: Any) -> bytes:
        with urlopen(Request(self.url + path, data=json.dumps(obj).encode(), method="POST",
                             headers={"Content-Type": "application/json"}), timeout=10) as r:
            return r.read()

    def config(self, variant: str, token: str, submit_delay_ms: int = 0) -> None:
        self._post("config", {"variant": variant, "token": token, "submit_delay_ms": submit_delay_ms})

    def state(self) -> dict[str, Any]:
        return self._get("state")

    def trial(self) -> dict[str, Any]:
        return self._get("trial")

    def journal(self) -> list[dict[str, Any]]:
        return self._get("journal")["journal"]

    def count(self, event: str) -> int:
        return int(self._get(f"journal-count?event={event}")["count"])

    def control(self, op: str, args: dict[str, Any]) -> int:
        return int(json.loads(self._post("control", {"op": op, "args": args}))["id"])

    def ack_wait(self, op_id: int, timeout: float) -> dict[str, Any]:
        return self._get(f"ack-wait?id={op_id}&timeout={timeout}", timeout=timeout + 10)

    def note_wait(self, kind: str, after: int, timeout: float) -> dict[str, Any]:
        return self._get(f"note-wait?kind={kind}&after={after}&timeout={timeout}", timeout=timeout + 10)


# ── per-trial context ─────────────────────────────────────────────────────────

class Recorder:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, name: str, **fields: Any) -> None:
        self.events.append({"event": name, "t_mono_ns": now(), **fields})


@dataclass
class Options:
    driver: str
    out: Path
    binary_sha256: str
    caller_tree: str
    lock_label: str
    fake: bool = False


class TrialCtx:
    def __init__(self, spec: dict[str, Any], opts: Options, fixture: FixtureClient, trace_path: Path | None) -> None:
        self.spec, self.opts, self.fixture, self.trace_path = spec, opts, fixture, trace_path
        self.rec = Recorder()
        self.control = d_plan.CONTROLS.get(spec.get("control") or "", None)
        self.snapshots = 0
        self.cursor_ack: dict[str, Any] | None = None
        self.typed = self.clicked = False
        self.prepared_pid: int | None = None
        self.driver_pid: int | None = None
        self.bound_target: str | None = None
        self.resources: dict[str, Any] = {}
        self.probe: dict[str, Any] | None = None
        self.fault_plan: ft.FaultPlan | None = None
        self.fake_page: Any = None
        self.real_env: Any = jev_run.driver_environment

    def label_for(self, name: str, args: dict[str, Any]) -> str:
        if name == "get_browser_state":
            if args.get("snapshot_format"):
                self.snapshots += 1
                return f"snapshot{self.snapshots}"
            return "bind"
        if name in MUTATION_TOOLS:
            return f"action{self.snapshots}"
        return {"browser_prepare": "prepare", "browser_navigate": "navigate"}.get(name, name)

    async def hook(self, point: str, args: dict[str, Any]) -> None:
        c = self.control
        if not c or c.get("point") != point:
            return
        self.rec.add("control_start", control=self.spec["control"], point=point)
        if c.get("op"):
            t = now()
            op_id = await asyncio.to_thread(self.fixture.control, c["op"], c.get("args") or {})
            ack = await asyncio.to_thread(self.fixture.ack_wait, op_id, 5.0)
            result = (ack.get("entry") or {}).get("result") or {}
            self.rec.add("control_acked", op=c["op"], acked=bool(ack.get("acked")), applied=bool(result.get("applied")))
            if c.get("settle") == "control_open":
                hit = await asyncio.to_thread(self.fixture.note_wait, "control_open", t, 10.0)
                self.rec.add("control_settled", hit=bool(hit.get("hit")))
        if c.get("probe") == "session_replacement":
            self.probe = await session_replacement_probe(self, args)
        self.rec.add("control_done")


async def session_replacement_probe(ctx: TrialCtx, args: dict[str, Any]) -> dict[str, Any]:
    """DC10: send the pending click (old target_id/tab_id/ref/session label) through a NEW MCP session."""
    before = await asyncio.to_thread(ctx.fixture.count, "submit")
    ctx.rec.add("probe_start")
    result: dict[str, Any] = {}
    if ctx.opts.fake:
        from fake_driver import FakeSession
        res = await FakeSession(ctx.fixture.url, ctx.fake_page, bound=False).call_tool("browser_click", dict(args))
    else:
        env = probe_env(ctx)
        async with real_stdio_client(StdioServerParameters(command=ctx.opts.driver, args=["mcp"], env=env)) as (r, w):
            async with RealClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("browser_click", dict(args))
    structured = res.structuredContent if isinstance(res.structuredContent, dict) else {}
    result = {"is_error": bool(res.isError), "code": _code(structured), "status": structured.get("status")}
    ctx.rec.add("probe_end", **result)
    await asyncio.sleep(0.3)
    result["submits_during_probe"] = await asyncio.to_thread(ctx.fixture.count, "submit") - before
    return result


def probe_env(ctx: TrialCtx) -> dict[str, str]:
    env = ctx.real_env()
    env.pop(TRACE_ENV, None)
    env.pop(KNOB_ENV, None)
    return env


def _code(structured: dict[str, Any]) -> str | None:
    code = structured.get("code")
    for key in ("refusal", "error"):
        nested = structured.get(key)
        if not code and isinstance(nested, dict):
            code = nested.get("code")
    return code if isinstance(code, str) and code else None


def envelope(structured: dict[str, Any]) -> dict[str, Any]:
    """Content-free view of a mutation result: short scalars, and only codes/kinds one level down."""
    out: dict[str, Any] = {"_keys": sorted(structured)}
    for k, v in structured.items():
        if isinstance(v, (bool, int, float)) or v is None or (isinstance(v, str) and len(v) <= 64):
            out[k] = v
        elif isinstance(v, dict):
            sub = {kk: vv for kk, vv in v.items() if kk in ("code", "kind", "reason", "status")
                   and (isinstance(vv, (bool, int, float)) or (isinstance(vv, str) and len(vv) <= 64))}
            if sub:
                out[k] = sub
    return out


class TimedSession:
    """Wraps the real (or fake) MCP ClientSession that run.py's Driver uses."""

    def __init__(self, inner: Any, ctx: TrialCtx) -> None:
        self.inner, self.ctx = inner, ctx

    async def __aenter__(self) -> "TimedSession":
        await self.inner.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self.inner.__aexit__(*exc)

    async def initialize(self) -> Any:
        self.ctx.rec.add("mcp_initialize_start")
        out = await self.inner.initialize()
        self.ctx.rec.add("mcp_initialize_end")
        if not self.ctx.opts.fake:
            pids = child_pids_named(Path(self.ctx.opts.driver).name)
            self.ctx.driver_pid = pids[-1] if pids else None
        return out

    async def list_tools(self) -> Any:
        return await self.inner.list_tools()

    async def _timed(self, label: str, name: str, args: dict[str, Any]) -> Any:
        rec = self.ctx.rec
        fields: dict[str, Any] = {"label": label, "tool": name}
        if name == "get_browser_state":
            fields.update(snapshot_format=args.get("snapshot_format"), has_query="query" in args)
        if name in MUTATION_TOOLS:
            fields["target_match"] = (self.ctx.bound_target is None or args.get("target_id") is None
                                      or args.get("target_id") == self.ctx.bound_target)
        rec.add("call_send", **fields)
        try:
            result = await self.inner.call_tool(name, args)
        except BaseException as error:
            rec.add("call_return", label=label, tool=name, ok=False, error=type(error).__name__)
            raise
        structured = result.structuredContent if isinstance(result.structuredContent, dict) else {}
        ret: dict[str, Any] = {"label": label, "tool": name, "ok": not result.isError, "is_error": bool(result.isError),
                               "code": _code(structured), "bytes": len(json.dumps(structured, default=str)),
                               "status": structured.get("status"), "route": structured.get("route"),
                               "effect": structured.get("effect")}
        if name in MUTATION_TOOLS:
            ret["envelope"] = envelope(structured)
        if name == "get_browser_state" and args.get("snapshot_format"):
            ret["n_refs"] = len(structured.get("refs") or [])
            ret["n_content_refs"] = len(structured.get("content_refs") or [])
            snap = structured.get("snapshot") or {}
            ret.update({k: snap.get(k) for k in ("selected_nodes", "total_nodes", "complete") if k in snap})
            ret["omitted"] = snap.get("omitted")
        rec.add("call_return", **ret)
        return result

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        ctx = self.ctx
        if name == "browser_prepare" and ctx.cursor_ack is None:
            r = await self._timed("cursor_enabled", "set_agent_cursor_enabled",
                                  {"enabled": False, "session": args.get("session")})
            ctx.cursor_ack = {"requested": False, "ok": not r.isError}
        if name == "browser_click" and not ctx.clicked:
            ctx.clicked = True
            await ctx.hook("before_click", args)
        result = await self._timed(ctx.label_for(name, args), name, args)
        structured = result.structuredContent if isinstance(result.structuredContent, dict) else {}
        if name == "browser_prepare" and not result.isError:
            try:
                ctx.prepared_pid = int(structured.get("prepared_pid")) or None
            except (TypeError, ValueError):
                ctx.prepared_pid = None
        if name == "get_browser_state" and "pid" in args and not result.isError:
            ctx.bound_target = structured.get("target_id")
        if name == "browser_type" and not ctx.typed and not result.isError:
            ctx.typed = True
            await ctx.hook("after_type", args)
        return result


class AsyncioProxy:
    def __init__(self, rec: Recorder) -> None:
        self._rec = rec

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)

    async def sleep(self, delay: float, *a: Any, **k: Any) -> Any:
        self._rec.add("sleep_start", sleep_ms=round(delay * 1000, 3))
        try:
            return await asyncio.sleep(delay, *a, **k)
        finally:
            self._rec.add("sleep_end")


def make_stdio(ctx: TrialCtx) -> Any:
    @asynccontextmanager
    async def timed_stdio(params: Any, *a: Any, **k: Any):
        if ctx.opts.fake:
            inner = _fake_transport()
        elif ctx.fault_plan is not None:
            inner = ft.fault_stdio_client(params, ctx.fault_plan)
        else:
            inner = real_stdio_client(params, *a, **k)
        try:
            async with inner as streams:
                try:
                    yield streams
                finally:
                    ctx.rec.add("stdio_close_start")
                    ctx.rec.add("resource_sample_start")
                    ctx.resources = {} if ctx.opts.fake else sample_resources(ctx.driver_pid, ctx.prepared_pid)
                    ctx.rec.add("resource_sample_end")
        finally:
            ctx.rec.add("stdio_closed")

    return timed_stdio


@asynccontextmanager
async def _fake_transport():
    yield None, None


def make_task_class(ctx: TrialCtx) -> type:
    class StampedFixtureFormTask(jev_tasks.FixtureFormTask):
        def read_oracle(self):  # type: ignore[override]
            ctx.rec.add("oracle_send")
            state = super().read_oracle()
            sub = state.get("submitted")
            ctx.rec.add("oracle_return",
                        outcome="verified" if sub == self.token else ("refuted" if sub is not None else "unknown"))
            return state

    return StampedFixtureFormTask


def stamped(ctx: TrialCtx) -> dict[str, Any]:
    orig_choose, orig_plan = jev_run.choose_mock_for_task, jev_run.plan_guarded_completion
    orig_resolve, orig_cand = jev_run.resolve_guarded_completion, jev_run.task_candidates_for_step

    def choose(*a: Any, **k: Any) -> Any:
        ctx.rec.add("decide_start")
        out = orig_choose(*a, **k)
        ctx.rec.add("decided", choice=out[0])
        return out

    def plan(*a: Any, **k: Any) -> Any:
        ctx.rec.add("plan_start")
        out = orig_plan(*a, **k)
        ctx.rec.add("plan_done", bound=out is not None)
        return out

    def resolve(*a: Any, **k: Any) -> Any:
        ctx.rec.add("guard_start")
        out = orig_resolve(*a, **k)
        ctx.rec.add("guard_done", status=out.telemetry.get("status"), reason=out.telemetry.get("reason"))
        return out

    async def cand(*a: Any, **k: Any) -> Any:
        ctx.rec.add("cand_start")
        out = await orig_cand(*a, **k)
        ctx.rec.add("cand_done", ids=[c.id for c in out[0]])
        return out

    return {"choose_mock_for_task": choose, "plan_guarded_completion": plan,
            "resolve_guarded_completion": resolve, "task_candidates_for_step": cand}


async def run_trial(spec: dict[str, Any], opts: Options, fixture_url: str) -> dict[str, Any]:
    out = Path(opts.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    name = spec["name"]
    trace_rel, log_rel = f"{name}.driver-trace.jsonl", f"{name}.run-log.jsonl"
    trace_path, log_path = out / "trials" / trace_rel, out / "trials" / log_rel
    fixture = FixtureClient(fixture_url)
    ctx = TrialCtx(spec, opts, fixture, trace_path)
    control = ctx.control or {}
    token = d_plan.make_token(spec.get("cohort", "K1"))
    record: dict[str, Any] = {
        "trial": name, **{k: spec.get(k) for k in ("block", "plan", "pair", "order", "arm", "condition", "cohort",
                                                    "comparison", "kind", "control", "rep")},
        "excluded": spec.get("excluded"), "regime": "fresh_driver_and_isolated_new_browser_per_trial",
        "evidence": "UNIT_FAKE_DRIVER" if opts.fake else "REAL", "chooser": CHOOSER,
        "binary_sha256": opts.binary_sha256, "caller_tree": opts.caller_tree, "lock_label": opts.lock_label,
        "fixture_variant": spec.get("variant"), "submit_delay_ms": int(control.get("submit_delay_ms", 0)),
        "token_sha16": sha16(token), "token_len": len(token), "driver_trace": trace_rel, "run_log": log_rel,
        "guarded_completion_flag": spec["arm"] == "D", "visual_observation": "auto",
        "loadavg_before": loadavg(), "psi_before": psi(),
    }
    fixture.config(spec.get("variant", "quiet"), token, int(control.get("submit_delay_ms", 0)))
    fake_channel = None
    if opts.fake:
        from fake_driver import FakePage, FakePageChannel
        ctx.fake_page = FakePage()
        if spec.get("variant") == "control":
            fake_channel = FakePageChannel(fixture_url, ctx.fake_page)
            fake_channel.start()
            await asyncio.to_thread(fixture.note_wait, "control_open", 0, 5.0)
    if control.get("fault"):
        f = control["fault"]

        def barrier_wait(kind: str, timeout: float) -> bool:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if fixture.count("submit") >= 1:
                    return True
                time.sleep(0.005)
            return False

        ctx.fault_plan = ft.FaultPlan(mode=f["mode"], barrier_kind=f["barrier"], barrier_wait=barrier_wait,
                                      probe=lambda: {"submits": fixture.count("submit")})

    real_env = jev_run.driver_environment

    def driver_env(*a: Any, **k: Any) -> dict[str, str]:
        env = real_env(*a, **k)
        env.pop(TRACE_ENV, None)
        env.pop(KNOB_ENV, None)
        env[TRACE_ENV] = str(trace_path)
        return env

    def session_factory(read: Any, write: Any) -> TimedSession:
        if opts.fake:
            from fake_driver import FakeSession
            return TimedSession(FakeSession(fixture_url, ctx.fake_page, trace_path=str(trace_path)), ctx)
        return TimedSession(RealClientSession(read, write), ctx)

    args = argparse.Namespace(provider="mock", fixture_url=fixture_url, token=token, max_steps=4, dry_run=False,
                              guarded_completion=spec["arm"] == "D", log=str(log_path), visual_observation="auto")
    CLIENT["rec"] = ctx.rec
    t0 = now()
    ctx.rec.add("trial_start", arm=spec["arm"], control=spec.get("control"))
    outcome, exc = "unknown", None
    patches = [patch.object(jev_run, "stdio_client", make_stdio(ctx)),
               patch.object(jev_run, "ClientSession", session_factory),
               patch.object(jev_run, "FixtureFormTask", make_task_class(ctx)),
               patch.object(jev_run, "asyncio", AsyncioProxy(ctx.rec)),
               patch.object(jev_run, "driver_environment", driver_env),
               patch.dict(os.environ, {"CUA_DRIVER_BIN": opts.driver})]
    patches += [patch.object(jev_run, k, v) for k, v in stamped(ctx).items()]
    try:
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            try:
                outcome = await asyncio.wait_for(jev_run.run(args), TRIAL_TIMEOUT_S)
            except (asyncio.TimeoutError, TimeoutError):
                outcome = "timeout"
            except BaseException as error:  # noqa: BLE001 - every failure stays in the denominator
                if isinstance(error, KeyboardInterrupt):
                    raise
                outcome = "error"
                leaves, pending = [], [error]
                while pending:
                    item = pending.pop()
                    if isinstance(item, BaseExceptionGroup):
                        pending.extend(item.exceptions)
                    else:
                        leaves.append(type(item).__name__)
                exc = sorted(leaves)
    finally:
        ctx.rec.add("run_return", outcome=outcome)
        CLIENT["rec"] = None
    # Cleanup span end: the Driver-launched browser has exited.
    if opts.fake:
        ctx.rec.add("browser_gone", fake=True)
        alive = None
    else:
        alive = pid_alive(ctx.prepared_pid)
        deadline = time.monotonic() + 5.0
        while alive and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
            alive = pid_alive(ctx.prepared_pid)
        if alive is False:
            ctx.rec.add("browser_gone")
    # Let a late effect land before the independent read is closed (not part of any span).
    deadline = time.monotonic() + LATE_EFFECT_WAIT_S
    while time.monotonic() < deadline and fixture.state().get("submitted") != token:
        await asyncio.sleep(0.05)
    if fake_channel is not None:
        fake_channel.stop.set()
    trial_res = fixture.trial()
    final = fixture.state()
    journal = fixture.journal()
    record.update({
        "outcome": outcome, "runner_exception_leaves": exc, "trial_wall_ns": now() - t0,
        "cursor_ack": ctx.cursor_ack, "resources": ctx.resources, "browser_alive_after_close": alive,
        "poller_first_ok_ns": trial_res.get("poller_first_ok_ns"), "poller_reads": trial_res.get("poller_reads"),
        "poller_started_ns": trial_res.get("poller_started_ns"), "journal": journal,
        "final_state": {"submitted_sha16": sha16(final.get("submitted")), "endpoint": final.get("endpoint"),
                        "submitted_len": None if final.get("submitted") is None else len(final["submitted"])},
        "probe": ctx.probe, "network": dict(NETWORK),
        "fault": None if ctx.fault_plan is None else {
            "mode": ctx.fault_plan.mode, "fired": ctx.fault_plan.fired, "seam_events": ctx.fault_plan.events,
            "clicks_after_fault": max(0, sum(1 for e in ctx.rec.events if e["event"] == "call_send"
                                             and e.get("tool") == "browser_click") - 1)},
        "loadavg_after": loadavg(), "psi_after": psi(),
    })
    with (out / "trials" / f"{name}.jsonl").open("w") as f:
        for ev in ctx.rec.events:
            f.write(json.dumps(ev, sort_keys=True, default=str) + "\n")
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True, default=str) + "\n")
    if not trace_path.exists():
        trace_path.write_text("")
    print(json.dumps({k: record.get(k) for k in ("trial", "outcome", "poller_first_ok_ns", "loadavg_before")}),
          file=sys.stderr, flush=True)
    return {**record, "_token": token}


# ── block entry point ─────────────────────────────────────────────────────────

def start_fixture() -> tuple[subprocess.Popen, str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(JEV), str(HERE)])}
    proc = subprocess.Popen([sys.executable, str(HERE / "i107_fixture.py"), "--port", "0"], stdout=subprocess.PIPE,
                            text=True, env=env)
    port = json.loads(proc.stdout.readline())["port"]
    return proc, f"http://127.0.0.1:{port}/"


async def run_block(block: dict[str, Any], opts: Options) -> dict[str, Any]:
    proc, url = start_fixture()
    manifest: dict[str, Any] = {"block": block["block"], "plan": block["plan"], "lock_label": opts.lock_label,
                                "trials": [t["name"] for t in block["trials"]], "provider": "mock", "chooser": CHOOSER,
                                "binary_sha256": opts.binary_sha256, "caller_tree": opts.caller_tree,
                                "started_mono_ns": now(), "started_utc": utc_now(),
                                "loadavg_start": loadavg(), "fixture_pid_separate": proc.pid != os.getpid(),
                                "isolation": None if opts.fake else isolation_record(dict(os.environ))}
    try:
        for spec in block["trials"]:
            await run_trial(spec, opts, url)
    finally:
        manifest.update(ended_mono_ns=now(), ended_utc=utc_now(),
                        loadavg_end=loadavg(), network=dict(NETWORK))
        (Path(opts.out) / "manifests").mkdir(parents=True, exist_ok=True)
        (Path(opts.out) / "manifests" / f"{block['block']}.json").write_text(json.dumps(manifest, indent=1))
        proc.terminate()
        proc.wait(5)
    return manifest


def hostless_ancestor(pid: int) -> int | None:
    """The nearest process (self included) whose environment carries CUA_HOSTLESS=1 (set by the lanes'
    hostless wrapper). cua-x11-session.sh clears the environment, so the process tree is checked."""
    while pid > 1:
        try:
            environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            environ = []
        if b"CUA_HOSTLESS=1" in environ:
            return pid
        st = _stat(pid)
        if st is None:
            return None
        pid = st[0]
    return None


def refuse_unsafe_environment(env: dict[str, str], ancestor: Any = None) -> None:
    find = ancestor or (lambda: hostless_ancestor(os.getpid()))
    if env.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in env):
        raise SystemExit("refusing: host Wayland/Hyprland variables present")
    for name in (TRACE_ENV, KNOB_ENV, "CUA_E2E_BROWSER_NO_SANDBOX"):
        if name in env:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    if not env.get("DISPLAY") or env.get("DISPLAY") in (":0", ":0.0"):
        raise SystemExit("refusing: no private DISPLAY (run inside cua-x11-session.sh)")
    if find() is None:
        raise SystemExit("refusing: no hostless ancestor (CUA_HOSTLESS=1) in the process tree")


def isolation_record(env: dict[str, str], ancestor: Any = None) -> dict[str, Any]:
    find = ancestor or (lambda: hostless_ancestor(os.getpid()))
    return {"hostless_ancestor_found": find() is not None,
            "uid_map": " ".join((read_text("/proc/self/uid_map") or "").split()),
            "display_is_private": bool(env.get("DISPLAY")) and env.get("DISPLAY") not in (":0", ":0.0"),
            "wayland_display_set": bool(env.get("WAYLAND_DISPLAY"))}


def resolve_blocks(names: list[str]) -> list[dict[str, Any]]:
    """Blocks of one lock group, in schedule order (PREREG-AMENDMENT-1: consecutive blocks only)."""
    order = [b["block"] for b in d_plan.schedule()]
    idx = [order.index(n) for n in names]
    if idx != list(range(idx[0], idx[0] + len(idx))):
        raise SystemExit(f"refusing: a lock group must be consecutive blocks in schedule order: {names}")
    return [d_plan.block_by_name(n) for n in names]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--block", required=True, nargs="+", help="one block, or a lock group of consecutive blocks")
    p.add_argument("--binary-sha256", required=True)
    p.add_argument("--caller-tree", required=True)
    p.add_argument("--lock-label", required=True)
    a = p.parse_args()
    refuse_unsafe_environment(dict(os.environ))
    digest = hashlib.sha256(Path(a.driver).read_bytes()).hexdigest()
    if digest != a.binary_sha256:
        raise SystemExit(f"refusing: driver sha256 {digest} != expected {a.binary_sha256}")
    opts = Options(driver=a.driver, out=Path(a.out), binary_sha256=a.binary_sha256, caller_tree=a.caller_tree,
                   lock_label=a.lock_label)
    for block in resolve_blocks(a.block):
        asyncio.run(run_block(block, opts))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""N-03: native one-source closure on the R2-10 source (lazy per-schema caller-compiled
output validators HCL, the Driver admission tools-list cache V, session amortization) and
the R2-09 X11 ``ax_fg`` unguarded DoAction route (measurement only).

Lineage: the N-02 harness (``n02_harness.py``, blob 1fe9454fa3b5, itself derived from the
N-01R harness used verbatim by R2-10's ``r2_10_native.py``, blob 1ff4fa7e42f5). Same
fixture, task window, observation call, jev-use ``eligible_controls`` lookup, forced
background element-token AT-SPI route, independent 2 ms state-file oracle, fresh Driver +
fresh fixture per trial (k=1), the same client stamps without monkeypatching
(``StampedClientSession`` / ``StampedRead`` / ``StampedWrite``) and the same X focus sampler
and decoy (``xprobe.py``, verbatim, blob f17d83691faa). Changes for N-03 (pre-registered in
PREREG.json):

* Part A arms are R2-10's native composed arm X (S0 + ``set_agent_cursor_motion
  {glide_duration_ms: 1}``, library output validation) crossed with HCL and V:
  - HCL: the output validator for a tool's schema is compiled at that schema's first use,
    INSIDE the call that needs it (and so inside T for the in-T tools), with
    ``jsonschema.validate``'s exact rule (validator_for + check_schema + cls(schema,
    registry=Registry()); best_match over iter_errors). A re-listed tool whose schema
    object changed is recompiled. Every lazily validated call is re-validated with the
    library path after the trial (outside T) and both verdicts are recorded.
  - V: ``CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`` (B-02 knob, already in the source).
* kinds: ``main`` (k=1), ``session`` (k=5 tasks in one Driver session and one fixture),
  ``decoy`` (focus steal ~100 ms after the app's state change), ``vctl`` (tools/list re-listed
  mid-session; admission probes), ``smoke`` (default-off: no knob, no trace file);
* Part B kinds: ``axfg`` (fixture_axfg.py, CUA_N03_AXFG=1, a scrolled-out check box or button
  clicked with ``delivery_mode: foreground``), ``axfg_delay`` (positive control: the app applies
  its effect 30 ms late), ``axfg_smoke`` (the wrapper with the gate off vs the repository fixture).

Driver phase marks are read in the R2-10 source's union format (``phase``/``session``;
``t_mono_ns`` is host CLOCK_MONOTONIC, the clock of ``time.monotonic_ns()``).

Runs INSIDE cua-x11-session.sh with a private AT-SPI bus. It refuses to run otherwise. No
provider is used: any non-loopback TCP connect from this process is refused and counted.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xprobe  # noqa: E402

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use"
WINDOW_TITLE = "CuaTestHarness GTK3 Tasks"
STATE_SCHEMA = "cua.gtk3_task_state_v1"
SLEEP_ENV = "CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS"
V_ENV = "CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE"
WCT_ENV = "CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS"
WCP_ENV = "CUA_DRIVER_WINDOW_CHANGE_POLL_MS"
AXFG_ENV = "CUA_N03_AXFG"
AXFG_DELAY_ENV = "CUA_N03_AXFG_APPLY_DELAY_MS"
ARMS: dict[str, dict[str, Any]] = {
    "X": {"fast_cursor": True, "hcl": False, "env": {SLEEP_ENV: "0"}},
    "X+HCL": {"fast_cursor": True, "hcl": True, "env": {SLEEP_ENV: "0"}},
    "X+V": {"fast_cursor": True, "hcl": False, "env": {SLEEP_ENV: "0", V_ENV: "1"}},
    "X+HCL+V": {"fast_cursor": True, "hcl": True, "env": {SLEEP_ENV: "0", V_ENV: "1"}},
    # default-off smoke: no CUA_DRIVER_EXP_* and no phase trace file in the Driver env
    "D": {"fast_cursor": False, "hcl": False, "env": {}, "trace": False},
    # Part B (ax_fg): default 50 ms post-DoAction sleep vs the sleep knob at 0 ...
    "B": {"fast_cursor": False, "hcl": False, "env": {}},
    "S0": {"fast_cursor": False, "hcl": False, "env": {SLEEP_ENV: "0"}},
    # ... and family U: the same two arms with the foreground post-check's window-change
    # observation off (shipped host setting CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS=0: the window
    # set is read once, no polling), so the post-DoAction sleep is the only post-action wait.
    "BU": {"fast_cursor": False, "hcl": False, "env": {WCT_ENV: "0"}},
    "S0U": {"fast_cursor": False, "hcl": False, "env": {SLEEP_ENV: "0", WCT_ENV: "0"}},
}
FAST_MOTION = {"glide_duration_ms": 1}
STATE_PERIOD_S = 0.002
CONFIRM_DEADLINE_S = 3.0
POST_HOLD_S = {"main": 0.15, "session": 0.15, "smoke": 0.15, "decoy": 0.7, "vctl": 0.15,
               "axfg": 0.15, "axfg_delay": 0.3, "axfg_smoke": 0.15}
SESSION_TASKS = 5
AXFG_LABELS = {"checkbox": "Hidden agree", "button": "Hidden save"}
MODERN_META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
               "io.modelcontextprotocol/clientCapabilities": {}}

# ----------------------------------------------------------------------------- no provider
NET = {"refused_non_loopback_connects": 0, "targets": []}
_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            NET["refused_non_loopback_connects"] += 1
            NET["targets"].append(str(host)[:64])
            raise ConnectionRefusedError("N-03: provider cap 0, non-loopback connect refused")
    return _real_connect(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]


def now() -> tuple[int, int]:
    """(monotonic_ns, wall_ns) taken back to back."""
    return time.monotonic_ns(), time.time_ns()


def loadavg() -> list[float]:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return [float(x) for x in stream.read().split()[:3]]


def read_state(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class StateSampler(threading.Thread):
    """Independent oracle (as N-01R / N-02): reads the app's own state file every 2 ms."""

    def __init__(self, path: Path) -> None:
        super().__init__(daemon=True)
        self.path = path
        self.stop_flag = threading.Event()
        self.t0: list[int] = []
        self.t1: list[int] = []
        self.idx: list[int] = []
        self.states: list[Any] = []
        self._index: dict[str, int] = {}
        self.expected: dict[str, Any] | None = None
        self.return_ns: int | None = None
        self.confirmed = threading.Event()

    def matches(self, state: Any) -> bool:
        exp = self.expected
        return (isinstance(state, dict) and exp is not None and state.get("schema") == STATE_SCHEMA
                and all(state.get(k) == v for k, v in exp.items()))

    def run(self) -> None:
        start = time.monotonic_ns()
        k = 0
        period = int(STATE_PERIOD_S * 1e9)
        while not self.stop_flag.is_set():
            a = time.monotonic_ns()
            try:
                raw = self.path.read_text(encoding="utf-8")
            except OSError:
                raw = ""
            b = time.monotonic_ns()
            i = self._index.get(raw)
            if i is None:
                try:
                    parsed: Any = json.loads(raw) if raw else None
                except ValueError:
                    parsed = {"unparsable": raw[:80]}
                i = len(self.states)
                self._index[raw] = i
                self.states.append(parsed)
            self.t0.append(a)
            self.t1.append(b)
            self.idx.append(i)
            ret = self.return_ns
            if ret is not None and a >= ret and not self.confirmed.is_set() and self.matches(self.states[i]):
                self.confirmed.set()
            k += 1
            delay = (start + k * period - time.monotonic_ns()) / 1e9
            if delay > 0:
                time.sleep(delay)

    def stop(self, anchor_ns: int) -> dict[str, Any]:
        self.stop_flag.set()
        self.join(timeout=2)
        return {
            "anchor": "T0 (caller monotonic ns of the first observation send)",
            "anchor_ns": anchor_ns,
            "t0_us": [round((t - anchor_ns) / 1000) for t in self.t0],
            "t1_us": [round((t - anchor_ns) / 1000) for t in self.t1],
            "idx": self.idx,
            "states": self.states,
        }


# ----------------------------------------------------------------------------- client stamps
class Stamps:
    """Caller-side monotonic stamps (no monkeypatching): stream hand-offs, the output-schema
    validation span and (HCL) the lazy compile span."""

    def __init__(self) -> None:
        self.events: list[tuple[str, int, str]] = []  # (kind, mono_ns, detail)

    def add(self, kind: str, detail: str = "") -> None:
        self.events.append((kind, time.monotonic_ns(), detail))

    def window(self, m0: int, m1: int) -> list[tuple[str, int, str]]:
        return [e for e in self.events if m0 <= e[1] <= m1]


class StampedWrite:
    """Delegating wrapper of the session's write stream (as N-02)."""

    def __init__(self, inner: Any, stamps: Stamps) -> None:
        self._inner = inner
        self._stamps = stamps

    async def send(self, item: Any) -> None:
        self._stamps.add("client_send")
        await self._inner.send(item)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> "StampedWrite":
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._inner.__aexit__(*exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class StampedRead:
    """Delegating wrapper of the session's read stream (as N-02)."""

    def __init__(self, inner: Any, stamps: Stamps) -> None:
        self._inner = inner
        self._stamps = stamps

    def __aiter__(self) -> "StampedRead":
        return self

    async def __anext__(self) -> Any:
        item = await self._inner.__anext__()
        self._stamps.add("client_recv")
        return item

    async def receive(self) -> Any:
        item = await self._inner.receive()
        self._stamps.add("client_recv")
        return item

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> "StampedRead":
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._inner.__aexit__(*exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def make_session_class(ClientSession: Any) -> Any:
    class StampedClientSession(ClientSession):  # type: ignore[misc, valid-type]
        """``ClientSession`` with a timed ``_validate_tool_result``. With ``hcl`` set, a result
        is validated by a validator compiled lazily for its tool's current schema object at
        that schema's first use (inside the call), with jsonschema.validate's acceptance rule;
        otherwise the library path runs unchanged. ``equiv_log`` (HCL only) keeps every lazily
        validated result and its verdict for the post-trial library re-check."""

        stamps: Stamps
        hcl: bool = False
        lazy: dict[str, tuple[Any, Any]]
        equiv_log: list[tuple[str, Any, bool, str]] | None = None
        compiles: list[dict[str, Any]]

        async def _validate_tool_result(self, name: str, result: Any) -> None:
            self.stamps.add("validate_start", name)
            try:
                if not self.hcl:
                    await super()._validate_tool_result(name, result)
                else:
                    await self._lazy_validate(name, result)
            finally:
                self.stamps.add("validate_end", name)

        async def _lazy_validate(self, name: str, result: Any) -> None:
            ok, msg = True, ""
            try:
                await self._lazy_validate_inner(name, result)
            except Exception as exc:  # noqa: BLE001 - recorded, then re-raised unchanged
                ok, msg = False, f"{type(exc).__name__}: {exc}"
                raise
            finally:
                if self.equiv_log is not None:
                    self.equiv_log.append((name, result.structuredContent, ok, msg))

        async def _lazy_validate_inner(self, name: str, result: Any) -> None:
            from jsonschema.exceptions import best_match
            from referencing.exceptions import Unresolvable

            if name not in self._tool_output_schemas:
                await self.list_tools()  # the library's refresh rule
            schema = self._tool_output_schemas.get(name)
            if schema is None:
                return
            if result.structuredContent is None:
                raise RuntimeError(f"Tool {name} has an output schema but did not return structured content")
            entry = self.lazy.get(name)
            if entry is None or entry[0] is not schema:
                validator = self._compile(name, schema)
                self.lazy[name] = (schema, validator)
            else:
                validator = entry[1]
            try:
                error = best_match(validator.iter_errors(result.structuredContent))
            except Unresolvable as exc:
                raise RuntimeError(f"Invalid schema for tool {name}: {exc}") from exc
            if error is not None:
                raise RuntimeError(f"Invalid structured content returned by tool {name}: {error}")

        def _compile(self, name: str, schema: Any) -> Any:
            from jsonschema import SchemaError
            from jsonschema.validators import validator_for
            from referencing import Registry

            c0 = time.monotonic_ns()
            self.stamps.add("compile_start", name)
            try:
                cls = validator_for(schema)
                try:
                    cls.check_schema(schema)
                except SchemaError as exc:
                    raise RuntimeError(f"Invalid schema for tool {name}: {exc}") from exc
                return cls(schema, registry=Registry())
            finally:
                self.stamps.add("compile_end", name)
                self.compiles.append({"tool": name, "m0": c0, "ms": (time.monotonic_ns() - c0) / 1e6})

        async def library_recheck(self) -> dict[str, Any]:
            """Post-trial (outside T): the library verdict for every lazily validated result."""
            from mcp import types

            rows = []
            for name, sc, lazy_ok, lazy_msg in self.equiv_log or []:
                result = types.CallToolResult(content=[], structuredContent=sc, isError=False)
                try:
                    await ClientSession._validate_tool_result(self, name, result)
                    ref_ok, ref_msg = True, ""
                except Exception as exc:  # noqa: BLE001
                    ref_ok, ref_msg = False, f"{type(exc).__name__}: {exc}"
                rows.append({"tool": name, "lazy_ok": lazy_ok, "library_ok": ref_ok, "agree": lazy_ok == ref_ok,
                             "same_message": lazy_msg == ref_msg})
            return {"calls": len(rows), "agree": sum(1 for r in rows if r["agree"]),
                    "same_message": sum(1 for r in rows if r["same_message"]),
                    "lazy_rejects": sum(1 for r in rows if not r["lazy_ok"]), "rows": rows}

    return StampedClientSession


# ----------------------------------------------------------------------------- harness
async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402
    from run import Driver, DriverToolError  # noqa: E402

    session_cls = make_session_class(ClientSession)
    sys.setswitchinterval(0.0005)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    block = next(b for b in plan["blocks"] if b["block"] == args.block)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    driver_bin = str(Path(args.driver).resolve())
    fixture_path = str(wt / FIXTURE_REL)
    axfg_path = str(HERE / "fixture_axfg.py")

    pre = xprobe.snapshot()
    meta = {
        "event": "meta", "block": args.block, "kind": block["kind"], "label": args.label,
        "display": os.environ.get("DISPLAY"), "x_clients_at_start": pre["clients"],
        "display_collision": bool(pre["clients"]), "loadavg": loadavg(), "wall_ns": time.time_ns(),
        "driver_bin_name": Path(driver_bin).name, "plan_sha256": args.plan_sha256,
        "driver_sha256": args.driver_sha256, "pid": os.getpid(),
    }
    ledger_path = out / "trials.jsonl"
    ledger = open(ledger_path, "w", encoding="utf-8")
    ledger.write(json.dumps(meta, sort_keys=True) + "\n")
    ledger.flush()
    if meta["display_collision"]:
        for t in block["trials"]:
            ledger.write(json.dumps({"event": "trial", **t, "failure": "display_collision",
                                     "oracle_verified": False, "valid_route": False}) + "\n")
        ledger.write(json.dumps({"event": "end", "failures": len(block["trials"]), "net": NET}) + "\n")
        ledger.close()
        return 3

    decoy = xprobe.Decoy() if block["kind"] == "decoy" else None
    failures = 0
    tools_written = False

    def fixture_command(kind: str, plain: bool = False) -> tuple[list[str], dict[str, str]]:
        fenv = dict(os.environ)
        fenv.pop(AXFG_ENV, None)
        fenv.pop(AXFG_DELAY_ENV, None)
        if kind in ("axfg", "axfg_delay"):
            fenv[AXFG_ENV] = "1"
            return ["/usr/bin/python3", axfg_path, fixture_path], fenv
        if kind == "axfg_smoke" and not plain:
            return ["/usr/bin/python3", axfg_path, fixture_path], fenv  # wrapper, gate off
        return ["/usr/bin/python3", fixture_path], fenv

    def start_fixture_wait(proc: subprocess.Popen, path: Path) -> None:
        deadline = time.monotonic() + 15
        while read_state(path) is None:
            if time.monotonic() > deadline or proc.poll() is not None:
                raise RuntimeError("fixture did not publish its state file")
            time.sleep(0.02)
        time.sleep(1.0)  # AT-SPI registration settle (as R2-04 / N-01R / N-02)

    async def run_trial(t: dict[str, Any]) -> dict[str, Any]:
        nonlocal tools_written
        kind = t["kind"]
        arm = ARMS[t["arm"]]
        traced = arm.get("trace", True)
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": loadavg(),
                               "display": os.environ.get("DISPLAY"), "w_begin": time.time_ns()}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        state_path = tdir / "state.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        cmd, fenv = fixture_command(kind)
        fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
        if kind == "axfg_delay":
            fenv[AXFG_DELAY_ENV] = str(t["variant_ms"])
        rec["fixture_cmd"] = [Path(c).name for c in cmd]
        rec["fixture_env_gate"] = {k: fenv.get(k) for k in (AXFG_ENV, AXFG_DELAY_ENV)}
        fixture_log = open(tdir / "fixture.log", "w", encoding="utf-8")
        fixtures = [subprocess.Popen(cmd, env=fenv, stdout=fixture_log, stderr=subprocess.STDOUT)]
        focus: xprobe.FocusSampler | None = None
        stamps = Stamps()
        session_ref: dict[str, Any] = {}
        tasks_out: list[dict[str, Any]] = []
        rec["tasks"] = tasks_out

        env = driver_environment()
        for key in list(env):
            if key.startswith("CUA_DRIVER_EXP_") or key in ("CUA_DRIVER_PHASE_TRACE_FILE", WCT_ENV, WCP_ENV):
                env.pop(key)
        if traced:
            env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
        env["DO_NOT_TRACK"] = "1"
        env.update(arm["env"])
        rec["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
        rec["driver_env_window_change"] = {k: env[k] for k in (WCT_ENV, WCP_ENV) if k in env}
        rec["driver_env_keys"] = sorted(env)
        rec["traced"] = traced
        rec["hcl"] = arm["hcl"]
        try:
            start_fixture_wait(fixtures[0], state_path)
            rec["before"] = read_state(state_path) or {}
            rec["fixture_pid"] = fixtures[0].pid
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            s0m = time.monotonic_ns()
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with session_cls(StampedRead(read, stamps), StampedWrite(write, stamps)) as session:
                    session.stamps = stamps
                    session.hcl = arm["hcl"]
                    session.lazy = {}
                    session.compiles = []
                    session.equiv_log = [] if arm["hcl"] else None
                    session_ref["s"] = session
                    await session.initialize()
                    lt0 = time.monotonic_ns()
                    tools = await session.list_tools()
                    rec["tools_list_ms"] = (time.monotonic_ns() - lt0) / 1e6
                    tools_json = tools.model_dump(mode="json", by_alias=True, exclude_none=True)
                    rec["tools_list_sha256"] = canonical_sha(tools_json)
                    rec["output_schema_tools"] = sorted(tool.name for tool in tools.tools if tool.outputSchema is not None)
                    if not tools_written:
                        (out / "tools-list.json").write_text(json.dumps(tools_json, indent=1, sort_keys=True) + "\n",
                                                             encoding="utf-8")
                        tools_written = True
                    driver = Driver(session, f"n03-{uuid.uuid4().hex[:8]}")

                    async def find_window(pid: int) -> int:
                        for _ in range(60):
                            wins = (await driver.call("list_windows", {"pid": pid})).get("windows", [])
                            hits = [w for w in wins if w.get("title") == WINDOW_TITLE
                                    and w.get("is_on_screen") is not False]
                            if hits:
                                return int(hits[0]["window_id"])
                            await asyncio.sleep(0.25)
                        raise RuntimeError("task window did not appear")

                    window_id = await find_window(fixtures[0].pid)
                    rec["window_id"] = window_id
                    target = {"pid": fixtures[0].pid, "window_id": window_id}
                    motion = await driver.call("set_agent_cursor_motion",
                                               dict(FAST_MOTION) if arm["fast_cursor"] else {})
                    cstate = await driver.call("get_agent_cursor_state", {})
                    rec["cursor_motion"] = motion.get("motion")
                    rec["cursor_state"] = {k: cstate.get(k) for k in ("enabled", "visible", "motion", "position")
                                           if k in cstate} or {"keys": sorted(cstate)[:20]}
                    rec["session_setup_ms"] = (time.monotonic_ns() - s0m) / 1e6

                    async def timed(name: str, arguments: dict[str, Any], raw: bool = False,
                                    meta: dict[str, Any] | None = None) -> dict[str, Any]:
                        m0, w0 = now()
                        error = None
                        payload: dict[str, Any] = {}
                        content_text: list[str] = []
                        try:
                            if raw:
                                res = await session.call_tool(name, {**arguments, "session": driver.label}, meta=meta)
                                payload = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                                content_text = [getattr(c, "text", "")[:400] for c in (res.content or [])]
                                if res.isError:
                                    error = {"code": payload.get("code"), "is_error": True}
                            else:
                                payload = await driver.call(name, arguments)
                        except DriverToolError as exc:
                            error = {"code": exc.code, "message": str(exc)[:400]}
                        except Exception as exc:  # noqa: BLE001 - protocol errors (McpError) are data here
                            error = {"exception": type(exc).__name__, "message": str(exc)[:400],
                                     "mcp_code": getattr(getattr(exc, "error", None), "code", None)}
                        m1, w1 = now()
                        return {"tool": name, "m0": m0, "w0": w0, "m1": m1, "w1": w1,
                                "wrapper_ms": (m1 - m0) / 1e6, "error": error, "payload": payload,
                                "content_text": content_text,
                                "client_stamps": [[k, v, d] for k, v, d in stamps.window(m0, m1)]}

                    async def observe() -> tuple[dict[str, Any], dict[str, Any]]:
                        c = await timed("get_window_state", {
                            **target, "include_accessibility_tree": True, "include_screenshot": True})
                        p = c.pop("payload")
                        c["summary"] = {k: p.get(k) for k in (
                            "walk_elapsed_ms", "element_count", "nodes_visited", "snapshot_id", "degraded")}
                        c["summary"]["has_screenshot"] = "screenshot_mime_type" in p
                        c["summary"]["payload_json_bytes"] = len(json.dumps(p, separators=(",", ":")))
                        return c, p

                    def lookup(payload: dict[str, Any], labels: list[str]):
                        m0, w0 = now()
                        obs = NativeObservation.from_window_state(payload, expected_pid=target["pid"],
                                                                  expected_window_id=window_id)
                        controls = eligible_controls(obs, "linux").controls
                        found = {}
                        for label in labels:
                            matches = [c for c in controls if c.label == label]
                            found[label] = matches[0].element_token if len(matches) == 1 else None
                        m1, w1 = now()
                        return {"m0": m0, "w0": w0, "m1": m1, "w1": w1, "lookup_ms": (m1 - m0) / 1e6,
                                "found": {k: v is not None for k, v in found.items()}}, found

                    def lookup_axfg(payload: dict[str, Any], label: str):
                        """Part B: the scrolled-out control is off-screen, so eligible_controls (which
                        requires a frame inside the window) excludes it by design; find it in the raw
                        element list by its exact label instead (unique match with a token)."""
                        m0, w0 = now()
                        hits = [e for e in payload.get("elements") or []
                                if isinstance(e, dict) and e.get("label") == label and e.get("element_token")]
                        m1, w1 = now()
                        el = hits[0] if len(hits) == 1 else None
                        info = {"m0": m0, "w0": w0, "m1": m1, "w1": w1, "lookup_ms": (m1 - m0) / 1e6,
                                "hits": len(hits)}
                        if el is not None:
                            info["element"] = {k: el.get(k) for k in el if k not in ("element_token",)}
                        return info, (el or {}).get("element_token")

                    def shape(a: dict[str, Any]) -> dict[str, Any]:
                        p = a.pop("payload")
                        a["structured"] = {k: v for k, v in p.items()
                                           if k not in ("screenshot", "image", "tree", "elements")}
                        return a

                    async def one_task(task_i: int, focus_steal: bool) -> dict[str, Any]:
                        """One measured task: T0 = the first observation's send; T ends at the
                        first oracle sample, at or after the last action's return, that shows the
                        expected app state."""
                        trec: dict[str, Any] = {"task_i": task_i, "loadavg": loadavg()}
                        before = read_state(state_path) or {}
                        trec["before"] = before
                        sampler = StateSampler(state_path)
                        local_focus = None
                        anchor = None
                        try:
                            focus_pre = xprobe.snapshot()
                            if focus_steal:
                                trec["focus_placement"] = xprobe.activate_and_wait(window_id)
                                focus_pre = xprobe.snapshot()
                                local_focus = xprobe.FocusSampler()
                                local_focus.start()
                                assert decoy is not None
                                decoy.arm(str(state_path), int(before["seq"]), float(t["variant_ms"]))
                                trec["decoy_window"] = decoy.window
                            trec["focus_pre"] = {k: focus_pre[k] for k in ("focus", "active")}
                            sampler.start()
                            while not sampler.t0:
                                await asyncio.sleep(0.001)
                            task = t["task"]
                            seq1 = int(before["seq"]) + 1
                            if kind in ("axfg", "axfg_delay"):
                                label = AXFG_LABELS[task]
                                if task == "checkbox":
                                    expected = {"axfg_agreed": not bool(before.get("axfg_agreed")), "seq": seq1}
                                else:
                                    expected = {"axfg_clicks": int(before.get("axfg_clicks") or 0) + 1, "seq": seq1}
                            elif task == "checkbox":
                                expected = {"agreed": not bool(before.get("agreed")), "seq": seq1}
                            else:
                                token = f"n03-{t['id']}-{task_i}-{uuid.uuid4().hex[:6]}"
                                expected = {"note_saved": token, "seq": seq1}
                            sampler.expected = expected
                            trec["expected"] = expected
                            t0m, t0w = now()
                            anchor = t0m
                            trec["T0_m"], trec["T0_w"] = t0m, t0w
                            tree, payload = await observe()
                            trec["tree"] = tree
                            actions: list[dict[str, Any]] = []
                            if kind in ("axfg", "axfg_delay"):
                                lk, tok = lookup_axfg(payload, label)
                                trec["lookup"] = lk
                                if tree["error"] or tok is None:
                                    trec["failure"] = "observe_error" if tree["error"] else "target_not_found"
                                else:
                                    actions.append(shape(await timed("click", {
                                        **target, "element_token": tok, "delivery_mode": "foreground"}, raw=True)))
                            else:
                                labels = {"checkbox": ["I agree"], "text": ["Note", "Save note"]}[task]
                                lk, found = lookup(payload, labels)
                                trec["lookup"] = lk
                                if tree["error"] or not all(found.values()):
                                    trec["failure"] = "observe_error" if tree["error"] else "target_not_found"
                                elif task == "checkbox":
                                    actions.append(shape(await timed("click", {
                                        **target, "element_token": found["I agree"],
                                        "delivery_mode": "background"}, raw=True)))
                                else:
                                    sv = shape(await timed("set_value", {
                                        **target, "element_token": found["Note"], "value": token}))
                                    actions.append(sv)
                                    if sv["error"] is None:
                                        actions.append(shape(await timed("click", {
                                            **target, "element_token": found["Save note"],
                                            "delivery_mode": "background"}, raw=True)))
                            trec["actions"] = actions
                            if actions:
                                sampler.return_ns = actions[-1]["m1"]
                                await asyncio.to_thread(sampler.confirmed.wait, CONFIRM_DEADLINE_S)
                            trec["confirm_wait_end_m"] = time.monotonic_ns()
                            await asyncio.sleep(POST_HOLD_S[kind])
                            trec["focus_post"] = {k: v for k, v in xprobe.snapshot().items() if k in ("focus", "active")}
                        finally:
                            if sampler.is_alive():
                                trec["state_samples"] = sampler.stop(anchor or time.monotonic_ns())
                                trec["confirmed_live"] = sampler.confirmed.is_set()
                            if local_focus is not None:
                                trec["focus_samples"] = local_focus.stop()
                                if anchor is not None:
                                    trec["focus_samples"]["anchor_ns"] = anchor
                            if focus_steal and decoy is not None:
                                trec["decoy"] = decoy.wait()
                        trec["oracle_verified"] = bool(trec.get("confirmed_live")) and "failure" not in trec
                        return trec

                    if kind == "vctl":
                        await vctl_row(rec, session, timed, one_task, tasks_out)
                    elif kind == "axfg_smoke":
                        await axfg_smoke(rec, observe, target, tdir, fixtures, fixture_log, find_window,
                                         start_fixture_wait)
                    else:
                        n_tasks = SESSION_TASKS if kind == "session" else 1
                        for i in range(n_tasks):
                            try:
                                tasks_out.append(await one_task(i, focus_steal=(kind == "decoy")))
                            except Exception as exc:  # retained in the denominator
                                tasks_out.append({"task_i": i, "failure": f"{type(exc).__name__}: {str(exc)[:300]}",
                                                  "oracle_verified": False})
                    if arm["hcl"]:
                        # Post-trial, outside every T: the library verdict for every lazily
                        # validated result of this session.
                        rec["hcl_compiles"] = session.compiles
                        rec["hcl_equivalence"] = await session.library_recheck()
                        if kind == "main" and t.get("round", -1) % 12 == 0:
                            # Corpus of full real results for the offline HC control.
                            with open(out / "hc-corpus.jsonl", "a", encoding="utf-8") as stream:
                                for i, (name, sc, _ok, _msg) in enumerate(session.equiv_log or []):
                                    stream.write(json.dumps({"trial": t["id"], "i": i, "tool": name,
                                                             "structuredContent": sc}, sort_keys=True) + "\n")
                            if "schemas" not in session_ref:
                                session_ref["schemas"] = True
                                (out / "output-schemas.json").write_text(json.dumps(
                                    dict(session._tool_output_schemas), indent=1, sort_keys=True) + "\n",
                                    encoding="utf-8")
        except Exception as exc:  # retained in the denominator
            rec["failure"] = rec.get("failure") or f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            if focus is not None:
                rec["focus_samples"] = focus.stop()
            for proc in fixtures:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            fixture_log.close()
            rec["fixture_log"] = (tdir / "fixture.log").read_text(encoding="utf-8", errors="replace")[-4000:]
            try:
                rec["marks"] = [json.loads(x) for x in phase_path.read_text(encoding="utf-8").splitlines()
                                if x.strip()]
            except (OSError, ValueError) as exc:
                rec["marks"] = []
                rec["marks_error"] = str(exc)
            rec["phase_file_bytes"] = phase_path.stat().st_size if phase_path.exists() else None
            rec["w_end"] = time.time_ns()
        return rec

    async def vctl_row(rec, session, timed, one_task, tasks_out) -> None:
        """V control: the tool set is re-listed mid-session. tools/list A; a modern-era call to an
        unknown tool (admission must refuse it against the inventory); a measured checkbox task;
        tools/list B (re-list); the unknown-tool probe again; a modern-era call to a known tool
        (admitted); a legacy call to a known tool. Run in X and X+V; responses compared."""
        probes = []
        lst_a = await session.list_tools()
        inv_a = canonical_sha(lst_a.model_dump(mode="json", by_alias=True, exclude_none=True))
        probes.append({"step": "unknown_modern_1", **_probe(await timed("n03_not_a_tool", {}, raw=True,
                                                                        meta=MODERN_META))})
        tasks_out.append(await one_task(0, focus_steal=False))
        lst_b = await session.list_tools()
        inv_b = canonical_sha(lst_b.model_dump(mode="json", by_alias=True, exclude_none=True))
        probes.append({"step": "unknown_modern_2", **_probe(await timed("n03_not_a_tool", {}, raw=True,
                                                                        meta=MODERN_META))})
        probes.append({"step": "known_modern", **_probe(await timed("get_agent_cursor_state", {}, raw=True,
                                                                    meta=MODERN_META))})
        probes.append({"step": "known_legacy", **_probe(await timed("get_agent_cursor_state", {}, raw=True))})
        rec["vctl"] = {"inventory_a": inv_a, "inventory_b": inv_b, "relist_identical": inv_a == inv_b,
                       "tools_a": len(lst_a.tools), "tools_b": len(lst_b.tools), "probes": probes}

    def _probe(call: dict[str, Any]) -> dict[str, Any]:
        err = call.get("error") or {}
        payload = call.get("payload") or {}
        return {"error": err or None, "ok": not err, "payload_keys": sorted(payload)[:20],
                "content_text": call.get("content_text"), "wrapper_ms": call.get("wrapper_ms"),
                "m0": call.get("m0"), "m1": call.get("m1")}

    async def axfg_smoke(rec, observe, target, tdir, fixtures, fixture_log, find_window, start_fixture_wait) -> None:
        """Default-off fixture smoke: the wrapper with CUA_N03_AXFG unset must show the same
        window (element labels/roles) and the same state keys as the repository fixture."""
        _, p1 = await observe()
        wrap = {"labels": sorted({f"{e.get('role')}|{e.get('label')}" for e in p1.get("elements") or []}),
                "state_keys": sorted((read_state(tdir / "state.json") or {}).keys())}
        fixtures[0].terminate()
        fixtures[0].wait(timeout=5)
        plain_state = tdir / "state-plain.json"
        cmd, fenv = fixture_command("axfg_smoke", plain=True)
        fenv["CUA_GTK3_TASK_STATE"] = str(plain_state)
        proc = subprocess.Popen(cmd, env=fenv, stdout=fixture_log, stderr=subprocess.STDOUT)
        fixtures.append(proc)
        start_fixture_wait(proc, plain_state)
        wid = await find_window(proc.pid)
        target_plain = {"pid": proc.pid, "window_id": wid}
        target.clear()
        target.update(target_plain)
        _, p2 = await observe()
        plain = {"labels": sorted({f"{e.get('role')}|{e.get('label')}" for e in p2.get("elements") or []}),
                 "state_keys": sorted((read_state(plain_state) or {}).keys())}
        rec["axfg_smoke"] = {"wrapper_gate_off": wrap, "repository": plain,
                             "identical": wrap == plain,
                             "hidden_controls_absent": not any("Hidden" in x for x in wrap["labels"])}
        rec["oracle_verified"] = rec["axfg_smoke"]["identical"] and rec["axfg_smoke"]["hidden_controls_absent"]

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            tasks = r.get("tasks") or []
            if r["kind"] == "axfg_smoke":
                ok = bool(r.get("oracle_verified")) and "failure" not in r
            elif r["kind"] == "vctl":
                ok = ("failure" not in r and len(tasks) == 1 and tasks[0].get("oracle_verified")
                      and bool((r.get("vctl") or {}).get("relist_identical")))
            else:
                want = SESSION_TASKS if r["kind"] == "session" else 1
                ok = "failure" not in r and len(tasks) == want and all(x.get("oracle_verified") for x in tasks)
            r["oracle_verified"] = bool(ok)
            failures += 0 if ok else 1
            ledger.write(json.dumps(r, sort_keys=True) + "\n")
            ledger.flush()
    finally:
        if decoy is not None:
            decoy.close()
        ledger.write(json.dumps({"event": "end", "failures": failures, "loadavg": loadavg(),
                                 "wall_ns": time.time_ns(), "net": NET}, sort_keys=True) + "\n")
        ledger.close()
    print(f"done: {ledger_path} failures={failures} net_refused={NET['refused_non_loopback_connects']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wt", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--block", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()
    host_runtime = Path(f"/run/user/{os.getuid()}")
    names = sorted(p.name for p in host_runtime.iterdir()) if host_runtime.is_dir() else []
    # hostless-strict masks the host runtime dir: the host's Wayland/Hyprland/session-bus
    # sockets must not be visible there.
    host_sockets = [n for n in names if n.startswith(("wayland-", "hypr", "pipewire"))
                    or n in ("bus", "at-spi", "systemd")]
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY") or host_sockets
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith("/run/user")):
        raise SystemExit(f"refusing: not inside hostless + the isolated X11 session ({host_sockets})")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

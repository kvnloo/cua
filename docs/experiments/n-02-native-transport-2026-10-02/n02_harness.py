#!/usr/bin/env python3
"""N-02: native MCP transport attribution + causal A/B of caller-compiled output
validators (HC) and the focus-guard settle-overshoot clamp (CL), on the canonical
GTK3 task fixture (measurement only).

Derived from the N-01R harness (``../n-01r-native-wait-ab-2026-10-02/n01r_harness.py``,
blob bc79513f8b9a): same fixture, task window, observation call, jev-use
``eligible_controls`` lookup, forced background element-token AT-SPI route,
independent 2 ms state-file oracle, fresh Driver + fresh fixture per trial, and the
same X focus sampler / decoy (``xprobe.py``, verbatim). Changes for N-02
(pre-registered in PREREG.json):

* client-side marks without monkeypatching: ``StampedClientSession`` is a
  ``ClientSession`` subclass whose ``_validate_tool_result`` override stamps the
  validation span (and, in HC arms, validates with validators compiled once at
  tools/list, outside T); the session's read/write memory streams are wrapped by
  delegating objects that stamp the hand-off of each outgoing message and the
  arrival of each parsed incoming message;
* every arm calls ``tools/list`` once before T (so the schema cache is filled the
  same way in every arm), and records its output schemas;
* arms: S0 / S0+HC / S0+CL / S0+HC+CL (checkbox), X / X+HC / X+CL / X+HC+CL (text);
  CL = ``CUA_DRIVER_EXP_FOCUS_GUARD_CLAMP=1``;
* controls: decoy focus steal at 100 ms, edge steal at 205-215 ms (both after the
  app's state change), and a no-steal control with the decoy mapped and the focus
  sampler running;
* a small corpus of full structuredContent results is kept for the offline HC
  equivalence control (``hc_equivalence.py``).

Runs INSIDE cua-x11-session.sh with a private AT-SPI bus. It refuses to run
otherwise. No provider is used: any non-loopback TCP connect from this process is
refused and counted.
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
CLAMP_ENV = "CUA_DRIVER_EXP_FOCUS_GUARD_CLAMP"
ARMS: dict[str, dict[str, Any]] = {
    "S0": {"fast_cursor": False, "hc": False, "env": {SLEEP_ENV: "0"}},
    "S0+HC": {"fast_cursor": False, "hc": True, "env": {SLEEP_ENV: "0"}},
    "S0+CL": {"fast_cursor": False, "hc": False, "env": {SLEEP_ENV: "0", CLAMP_ENV: "1"}},
    "S0+HC+CL": {"fast_cursor": False, "hc": True, "env": {SLEEP_ENV: "0", CLAMP_ENV: "1"}},
    "X": {"fast_cursor": True, "hc": False, "env": {SLEEP_ENV: "0"}},
    "X+HC": {"fast_cursor": True, "hc": True, "env": {SLEEP_ENV: "0"}},
    "X+CL": {"fast_cursor": True, "hc": False, "env": {SLEEP_ENV: "0", CLAMP_ENV: "1"}},
    "X+HC+CL": {"fast_cursor": True, "hc": True, "env": {SLEEP_ENV: "0", CLAMP_ENV: "1"}},
    # default-off smoke: no knob at all (N2 binary with every CUA_DRIVER_EXP_* unset)
    "D": {"fast_cursor": False, "hc": False, "env": {}},
}
FAST_MOTION = {"glide_duration_ms": 1, "dwell_after_click_ms": 0}
STATE_PERIOD_S = 0.002
CONFIRM_DEADLINE_S = 3.0
POST_HOLD_S = {"main": 0.15, "smoke": 0.15, "decoy": 0.7, "edge": 0.7, "nosteal": 0.7}
STEAL_KINDS = ("decoy", "edge", "nosteal")
CORPUS_TOOLS = ("list_windows", "set_agent_cursor_motion", "get_agent_cursor_state",
                "get_window_state", "click", "set_value")

# ----------------------------------------------------------------------------- no provider
NET = {"refused_non_loopback_connects": 0, "targets": []}
_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            NET["refused_non_loopback_connects"] += 1
            NET["targets"].append(str(host)[:64])
            raise ConnectionRefusedError("N-02: provider cap 0, non-loopback connect refused")
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


def schema_key(schema: Any) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class StateSampler(threading.Thread):
    """Independent oracle (as N-01R): reads the app's own state file every 2 ms."""

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
            "t0_us": [round((t - anchor_ns) / 1000) for t in self.t0],
            "t1_us": [round((t - anchor_ns) / 1000) for t in self.t1],
            "idx": self.idx,
            "states": self.states,
        }


# ----------------------------------------------------------------------------- client stamps
class Stamps:
    """Caller-side monotonic stamps (no monkeypatching): stream hand-offs and the
    output-schema validation span."""

    def __init__(self) -> None:
        self.events: list[tuple[str, int, str]] = []  # (kind, mono_ns, detail)

    def add(self, kind: str, detail: str = "") -> None:
        self.events.append((kind, time.monotonic_ns(), detail))

    def window(self, m0: int, m1: int) -> list[tuple[str, int, str]]:
        return [e for e in self.events if m0 <= e[1] <= m1]


class StampedWrite:
    """Delegating wrapper of the session's write stream: stamps each hand-off of
    an outgoing message to mcp's stdio writer task (before its JSON dump and pipe
    write)."""

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
    """Delegating wrapper of the session's read stream: stamps the arrival of each
    message already read from the pipe and JSON-parsed by mcp's stdio reader task."""

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
        """``ClientSession`` with a timed ``_validate_tool_result``. With
        ``compiled`` set (HC arms) a result is validated by the validator compiled
        at tools/list for its schema, with jsonschema.validate's acceptance rule
        (validator_for + check_schema at compile time; best_match over
        iter_errors); without it, the library path runs unchanged."""

        stamps: Stamps
        compiled: dict[str, Any] | None = None

        async def _validate_tool_result(self, name: str, result: Any) -> None:
            self.stamps.add("validate_start", name)
            try:
                if self.compiled is None:
                    await super()._validate_tool_result(name, result)
                else:
                    await self._compiled_validate(name, result)
            finally:
                self.stamps.add("validate_end", name)

        async def _compiled_validate(self, name: str, result: Any) -> None:
            from jsonschema.exceptions import best_match

            if name not in self._tool_output_schemas:
                await self.list_tools()
            schema = self._tool_output_schemas.get(name)
            if schema is None:
                return
            if result.structuredContent is None:
                raise RuntimeError(f"Tool {name} has an output schema but did not return structured content")
            validator = (self.compiled or {}).get(schema_key(schema))
            if validator is None:  # not compiled at tools/list: library path
                await super()._validate_tool_result(name, result)
                return
            error = best_match(validator.iter_errors(result.structuredContent))
            if error is not None:
                raise RuntimeError(f"Invalid structured content returned by tool {name}: {error}")

        def compile_output_validators(self) -> int:
            from jsonschema.validators import validator_for
            from referencing import Registry

            compiled: dict[str, Any] = {}
            for schema in self._tool_output_schemas.values():
                if schema is None:
                    continue
                key = schema_key(schema)
                if key not in compiled:
                    cls = validator_for(schema)
                    cls.check_schema(schema)
                    compiled[key] = cls(schema, registry=Registry())
            self.compiled = compiled
            return len(compiled)

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

    decoy = xprobe.Decoy() if block["kind"] in STEAL_KINDS else None
    failures = 0
    schemas_written = False

    async def run_trial(t: dict[str, Any]) -> dict[str, Any]:
        nonlocal schemas_written
        kind = t["kind"]
        arm = ARMS[t["arm"]]
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": loadavg(),
                               "display": os.environ.get("DISPLAY"), "w_begin": time.time_ns()}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        state_path = tdir / "state.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        fenv = dict(os.environ)
        fenv["CUA_GTK3_TASK_STATE"] = str(state_path)
        cmd = ["/usr/bin/python3", fixture_path]
        fixture_log = open(tdir / "fixture.log", "w", encoding="utf-8")
        fixtures = [subprocess.Popen(cmd, env=fenv, stdout=fixture_log, stderr=subprocess.STDOUT)]
        sampler: StateSampler | None = None
        focus: xprobe.FocusSampler | None = None
        anchor = None
        stamps = Stamps()
        corpus: list[dict[str, Any]] = []
        keep_corpus = bool(t.get("corpus"))

        def start_fixture_wait(proc: subprocess.Popen, path: Path) -> None:
            deadline = time.monotonic() + 15
            while read_state(path) is None:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise RuntimeError("fixture did not publish its state file")
                time.sleep(0.02)
            time.sleep(1.0)  # AT-SPI registration settle (as R2-04 / N-01R)

        env = driver_environment()
        for key in list(env):
            if key.startswith("CUA_DRIVER_EXP_") or key == "CUA_DRIVER_PHASE_TRACE_FILE":
                env.pop(key)
        env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
        env["DO_NOT_TRACK"] = "1"
        env.update(arm["env"])
        rec["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
        rec["driver_env_keys"] = sorted(env)
        rec["hc"] = arm["hc"]
        try:
            start_fixture_wait(fixtures[0], state_path)
            before = read_state(state_path) or {}
            rec["before"] = before
            rec["fixture_pid"] = fixtures[0].pid
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with session_cls(StampedRead(read, stamps), StampedWrite(write, stamps)) as session:
                    session.stamps = stamps
                    await session.initialize()
                    # Every arm lists the tools before T (fills the output-schema cache the
                    # same way); HC arms compile one validator per schema here, outside T.
                    lt0 = time.monotonic_ns()
                    tools = await session.list_tools()
                    lt1 = time.monotonic_ns()
                    rec["tools_list_ms"] = (lt1 - lt0) / 1e6
                    rec["output_schema_tools"] = sorted(
                        tool.name for tool in tools.tools if tool.outputSchema is not None)
                    if not schemas_written:
                        schemas = {tool.name: tool.outputSchema for tool in tools.tools
                                   if tool.name in CORPUS_TOOLS}
                        (out / "output-schemas.json").write_text(json.dumps(schemas, indent=1, sort_keys=True) + "\n",
                                                                 encoding="utf-8")
                        schemas_written = True
                    if arm["hc"]:
                        c0 = time.monotonic_ns()
                        rec["compiled_validators"] = session.compile_output_validators()
                        rec["compile_ms"] = (time.monotonic_ns() - c0) / 1e6
                    driver = Driver(session, f"n02-{uuid.uuid4().hex[:8]}")

                    async def keep(name: str, payload: Any) -> None:
                        if keep_corpus and name in CORPUS_TOOLS and isinstance(payload, dict):
                            corpus.append({"tool": name, "structuredContent": payload})

                    async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                        payload = await driver.call(name, arguments)
                        await keep(name, payload)
                        return payload

                    async def find_window(pid: int) -> int:
                        for _ in range(60):
                            wins = (await call("list_windows", {"pid": pid})).get("windows", [])
                            hits = [w for w in wins if w.get("title") == WINDOW_TITLE
                                    and w.get("is_on_screen") is not False]
                            if hits:
                                return int(hits[0]["window_id"])
                            await asyncio.sleep(0.25)
                        raise RuntimeError("task window did not appear")

                    window_id = await find_window(fixtures[0].pid)
                    rec["window_id"] = window_id
                    target = {"pid": fixtures[0].pid, "window_id": window_id}
                    motion = await call("set_agent_cursor_motion",
                                        dict(FAST_MOTION) if arm["fast_cursor"] else {})
                    cstate = await call("get_agent_cursor_state", {})
                    rec["cursor_motion"] = motion.get("motion")
                    rec["cursor_state"] = {k: cstate.get(k) for k in ("enabled", "visible", "motion", "position")
                                           if k in cstate} or {"keys": sorted(cstate)[:20]}

                    async def timed(name: str, arguments: dict[str, Any], raw: bool = False) -> dict[str, Any]:
                        m0, w0 = now()
                        error = None
                        payload: dict[str, Any] = {}
                        content_text: list[str] = []
                        try:
                            if raw:
                                res = await session.call_tool(name, {**arguments, "session": driver.label})
                                payload = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                                content_text = [getattr(c, "text", "")[:400] for c in (res.content or [])]
                                if res.isError:
                                    error = {"code": payload.get("code"), "is_error": True}
                            else:
                                payload = await driver.call(name, arguments)
                        except DriverToolError as exc:
                            error = {"code": exc.code, "message": str(exc)[:400]}
                        m1, w1 = now()
                        await keep(name, payload)
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
                        c["summary"]["payload_keys"] = sorted(p)[:40]
                        c["summary"]["payload_json_bytes"] = len(json.dumps(p, separators=(",", ":")))
                        return c, p

                    def lookup(payload: dict[str, Any], labels: list[str], pid: int, wid: int):
                        m0, w0 = now()
                        obs = NativeObservation.from_window_state(payload, expected_pid=pid, expected_window_id=wid)
                        controls = eligible_controls(obs, "linux").controls
                        found = {}
                        for label in labels:
                            matches = [c for c in controls if c.label == label]
                            found[label] = matches[0] if len(matches) == 1 else None
                        m1, w1 = now()
                        return {"m0": m0, "w0": w0, "m1": m1, "w1": w1, "lookup_ms": (m1 - m0) / 1e6,
                                "found": {k: v is not None for k, v in found.items()}}, found

                    def shape(a: dict[str, Any]) -> dict[str, Any]:
                        p = a.pop("payload")
                        a["structured"] = {k: v for k, v in p.items()
                                           if k not in ("screenshot", "image", "tree", "elements")}
                        return a

                    focus_pre = xprobe.snapshot()
                    if kind in STEAL_KINDS:
                        rec["focus_placement"] = xprobe.activate_and_wait(window_id)
                        focus_pre = xprobe.snapshot()
                        focus = xprobe.FocusSampler()
                        focus.start()
                        assert decoy is not None
                        if kind != "nosteal":
                            decoy.arm(str(state_path), int(before["seq"]), float(t["variant_ms"]))
                        rec["decoy_window"] = decoy.window
                    rec["focus_pre"] = {k: focus_pre[k] for k in ("focus", "active")}
                    sampler = StateSampler(state_path)
                    sampler.start()
                    while not sampler.t0:
                        await asyncio.sleep(0.001)
                    task = t["task"]
                    labels = {"checkbox": ["I agree"], "text": ["Note", "Save note"]}[task]
                    if task == "checkbox":
                        expected = {"agreed": not bool(before.get("agreed")), "seq": int(before["seq"]) + 1}
                    else:
                        token = f"n02-{t['id']}-{uuid.uuid4().hex[:6]}"
                        expected = {"note_saved": token, "seq": int(before["seq"]) + 1}
                    sampler.expected = expected
                    rec["expected"] = expected

                    t0m, t0w = now()
                    anchor = t0m
                    rec["T0_m"], rec["T0_w"] = t0m, t0w
                    tree, payload = await observe()
                    rec["tree"] = tree
                    lk, found = lookup(payload, labels, fixtures[0].pid, window_id)
                    rec["lookup"] = lk
                    actions: list[dict[str, Any]] = []
                    if tree["error"] or not all(found.values()):
                        rec["failure"] = "observe_error" if tree["error"] else "target_not_found"
                    elif task == "checkbox":
                        actions.append(shape(await timed("click", {
                            **target, "element_token": found["I agree"].element_token,
                            "delivery_mode": "background"}, raw=True)))
                    else:
                        sv = shape(await timed("set_value", {
                            **target, "element_token": found["Note"].element_token, "value": token}))
                        actions.append(sv)
                        if sv["error"] is None:
                            actions.append(shape(await timed("click", {
                                **target, "element_token": found["Save note"].element_token,
                                "delivery_mode": "background"}, raw=True)))
                    rec["actions"] = actions
                    if actions:
                        sampler.return_ns = actions[-1]["m1"]
                        await asyncio.to_thread(sampler.confirmed.wait, CONFIRM_DEADLINE_S)
                    await asyncio.sleep(POST_HOLD_S[kind])
                    rec["focus_post"] = {k: v for k, v in xprobe.snapshot().items() if k in ("focus", "active")}
        except Exception as exc:  # retained in the denominator
            rec["failure"] = rec.get("failure") or f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            if sampler is not None:
                rec["state_samples"] = sampler.stop(anchor or time.monotonic_ns())
                rec["confirmed_live"] = sampler.confirmed.is_set()
            if focus is not None:
                rec["focus_samples"] = focus.stop()
                if anchor is not None:
                    rec["focus_samples"]["anchor_ns"] = anchor
            if decoy is not None and kind in ("decoy", "edge"):
                rec["decoy"] = decoy.wait()
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
            if corpus:
                with open(out / "hc-corpus.jsonl", "a", encoding="utf-8") as stream:
                    for i, item in enumerate(corpus):
                        stream.write(json.dumps({"trial": t["id"], "i": i, **item}, sort_keys=True) + "\n")
                rec["corpus_items"] = len(corpus)
            rec["w_end"] = time.time_ns()
        return rec

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            r["oracle_verified"] = bool(r.get("confirmed_live")) and "failure" not in r
            failures += 0 if r.get("oracle_verified") else 1
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
    # hostless(-strict) masks the host runtime dir: the host's Wayland/Hyprland/
    # session-bus sockets must not be visible there.
    host_sockets = [n for n in names if n.startswith(("wayland-", "hypr", "pipewire"))
                    or n in ("bus", "at-spi", "systemd")]
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY") or host_sockets
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith("/run/user")):
        raise SystemExit(f"refusing: not inside hostless + the isolated X11 session ({host_sockets})")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

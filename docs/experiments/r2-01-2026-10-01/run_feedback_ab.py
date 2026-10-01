"""R2-01 feedback/cursor A/B trial runner (measurement only).

Run inside the isolated X11 session with the jev-use virtualenv:

    <jev-use>/.venv/bin/python run_feedback_ab.py --driver <bin> --out <dir> \
        --pairs 24 [--shakedown] [--controls]

Each trial mirrors ``python/run.py`` (mock provider) and reuses its functions:
fresh ``cua-driver mcp`` process, arm toggle, browser_prepare isolated_new,
wait_for_window, bind, navigate, step 1 browser_type, step 2 browser_click
(input_route=dom_event), then the runner's completion loop. Every caller
phase is stamped with ``time.monotonic_ns()``; the Driver writes its own
CLOCK_MONOTONIC marks to a per-trial file through CUA_DRIVER_PHASE_TRACE_FILE.
The fixture journal (a FixtureState subclass) stamps the POST /submit
mutation on the same clock. The oracle is the fixture's /state endpoint.
Output paths are written relative to --out; no absolute paths are recorded.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

JEV = Path(os.environ.get("JEV_USE_DIR", "")).resolve()
sys.path.insert(0, str(JEV))
sys.path.insert(0, str(JEV / "python"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from core import validate_choice  # noqa: E402
from driver_env import driver_environment  # noqa: E402
from fixture_server import FixtureServer, FixtureState  # noqa: E402
from jev_adapter import choose_mock_for_task  # noqa: E402
from run import (  # noqa: E402
    Driver,
    select_tab_id,
    supports_capture_bound_click,
    task_candidates_for_step,
    wait_for_window,
)
from tasks import FixtureFormTask, fixture_state, reset_fixture  # noqa: E402

TRACE_ENV = "CUA_DRIVER_PHASE_TRACE_FILE"


def now() -> int:
    return time.monotonic_ns()


def token_digest(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:16]


class JournalState(FixtureState):
    """Fixture state that journals every mutation on CLOCK_MONOTONIC."""

    def __init__(self) -> None:
        super().__init__()
        self.journal: list[dict[str, Any]] = []
        self._jlock = threading.Lock()

    def submit(self, value: str) -> None:
        t = now()
        super().submit(value)
        with self._jlock:
            self.journal.append({"event": "submit", "t_mono_ns": t, "value_sha16": token_digest(value)})

    def reset(self) -> None:
        t = now()
        super().reset()
        with self._jlock:
            self.journal.append({"event": "reset", "t_mono_ns": t})

    def drain(self) -> list[dict[str, Any]]:
        with self._jlock:
            out, self.journal = self.journal, []
        return out


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
    rec.add("call_return", label=label, tool=tool, ok=True,
            route=result.get("route"), effect=result.get("effect"), status=result.get("status"))
    return result


def oracle_read(rec: Recorder, url: str, label: str) -> str | None:
    rec.add("oracle_send", label=label)
    submitted = fixture_state(url).get("submitted")
    rec.add("oracle_return", label=label, submitted_sha16=token_digest(submitted))
    return submitted


async def open_driver(driver_bin: str, trace_path: Path):
    env = driver_environment()
    env[TRACE_ENV] = str(trace_path)
    params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
    return stdio_client(params)


def loadavg() -> str:
    try:
        return Path("/proc/loadavg").read_text().strip()
    except OSError:
        return "unavailable"


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


async def run_trial(kind: str, arm: str, driver_bin: str, fixture_url: str, trace_path: Path,
                    rec: Recorder) -> dict[str, Any]:
    """kind: measured | no_submit | stale_ref."""
    token = f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-r201-{uuid.uuid4().hex[:8]}"
    task = FixtureFormTask(token, fixture_url, 4)
    result: dict[str, Any] = {"token_sha16": token_digest(token), "session_label": label,
                              "outcome": "unknown", "forced_path_ok": None}
    reset_fixture(fixture_url)
    rec.add("trial_start", arm=arm, kind=kind)
    prepared_pid: int | None = None
    async with await open_driver(driver_bin, trace_path) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            available = {tool.name for tool in tools}
            capture_bound = supports_capture_bound_click(tools)
            driver = Driver(session, label)
            await timed_call(rec, driver, "arm_toggle", "set_agent_cursor_enabled",
                             {"enabled": arm == "ON"})
            prepared = await timed_call(rec, driver, "prepare", "browser_prepare",
                                        {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            prepared_pid = int(prepared["prepared_pid"])
            result["prepared_pid"] = prepared_pid
            rec.add("wait_window_start")
            window = await wait_for_window(driver, prepared_pid)
            rec.add("wait_window_end")
            bound = await timed_call(rec, driver, "bind", "get_browser_state",
                                     {"pid": prepared_pid, "window_id": window["window_id"]})
            target_id = bound["target_id"]
            tab_id = select_tab_id(bound["tabs"])
            await timed_call(rec, driver, "navigate", "browser_navigate",
                             {"target_id": target_id, "tab_id": tab_id, "url": fixture_url})

            async def step(n: int) -> tuple[Any, dict[str, Any]]:
                oracle_read(rec, fixture_url, f"pre_step{n}")
                snap = await timed_call(rec, driver, f"snapshot{n}", "get_browser_state",
                                        {"target_id": target_id, "tab_id": tab_id,
                                         "snapshot_format": "semantic_v2"})
                candidates, sources, _ = await task_candidates_for_step(
                    driver, task, snap, prepared_pid, int(window["window_id"]), available,
                    capture_bound, visual_mode="auto")
                choice, _, _ = choose_mock_for_task(task, sources, candidates, [])
                cand = validate_choice(choice, candidates, current_capture_id=None)
                rec.add("decided", step=n, candidate=cand.id, tool=cand.tool,
                        input_route=(cand.arguments or {}).get("input_route"))
                return cand, snap

            cand1, _ = await step(1)
            if cand1.tool != "browser_type":
                result["forced_path_ok"] = False
                result["outcome"] = "forced_path_violation"
                return result
            try:
                await timed_call(rec, driver, "type", cand1.tool, cand1.arguments)
            except Exception:
                result["outcome"] = "unknown"
                return result

            if kind == "no_submit":
                await asyncio.sleep(1.0)
                submitted = oracle_read(rec, fixture_url, "no_submit_check")
                result["outcome"] = "unchanged" if submitted is None else "unexpected_submit"
                result["forced_path_ok"] = True
                return result

            cand2, snap2 = await step(2)
            forced = cand2.tool == "browser_click" and cand2.arguments.get("input_route") == "dom_event"
            result["forced_path_ok"] = forced
            if not forced:
                result["outcome"] = "forced_path_violation"
                return result

            if kind == "stale_ref":
                await timed_call(rec, driver, "renavigate", "browser_navigate",
                                 {"target_id": target_id, "tab_id": tab_id, "url": fixture_url})
                rec.add("call_send", label="stale_click", tool="browser_click")
                raw = await session.call_tool("browser_click", {**cand2.arguments, "session": label})
                structured = raw.structuredContent if isinstance(raw.structuredContent, dict) else {}
                refusal = structured.get("refusal") if isinstance(structured.get("refusal"), dict) else {}
                code = structured.get("code") or refusal.get("code")
                refused = bool(raw.isError) or structured.get("status") == "refused" or bool(refusal) \
                    or structured.get("effect") == "refused"
                rec.add("call_return", label="stale_click", tool="browser_click", ok=not refused,
                        is_error=bool(raw.isError), status=structured.get("status"),
                        effect=structured.get("effect"), code=code)
                await asyncio.sleep(1.0)
                submitted = oracle_read(rec, fixture_url, "stale_check")
                result["stale_refused"] = refused
                result["stale_code"] = code
                result["outcome"] = "refused_unchanged" if (refused and submitted is None) else "control_failed"
                return result

            try:
                await timed_call(rec, driver, "click", cand2.tool, cand2.arguments)
            except Exception:
                result["outcome"] = "unknown"
                return result
            for i in range(20):
                submitted = oracle_read(rec, fixture_url, f"verify{i}")
                outcome = task.classify({"submitted": submitted}, steps=2)
                if outcome in {"verified", "refuted"}:
                    result["outcome"] = outcome
                    break
                await asyncio.sleep(0.1)
            else:
                result["outcome"] = task.classify({"submitted": fixture_state(fixture_url).get("submitted")}, steps=4)
    rec.add("driver_closed")
    return result


async def one(kind: str, arm: str, idx: str, args: argparse.Namespace, url: str,
              state: JournalState, out: Path) -> dict[str, Any]:
    name = f"{idx}-{kind}-{arm}"
    trace_rel = f"trials/{name}.driver-trace.jsonl"
    trace_path = out / trace_rel
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    rec = Recorder()
    record: dict[str, Any] = {"trial": name, "kind": kind, "arm": arm, "loadavg_before": loadavg(),
                              "driver_trace": trace_rel}
    t0 = now()
    try:
        res = await asyncio.wait_for(run_trial(kind, arm, args.driver, url, trace_path, rec), timeout=180)
    except Exception as error:
        res = {"outcome": "error", "error": f"{type(error).__name__}: {str(error)[:300]}"}
    record["trial_wall_ns"] = now() - t0
    pid = res.pop("prepared_pid", None)
    alive = pid_alive(pid)
    for _ in range(50):
        if not alive:
            break
        await asyncio.sleep(0.1)
        alive = pid_alive(pid)
    record["browser_alive_after_close"] = alive
    await asyncio.sleep(0.3)
    record.update(res)
    record["journal"] = state.drain()
    record["loadavg_after"] = loadavg()
    with (out / f"trials/{name}.jsonl").open("w") as f:
        for ev in rec.events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
        f.write(json.dumps({"event": "summary", **record}, sort_keys=True) + "\n")
    print(json.dumps({k: record.get(k) for k in ("trial", "outcome", "forced_path_ok", "loadavg_before")}), flush=True)
    return record


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    state = JournalState()
    server = FixtureServer(("127.0.0.1", 0))
    server.state = state
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    plan: list[tuple[str, str, str]] = []
    if args.shakedown:
        plan += [("measured", "ON", "s00"), ("measured", "OFF", "s01")]
    for k in range(args.pairs):
        order = ("ON", "OFF") if k % 2 == 0 else ("OFF", "ON")
        for j, arm in enumerate(order):
            plan.append(("measured", arm, f"p{k:02d}{'ab'[j]}"))
    if args.controls:
        for i, arm in enumerate(["ON", "OFF", "OFF", "ON"]):
            plan.append(("no_submit", arm, f"c{i:02d}"))
        for i, arm in enumerate(["OFF", "ON", "ON", "OFF"]):
            plan.append(("stale_ref", arm, f"c{i + 4:02d}"))
    manifest = {"plan": [list(p) for p in plan], "started_mono_ns": now(), "loadavg_start": loadavg()}
    try:
        for kind, arm, idx in plan:
            await one(kind, arm, idx, args, url, state, out)
    finally:
        manifest["ended_mono_ns"] = now()
        manifest["loadavg_end"] = loadavg()
        (out / "run-manifest.json").write_text(json.dumps(manifest, indent=1))
        server.shutdown()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--pairs", type=int, default=0)
    p.add_argument("--shakedown", action="store_true")
    p.add_argument("--controls", action="store_true")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

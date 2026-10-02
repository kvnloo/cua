"""Frozen scripted caller for the autoresearch pilot (no provider of any kind).

One call of :func:`run_trial` spawns ONE fresh Driver (through ``sandbox-driver.sh``),
drives one trial of one kind against the GTK3 task fixture, and returns a raw row
(``ar.trial.v1``). The clock is the harness ``CLOCK_MONOTONIC`` (``time.monotonic_ns``):

    T = t_done - t_spawn

``t_spawn`` is taken immediately before the Driver process is spawned; ``t_done`` is the
first instant the caller has *verified* the outcome against the fixture's own state file
(the oracle). The state file's mtime (``CLOCK_REALTIME``) is mapped onto the monotonic clock
with a back-to-back (monotonic, wall) pair, and the row records whether that journal
mutation time is <= ``t_done``.

Kinds:
  task               observe -> lookup "I agree" -> click(element_token, background) -> verify
  stale_negative     observe -> keep token -> observe again -> click old token: must be refused,
                     no mutation
  impossible_canary  click a fabricated element token: must be refused (or unknown), never a
                     claimed success, no mutation
  spot_gtk3_text     observe -> lookup "Note" + "Save note" -> set_value(unique) -> click(Save) ->
                     verify note_saved

Nothing here changes Driver behaviour. The Driver sees only what ``driver_environment()``
forwards, minus whatever the sandbox drops.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

WINDOW_TITLE = "CuaTestHarness GTK3 Tasks"
STATE_SCHEMA = "cua.gtk3_task_state_v1"
VERIFY_DEADLINE_S = 5.0
SETTLE_AFTER_S = 0.3
POLL_S = 0.0005
TRACE_ENV = "CUA_DRIVER_PHASE_TRACE_FILE"


def read_state(path: Path) -> tuple[dict[str, Any] | None, int | None]:
    try:
        st = os.stat(path)
        return json.loads(path.read_text(encoding="utf-8")), st.st_mtime_ns
    except (OSError, ValueError):
        return None, None


def loadavg() -> list[float]:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return [float(x) for x in stream.read().split()[:3]]


# ----------------------------------------------------------------------------- footprint
def _children_map() -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="ascii", errors="replace") as stream:
                fields = stream.read().rsplit(")", 1)[1].split()
            children.setdefault(int(fields[1]), []).append(int(entry))
        except (OSError, IndexError, ValueError):
            continue
    return children


def _descendants(root: int, children: dict[int, list[int]]) -> list[int]:
    out, stack = [], [root]
    while stack:
        pid = stack.pop()
        for child in children.get(pid, []):
            out.append(child)
            stack.append(child)
    return out


def _comm(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as stream:
            return stream.read().strip()
    except OSError:
        return ""


def footprint(exclude: set[int]) -> dict[str, Any]:
    """Processes, sockets and trial-HOME files of the sandboxed Driver, read from outside.

    Every descendant of this caller except ``exclude`` (the fixture) belongs to the Driver's
    sandbox: the two bwrap processes, the Driver and anything it spawned.
    """
    children = _children_map()
    me = os.getpid()
    pids = [p for p in _descendants(me, children) if p not in exclude]
    for gone in list(exclude):
        pids = [p for p in pids if p not in _descendants(gone, children)]
    procs = [{"pid": p, "comm": _comm(p)} for p in pids]
    driver = [p["pid"] for p in procs if p["comm"] != "bwrap"]
    sockets = 0
    fds = 0
    for pid in driver:
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                fds += 1
                try:
                    if os.readlink(f"/proc/{pid}/fd/{fd}").startswith("socket:"):
                        sockets += 1
                except OSError:
                    pass
        except OSError:
            pass
    files: list[str] = []
    if driver:
        root = f"/proc/{min(driver)}/root"
        for base in ("home/trial", "run/user/trial", "tmp"):
            top = Path(root) / base
            try:
                for path in sorted(top.rglob("*")):
                    files.append(f"/{base}/{path.relative_to(top)}")
            except OSError:
                pass
    return {
        "procs": len(driver),
        "proc_comms": sorted(p["comm"] for p in procs if p["comm"] != "bwrap"),
        "sockets": sockets,
        "fds": fds,
        "home_files": files,
        "driver_pids": driver,
    }


# ----------------------------------------------------------------------------- trial
async def run_trial(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Run one trial. ``spec`` comes from the schedule, ``ctx`` from the session runner."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from driver_env import driver_environment
    from native import NativeObservation, eligible_controls
    from run import Driver, DriverToolError

    state_path: Path = ctx["state_path"]
    fixture_pid: int = ctx["fixture_pid"]
    trial_dir = Path(ctx["work"]) / f"t{spec['trial_id']:05d}"
    trial_dir.mkdir(parents=True, exist_ok=True)
    trace_file = trial_dir / "trace" / "phase.jsonl"

    env = driver_environment()
    env.pop(TRACE_ENV, None)
    if spec["trace"]:
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        trace_file.write_text("", encoding="utf-8")
        env[TRACE_ENV] = str(trace_file)
    env["AR_A11Y_ADDRESS"] = ctx["a11y_address"]
    params = StdioServerParameters(command=ctx["sandbox"], args=[spec["binary"], "mcp"], env=env)

    row: dict[str, Any] = {
        "schema": "ar.trial.v1",
        **{k: spec[k] for k in ("trial_id", "session", "pair_id", "order", "position", "arm",
                                "kind", "trace", "warmup", "binary_sha256")},
        "loadavg_start": loadavg(),
    }
    before, _ = read_state(state_path)
    before = before or {}
    row["before"] = {k: before.get(k) for k in ("seq", "agreed", "counter", "note_saved")}
    journal: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    result: dict[str, Any] = {"verified": False, "claimed_success": None, "failure": None}

    def note(tool: str, m0: int, m1: int, error: Any, payload: dict[str, Any]) -> None:
        calls.append({
            "tool": tool, "m0": m0, "m1": m1, "ms": (m1 - m0) / 1e6, "error": error,
            "structured": {k: payload.get(k) for k in ("path", "route", "effect", "verified",
                                                         "readback", "value_matches", "code")
                           if k in payload},
        })

    t_spawn = time.monotonic_ns()
    row["t_spawn_ns"] = t_spawn
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                row["t_init_ns"] = time.monotonic_ns()
                driver = Driver(session, f"ar-{uuid.uuid4().hex[:8]}")

                async def call(tool: str, args: dict[str, Any]) -> tuple[dict[str, Any], Any]:
                    m0 = time.monotonic_ns()
                    try:
                        payload = await driver.call(tool, args)
                        note(tool, m0, time.monotonic_ns(), None, payload)
                        return payload, None
                    except DriverToolError as exc:
                        err = {"code": exc.code, "message": str(exc)[:300]}
                        note(tool, m0, time.monotonic_ns(), err, {})
                        return {}, err

                window_id = None
                for _ in range(200):
                    payload, err = await call("list_windows", {"pid": fixture_pid})
                    hits = [w for w in payload.get("windows", [])
                            if w.get("title") == WINDOW_TITLE and w.get("is_on_screen") is not False]
                    if hits:
                        window_id = int(hits[0]["window_id"])
                        break
                    await asyncio.sleep(0.05)
                if window_id is None:
                    raise RuntimeError("task window not found")
                target = {"pid": fixture_pid, "window_id": window_id}

                async def observe() -> dict[str, Any]:
                    payload, err = await call("get_window_state", {
                        **target, "include_accessibility_tree": True, "include_screenshot": True})
                    if err:
                        raise RuntimeError(f"observe failed: {err}")
                    row.setdefault("observations", []).append({
                        k: payload.get(k) for k in ("element_count", "degraded", "degraded_reason",
                                                    "walk_elapsed_ms", "truncated")})
                    return payload

                def lookup(payload: dict[str, Any], label: str) -> Any:
                    obs = NativeObservation.from_window_state(
                        payload, expected_pid=fixture_pid, expected_window_id=window_id)
                    matches = [c for c in eligible_controls(obs, "linux").controls if c.label == label]
                    if len(matches) != 1:
                        raise RuntimeError(f"lookup {label!r}: {len(matches)} matches")
                    return matches[0]

                kind = spec["kind"]
                expected: dict[str, Any] = {}
                if kind in ("task", "soak"):
                    control = lookup(await observe(), "I agree")
                    expected = {"agreed": not bool(before.get("agreed")), "seq": int(before["seq"]) + 1}
                    payload, err = await call("click", {**target, "element_token": control.element_token,
                                                        "delivery_mode": "background"})
                    result["claimed_success"] = err is None
                elif kind == "spot_gtk3_text":
                    payload0 = await observe()
                    note_ctl, save_ctl = lookup(payload0, "Note"), lookup(payload0, "Save note")
                    value = f"ar-{spec['trial_id']:05d}-{uuid.uuid4().hex[:6]}"
                    expected = {"note_saved": value, "seq": int(before["seq"]) + 1}
                    _, err = await call("set_value", {**target, "element_token": note_ctl.element_token,
                                                      "value": value})
                    if err is None:
                        _, err = await call("click", {**target, "element_token": save_ctl.element_token,
                                                      "delivery_mode": "background"})
                    result["claimed_success"] = err is None
                elif kind == "stale_negative":
                    old = lookup(await observe(), "I agree")
                    await observe()  # publishes a replacement snapshot
                    _, err = await call("click", {**target, "element_token": old.element_token,
                                                  "delivery_mode": "background"})
                    result["claimed_success"] = err is None
                    result["refused"] = err is not None
                    result["refusal_code"] = (err or {}).get("code")
                    result["refused_stale"] = err is not None and "stale" in json.dumps(err).lower()
                elif kind == "impossible_canary":
                    real = lookup(await observe(), "I agree")
                    token = str(real.element_token)
                    fake = token[:-6] + ("zzzzzz" if not token.endswith("zzzzzz") else "yyyyyy")
                    payload, err = await call("click", {**target, "element_token": fake,
                                                        "delivery_mode": "background"})
                    result["claimed_success"] = err is None and payload.get("verified") is True
                    result["refused"] = err is not None
                    result["refusal_code"] = (err or {}).get("code")
                    result["canary_outcome"] = ("refused" if err is not None
                                                else "claimed_success" if payload.get("verified") is True
                                                else "unknown")
                else:
                    raise RuntimeError(f"unknown kind {kind}")

                # Verify against the oracle (positive kinds) or watch for any mutation (negatives).
                deadline = time.monotonic() + (VERIFY_DEADLINE_S if expected else SETTLE_AFTER_S)
                last = None
                while True:
                    state, mtime = read_state(state_path)
                    if state is not None and (state.get("seq"), mtime) != last:
                        last = (state.get("seq"), mtime)
                        mono, wall = time.monotonic_ns(), time.time_ns()
                        journal.append({"seq": state.get("seq"), "mtime_ns": mtime,
                                        "seen_mono_ns": mono, "mtime_mono_est_ns": mtime - (wall - mono)})
                    if expected and state is not None and state.get("schema") == STATE_SCHEMA and all(
                            state.get(k) == v for k, v in expected.items()):
                        t_done = time.monotonic_ns()
                        result["verified"] = True
                        row["t_done_ns"] = t_done
                        row["T_ns"] = t_done - t_spawn
                        row["mutation_mono_est_ns"] = journal[-1]["mtime_mono_est_ns"]
                        row["journal_before_done"] = journal[-1]["mtime_mono_est_ns"] <= t_done
                        break
                    if time.monotonic() > deadline:
                        if expected:
                            result["failure"] = "verify_timeout"
                        break
                    time.sleep(POLL_S)
                row["expected"] = expected
                row["footprint"] = footprint({fixture_pid})
    except Exception as exc:  # retained in the denominator
        result["failure"] = result["failure"] or f"{type(exc).__name__}: {str(exc)[:300]}"
    row["t_exit_ns"] = time.monotonic_ns()
    # Settle, then re-read: a duplicate or late mutation shows up as an extra seq step.
    time.sleep(SETTLE_AFTER_S)
    after, _ = read_state(state_path)
    after = after or {}
    row["after"] = {k: after.get(k) for k in ("seq", "agreed", "counter", "note_saved")}
    if before.get("seq") is not None and after.get("seq") is not None:
        row["seq_delta"] = int(after["seq"]) - int(before["seq"])
    row["journal"] = journal
    row["calls"] = calls
    clicks = [c for c in calls if c["tool"] == "click"]
    row["route"] = clicks[-1]["structured"].get("route") if clicks else None
    row["path"] = clicks[-1]["structured"].get("path") if clicks else None
    row["dispatch_calls"] = len(clicks)
    row.update(result)
    if spec["trace"] and trace_file.exists():
        row["marks"] = [json.loads(x) for x in trace_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    row["loadavg_end"] = loadavg()
    return row

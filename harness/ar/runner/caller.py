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
  spot_browser_fill_submit
                     the jev-use fill->submit path against the evaluator's browser fixture
                     (docs/experiments/ar-harness-2026-10-02/fixtures): browser_prepare
                     isolated_new -> list_windows -> get_browser_state -> browser_navigate ->
                     semantic_v2 refs -> browser_type(token) -> trusted browser_click
                     (foreground) -> poll the fixture's /state; the fixture oracle
                     (ar_oracle.evaluate_browser) must then confirm exactly one POST with the
                     token, stamped <= done, after a trusted pointer sequence on Submit.
                     This Driver is NOT run inside sandbox-driver.sh: any unprivileged bwrap is
                     a user namespace, where root-owned Chromium shows as the overflow uid and
                     the Driver's isolated launch refuses it (browser_route_unavailable). It
                     runs directly in the private session (no session-pidns.sh either, for the
                     same reason) with HOME/TMPDIR moved to a fresh per-trial home.

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


def footprint(exclude: set[int], home: Path | None = None) -> dict[str, Any]:
    """Processes, sockets and trial-HOME files of the sandboxed Driver, read from outside.

    Every descendant of this caller except ``exclude`` (the fixture) belongs to the Driver's
    sandbox: the two bwrap processes, the Driver and anything it spawned. ``home`` is the
    trial home of an unsandboxed Driver (browser spot check); its files are listed directly.
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
    if home is not None:
        files = [f"/home/trial/{p.relative_to(home)}" for p in sorted(home.rglob("*"))]
    elif driver:
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


# ----------------------------------------------------------------------------- browser spot
BROWSER_KIND = "spot_browser_fill_submit"
BROWSER_SETTLE_S = 1.0  # page beacons (pointer sequence) land asynchronously; outside T
XDG_DIRS = ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")


def _alive(pid: int, comm: str) -> bool:
    return os.path.exists(f"/proc/{pid}") and _comm(pid) == comm


async def run_browser_trial(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """One browser fill->submit spot trial (see the module docstring). Same row schema."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    import ar_oracle
    from driver_env import driver_environment
    from run import Driver, DriverToolError

    server = ctx["browser_server"]
    trial_dir = Path(ctx["work"]) / f"t{spec['trial_id']:05d}"
    home = trial_dir / "home"
    home.mkdir(parents=True, exist_ok=False)
    home.chmod(0o700)
    # Chromium binds <TMPDIR>/com.google.Chrome.XXXXXX/SingletonSocket and aborts (FATAL "Socket
    # path too long", SIGTRAP) when that exceeds the 107-byte sun_path. A TMPDIR under the deep
    # trial dir does exactly that, so the trial TMPDIR is a short per-trial dir in the session's
    # own TMPDIR (private to this session) instead.
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"b{spec['trial_id']}"
    tmp.mkdir(mode=0o700, exist_ok=False)
    if len(f"{tmp}/com.google.Chrome.XXXXXX/SingletonSocket") > 107:
        raise RuntimeError(f"session TMPDIR too deep for Chromium's singleton socket: {len(str(tmp))}")
    trace_file = trial_dir / "trace" / "phase.jsonl"
    tag = f"t{spec['trial_id']:05d}"
    server.trial = tag
    server.pad_px = (int(spec.get("seed") or spec["trial_id"]) * 37) % 240  # same for both arms of a pair
    server.js_token = ""
    server.state.reset()
    token = f"ar-{spec['trial_id']:05d}-{uuid.uuid4().hex[:8]}"
    url = f"http://127.0.0.1:{server.server_port}/?t={tag}"

    env = driver_environment()
    env.pop(TRACE_ENV, None)
    for key in XDG_DIRS:
        env.pop(key, None)
    env["HOME"] = str(home)
    env["TMPDIR"] = str(tmp)
    if spec["trace"]:
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        trace_file.write_text("", encoding="utf-8")
        env[TRACE_ENV] = str(trace_file)
    params = StdioServerParameters(command=spec["binary"], args=["mcp"], env=env)

    row: dict[str, Any] = {
        "schema": "ar.trial.v1",
        **{k: spec[k] for k in ("trial_id", "session", "pair_id", "order", "position", "arm",
                                "kind", "trace", "warmup", "binary_sha256")},
        "seed": spec.get("seed"), "sandbox": "none: private session + trial HOME (root-owned Chromium check)",
        "loadavg_start": loadavg(),
    }
    row["before"] = {"submitted": server.state.snapshot().get("submitted")}
    calls: list[dict[str, Any]] = []
    result: dict[str, Any] = {"verified": False, "claimed_success": None, "failure": None}
    seen: dict[int, str] = {}

    def note(tool: str, m0: int, m1: int, error: Any, payload: dict[str, Any]) -> None:
        calls.append({"tool": tool, "m0": m0, "m1": m1, "ms": (m1 - m0) / 1e6, "error": error,
                      "structured": {k: payload.get(k) for k in ("path", "route", "effect", "verified", "code")
                                     if k in payload}})

    t_spawn = time.monotonic_ns()
    row["t_spawn_ns"] = t_spawn
    t_done = None
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                row["t_init_ns"] = time.monotonic_ns()
                driver = Driver(session, f"ar-{uuid.uuid4().hex[:8]}")

                async def call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
                    m0 = time.monotonic_ns()
                    try:
                        payload = await driver.call(tool, args)
                    except DriverToolError as exc:
                        note(tool, m0, time.monotonic_ns(), {"code": exc.code, "message": str(exc)[:300]}, {})
                        raise
                    note(tool, m0, time.monotonic_ns(), None, payload)
                    return payload

                try:
                    prep = await call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                    pid = int(prep["prepared_pid"])
                    window = None
                    for _ in range(200):
                        wins = (await call("list_windows", {"pid": pid})).get("windows", [])
                        vis = [w for w in wins if w.get("is_on_screen")]
                        if vis:
                            window = max(vis, key=lambda w: w["bounds"]["width"] * w["bounds"]["height"])
                            break
                        await asyncio.sleep(0.05)
                    if window is None:
                        raise RuntimeError("browser window did not appear")
                    bound = await call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
                    tabs = bound.get("tabs") or []
                    tab = next((t for t in tabs if t.get("active")), tabs[0])
                    ids = {"target_id": bound["target_id"], "tab_id": str(tab["tab_id"])}
                    await call("browser_navigate", {**ids, "url": url})
                    field_ref = submit_ref = None
                    for _ in range(60):
                        snap = await call("get_browser_state", {**ids, "snapshot_format": "semantic_v2"})
                        for item in snap.get("refs") or []:
                            if item.get("role") == "textbox" and item.get("name") == "verification value":
                                field_ref = item.get("ref")
                            if item.get("role") == "button" and item.get("name") == "Submit":
                                submit_ref = item.get("ref")
                        if field_ref and submit_ref:
                            break
                        await asyncio.sleep(0.05)
                    if not (field_ref and submit_ref):
                        raise RuntimeError("fixture refs not found")
                    await call("browser_type", {**ids, "ref": field_ref, "text": token, "replace": True})
                    await call("browser_click", {**ids, "ref": submit_ref, "delivery_mode": "foreground"})
                    result["claimed_success"] = True
                    deadline = time.monotonic() + VERIFY_DEADLINE_S
                    while time.monotonic() < deadline:
                        if server.state.snapshot().get("submitted") == token:
                            t_done = time.monotonic_ns()
                            break
                        time.sleep(POLL_S)
                    if t_done is None:
                        result["failure"] = "verify_timeout"
                except DriverToolError as exc:
                    result["claimed_success"] = False
                    result["failure"] = f"refused:{exc.code}"
                fp = footprint(set(), home=home)
                seen = {p: _comm(p) for p in fp["driver_pids"]}
                row["footprint"] = fp
    except Exception as exc:  # retained in the denominator
        result["failure"] = result["failure"] or f"{type(exc).__name__}: {str(exc)[:300]}"
    row["t_exit_ns"] = time.monotonic_ns()
    time.sleep(BROWSER_SETTLE_S)
    # A browser the Driver launched must not outlive it; any survivor is recorded (G2), then
    # stopped by the harness so it cannot perturb the next trial.
    leftover = [p for p, c in seen.items() if _alive(p, c)]
    row["leftover_procs"] = len(leftover)
    for p in leftover:
        try:
            os.kill(p, 15)
        except OSError:
            pass
    journal = server.journal_for(tag)
    oracle = ar_oracle.evaluate_browser(journal, server.state.snapshot(), token=token, t_spawn_ns=t_spawn,
                                        t_done_ns=t_done)
    row["oracle"] = oracle
    row["journal"] = [r for r in journal if r.get("source") == "target"]
    row["after"] = {"submitted": server.state.snapshot().get("submitted") == token}
    row["seq_delta"] = oracle["posts"]
    result["verified"] = bool(t_done is not None and oracle["verified"])
    if t_done is not None:
        row["t_done_ns"] = t_done
        row["mutation_mono_est_ns"] = oracle["t_post_ns"]
        row["journal_before_done"] = bool(oracle["ts_ok"])
        if result["verified"]:
            row["T_ns"] = t_done - t_spawn
        elif not result["failure"]:
            result["failure"] = "oracle_rejected"
    row["calls"] = calls
    clicks = [c for c in calls if c["tool"] == "browser_click"]
    row["route"] = clicks[-1]["structured"].get("route") if clicks else None
    row["path"] = clicks[-1]["structured"].get("path") if clicks else None
    row["dispatch_calls"] = len(clicks)
    row.update(result)
    if spec["trace"] and trace_file.exists():
        row["marks"] = [json.loads(x) for x in trace_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    row["loadavg_end"] = loadavg()
    return row


# ----------------------------------------------------------------------------- trial
async def run_trial(spec: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Run one trial. ``spec`` comes from the schedule, ``ctx`` from the session runner."""
    if spec["kind"] == BROWSER_KIND:
        return await run_browser_trial(spec, ctx)
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

#!/usr/bin/env python3
"""N-01R: native causal wait A/B on the canonical GTK3 task fixture (measurement only).

Derived from the R2-04 harness (``r2-04-harness/profile_atspi.py``): same
fixture, task window, observation call, jev-use ``eligible_controls`` lookup,
forced background element-token AT-SPI route and app-owned state-file oracle.
Changes for N-01R (pre-registered in PREREG.json):

* one fresh Driver process AND one fresh fixture process per trial (the env
  knobs are read once per process and ARRIVAL_DEGRADED latches);
* the oracle is an independent harness thread that reads the app's state file
  every 2 ms; spec T ends at the first such sample, taken at or after the last
  action's tool return, that shows the expected state;
* per-arm configuration: cursor motion (set_agent_cursor_motion, pre-T, every
  arm sends the call so the overlay is touched identically) and the two
  measurement-only Driver env knobs;
* controls: decoy focus steal (independent 2 ms X focus sampler), late effect
  (fixture-side delayed state application), stale token after fixture
  restart, default-off smoke.

Runs INSIDE cua-x11-session.sh with a private AT-SPI bus. It refuses to run
otherwise. No provider is used: any non-loopback TCP connect from this process
is refused and counted.
"""

from __future__ import annotations

import argparse
import asyncio
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
SETTLE_ENV = "CUA_DRIVER_EXP_FOCUS_GUARD_SETTLE_MS"
DELAY_ENV = "CUA_N01R_FIXTURE_APPLY_DELAY_MS"
ARMS: dict[str, dict[str, Any]] = {
    "B": {"fast_cursor": False, "env": {}},
    "C": {"fast_cursor": True, "env": {}},
    "S0": {"fast_cursor": False, "env": {SLEEP_ENV: "0"}},
    "F0": {"fast_cursor": False, "env": {SETTLE_ENV: "0"}},
    "X": {"fast_cursor": True, "env": {SLEEP_ENV: "0"}},
    "X2": {"fast_cursor": True, "env": {SLEEP_ENV: "0", SETTLE_ENV: "0"}},
    # Supplementary block O only: X2 with an accessibility-only task observation.
    "X2o": {"fast_cursor": True, "env": {SLEEP_ENV: "0", SETTLE_ENV: "0"}, "screenshot": False},
}
FAST_MOTION = {"glide_duration_ms": 1, "dwell_after_click_ms": 0}
STATE_PERIOD_S = 0.002
CONFIRM_DEADLINE_S = 3.0
POST_HOLD_S = {"main": 0.15, "warm": 0.15, "smoke": 0.15, "obs": 0.15, "late": 0.3, "decoy": 0.7}

# ----------------------------------------------------------------------------- no provider
NET = {"refused_non_loopback_connects": 0, "targets": []}
_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            NET["refused_non_loopback_connects"] += 1
            NET["targets"].append(str(host)[:64])
            raise ConnectionRefusedError("N-01R: provider cap 0, non-loopback connect refused")
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


class StateSampler(threading.Thread):
    """Independent oracle: reads the app's own state file every 2 ms. Stores every
    sample's read-start/read-end monotonic time and an index into the distinct
    file contents seen."""

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


# ----------------------------------------------------------------------------- harness
async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402
    from run import Driver, DriverToolError  # noqa: E402

    sys.setswitchinterval(0.0005)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    block = next(b for b in plan["blocks"] if b["block"] == args.block)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    driver_bin = str(Path(args.driver).resolve())
    fixture_path = str(wt / FIXTURE_REL)
    late_path = str(HERE / "fixture_late.py")

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
        # Another client is already on this display: every cell of the block is
        # kept as a failure and the block is re-run under a new label.
        for t in block["trials"]:
            ledger.write(json.dumps({"event": "trial", **t, "failure": "display_collision",
                                     "oracle_verified": False, "valid_route": False}) + "\n")
        ledger.write(json.dumps({"event": "end", "failures": len(block["trials"]), "net": NET}) + "\n")
        ledger.close()
        return 3

    decoy = xprobe.Decoy() if block["kind"] == "decoy" else None
    failures = 0

    async def run_trial(t: dict[str, Any]) -> dict[str, Any]:
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
        fenv.pop(DELAY_ENV, None)
        if kind == "late":
            fenv[DELAY_ENV] = str(t["variant_ms"])
            cmd = ["/usr/bin/python3", late_path, fixture_path]
        else:
            cmd = ["/usr/bin/python3", fixture_path]
        fixture_log = open(tdir / "fixture.log", "w", encoding="utf-8")
        fixtures = [subprocess.Popen(cmd, env=fenv, stdout=fixture_log, stderr=subprocess.STDOUT)]
        sampler: StateSampler | None = None
        focus: xprobe.FocusSampler | None = None
        anchor = None

        def start_fixture_wait(proc: subprocess.Popen, path: Path) -> None:
            deadline = time.monotonic() + 15
            while read_state(path) is None:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise RuntimeError("fixture did not publish its state file")
                time.sleep(0.02)
            time.sleep(1.0)  # AT-SPI registration settle (as R2-04)

        env = driver_environment()
        for key in list(env):
            if key.startswith("CUA_DRIVER_EXP_") or key == "CUA_DRIVER_PHASE_TRACE_FILE":
                env.pop(key)
        env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_path)
        env.update(arm["env"])
        rec["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
        rec["driver_env_keys"] = sorted(env)
        try:
            start_fixture_wait(fixtures[0], state_path)
            before = read_state(state_path) or {}
            rec["before"] = before
            rec["fixture_pid"] = fixtures[0].pid
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    driver = Driver(session, f"n01r-{uuid.uuid4().hex[:8]}")

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
                        return {"tool": name, "m0": m0, "w0": w0, "m1": m1, "w1": w1,
                                "wrapper_ms": (m1 - m0) / 1e6, "error": error, "payload": payload,
                                "content_text": content_text}

                    async def observe() -> tuple[dict[str, Any], dict[str, Any]]:
                        call = await timed("get_window_state", {
                            **target, "include_accessibility_tree": True,
                            "include_screenshot": arm.get("screenshot", True)})
                        p = call.pop("payload")
                        call["summary"] = {k: p.get(k) for k in (
                            "walk_elapsed_ms", "element_count", "nodes_visited", "snapshot_id", "degraded")}
                        call["summary"]["has_screenshot"] = "screenshot_mime_type" in p
                        call["summary"]["payload_keys"] = sorted(p)[:40]
                        return call, p

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

                    if kind == "stale":
                        await stale_trial(rec, t, driver, timed, observe, lookup, shape, find_window,
                                          fixtures, fenv, cmd, tdir, fixture_log, start_fixture_wait)
                        return rec

                    if kind == "warm":
                        # Pre-T cursor placement without an app-state change: set_value
                        # on Note (no publish) leaves the session cursor at the Note
                        # field, so the checkbox click glides from a prior position.
                        wtree, wpayload = await observe()
                        wlk, wfound = lookup(wpayload, ["Note"], fixtures[0].pid, window_id)
                        if not wfound["Note"]:
                            raise RuntimeError("warm-up target not found")
                        warm = shape(await timed("set_value", {**target,
                                                               "element_token": wfound["Note"].element_token,
                                                               "value": ""}))
                        rec["warm_step"] = {"observe_ms": wtree["wrapper_ms"], "set_value": warm}
                        rec["before"] = read_state(state_path) or {}
                        before = rec["before"]

                    focus_pre = xprobe.snapshot()
                    if kind == "decoy":
                        rec["focus_placement"] = xprobe.activate_and_wait(window_id)
                        focus_pre = xprobe.snapshot()
                        focus = xprobe.FocusSampler()
                        focus.start()
                        assert decoy is not None
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
                        token = f"n01r-{t['id']}-{uuid.uuid4().hex[:6]}"
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
            if decoy is not None and kind == "decoy":
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
            rec["w_end"] = time.time_ns()
        return rec

    async def stale_trial(rec, t, driver, timed, observe, lookup, shape, find_window,
                          fixtures, fenv, cmd, tdir, fixture_log, start_fixture_wait) -> None:
        """Negative control (c): an element_token observed on fixture A is used
        after A is replaced by a fresh fixture B; it must be refused with no
        mutation of B and no AT-SPI DoAction."""
        a_pid = fixtures[0].pid
        a_window = rec["window_id"]
        tree, payload = await observe()
        _, found = lookup(payload, ["I agree"], a_pid, a_window)
        old = found["I agree"]
        if old is None:
            rec["failure"] = "target_not_found"
            return
        fixtures[0].terminate()
        fixtures[0].wait(timeout=5)
        b_state = tdir / "state-b.json"
        benv = dict(fenv)
        benv["CUA_GTK3_TASK_STATE"] = str(b_state)
        proc_b = subprocess.Popen(cmd, env=benv, stdout=fixture_log, stderr=subprocess.STDOUT)
        fixtures.append(proc_b)
        start_fixture_wait(proc_b, b_state)
        b_window = await find_window(proc_b.pid)
        before_b = read_state(b_state) or {}
        marks_before = len([x for x in (tdir / "phase.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()])
        call = shape(await timed("click", {"pid": proc_b.pid, "window_id": b_window,
                                           "element_token": old.element_token,
                                           "delivery_mode": "background"}, raw=True))
        await asyncio.sleep(0.3)
        after_b = read_state(b_state) or {}
        lines = [json.loads(x) for x in (tdir / "phase.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        do_actions = sum(1 for m in lines[marks_before:] if m.get("mark") == "do_action_replied")
        st = call["structured"]
        refusal = st.get("refusal") if isinstance(st.get("refusal"), dict) else {}
        rec.update({
            "fixture_a_pid": a_pid, "fixture_b_pid": proc_b.pid, "window_b": b_window,
            "actions": [call], "before_b": before_b, "after_b": after_b,
            "refused": bool(call["error"]) or st.get("status") == "refused",
            "refusal_code": st.get("code") or refusal.get("code"),
            "effect": st.get("effect"),
            "mutations_b": int(after_b.get("seq", 0)) - int(before_b.get("seq", 0)),
            "do_action_marks_after_restart": do_actions,
        })
        rec["control_passed"] = bool(rec["refused"] and rec["mutations_b"] == 0 and do_actions == 0
                                     and rec["effect"] in ("refused", "none", None))
        rec["oracle_verified"] = rec["control_passed"]

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            if r["kind"] != "stale":
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
    # hostless masks the host runtime dir with a private tmpfs: the host's
    # Wayland/Hyprland/session-bus sockets must not be visible there.
    host_sockets = [n for n in names if n.startswith(("wayland-", "hypr", "pipewire"))
                    or n in ("bus", "at-spi", "systemd")]
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY") or host_sockets
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith("/run/user")):
        raise SystemExit(f"refusing: not inside hostless + the isolated X11 session ({host_sockets})")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

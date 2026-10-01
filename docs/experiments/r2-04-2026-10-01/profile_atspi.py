#!/usr/bin/env python3
"""R2-04: AT-SPI phase / D-Bus RPC profile of the locally built Driver (measurement only).

Runs INSIDE the isolated X11 session (cua-x11-session.sh with a private AT-SPI
bus). It starts the canonical GTK3 fixture in its opt-in task mode
(``CUA_GTK3_TASK_STATE``: the app atomically rewrites its own JSON state file on
every change; that file is the independent, target-owned oracle), opens one
Driver MCP stdio session, and runs interleaved trials of three action types:

* ``checkbox``: get_window_state -> lookup "I agree" -> click(element_token, background)
* ``button``:   get_window_state -> lookup "Increment" -> click(element_token, background)
* ``text``:     get_window_state -> lookup "Note" + "Save note" -> set_value(token, value)
                -> click(Save note token)  (the save publishes note_saved)

Each trial records caller-side monotonic + wall-clock boundaries for: tree
acquisition (get_window_state), target lookup (the production jev-use
``eligible_controls`` parser), each action tool call, target mutation (first
caller detection of the app's new state ``seq``), independent oracle read, and a
fresh verification observation. When the trial's monitor flag is on, a
``dbus-monitor --monitor`` process on the private AT-SPI bus records every
message during the trial; RPCs are attributed to phases by wall-clock window.

Nothing here changes Driver behaviour. No Driver env beyond what jev-use's
``driver_environment()`` forwards is added, except ``CUA_LOG`` when ``--cua-log``
is given (not used by the pre-registered arms).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use"
WINDOW_TITLE = "CuaTestHarness GTK3 Tasks"
STATE_SCHEMA = "cua.gtk3_task_state_v1"
ACTION_TYPES = ("checkbox", "button", "text")
MUTATION_DEADLINE_S = 3.0


class _Abort(Exception):
    """A trial stops early; its record (with the failure reason) is still kept."""
POLL_S = 0.0005


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


def a11y_address() -> str:
    out = subprocess.run(
        ["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
         "--method", "org.a11y.Bus.GetAddress"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout
    match = re.search(r"'([^']+)'", out)
    if not match:
        raise RuntimeError("could not read the AT-SPI bus address")
    return match.group(1)


# --------------------------------------------------------------------------- monitor
HEADER = re.compile(
    r"^(method call|method return|error|signal) time=(\d+)\.(\d+) sender=(\S+) -> destination=(.+?) "
    r"serial=(\d+)(.*)$"
)


def parse_monitor(text: str) -> list[dict[str, Any]]:
    """Parse dbus-monitor text output into message records (header + first string arg)."""
    messages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        match = HEADER.match(line)
        if match:
            kind, sec, usec, sender, dest, serial, rest = match.groups()
            record: dict[str, Any] = {
                "type": kind, "t_ns": int(sec) * 1_000_000_000 + int(usec.ljust(6, "0")[:6]) * 1000,
                "sender": sender, "dest": dest.strip(), "serial": int(serial),
            }
            for key in ("path", "interface", "member", "reply_serial", "error_name"):
                found = re.search(rf"{key}=([^;\s]+)", rest)
                if found:
                    record[key] = int(found.group(1)) if key == "reply_serial" else found.group(1)
            messages.append(record)
            current = record
            continue
        if current is not None and "arg0" not in current:
            stripped = line.strip()
            if stripped.startswith("string "):
                current["arg0"] = stripped[len("string "):].strip('"')[:80]
            elif stripped.startswith(("int32 ", "uint32 ", "boolean ")) and current["type"] != "signal":
                current["arg0"] = stripped[:40]
    return messages


class Monitor:
    def __init__(self, address: str, log_path: Path) -> None:
        self.log_path = log_path
        self.stream = open(log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            ["dbus-monitor", "--address", address, "--monitor"],
            stdout=self.stream, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if log_path.stat().st_size > 0:
                break
            time.sleep(0.005)
        time.sleep(0.03)

    def stop(self) -> list[dict[str, Any]]:
        time.sleep(0.08)  # let trailing messages (late signals) drain
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.stream.close()
        return parse_monitor(self.log_path.read_text(encoding="utf-8", errors="replace"))


def rpc_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair every method call with its return/error (by caller + serial)."""
    replies = {}
    for m in messages:
        if m["type"] in ("method return", "error") and "reply_serial" in m:
            replies[(m["dest"], m["reply_serial"])] = m
    pairs = []
    for m in messages:
        if m["type"] != "method call":
            continue
        reply = replies.get((m["sender"], m["serial"]))
        pairs.append({
            "t_ns": m["t_ns"], "end_ns": reply["t_ns"] if reply else None,
            "sender": m["sender"], "dest": m["dest"], "interface": m.get("interface"),
            "member": m.get("member"), "path": m.get("path"), "arg0": m.get("arg0"),
            "reply": reply["type"] if reply else None, "error_name": reply.get("error_name") if reply else None,
        })
    return pairs


# --------------------------------------------------------------------------- harness
async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402
    from run import Driver, DriverToolError  # noqa: E402

    out = Path(args.out).resolve()
    (out / "monitor").mkdir(parents=True, exist_ok=True)
    trials_path = out / "trials.jsonl"
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    state_path = work / "gtk3-task-state.json"
    if state_path.exists():
        state_path.unlink()

    fixture_env = dict(os.environ)
    fixture_env["CUA_GTK3_TASK_STATE"] = str(state_path)
    fixture = subprocess.Popen(["/usr/bin/python3", str(wt / FIXTURE_REL)], env=fixture_env,
                               stdout=open(work / "fixture.log", "w"), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while read_state(state_path) is None:
        if time.monotonic() > deadline or fixture.poll() is not None:
            raise RuntimeError("fixture did not publish its state file")
        time.sleep(0.05)
    time.sleep(1.0)
    address = a11y_address()

    env = driver_environment()
    if args.cua_log:
        env["CUA_LOG"] = args.cua_log
    env.pop("CUA_DRIVER_PHASE_TRACE_FILE", None)
    phase_log = Path(args.phase_log).resolve() if args.phase_log else None
    if phase_log is not None:
        phase_log.write_text("", encoding="utf-8")
        env["CUA_DRIVER_PHASE_TRACE_FILE"] = str(phase_log)
    phase_offset = [0]

    def take_marks() -> list[dict[str, Any]]:
        """Driver phase marks appended since the previous call (measurement-only sink)."""
        if phase_log is None:
            return []
        with open(phase_log, "rb") as stream:
            stream.seek(phase_offset[0])
            chunk = stream.read()
        complete = chunk[: chunk.rfind(b"\n") + 1] if b"\n" in chunk else b""
        phase_offset[0] += len(complete)
        return [json.loads(x) for x in complete.decode("utf-8").splitlines() if x.strip()]
    params = StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    meta = {
        "event": "meta", "arm": args.arm, "rounds": args.rounds, "monitor_pattern": args.monitor_pattern,
        "fixture_pid": fixture.pid, "state_schema": STATE_SCHEMA, "window_title": WINDOW_TITLE,
        "driver_env_keys": sorted(env), "a11y_bus_private": address.startswith("unix:"),
        "phase_trace": phase_log is not None,
        "loadavg": loadavg(),
    }
    failures = 0
    with open(trials_path, "w", encoding="utf-8") as ledger:
        ledger.write(json.dumps(meta, sort_keys=True) + "\n")
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    t_init0 = time.perf_counter_ns()
                    await session.initialize()
                    init_ms = (time.perf_counter_ns() - t_init0) / 1e6
                    driver = Driver(session, f"r2-04-{uuid.uuid4().hex[:8]}")
                    window = None
                    for _ in range(60):
                        wins = (await driver.call("list_windows", {"pid": fixture.pid})).get("windows", [])
                        hits = [w for w in wins if w.get("title") == WINDOW_TITLE and w.get("is_on_screen") is not False]
                        if hits:
                            window = hits[0]
                            break
                        await asyncio.sleep(0.25)
                    if window is None:
                        raise RuntimeError("task window did not appear")
                    window_id = int(window["window_id"])
                    ledger.write(json.dumps({"event": "session", "init_ms": init_ms, "window_found": True}) + "\n")

                    async def timed(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                        m0, w0 = now()
                        error = None
                        payload: dict[str, Any] = {}
                        try:
                            payload = await driver.call(name, arguments)
                        except DriverToolError as exc:
                            error = {"code": exc.code, "message": str(exc)[:300]}
                        m1, w1 = now()
                        return {"tool": name, "m0": m0, "w0": w0, "m1": m1, "w1": w1,
                                "wrapper_ms": (m1 - m0) / 1e6, "error": error, "payload": payload}

                    async def observe() -> tuple[dict[str, Any], Any]:
                        call = await timed("get_window_state", {
                            "pid": fixture.pid, "window_id": window_id,
                            "include_accessibility_tree": True, "include_screenshot": True,
                        })
                        p = call["payload"]
                        summary = {k: p.get(k) for k in (
                            "walk_elapsed_ms", "element_count", "total_element_count", "nodes_visited",
                            "truncated", "elements_complete", "bounds_complete", "snapshot_id", "degraded",
                            "degraded_reason")}
                        call["summary"] = summary
                        call.pop("payload")
                        return call, p

                    def lookup(payload: dict[str, Any], labels: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
                        m0, w0 = now()
                        obs = NativeObservation.from_window_state(payload, expected_pid=fixture.pid,
                                                                  expected_window_id=window_id)
                        controls = eligible_controls(obs, "linux").controls
                        found = {}
                        for label in labels:
                            matches = [c for c in controls if c.label == label]
                            found[label] = matches[0] if len(matches) == 1 else None
                        m1, w1 = now()
                        rec = {"m0": m0, "w0": w0, "m1": m1, "w1": w1, "lookup_ms": (m1 - m0) / 1e6,
                               "control_count": len(controls),
                               "found": {k: (v is not None) for k, v in found.items()},
                               "selected": {k: (v.selected if v else None) for k, v in found.items()},
                               "values": {k: (v.value if v else None) for k, v in found.items()}}
                        return rec, found

                    def wait_mutation(prior_seq: int) -> dict[str, Any]:
                        m0, w0 = now()
                        end = time.monotonic() + MUTATION_DEADLINE_S
                        polls = 0
                        while time.monotonic() < end:
                            polls += 1
                            try:
                                st = os.stat(state_path)
                            except OSError:
                                st = None
                            state = read_state(state_path) if st is not None else None
                            if state is not None and int(state.get("seq", -1)) > prior_seq:
                                m1, w1 = now()
                                return {"detected": True, "m_detect": m1, "w_detect": w1,
                                        "wait_ms": (m1 - m0) / 1e6, "polls": polls,
                                        "state_mtime_ns": st.st_mtime_ns, "state": state}
                            time.sleep(POLL_S)
                        m1, w1 = now()
                        return {"detected": False, "m_detect": m1, "w_detect": w1,
                                "wait_ms": (m1 - m0) / 1e6, "polls": polls, "state": read_state(state_path)}

                    def oracle_read() -> dict[str, Any]:
                        m0, w0 = now()
                        state = read_state(state_path)
                        m1, w1 = now()
                        return {"m0": m0, "w0": w0, "m1": m1, "w1": w1, "read_ms": (m1 - m0) / 1e6, "state": state}

                    async def trial(index: int, kind: str, monitored: bool, phase: str) -> dict[str, Any]:
                        rec: dict[str, Any] = {"event": "trial", "index": index, "kind": kind,
                                               "monitored": monitored, "phase": phase, "arm": args.arm,
                                               "loadavg": loadavg()}
                        before = read_state(state_path) or {}
                        rec["before"] = before
                        mon = Monitor(address, out / "monitor" / f"{index:03d}-{kind}.log") if monitored else None
                        take_marks()
                        mt0, wt0 = now()
                        rec["m_start"], rec["w_start"] = mt0, wt0
                        expected: dict[str, Any] = {}
                        try:
                            tree, payload = await observe()
                            rec["tree"] = tree
                            labels = {"checkbox": ["I agree"], "button": ["Increment"],
                                      "text": ["Note", "Save note"]}[kind]
                            lk, found = lookup(payload, labels)
                            rec["lookup"] = lk
                            if not all(found.values()) or tree["error"]:
                                rec["failure"] = "target_not_found" if not tree["error"] else "observe_error"
                                raise _Abort
                            target = {"pid": fixture.pid, "window_id": window_id}
                            actions = []
                            if kind == "checkbox":
                                expected = {"agreed": not bool(before.get("agreed")), "seq": int(before["seq"]) + 1}
                                actions.append(await timed("click", {**target, "element_token": found["I agree"].element_token,
                                                                     "delivery_mode": "background"}))
                            elif kind == "button":
                                expected = {"counter": int(before.get("counter", 0)) + 1, "seq": int(before["seq"]) + 1}
                                actions.append(await timed("click", {**target, "element_token": found["Increment"].element_token,
                                                                     "delivery_mode": "background"}))
                            else:
                                token = f"r204-{index:03d}-{uuid.uuid4().hex[:6]}"
                                expected = {"note_saved": token, "seq": int(before["seq"]) + 1}
                                sv = await timed("set_value", {**target, "element_token": found["Note"].element_token,
                                                               "value": token})
                                actions.append(sv)
                                if sv["error"] is None:
                                    actions.append(await timed("click", {**target, "element_token": found["Save note"].element_token,
                                                                         "delivery_mode": "background"}))
                            for a in actions:
                                p = a.pop("payload")
                                a["structured"] = {k: p.get(k) for k in ("path", "route", "effect", "verified", "readback",
                                                                       "value_matches", "note", "code") if k in p}
                            rec["actions"] = actions
                            mut = wait_mutation(int(before["seq"]))
                            rec["mutation"] = {k: v for k, v in mut.items() if k != "state"}
                            orc = oracle_read()
                            rec["oracle"] = orc
                            vtree, vpayload = await observe()
                            rec["verify_tree"] = vtree
                            vlk, vfound = lookup(vpayload, labels)
                            rec["verify_lookup"] = vlk
                            state = orc["state"] or {}
                            ok = all(state.get(k) == v for k, v in expected.items()) and state.get("schema") == STATE_SCHEMA
                            rec["expected"] = expected
                            rec["oracle_verified"] = bool(ok)
                            # Cross-layer: the fresh Driver observation agrees with the app's own file.
                            if kind == "checkbox":
                                rec["observation_agrees"] = vlk["selected"].get("I agree") == state.get("agreed")
                            elif kind == "text":
                                rec["observation_agrees"] = vlk["values"].get("Note") == expected["note_saved"]
                            else:
                                rec["observation_agrees"] = None
                        except _Abort:
                            pass
                        except Exception as exc:  # retained in the denominator
                            rec["failure"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                        mt1, wt1 = now()
                        rec["m_end"], rec["w_end"] = mt1, wt1
                        rec["trial_ms"] = (mt1 - mt0) / 1e6
                        if phase_log is not None:
                            rec["marks"] = take_marks()
                        if mon is not None:
                            msgs = mon.stop()
                            rec["rpc"] = rpc_pairs(msgs)
                            rec["signals"] = [
                                {"t_ns": m["t_ns"], "sender": m["sender"], "interface": m.get("interface"),
                                 "member": m.get("member"), "arg0": m.get("arg0")}
                                for m in msgs if m["type"] == "signal"
                            ]
                            rec["monitor_message_count"] = len(msgs)
                        if "oracle_verified" not in rec:
                            rec["oracle_verified"] = False
                        return rec

                    async def stale_trial(index: int) -> dict[str, Any]:
                        """Negative control: a token from a replaced snapshot must be refused
                        with no AT-SPI DoAction on the bus and no app mutation."""
                        rec: dict[str, Any] = {"event": "trial", "index": index, "kind": "stale_negative",
                                               "monitored": True, "phase": "negative", "arm": args.arm,
                                               "loadavg": loadavg()}
                        before = read_state(state_path) or {}
                        rec["before"] = before
                        mon = Monitor(address, out / "monitor" / f"{index:03d}-stale_negative.log")
                        take_marks()
                        mt0, wt0 = now()
                        rec["m_start"], rec["w_start"] = mt0, wt0
                        try:
                            tree, payload = await observe()
                            _, found = lookup(payload, ["I agree"])
                            old = found["I agree"]
                            replaced, _ = await observe()  # publishes a new snapshot
                            rec["tree"], rec["replacement_tree"] = tree, replaced
                            call = await timed("click", {"pid": fixture.pid, "window_id": window_id,
                                                         "element_token": old.element_token,
                                                         "delivery_mode": "background"})
                            call.pop("payload")
                            rec["actions"] = [call]
                            time.sleep(0.3)
                            after = read_state(state_path) or {}
                            rec["after"] = after
                            rec["refused_stale"] = bool(call["error"]) and "stale" in json.dumps(call["error"])
                            rec["no_mutation"] = after.get("seq") == before.get("seq") and after.get("agreed") == before.get("agreed")
                        except Exception as exc:
                            rec["failure"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                        mt1, wt1 = now()
                        rec["m_end"], rec["w_end"] = mt1, wt1
                        rec["trial_ms"] = (mt1 - mt0) / 1e6
                        if phase_log is not None:
                            rec["marks"] = take_marks()
                        msgs = mon.stop()
                        rec["rpc"] = rpc_pairs(msgs)
                        rec["signals"] = [
                            {"t_ns": m["t_ns"], "sender": m["sender"], "interface": m.get("interface"),
                             "member": m.get("member"), "arg0": m.get("arg0")}
                            for m in msgs if m["type"] == "signal"
                        ]
                        rec["monitor_message_count"] = len(msgs)
                        rec["do_action_on_bus"] = sum(1 for p in rec["rpc"] if p["member"] == "DoAction")
                        rec["control_passed"] = bool(rec.get("refused_stale") and rec.get("no_mutation")
                                                     and rec["do_action_on_bus"] == 0)
                        rec["oracle_verified"] = rec["control_passed"]
                        return rec

                    # Warm-up (kept, reported separately, excluded from steady-state stats).
                    index = 0
                    for kind in ACTION_TYPES:
                        for monitored in (False, True):
                            r = await trial(index, kind, monitored, "warmup")
                            ledger.write(json.dumps(r, sort_keys=True) + "\n")
                            ledger.flush()
                            failures += 0 if r["oracle_verified"] else 1
                            index += 1
                    for _ in range(2):
                        r = await stale_trial(index)
                        ledger.write(json.dumps(r, sort_keys=True) + "\n")
                        ledger.flush()
                        failures += 0 if r["control_passed"] else 1
                        index += 1
                    # Measured rounds: action order rotates per round (Latin square over the
                    # three types); monitor on/off follows ABBA per round.
                    abba = [True, False, False, True]
                    for rnd in range(args.rounds):
                        order = ACTION_TYPES[rnd % 3:] + ACTION_TYPES[:rnd % 3]
                        if args.monitor_pattern == "abba":
                            mon_flag = abba[rnd % 4]
                        else:
                            mon_flag = args.monitor_pattern == "on"
                        for kind in order:
                            r = await trial(index, kind, mon_flag, "measured")
                            r["round"] = rnd
                            ledger.write(json.dumps(r, sort_keys=True) + "\n")
                            ledger.flush()
                            failures += 0 if r["oracle_verified"] else 1
                            index += 1
                    for _ in range(2):
                        r = await stale_trial(index)
                        ledger.write(json.dumps(r, sort_keys=True) + "\n")
                        ledger.flush()
                        failures += 0 if r["control_passed"] else 1
                        index += 1
        finally:
            fixture.terminate()
            try:
                fixture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fixture.kill()
        ledger.write(json.dumps({"event": "end", "failures": failures, "loadavg": loadavg()}) + "\n")
    print(f"done: {trials_path} failures={failures}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wt", required=True, help="tested worktree (fixture + jev-use)")
    parser.add_argument("--driver", required=True, help="Driver binary")
    parser.add_argument("--out", required=True, help="raw output dir")
    parser.add_argument("--work", required=True, help="scratch dir for the fixture state file")
    parser.add_argument("--arm", required=True)
    parser.add_argument("--rounds", type=int, default=24)
    parser.add_argument("--monitor-pattern", choices=("abba", "on", "off"), default="abba")
    parser.add_argument("--cua-log", default=None)
    parser.add_argument("--phase-log", default=None,
                        help="enable the Driver's measurement-only phase marks into this file")
    args = parser.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ) or not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: not inside the isolated X11 session")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

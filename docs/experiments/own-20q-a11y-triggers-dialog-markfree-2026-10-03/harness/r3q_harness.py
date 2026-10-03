#!/usr/bin/env python3
"""OWN-20Q A2 rows: AT-SPI reconnect triggers on the private accessibility bus (measurement only).

A new file; OWN-20G's ``r3_harness.py`` stays blob-identical and is only imported (process lookup,
``Bus``, ``truthful``, ``digest``). Runs INSIDE cua-x11-session.sh with CUA_SESSION_ATSPI=1; refuses
otherwise. One fresh Driver and one fresh GTK3 task fixture A per trial. Only processes this harness
started, or the session's own launcher / bus daemon / registry (children of this process's parent,
the session's inner shell, with this session's XDG_RUNTIME_DIR, checked before every signal), are
ever signalled. Variants (PREREG.json):

* ``launcher_keep`` (R3n): SIGKILL the session's at-spi-bus-launcher, so it cannot stop its bus
  daemon: the old daemon stays alive and keeps serving A and the Driver's connection. A new launcher
  (new daemon, new address, the org.a11y.Bus name) and a new registry start; the old registry stays.
* ``launcher_wedge`` (R3w, supplementary): as ``launcher_keep``, but the old daemon's processes are
  SIGSTOPped first: alive, socket open, never answering.
* ``slow`` (R3s): no bus change. A is SIGSTOPped, the Driver clicks A's token, and A is SIGCONTed when
  the click returns (at most 12 s): A's AT-SPI calls get no reply while the bus answers Peer.Ping.

Sequence (launcher variants): observe A (token T_old) -> perturb -> click T_old -> start fixture B
(it registers on the bus that serves the session now) -> the same Driver process observes B (5 tries,
1 s apart) -> a truthful token of B is clicked and verified by B's own state file.
Sequence (slow): observe A -> stop A -> click A's token -> resume A -> 4 s oracle window -> a fresh
observation of A and a fresh click, verified by A's state file.

Oracles: the fixtures' state files, and a dbus-monitor (``q_common.BusWatch``) on every bus involved,
which attributes each connection to its pid through the bus daemon (the Driver's reconnects). No
provider: non-loopback connects are refused and counted.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness_common as hc  # noqa: E402
import q_common  # noqa: E402
from r3_harness import (LAUNCHER, REGISTRYD, Bus, children, digest, mine, proc_info,  # noqa: E402
                        truthful)

OBSERVE_TRIES = 5
CONFIRM_DEADLINE_S = 4.0
STALE_HOLD_S = 1.0
STOP_MAX_S = 12.0
RESUME_WINDOW_S = 4.0


def descendants(pid: int) -> list[dict[str, Any]]:
    out, todo = [], [pid]
    while todo:
        for k in children(todo.pop()):
            out.append(k)
            todo.append(k["pid"])
    return out


def alive(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def proc_state(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return None


def signal_mine(info: dict[str, Any] | None, sig: int, events: list[Any], what: str) -> bool:
    if not info or not mine(proc_info(info["pid"])):
        events.append({"signal": what, "skipped": "not this session's process"})
        return False
    os.kill(info["pid"], sig)
    events.append({"signal": what, "sig": int(sig), "comm": info["comm"], "mono_ns": time.monotonic_ns()})
    return True


def session_name_owner_pid(name: str) -> int | None:
    """The pid owning ``name`` on the session bus; None when unowned (never activates the name)."""
    try:
        res = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                              "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.GetConnectionUnixProcessID",
                              name], capture_output=True, text=True, timeout=1.0)
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = res.stdout.strip()
    return int(out.split()[1].rstrip(",)")) if res.returncode == 0 and out.startswith("(uint32") else None


def ping(address: str | None) -> bool:
    if not address:
        return False
    try:
        res = subprocess.run(["gdbus", "call", "--address", address, "--dest", "org.freedesktop.DBus",
                              "--object-path", "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.Peer.Ping"],
                             capture_output=True, text=True, timeout=1.5)
        return res.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


class LauncherRestart:
    """Restart the launcher (and registry) while the old daemon stays alive (serving or wedged)."""

    def __init__(self, bus: Bus) -> None:
        self.bus = bus
        self.orphans: list[dict[str, Any]] = []
        self.old_registry: dict[str, Any] | None = None

    def perturb(self, work: Path, events: list[Any], wedge: bool) -> dict[str, Any]:
        old_address = q_common.a11y_address()
        launcher = self.bus.launcher
        daemon_tree = descendants(launcher["pid"]) if launcher else []
        daemon_tree = [d for d in daemon_tree if mine(d)]
        events.append({"old_daemon_procs": [d["comm"] for d in daemon_tree]})
        if wedge:
            for d in daemon_tree:
                signal_mine(d, signal.SIGSTOP, events, "stop-old-daemon")
        signal_mine(launcher, signal.SIGKILL, events, "kill-launcher")
        if launcher:
            events.append({"launcher_gone": self.bus.wait_gone(launcher["pid"], 3.0)})
        time.sleep(0.2)
        self.orphans = [d for d in daemon_tree if alive(d["pid"])]
        self.old_registry = self.bus.registry
        proc = self.bus._spawn([LAUNCHER, "--launch-immediately"], work, f"launcher-{len(self.bus.started)}")
        # Wait for an owner of org.a11y.Bus WITHOUT asking it anything: a GetAddress before the new launcher
        # owns the name makes the session bus activate another launcher from its service file.
        owner = None
        end = time.monotonic() + 5.0
        while time.monotonic() < end and owner is None:
            owner = session_name_owner_pid("org.a11y.Bus")
            if owner is None:
                time.sleep(0.02)
        events.append({"a11y_bus_owner_is_started_launcher": owner == proc.pid, "owner_found": owner is not None})
        if owner is not None and owner != proc.pid and mine(proc_info(owner)):
            # an activated launcher won the name: it serves the session now; ours is surplus
            self.bus.launcher = proc_info(owner)
            hc.stop_process(proc)
        else:
            self.bus.launcher = proc_info(proc.pid)
        new_address = None
        end = time.monotonic() + 5.0
        while time.monotonic() < end:
            new_address = q_common.a11y_address()
            if new_address and self.bus.daemon() and ping(new_address):
                break
            time.sleep(0.02)
        reg = self.bus._spawn([REGISTRYD, "--use-gnome-session"], work, f"registryd-{len(self.bus.started)}")
        self.bus.registry = proc_info(reg.pid)
        self.bus.wait_registry(new_address, reg.pid, events)
        # the new daemon listens on the same socket path, so the old one can no longer be pinged by address:
        # its processes' scheduler states are recorded instead (T = stopped)
        facts = {"old_daemon_alive": bool(self.orphans) and all(alive(d["pid"]) for d in self.orphans),
                 "old_daemon_states": [proc_state(d["pid"]) for d in self.orphans],
                 "new_address_differs": new_address != old_address,
                 "new_daemon": bool(self.bus.daemon()), "new_address_answers_ping": ping(new_address)}
        events.append(facts)
        return {"old_address": old_address, "new_address": new_address, **facts}

    def cleanup(self, events: list[Any]) -> None:
        for d in self.orphans:
            if alive(d["pid"]):
                signal_mine(d, signal.SIGCONT, events, "cont-old-daemon")
        for d in reversed(self.orphans):
            if alive(d["pid"]):
                signal_mine(d, signal.SIGTERM, events, "term-old-daemon")
        for d in self.orphans:
            events.append({"old_daemon_gone": self.bus.wait_gone(d["pid"], 3.0), "comm": d["comm"]})
        old = self.old_registry
        if old and alive(old["pid"]):
            if not self.bus.wait_gone(old["pid"], 1.0):
                signal_mine(old, signal.SIGTERM, events, "term-old-registry")
                events.append({"old_registry_gone": self.bus.wait_gone(old["pid"], 3.0)})
        self.orphans = []
        self.old_registry = None


async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / hc.JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402
    from native import NativeObservation, eligible_controls  # noqa: E402

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    block = next(b for b in plan["blocks"] if b["block"] == args.block)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    bins = {"U": (str(Path(args.driver_u).resolve()), args.driver_u_sha256),
            "G": (str(Path(args.driver_g).resolve()), args.driver_g_sha256)}
    for name, (path, sha) in bins.items():
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if actual != sha:
            raise SystemExit(f"refusing: driver {name} sha256 {actual} != {sha}")
    bus = Bus()
    restart = LauncherRestart(bus)
    meta = {"event": "meta", "block": args.block, "kind": block["kind"], "label": args.label,
            "loadavg": hc.loadavg(), "wall_ns": time.time_ns(), "plan_sha256": args.plan_sha256,
            "driver_bins": {k: Path(v[0]).name for k, v in bins.items()},
            "driver_sha256": {k: v[1] for k, v in bins.items()}, "bus_at_start": bus.describe(), "pid": os.getpid()}
    ledger_path = out / "trials.jsonl"
    ledger = open(ledger_path, "w", encoding="utf-8")
    ledger.write(q_common.dumps(meta) + "\n")
    ledger.flush()
    failures = 0

    async def run_trial(t: dict[str, Any]) -> dict[str, Any]:
        driver_bin, driver_sha = bins[t["bin"]]
        variant = t["variant"]
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": hc.loadavg(), "w_begin": time.time_ns(),
                               "driver_bin": Path(driver_bin).name, "driver_sha256": driver_sha}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        state_a, state_b = tdir / "state-a.json", tdir / "state-b.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        fix_a = fix_b = None
        events: list[Any] = []
        steps: dict[str, Any] = {}
        watches: list[q_common.BusWatch] = []
        env = hc.driver_env(driver_environment(), phase_path, {})
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "false"
        address0 = q_common.a11y_address()
        try:
            if address0:
                w = q_common.BusWatch(address0, "bus-0")
                w.start()
                w.ready.wait(timeout=5)
                watches.append(w)
            fix_a = hc.start_fixture(wt, state_a, tdir / "fixture-a.log")
            before_a = hc.read_state(state_a) or {}
            rec["fixture_a_pid"] = fix_a.pid
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
                    from own20q_harness import driver_pid_of  # noqa: E402
                    rec["driver_pid"] = driver_pid_of(os.path.realpath(driver_bin))
                    label = f"own20q-r3-{uuid.uuid4().hex[:8]}"

                    async def call(name: str, arguments: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
                        m0, w0 = time.monotonic_ns(), time.time_ns()
                        try:
                            res = await asyncio.wait_for(
                                session.call_tool(name, {**arguments, "session": label}), timeout=timeout)
                        except asyncio.TimeoutError:
                            return {"tool": name, "timeout": True, "ms": (time.monotonic_ns() - m0) / 1e6, "w0": w0}
                        sc = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                        return {"tool": name, "is_error": bool(res.isError), "structured": sc, "w0": w0,
                                "text": [getattr(c, "text", "")[:500] for c in (res.content or [])
                                         if getattr(c, "type", "") == "text"],
                                "ms": (time.monotonic_ns() - m0) / 1e6}

                    async def find_window(pid: int) -> int | None:
                        for _ in range(40):
                            r = await call("list_windows", {"pid": pid})
                            wins = r.get("structured", {}).get("windows", []) if not r.get("is_error") else []
                            hits = [w for w in wins if w.get("title") == hc.WINDOW_TITLE]
                            if hits:
                                return int(hits[0]["window_id"])
                            await asyncio.sleep(0.25)
                        return None

                    async def observe(pid: int, wid: int) -> dict[str, Any]:
                        r = await call("get_window_state", {"pid": pid, "window_id": wid,
                                                            "include_accessibility_tree": True,
                                                            "include_screenshot": False})
                        sc = r.pop("structured", {})
                        if r.get("is_error") or r.get("timeout"):
                            r["code"] = sc.get("code") or (sc.get("refusal") or {}).get("code")
                            return r
                        r["digest"] = digest(sc, pid, wid, NativeObservation, eligible_controls)
                        return r

                    def outcome(r: dict[str, Any]) -> dict[str, Any]:
                        sc = r.get("structured") or {}
                        r["refused"] = bool(r.get("is_error")) or sc.get("status") == "refused" or bool(sc.get("refusal"))
                        r["code"] = sc.get("code") or (sc.get("refusal") or {}).get("code")
                        r["success"] = not r["refused"] and not r.get("timeout")
                        return r

                    async def click_verified(pid: int, wid: int, token: str, path: Path) -> dict[str, Any]:
                        st = hc.read_state(path) or {}
                        sampler = hc.StateSampler(path)
                        sampler.expected = {"agreed": not bool(st.get("agreed")), "seq": int(st.get("seq", 0)) + 1}
                        sampler.start()
                        r = outcome(await call("click", {"pid": pid, "window_id": wid, "element_token": token,
                                                         "delivery_mode": "background"}))
                        sampler.return_ns = time.monotonic_ns()
                        await asyncio.to_thread(sampler.confirmed.wait, CONFIRM_DEADLINE_S)
                        r["verified"] = sampler.confirmed.is_set()
                        r["expected"] = sampler.expected
                        r["seq_delta"] = int((hc.read_state(path) or {}).get("seq", -1)) - int(st.get("seq", 0))
                        sampler.stop()
                        return r

                    wid_a = await find_window(fix_a.pid)
                    if wid_a is None:
                        raise RuntimeError("task window A did not appear")
                    rec["window_a"] = wid_a
                    o1 = await observe(fix_a.pid, wid_a)
                    steps["observe_1"] = o1
                    if not truthful(o1.get("digest"), hc.read_state(state_a)):
                        rec["failure"] = "precondition: first observation not truthful"
                        return rec
                    t_old = o1["digest"]["agree_token"]
                    if variant == "slow":
                        seq0 = int((hc.read_state(state_a) or {}).get("seq", -1))
                        os.kill(fix_a.pid, signal.SIGSTOP)
                        stopped_ns = time.monotonic_ns()
                        task = asyncio.ensure_future(call("click", {"pid": fix_a.pid, "window_id": wid_a,
                                                                    "element_token": t_old,
                                                                    "delivery_mode": "background"}, timeout=40))
                        await asyncio.sleep(0.5)
                        rec["bus_answers_ping_while_stopped"] = await asyncio.to_thread(ping, address0)
                        try:
                            await asyncio.wait_for(asyncio.shield(task), timeout=STOP_MAX_S)
                        except asyncio.TimeoutError:
                            pass
                        os.kill(fix_a.pid, signal.SIGCONT)
                        rec["stopped_ms"] = (time.monotonic_ns() - stopped_ns) / 1e6
                        slow = outcome(await task)
                        await asyncio.sleep(RESUME_WINDOW_S)
                        slow["seq_delta"] = int((hc.read_state(state_a) or {}).get("seq", -1)) - seq0
                        slow["state_after"] = {k: (hc.read_state(state_a) or {}).get(k) for k in ("agreed", "seq")}
                        steps["slow_click"] = slow
                        o2 = await observe(fix_a.pid, wid_a)
                        steps["observe_2"] = o2
                        tok = (o2.get("digest") or {}).get("agree_token")
                        if truthful(o2.get("digest"), hc.read_state(state_a)) and tok:
                            steps["fresh_click"] = await click_verified(fix_a.pid, wid_a, tok, state_a)
                    else:
                        p0 = time.monotonic_ns()
                        facts = await asyncio.to_thread(restart.perturb, tdir, events, variant == "launcher_wedge")
                        rec["perturb_ms"] = (time.monotonic_ns() - p0) / 1e6
                        new_address = facts.pop("new_address")
                        facts.pop("old_address")
                        rec["perturb_facts"] = facts
                        rec["perturb_events"] = events
                        if new_address:
                            w = q_common.BusWatch(new_address, "bus-1")
                            w.start()
                            w.ready.wait(timeout=5)
                            watches.append(w)
                        seq_before = int((hc.read_state(state_a) or {}).get("seq", -1))
                        stale = outcome(await call("click", {"pid": fix_a.pid, "window_id": wid_a,
                                                             "element_token": t_old, "delivery_mode": "background"}))
                        await asyncio.sleep(STALE_HOLD_S)
                        stale["seq_delta"] = int((hc.read_state(state_a) or {}).get("seq", -1)) - seq_before
                        steps["stale_click"] = stale
                        fix_b = hc.start_fixture(wt, state_b, tdir / "fixture-b.log")
                        rec["fixture_b_pid"] = fix_b.pid
                        wid_b = await find_window(fix_b.pid)
                        rec["window_b"] = wid_b
                        tries: list[dict[str, Any]] = []
                        token_b = None
                        if wid_b is not None:
                            for _ in range(OBSERVE_TRIES):
                                o3 = await observe(fix_b.pid, wid_b)
                                tries.append(o3)
                                if truthful(o3.get("digest"), hc.read_state(state_b)):
                                    token_b = o3["digest"]["agree_token"]
                                    break
                                await asyncio.sleep(1.0)
                        steps["observe_b"] = tries
                        rec["b_truthful_on_try"] = len(tries) if token_b else None
                        if token_b:
                            steps["fresh_click"] = await click_verified(fix_b.pid, wid_b, token_b, state_b)
                    rec["final_state_a"] = hc.read_state(state_a)
                    rec["final_state_b"] = hc.read_state(state_b)
                    rec["seq_a_before"] = int(before_a.get("seq", -1))
        except Exception as exc:  # retained in the denominator
            rec["failure"] = rec.get("failure") or f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            rec["steps"] = steps
            rec["fixture_a_rc"] = hc.stop_process(fix_a)
            rec["fixture_b_rc"] = hc.stop_process(fix_b)
            if variant != "slow":
                await asyncio.to_thread(restart.cleanup, events)
                rec["cleanup_events"] = events[-8:]
            rec["buses"] = [w.stop() for w in watches]
            rec["marks_count"] = len(hc.read_marks(phase_path))
            rec["w_end"] = time.time_ns()
        return rec

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            ledger.write(q_common.dumps(r) + "\n")
            ledger.flush()
            failures += 1 if "failure" in r else 0
    finally:
        ledger.write(q_common.dumps({"event": "end", "failures": failures, "loadavg": hc.loadavg(),
                                     "bus_at_end": bus.describe(), "harness_started_bus_processes":
                                     len(bus.started), "wall_ns": time.time_ns(), "net": hc.NET}) + "\n")
        ledger.close()
        bus.close()
    print(f"done: {ledger_path} failures={failures} net_refused={hc.NET['refused_non_loopback_connects']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("wt", "driver-u", "driver-u-sha256", "driver-g", "driver-g-sha256", "plan",
                 "plan-sha256", "block", "label", "out", "work"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    hc.refuse_outside_session()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

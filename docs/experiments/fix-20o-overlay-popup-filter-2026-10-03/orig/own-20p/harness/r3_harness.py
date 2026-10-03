#!/usr/bin/env python3
"""OWN-20G R3: the AT-SPI accessibility bus restart row for kvnloo/cua#20 (measurement only).

Runs INSIDE cua-x11-session.sh with CUA_SESSION_ATSPI=1 (private session bus, private
AT-SPI bus + registry started by the session); refuses otherwise. One fresh Driver and
one fresh GTK3 task fixture (A) per trial. The sequence, pre-registered in PREREG.json:

1. observe A (``get_window_state``) and keep the element token of "I agree" (T_old);
2. perturb, by variant:
   * ``bus``: kill the accessibility bus daemon (the dbus-daemon child of
     at-spi-bus-launcher, not only the registry), wait for that launcher to exit,
     start a new ``at-spi-bus-launcher --launch-immediately`` and a new
     ``at-spi2-registryd``, and wait until the registry owns its name on the new bus;
   * ``registry``: kill the registry and start a new one on the same bus (the
     inherited OWN-20 registry-restart row);
   * ``noop``: nothing;
3. observe A again: either a fresh truthful tree (the fixture-declared control set,
   and "I agree" checked state equal to A's state file) or a structured error;
4. click T_old (background, A's pid/window): must be refused, and A's state file
   must not change (no mutation from stale authority);
5. a new token must verify: from step 3 when it was truthful, else from a fresh
   observation of a respawned fixture B (which registers on the current bus); the
   click's effect is confirmed by the app's own state file (A or B).

Only processes this harness started, or the session's own launcher/registry
(children of this process's parent, the session's inner shell, with this session's
XDG_RUNTIME_DIR), are ever signalled. No provider: non-loopback connects refused.
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

SLEEP_ENV = "CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS"
DECLARED = sorted(["Increment", "Reset", "I agree", "Small", "Medium", "Large", "Note", "Save note", "Exit"])
LAUNCHER = "/usr/lib/at-spi-bus-launcher"
REGISTRYD = "/usr/lib/at-spi2-registryd"
STALE_HOLD_S = 1.0
OBSERVE_TRIES = 5
CONFIRM_DEADLINE_S = 4.0


def proc_info(pid: int) -> dict[str, Any] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        ppid = int(stat[stat.rindex(")") + 2:].split()[1])
        environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        xdg = next((e.split(b"=", 1)[1].decode() for e in environ if e.startswith(b"XDG_RUNTIME_DIR=")), None)
        return {"pid": pid, "comm": comm, "ppid": ppid, "xdg": xdg}
    except (OSError, ValueError, IndexError):
        return None


def children(ppid: int) -> list[dict[str, Any]]:
    out = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            info = proc_info(int(entry.name))
            if info and info["ppid"] == ppid:
                out.append(info)
    return out


def mine(info: dict[str, Any] | None) -> bool:
    return bool(info) and info["xdg"] == os.environ.get("XDG_RUNTIME_DIR")


def gdbus(*args: str, timeout: float = 3.0) -> tuple[int, str]:
    try:
        res = subprocess.run(["gdbus", "call", *args], capture_output=True, text=True, timeout=timeout)
        return res.returncode, (res.stdout or res.stderr).strip()[:400]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return -1, f"{type(exc).__name__}"


def a11y_address() -> str | None:
    rc, out = gdbus("--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
                    "--method", "org.a11y.Bus.GetAddress", timeout=2.0)
    if rc == 0 and out.startswith("('"):
        return out[2:out.rindex("'")]
    return None


def registry_owner_pid(address: str) -> int | None:
    rc, out = gdbus("--address", address, "--dest", "org.freedesktop.DBus", "--object-path",
                    "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.GetConnectionUnixProcessID",
                    "org.a11y.atspi.Registry", timeout=1.0)
    if rc == 0 and out.startswith("(uint32"):
        return int(out.split()[1].rstrip(",)"))
    return None


class Bus:
    """The session's AT-SPI bus launcher + registry, and the ones this harness restarts."""

    def __init__(self) -> None:
        parent = os.getppid()
        kids = children(parent)
        self.launcher = next((k for k in kids if k["comm"].startswith("at-spi-bus-laun") and mine(k)), None)
        self.registry = next((k for k in kids if k["comm"].startswith("at-spi2-registr") and mine(k)), None)
        self.started: list[subprocess.Popen] = []
        self.logs: list[Any] = []

    def daemon(self) -> dict[str, Any] | None:
        if not self.launcher:
            return None
        return next((k for k in children(self.launcher["pid"]) if k["comm"].startswith("dbus-") and mine(k)), None)

    def describe(self) -> dict[str, Any]:
        address = a11y_address()
        return {"launcher": self.launcher, "daemon": self.daemon(), "registry": self.registry,
                "address_hash": hashlib.sha256(address.encode()).hexdigest()[:12] if address else None,
                "registry_owner_pid": registry_owner_pid(address) if address else None}

    def _spawn(self, cmd: list[str], work: Path, name: str) -> subprocess.Popen:
        log = open(work / f"{name}.log", "w", encoding="utf-8")
        self.logs.append(log)
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        self.started.append(proc)
        return proc

    def _kill(self, info: dict[str, Any] | None, events: list[Any], what: str) -> None:
        if not info or not mine(proc_info(info["pid"])):
            events.append({"kill": what, "skipped": "not this session's process"})
            return
        os.kill(info["pid"], signal.SIGTERM)
        events.append({"kill": what, "pid": info["pid"], "comm": info["comm"], "mono_ns": time.monotonic_ns()})

    def wait_gone(self, pid: int, timeout_s: float) -> bool:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            try:
                state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
            except (OSError, IndexError):
                return True
            if state == "Z":
                for proc in self.started:  # reap our own children
                    if proc.pid == pid:
                        proc.poll()
                return True
            time.sleep(0.01)
        return False

    def restart_registry(self, work: Path, events: list[Any]) -> None:
        address = a11y_address()
        old = self.registry
        self._kill(old, events, "registryd")
        if old:
            events.append({"registry_gone": self.wait_gone(old["pid"], 3.0)})
        proc = self._spawn([REGISTRYD, "--use-gnome-session"], work, f"registryd-{len(self.started)}")
        self.registry = proc_info(proc.pid)
        events.append({"registry_started": proc.pid, "mono_ns": time.monotonic_ns()})
        self.wait_registry(address, proc.pid, events)

    def wait_registry(self, address: str | None, pid: int, events: list[Any]) -> None:
        end = time.monotonic() + 5.0
        owner = None
        while time.monotonic() < end and address:
            owner = registry_owner_pid(address)
            if owner is not None:
                break
            time.sleep(0.02)
        events.append({"registry_owner_pid": owner, "registry_is_started_one": owner == pid,
                       "mono_ns": time.monotonic_ns()})

    def restart_bus(self, work: Path, events: list[Any]) -> None:
        old_address = a11y_address()
        daemon = self.daemon()
        old_launcher = self.launcher
        old_registry = self.registry
        self._kill(daemon, events, "a11y-bus-daemon")
        if daemon:
            events.append({"daemon_gone": self.wait_gone(daemon["pid"], 3.0)})
        if old_launcher:
            gone = self.wait_gone(old_launcher["pid"], 3.0)
            events.append({"launcher_exited_by_itself": gone})
            if not gone:
                self._kill(old_launcher, events, "at-spi-bus-launcher")
                events.append({"launcher_gone": self.wait_gone(old_launcher["pid"], 3.0)})
        if old_registry:
            gone = self.wait_gone(old_registry["pid"], 1.0)
            events.append({"old_registry_exited_by_itself": gone})
            if not gone:
                self._kill(old_registry, events, "registryd")
                events.append({"old_registry_gone": self.wait_gone(old_registry["pid"], 3.0)})
        proc = self._spawn([LAUNCHER, "--launch-immediately"], work, f"launcher-{len(self.started)}")
        self.launcher = proc_info(proc.pid)
        new_address = None
        end = time.monotonic() + 5.0
        while time.monotonic() < end:
            new_address = a11y_address()
            if new_address and self.daemon():
                break
            time.sleep(0.02)
        new_daemon = self.daemon()
        events.append({"launcher_started": proc.pid, "new_daemon": bool(new_daemon),
                       "new_address_same_as_old": new_address == old_address, "mono_ns": time.monotonic_ns()})
        reg = self._spawn([REGISTRYD, "--use-gnome-session"], work, f"registryd-{len(self.started)}")
        self.registry = proc_info(reg.pid)
        events.append({"registry_started": reg.pid, "mono_ns": time.monotonic_ns()})
        self.wait_registry(new_address, reg.pid, events)

    def close(self) -> None:
        for proc in self.started:
            hc.stop_process(proc)
        for log in self.logs:
            log.close()


def truthful(d: dict[str, Any] | None, state: dict[str, Any] | None) -> bool:
    """Fresh truthful tree: the fixture-declared control set, an "I agree" token, not degraded,
    and (when the tree carries it) the checked state equal to the app's own state file."""
    if not d or not state or d["labels"] != DECLARED or not d["agree_token"] or d.get("degraded"):
        return False
    return d["agree_checked"] is None or d["agree_checked"] == bool(state.get("agreed"))


def digest(payload: dict[str, Any], pid: int, wid: int, NativeObservation: Any, eligible_controls: Any) -> dict[str, Any]:
    nobs = NativeObservation.from_window_state(payload, expected_pid=pid, expected_window_id=wid)
    controls = eligible_controls(nobs, "linux").controls
    labels = sorted(c.label for c in controls)
    agree = [c for c in controls if c.label == "I agree"]
    # jev-use reads the element's "selected" field as the check box's checked state
    checked = agree[0].selected if len(agree) == 1 else None
    return {"labels": labels, "element_count": payload.get("element_count"), "snapshot_id": payload.get("snapshot_id"),
            "degraded": payload.get("degraded"), "degraded_reason": str(payload.get("degraded_reason"))[:300]
            if payload.get("degraded_reason") is not None else None,
            "invalidated_snapshot_ids": payload.get("invalidated_snapshot_ids"),
            "agree_token": agree[0].element_token if len(agree) == 1 else None,
            "agree_checked": checked, "keys": sorted(payload)[:40]}


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
    meta = {"event": "meta", "block": args.block, "kind": block["kind"], "label": args.label,
            "loadavg": hc.loadavg(), "wall_ns": time.time_ns(), "plan_sha256": args.plan_sha256,
            "driver_bins": {k: Path(v[0]).name for k, v in bins.items()},
            "driver_sha256": {k: v[1] for k, v in bins.items()}, "bus_at_start": bus.describe(),
            "pid": os.getpid()}
    ledger_path = out / "trials.jsonl"
    ledger = open(ledger_path, "w", encoding="utf-8")
    ledger.write(json.dumps(meta, sort_keys=True) + "\n")
    ledger.flush()
    failures = 0

    async def run_trial(t: dict[str, Any]) -> dict[str, Any]:
        driver_bin, driver_sha = bins[t["bin"]]
        rec: dict[str, Any] = {"event": "trial", **t, "loadavg": hc.loadavg(), "w_begin": time.time_ns(),
                               "driver_bin": Path(driver_bin).name, "driver_sha256": driver_sha}
        tdir = work / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)
        state_a = tdir / "state-a.json"
        state_b = tdir / "state-b.json"
        phase_path = tdir / "phase.jsonl"
        phase_path.write_text("", encoding="utf-8")
        fix_a = fix_b = None
        events: list[Any] = []
        steps: dict[str, Any] = {}
        env = hc.driver_env(driver_environment(), phase_path, {SLEEP_ENV: "0"})
        try:
            fix_a = hc.start_fixture(wt, state_a, tdir / "fixture-a.log")
            before_a = hc.read_state(state_a) or {}
            rec["fixture_a_pid"] = fix_a.pid
            params = StdioServerParameters(command=driver_bin, args=["mcp"], env=env)
            errlog = open(tdir / "driver.stderr", "w", encoding="utf-8")
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.list_tools()
                    label = f"own20g-r3-{uuid.uuid4().hex[:8]}"

                    async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                        m0 = time.monotonic_ns()
                        try:
                            res = await asyncio.wait_for(
                                session.call_tool(name, {**arguments, "session": label}), timeout=30)
                        except asyncio.TimeoutError:
                            return {"tool": name, "timeout": True, "ms": (time.monotonic_ns() - m0) / 1e6}
                        sc = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                        return {"tool": name, "is_error": bool(res.isError), "structured": sc,
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

                    async def observe(pid: int, wid: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
                        r = await call("get_window_state", {"pid": pid, "window_id": wid,
                                                            "include_accessibility_tree": True,
                                                            "include_screenshot": False})
                        sc = r.pop("structured", {})
                        if r.get("is_error") or r.get("timeout"):
                            r["code"] = sc.get("code") or (sc.get("refusal") or {}).get("code")
                            r["structured_keys"] = sorted(sc)[:20]
                            return r, None
                        r["digest"] = digest(sc, pid, wid, NativeObservation, eligible_controls)
                        return r, sc


                    wid_a = await find_window(fix_a.pid)
                    if wid_a is None:
                        raise RuntimeError("task window A did not appear")
                    rec["window_a"] = wid_a
                    o1, _ = await observe(fix_a.pid, wid_a)
                    steps["observe_1"] = o1
                    d1 = o1.get("digest")
                    if not truthful(d1, hc.read_state(state_a)):
                        rec["failure"] = "precondition: first observation not truthful"
                        return rec
                    t_old = d1["agree_token"]
                    rec["bus_before"] = bus.describe()
                    p0 = time.monotonic_ns()
                    if t["variant"] in ("bus", "bus_direct"):
                        await asyncio.to_thread(bus.restart_bus, tdir, events)
                    elif t["variant"] == "registry":
                        await asyncio.to_thread(bus.restart_registry, tdir, events)
                    rec["perturb_ms"] = (time.monotonic_ns() - p0) / 1e6
                    rec["perturb_events"] = events
                    rec["bus_after"] = bus.describe()
                    rec["fixture_a_alive_after_perturb"] = fix_a.poll() is None
                    # step 3: re-observe A (skipped by the *_direct variants: stale click first)
                    direct = t["variant"].endswith("_direct")
                    o2: dict[str, Any] = {}
                    if not direct:
                        o2, _ = await observe(fix_a.pid, wid_a)
                        steps["observe_2"] = o2
                    st_a = hc.read_state(state_a)
                    o2_truthful = truthful(o2.get("digest"), st_a)
                    d2 = o2.get("digest") or {}
                    o2_structured_error = (bool(o2.get("is_error")) and bool(o2.get("code"))) or (
                        bool(d2.get("degraded")) and bool(d2.get("degraded_reason")) and not d2.get("agree_token"))
                    rec["observe_2_truthful"] = o2_truthful
                    rec["observe_2_structured_error"] = o2_structured_error
                    # step 4: the pre-restart token
                    seq_before_stale = int((hc.read_state(state_a) or {}).get("seq", -1))
                    stale = await call("click", {"pid": fix_a.pid, "window_id": wid_a, "element_token": t_old,
                                                 "delivery_mode": "background"})
                    await asyncio.sleep(STALE_HOLD_S)
                    seq_after_stale = int((hc.read_state(state_a) or {}).get("seq", -1))
                    sc = stale.get("structured") or {}
                    stale["refused"] = bool(stale.get("is_error")) or sc.get("status") == "refused" or bool(sc.get("refusal"))
                    stale["code"] = sc.get("code") or (sc.get("refusal") or {}).get("code")
                    stale["seq_before"], stale["seq_after"] = seq_before_stale, seq_after_stale
                    stale["mutated"] = seq_after_stale != seq_before_stale
                    steps["stale_click"] = stale
                    # step 5: a new token verifies
                    target_pid, target_wid, target_state = fix_a.pid, wid_a, state_a
                    new_token = (o2.get("digest") or {}).get("agree_token") if o2_truthful else None
                    if new_token is None:
                        fix_b = hc.start_fixture(wt, state_b, tdir / "fixture-b.log")
                        rec["fixture_b_pid"] = fix_b.pid
                        wid_b = await find_window(fix_b.pid)
                        rec["window_b"] = wid_b
                        if wid_b is not None:
                            tries = []
                            for _ in range(OBSERVE_TRIES):
                                o3, _ = await observe(fix_b.pid, wid_b)
                                tries.append(o3)
                                if truthful(o3.get("digest"), hc.read_state(state_b)):
                                    new_token = o3["digest"]["agree_token"]
                                    target_pid, target_wid, target_state = fix_b.pid, wid_b, state_b
                                    break
                                await asyncio.sleep(1.0)
                            steps["observe_3"] = tries
                    rec["new_token_path"] = ("same_fixture" if target_state == state_a else "respawned_fixture") \
                        if new_token else "none"
                    if new_token:
                        st = hc.read_state(target_state) or {}
                        sampler = hc.StateSampler(target_state)
                        sampler.expected = {"agreed": not bool(st.get("agreed")), "seq": int(st.get("seq", 0)) + 1}
                        sampler.start()
                        fresh = await call("click", {"pid": target_pid, "window_id": target_wid,
                                                     "element_token": new_token, "delivery_mode": "background"})
                        sampler.return_ns = time.monotonic_ns()
                        await asyncio.to_thread(sampler.confirmed.wait, CONFIRM_DEADLINE_S)
                        fresh["verified"] = sampler.confirmed.is_set()
                        fresh["expected"] = sampler.expected
                        sampler.stop()
                        steps["fresh_click"] = fresh
                    rec["final_state_a"] = hc.read_state(state_a)
                    rec["final_state_b"] = hc.read_state(state_b)
                    rec["seq_a_before"] = int(before_a.get("seq", -1))
            # step 6 (diagnostic, never a verdict input): a FRESH Driver process observes A (and B)
            diag: dict[str, Any] = {}
            async with stdio_client(StdioServerParameters(command=driver_bin, args=["mcp"], env=env),
                                    errlog=open(tdir / "driver-diag.stderr", "w", encoding="utf-8")) as (r2, w2):
                async with ClientSession(r2, w2) as s2:
                    await s2.initialize()
                    for name, proc, path, wid in (("a", fix_a, state_a, rec.get("window_a")),
                                                  ("b", fix_b, state_b, rec.get("window_b"))):
                        if proc is None or wid is None or proc.poll() is not None:
                            continue
                        res = await s2.call_tool("get_window_state", {
                            "pid": proc.pid, "window_id": wid, "include_accessibility_tree": True,
                            "include_screenshot": False, "session": "own20g-r3-diag"})
                        sc = res.structuredContent if isinstance(res.structuredContent, dict) else {}
                        dd = None if res.isError else digest(sc, proc.pid, wid, NativeObservation, eligible_controls)
                        diag[name] = {"is_error": bool(res.isError), "truthful": truthful(dd, hc.read_state(path)),
                                      "degraded": (dd or {}).get("degraded"), "labels": (dd or {}).get("labels")}
            rec["fresh_driver_diag"] = diag
        except Exception as exc:  # retained in the denominator
            rec["failure"] = rec.get("failure") or f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            rec["steps"] = steps
            rec["fixture_a_rc"] = hc.stop_process(fix_a)
            rec["fixture_b_rc"] = hc.stop_process(fix_b)
            rec["marks_count"] = len(hc.read_marks(phase_path))
            rec["w_end"] = time.time_ns()
        return rec

    try:
        for t in block["trials"]:
            r = await run_trial(t)
            ledger.write(json.dumps(r, sort_keys=True) + "\n")
            ledger.flush()
            failures += 1 if "failure" in r else 0
    finally:
        ledger.write(json.dumps({"event": "end", "failures": failures, "loadavg": hc.loadavg(),
                                 "bus_at_end": bus.describe(), "harness_started_bus_processes":
                                 [p.pid for p in bus.started], "wall_ns": time.time_ns(), "net": hc.NET},
                                sort_keys=True) + "\n")
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

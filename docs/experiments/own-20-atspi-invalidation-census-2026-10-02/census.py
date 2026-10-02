#!/usr/bin/env python3
"""OWN-20: AT-SPI invalidation-signal fidelity census on the canonical GTK3 fixture (kvnloo/cua#20).

Runs INSIDE one isolated X11 session (cua-x11-session.sh, private AT-SPI bus) per block. One block =
one pre-registered block type, at most 10 measured mutations. Per mutation (the #20 loop):

  1. fresh observation through the Driver (get_window_state, plus list_windows where the scope
     needs it) and a read of the fixture's own state file (cross-check oracle);
  2. the independent listener (atspi_listener.py, started and registered BEFORE the first mutation
     of the block and retained for the block) keeps recording every bus signal;
  3. a guard of GUARD_MS, then ONE known mutation: variant 1 = the fixture mutates itself through
     its env-gated control channel (the Driver is not the producer); variant 2 = the Driver acts;
  4. events are collected until mutation end + QUIESCE_MS (pre-registered, bounded);
  5. fresh observation again and a state-file read.

This harness only records raw data (timestamps on CLOCK_MONOTONIC, observations, acks, state).
analyze.py joins the listener's events to the mutation windows and classifies. Events are
candidate invalidators only; the fresh observation (and the state file) is the ground truth.
Nothing here changes Driver behaviour: the Driver gets jev-use's driver_environment() unchanged.
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
from pathlib import Path
from typing import Any

FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use"
PKT_REL = "docs/experiments/own-20-atspi-invalidation-census-2026-10-02"
TASK_TITLE = "CuaTestHarness GTK3 Tasks"
AUX_TITLE = "CuaTestHarness GTK3 Aux"
GUARD_MS = 100
QUIESCE_MS = 1000
SETTLE_S = 1.0
CHOICES = ("Alpha", "Beta", "Gamma")

# Pre-registered block types (PREREG.json "blocks"): measured mutations per rep, reps per block.
BLOCK_TYPES: dict[str, dict[str, Any]] = {
    "text_v1": {"plan": ["text_v1"], "reps": 10},
    "text_v2": {"plan": ["text_v2"], "reps": 10},
    "focus_v1": {"plan": ["focus_v1"], "reps": 10},
    "focus_v2": {"plan": ["focus_v2"], "reps": 10},
    "selection_v1": {"plan": ["selection_v1"], "reps": 10},
    "selection_v2": {"plan": ["selection_v2"], "reps": 10},
    "checkbox_v1": {"plan": ["checkbox_v1"], "reps": 10},
    "checkbox_v2": {"plan": ["checkbox_v2"], "reps": 10},
    "child_pts": {"plan": ["child_add_pts", "child_remove_pts"], "reps": 5},
    "child_stp": {"plan": ["child_add_stp", "child_remove_stp"], "reps": 5},
    "recreate": {"plan": ["recreate"], "reps": 10},
    "window": {"plan": ["window_create", "window_destroy"], "reps": 5},
    "process_v1": {"plan": ["exit_v1", "process_start", "post_restart_probe"], "reps": 3},
    "process_v2": {"plan": ["exit_v2", "process_start", "post_restart_probe"], "reps": 3},
    "registry": {"plan": ["registry_restart", "post_registry_probe"], "reps": 5},
    "noop": {"plan": ["noop"], "reps": 10},
    "decoy": {"plan": ["decoy"], "reps": 10},
    "listener_cycle": {"plan": ["listener_cycle"], "reps": 10},
}


def mono() -> int:
    return time.monotonic_ns()


def loadavg() -> list[float]:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return [float(x) for x in stream.read().split()[:3]]


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def session_procs(comm_prefix: str) -> list[int]:
    """Processes of THIS isolated session (same private XDG_RUNTIME_DIR) whose comm matches."""
    marker = f"XDG_RUNTIME_DIR={os.environ['XDG_RUNTIME_DIR']}".encode()
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text()
            env = Path(f"/proc/{entry}/environ").read_bytes().split(b"\0")
        except OSError:
            continue
        comm = stat[stat.find("(") + 1:stat.rfind(")")]
        if comm.startswith(comm_prefix) and marker in env:
            found.append(int(entry))
    return found


def scope_fields(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """The selected fields per scope, from one get_window_state element list."""
    def pick(pred, keys):
        return [[e.get(k) for k in keys] for e in elements if pred(e)]
    return {
        "text": pick(lambda e: e.get("role") == "text" and e.get("label") == "Note", ("label", "value")),
        "selection": pick(lambda e: str(e.get("label", "")).startswith("Choice "), ("label", "selected")),
        "checkbox": pick(lambda e: e.get("label") == "I agree", ("label", "selected")),
        "children": sorted([e.get("role"), e.get("label")] for e in elements),
        "recreate": pick(lambda e: e.get("label") == "Recreatable", ("role", "label", "frame")),
        "full": [[e.get(k) for k in ("role", "label", "value", "selected", "enabled", "frame")] for e in elements],
    }


class Fixture:
    """One GTK3 fixture process in task mode with the env-gated control channel."""

    def __init__(self, wt: Path, work: Path, tag: str) -> None:
        self.wt, self.work, self.tag = wt, work, tag
        self.fifo = work / f"{tag}.fifo"
        self.ack = work / f"{tag}.ack.jsonl"
        self.state = work / f"{tag}.state.json"
        self.proc: subprocess.Popen | None = None
        self.wfd: int | None = None
        self.ack_offset = 0
        self.counter = 0
        if not self.fifo.exists():
            os.mkfifo(self.fifo)

    def start(self) -> dict[str, Any]:
        if self.state.exists():
            self.state.unlink()
        env = dict(os.environ, CUA_GTK3_TASK_STATE=str(self.state), CUA_GTK3_CONTROL_FIFO=str(self.fifo),
                   CUA_GTK3_CONTROL_ACK=str(self.ack))
        m0 = mono()
        self.proc = subprocess.Popen(["/usr/bin/python3", str(self.wt / FIXTURE_REL)], env=env,
                                     stdout=open(self.work / f"{self.tag}.log", "a"), stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while True:
            st = read_json(self.state)
            if st is not None and st.get("pid") == self.proc.pid:
                break
            if time.monotonic() > deadline or self.proc.poll() is not None:
                raise RuntimeError(f"fixture {self.tag} did not publish its state file")
            time.sleep(0.002)
        m1 = mono()
        if self.wfd is not None:
            os.close(self.wfd)
        self.wfd = os.open(self.fifo, os.O_WRONLY)
        return {"pid": self.proc.pid, "m_start": m0, "m_published": m1}

    def command(self, op: str, timeout_s: float = 5.0, **kw: Any) -> dict[str, Any]:
        self.counter += 1
        cid = f"{self.tag}-{self.counter}-{op}"
        line = json.dumps({"id": cid, "op": op, **kw}) + "\n"
        m_write = mono()
        os.write(self.wfd, line.encode())
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with open(self.ack, "rb") as stream:
                    stream.seek(self.ack_offset)
                    chunk = stream.read()
            except OSError:
                chunk = b""
            done = chunk[: chunk.rfind(b"\n") + 1] if b"\n" in chunk else b""
            if done:
                self.ack_offset += len(done)
                for raw in done.decode().splitlines():
                    ack = json.loads(raw)
                    if ack.get("id") == cid:
                        return {"id": cid, "m_write": m_write, "m_seen": mono(), "ack": ack}
            time.sleep(0.001)
        return {"id": cid, "m_write": m_write, "m_seen": mono(), "ack": None, "error": "ack timeout"}

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


class Listener:
    """The independent AT-SPI listener process (system python3 + Gio)."""

    def __init__(self, wt: Path, path: Path, tag: str) -> None:
        self.path = path
        m0 = mono()
        self.proc = subprocess.Popen(["/usr/bin/python3", str(wt / PKT_REL / "atspi_listener.py"), str(path),
                                      "--tag", tag], stderr=open(str(path) + ".err", "w"))
        deadline = time.monotonic() + 15
        self.ready = None
        while self.ready is None:
            if time.monotonic() > deadline or self.proc.poll() is not None:
                raise RuntimeError(f"listener {tag} did not become ready")
            if path.exists():
                for raw in path.read_text().splitlines():
                    if '"event": "ready"' in raw:
                        self.ready = json.loads(raw)
                        break
            if self.ready is None:
                time.sleep(0.001)
        self.m_spawn, self.m_ready_seen = m0, mono()

    def stop(self) -> dict[str, Any]:
        m0 = mono()
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(5)
            rc = self.proc.returncode
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            rc = "killed"
        m1 = mono()
        cleanup = None
        for raw in self.path.read_text().splitlines():
            if '"event": "cleanup"' in raw:
                cleanup = json.loads(raw)
        return {"m_stop": m0, "m_exited": m1, "stop_to_exit_ms": (m1 - m0) / 1e6, "rc": rc, "cleanup": cleanup}

    def harness_view(self) -> dict[str, Any]:
        return {"m_spawn": self.m_spawn, "m_ready_seen": self.m_ready_seen,
                "spawn_to_ready_ms": (self.m_ready_seen - self.m_spawn) / 1e6, "ready": self.ready}


async def run(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL / "python"))
    from mcp import ClientSession, StdioServerParameters  # noqa: E402
    from mcp.client.stdio import stdio_client  # noqa: E402

    from driver_env import driver_environment  # noqa: E402

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    btype = BLOCK_TYPES[args.block_type]
    reps = args.reps if args.reps is not None else btype["reps"]
    ledger = open(out / "mutations.jsonl", "w", encoding="utf-8")

    def emit(rec: dict[str, Any]) -> None:
        ledger.write(json.dumps(rec, sort_keys=True) + "\n")
        ledger.flush()

    emit({"event": "block_start", "block_id": args.block_id, "block_type": args.block_type, "reps": reps,
          "plan": btype["plan"], "mode": args.mode, "guard_ms": GUARD_MS, "quiesce_ms": QUIESCE_MS,
          "display": os.environ.get("DISPLAY"), "session_atspi": os.environ.get("CUA_SESSION_ATSPI"),
          "loadavg": loadavg(), "m_ns": mono(), "w_ns": time.time_ns()})

    # The retained listener is registered BEFORE any fixture starts and before every mutation.
    listener = Listener(wt, out / "events.jsonl", "retained")
    emit({"event": "listener_ready", **listener.harness_view()})
    target = Fixture(wt, work, "target")
    started = target.start()
    emit({"event": "fixture_start", "role": "target", **started})
    decoy = None
    if args.block_type == "decoy":
        decoy = Fixture(wt, work, "decoy")
        emit({"event": "fixture_start", "role": "decoy", **decoy.start()})
    registry_children: list[subprocess.Popen] = []
    time.sleep(SETTLE_S)

    params = StdioServerParameters(command=args.driver, args=["mcp"], env=driver_environment())
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def tool(name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
                    m0 = mono()
                    try:
                        res = await session.call_tool(name, arguments)
                        exc = None
                    except Exception as error:  # kept in the denominator
                        res, exc = None, f"{type(error).__name__}: {str(error)[:300]}"
                    m1 = mono()
                    meta = {"tool": name, "m0": m0, "m1": m1, "ms": (m1 - m0) / 1e6}
                    if exc is not None:
                        meta["exception"] = exc
                    else:
                        meta["is_error"] = bool(res.isError)
                    return res, meta

                async def window_id_of(pid: int) -> int | None:
                    for _ in range(40):
                        res, _meta = await tool("list_windows", {"pid": pid})
                        wins = (res.structuredContent or {}).get("windows", []) if res is not None else []
                        hits = [w for w in wins if w.get("title") == TASK_TITLE]
                        if hits:
                            return int(hits[0]["window_id"])
                        await asyncio.sleep(0.1)
                    return None

                ctx: dict[str, Any] = {"pid": target.proc.pid}
                ctx["wid"] = await window_id_of(ctx["pid"])
                if ctx["wid"] is None:
                    emit({"event": "window_not_found"})
                    raise RuntimeError("task window did not appear")
                emit({"event": "driver_session", "window_found": True})

                async def observe(kind: str) -> dict[str, Any]:
                    """Fresh Driver observation of the target + the target's own state file."""
                    rec: dict[str, Any] = {"kind": kind, "pid": ctx["pid"], "window_id": ctx["wid"]}
                    res, meta = await tool("get_window_state", {"pid": ctx["pid"], "window_id": ctx["wid"],
                                                                "include_screenshot": False})
                    rec["gws"] = meta
                    sc = res.structuredContent if res is not None and isinstance(res.structuredContent, dict) else {}
                    elements = sc.get("elements") if isinstance(sc.get("elements"), list) else []
                    rec["element_count"] = len(elements)
                    rec["degraded"] = sc.get("degraded")
                    if res is not None and res.isError:
                        rec["error_text"] = " ".join(getattr(c, "text", "") for c in res.content or [])[:300]
                    fields = scope_fields(elements)
                    rec["fields"] = fields
                    rec["digests"] = {k: digest(v) for k, v in fields.items()}
                    rec["tokens"] = {e.get("label"): e.get("element_token") for e in elements}
                    if args.block_type in ("window", "process_v1", "process_v2"):
                        res2, meta2 = await tool("list_windows", {})
                        wins = (res2.structuredContent or {}).get("windows", []) if res2 is not None else []
                        rec["list_windows"] = meta2
                        rec["windows"] = sorted([w.get("pid"), w.get("title")] for w in wins
                                                if w.get("title") in (TASK_TITLE, AUX_TITLE))
                        rec["digests"]["windows_of_target"] = digest(sorted(w[1] for w in rec["windows"]
                                                                            if w[0] == ctx["pid"]))
                        rec["digests"]["task_windows"] = digest([w for w in rec["windows"] if w[1] == TASK_TITLE])
                    rec["state"] = read_json(target.state)
                    return rec

                await observe("warmup")  # unmeasured first walk, as in prior packets
                await asyncio.sleep(0.3)

                async def mutate(mid: str, rep: int) -> dict[str, Any]:
                    """Apply ONE known mutation; returns its timing and producer details."""
                    m: dict[str, Any] = {}
                    st = read_json(target.state) or {}
                    ctl = st.get("control") or {}
                    tokens = ctx.get("tokens", {})
                    target_wid = {"pid": ctx["pid"], "window_id": ctx["wid"]}
                    if mid == "text_v1":
                        r = target.command("set_text", value=f"v1-{args.block_id}-{rep}")
                        m.update(producer="fixture", control=r)
                    elif mid == "text_v2":
                        res, meta = await tool("set_value", {**target_wid, "element_token": tokens.get("Note"),
                                                             "value": f"v2-{args.block_id}-{rep}"})
                        m.update(producer="driver", call=meta, structured=_short(res))
                    elif mid == "focus_v1":
                        to = "I agree" if ctl.get("focus") == "Note" else "Note"
                        r = target.command("focus", target=to)
                        m.update(producer="fixture", control=r, focus_target=to)
                    elif mid == "focus_v2":
                        res, meta = await tool("press_key", {**target_wid, "key": "Tab", "delivery_mode": "foreground"})
                        m.update(producer="driver", call=meta, structured=_short(res))
                    elif mid == "selection_v1":
                        cur = ctl.get("selection")
                        nxt = CHOICES[(CHOICES.index(cur) + 1) % 3] if cur in CHOICES else CHOICES[0]
                        r = target.command("select", value=nxt)
                        m.update(producer="fixture", control=r, select_value=nxt)
                    elif mid == "selection_v2":
                        cur = ctl.get("selection")
                        nxt = CHOICES[(CHOICES.index(cur) + 1) % 3] if cur in CHOICES else CHOICES[0]
                        res, meta = await tool("click", {**target_wid, "element_token": tokens.get(f"Choice {nxt}"),
                                                         "delivery_mode": "foreground"})
                        m.update(producer="driver", call=meta, structured=_short(res), select_value=nxt)
                    elif mid in ("checkbox_v1", "post_restart_probe", "post_registry_probe"):
                        r = target.command("toggle_check")
                        m.update(producer="fixture", control=r)
                    elif mid == "checkbox_v2":
                        res, meta = await tool("click", {**target_wid, "element_token": tokens.get("I agree"),
                                                         "delivery_mode": "background"})
                        m.update(producer="driver", call=meta, structured=_short(res))
                    elif mid in ("child_add_pts", "child_add_stp"):
                        order = "pack_then_show" if mid.endswith("pts") else "show_then_pack"
                        r = target.command("add_child", order=order)
                        m.update(producer="fixture", control=r, order=order)
                    elif mid in ("child_remove_pts", "child_remove_stp"):
                        r = target.command("remove_child")
                        m.update(producer="fixture", control=r)
                    elif mid == "recreate":
                        r = target.command("recreate")
                        m.update(producer="fixture", control=r)
                    elif mid == "window_create":
                        r = target.command("window_open")
                        m.update(producer="fixture", control=r)
                    elif mid == "window_destroy":
                        r = target.command("window_close")
                        m.update(producer="fixture", control=r)
                    elif mid == "noop":
                        r = target.command("noop")
                        m.update(producer="fixture", control=r)
                    elif mid == "decoy":
                        op = "toggle_check" if rep % 2 == 0 else "set_text"
                        r = decoy.command(op, **({"value": f"decoy-{rep}"} if op == "set_text" else {}))
                        m.update(producer="decoy_fixture", control=r, decoy_pid=decoy.proc.pid, decoy_op=op)
                    elif mid == "exit_v1":
                        m0 = mono()
                        target.proc.send_signal(signal.SIGTERM)
                        rc = target.proc.wait(10)
                        m.update(producer="harness_sigterm", m_start=m0, m_end=mono(), exit_rc=rc,
                                 exited_pid=target.proc.pid)
                    elif mid == "exit_v2":
                        res, meta = await tool("click", {**target_wid, "element_token": tokens.get("Exit"),
                                                         "delivery_mode": "background"})
                        try:
                            rc = target.proc.wait(10)
                        except subprocess.TimeoutExpired:
                            rc = None
                        m.update(producer="driver", call=meta, structured=_short(res), m_reaped=mono(),
                                 exit_rc=rc, exited_pid=target.proc.pid)
                    elif mid == "process_start":
                        info = target.start()
                        ctx["pid"] = info["pid"]
                        ctx["wid"] = await window_id_of(ctx["pid"])
                        m.update(producer="harness_spawn", start=info, m_window_found=mono(),
                                 window_id=ctx["wid"])
                    elif mid == "registry_restart":
                        old = session_procs("at-spi2-registr")
                        m0 = mono()
                        for pid in old:
                            os.kill(pid, signal.SIGTERM)
                        deadline = time.monotonic() + 5
                        while any(Path(f"/proc/{p}").exists() for p in old) and time.monotonic() < deadline:
                            time.sleep(0.002)
                        m_gone = mono()
                        child = subprocess.Popen(["/usr/lib/at-spi2-registryd", "--use-gnome-session"],
                                                 stdout=open(work / "registry-relaunch.log", "a"),
                                                 stderr=subprocess.STDOUT)
                        registry_children.append(child)
                        m.update(producer="harness_registry_restart", m_start=m0, m_old_gone=m_gone,
                                 m_end=mono(), killed=old, relaunched_pid=child.pid)
                    elif mid == "listener_cycle":
                        fresh = Listener(wt, out / f"fresh-{rep:02d}.jsonl", f"fresh-{rep:02d}")
                        r = target.command("toggle_check")
                        m.update(producer="fixture", control=r, fresh_listener=fresh.harness_view())
                        ctx["fresh"] = fresh
                    else:
                        raise ValueError(mid)
                    return m

                index = 0
                for rep in range(reps):
                    for mid in btype["plan"]:
                        rec: dict[str, Any] = {"event": "mutation", "block_id": args.block_id,
                                               "block_type": args.block_type, "mutation_id": mid, "rep": rep,
                                               "index": index, "loadavg": loadavg()}
                        index += 1
                        try:
                            before = await observe("before")
                            ctx["tokens"] = before.pop("tokens")
                            rec["before"] = before
                            rec["pid_before"] = ctx["pid"]
                            await asyncio.sleep(GUARD_MS / 1000)
                            rec["m_mut_start"] = mono()
                            mres = await mutate(mid, rep)
                            rec["m_mut_end"] = mono()
                            rec["mutation"] = mres
                            await asyncio.sleep(max(0.0, (rec["m_mut_end"] + QUIESCE_MS * 1_000_000 - mono()) / 1e9))
                            rec["m_window_end"] = mono()
                            if "fresh" in ctx:
                                rec["fresh_listener_stop"] = ctx.pop("fresh").stop()
                            if mid in ("exit_v1", "exit_v2"):
                                after = await observe("after_exit")  # old pid/window: expected stale
                            else:
                                after = await observe("after")
                            after.pop("tokens", None)
                            rec["after"] = after
                            rec["pid_after"] = ctx["pid"]
                        except Exception as error:  # every failure stays in the denominator
                            rec["failure"] = f"{type(error).__name__}: {str(error)[:300]}"
                        emit(rec)
    finally:
        emit({"event": "teardown_start", "m_ns": mono(), "loadavg": loadavg()})
        target.stop()
        if decoy is not None:
            decoy.stop()
        for child in registry_children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(5)
                except subprocess.TimeoutExpired:
                    child.kill()
        emit({"event": "listener_stop", **listener.stop()})
        emit({"event": "block_end", "m_ns": mono(), "w_ns": time.time_ns(), "loadavg": loadavg()})
        ledger.close()
    return 0


def _short(res: Any) -> dict[str, Any] | None:
    if res is None:
        return None
    sc = res.structuredContent if isinstance(res.structuredContent, dict) else {}
    keep = {k: sc.get(k) for k in ("route", "effect", "status", "code", "delivery", "refusal") if k in sc}
    keep["is_error"] = bool(res.isError)
    return keep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wt", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--block-type", required=True, choices=sorted(BLOCK_TYPES))
    parser.add_argument("--block-id", required=True)
    parser.add_argument("--reps", type=int, default=None)
    parser.add_argument("--mode", default="measured", choices=("measured", "pilot"))
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())

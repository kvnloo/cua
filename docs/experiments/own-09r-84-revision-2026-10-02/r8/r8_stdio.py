#!/usr/bin/env python3
"""OWN-09R R8: REAL MCP stdio ``notifications/cancelled`` sent while the Driver's
native work is provably in flight (measurement only; no provider).

Per trial: a fresh barrier fixture (``fixture_barrier.py``, GTK3 task window)
and a fresh ``cua-driver mcp`` process. The harness speaks raw JSON-RPC lines
on the Driver's stdin/stdout so it controls exactly when each line is written.

1. initialize, list_windows, get_window_state; find the Note entry's
   element_token through the jev-use native observation helper.
2. tools/call set_value(Note, token) with JSON-RPC id K. The fixture's GTK
   handler journals ``effect-enter`` inside the AT-SPI SetTextContents call and
   blocks until released, so the Driver's native call is in flight.
3. variant ``notification_mid_native``: once ``effect-enter`` is in the
   journal, write ``notifications/cancelled {requestId: K}``. Variant
   ``control_no_cancel``: write nothing.
4. 300 ms negative window (is there any response for K yet?), then release the
   barrier, wait for the response to K, then send tools/list (K+1) to show the
   transport is alive and the notification produced no error response.

Oracle: the fixture's journal (effect-enter / effect-applied per token),
written only by the fixture process. Driver responses are recorded but are not
the oracle for whether the effect landed.

Classification (pre-registered): IGNORED = the effect landed exactly once and
the response for K was delivered as a success; HONORED = no success response
for K (cancelled/omitted). Any second ``effect-applied`` for the token is a
duplicate mutation (E4 failure) in every variant.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use/python"
WINDOW_TITLE = "CuaTestHarness GTK3 Tasks"
NEGATIVE_WINDOW_S = 0.3
WAIT_S = 10.0
SESSION_VARS = ("DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
                "AT_SPI_BUS_ADDRESS", "XDG_SESSION_TYPE", "HOME", "PATH", "USER", "LOGNAME",
                "LANG", "TMPDIR", "DO_NOT_TRACK")


def loadavg() -> list[float]:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return [float(x) for x in stream.read().split()[:3]]


class Rpc:
    """Raw JSON-RPC over the Driver's stdio, one line per message."""

    def __init__(self, cmd: list[str], env: dict[str, str], stderr_path: Path) -> None:
        self.stderr = open(stderr_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, env=env, text=True, bufsize=1)
        self.inbox: queue.Queue[tuple[int, Any]] = queue.Queue()
        self.received: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            mono = time.monotonic_ns()
            try:
                msg = json.loads(line)
            except ValueError:
                msg = {"unparsable": line[:200]}
            self.inbox.put((mono, msg))

    def send(self, msg: dict[str, Any]) -> int:
        assert self.proc.stdin is not None
        mono = time.monotonic_ns()
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        self.sent.append({"mono_ns": mono, "method": msg.get("method"), "id": msg.get("id")})
        return mono

    def wait(self, rid: Any, timeout: float) -> tuple[int, dict[str, Any]] | None:
        """Wait for the response with id ``rid``; every message is recorded."""
        deadline = time.monotonic() + timeout
        for entry in self.received:
            if entry["msg"].get("id") == rid and "method" not in entry["msg"]:
                return entry["mono_ns"], entry["msg"]
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            try:
                mono, msg = self.inbox.get(timeout=left)
            except queue.Empty:
                return None
            self.received.append({"mono_ns": mono, "msg": msg})
            if msg.get("id") == rid and "method" not in msg:
                return mono, msg

    def drain(self) -> None:
        while True:
            try:
                mono, msg = self.inbox.get_nowait()
            except queue.Empty:
                return
            self.received.append({"mono_ns": mono, "msg": msg})

    def call(self, rid: int, name: str, arguments: dict[str, Any], timeout: float = WAIT_S) -> dict[str, Any]:
        self.send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}})
        got = self.wait(rid, timeout)
        if got is None:
            raise RuntimeError(f"no response to {name} ({rid})")
        return got[1]

    def close(self) -> int | None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            return self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                return self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                return self.proc.wait()
        finally:
            self.stderr.close()


def read_journal(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def structured(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") or {}
    value = result.get("structuredContent")
    return value if isinstance(value, dict) else {}


def run_trial(args: argparse.Namespace, variant: str, index: int, work: Path) -> dict[str, Any]:
    from native import NativeObservation, eligible_controls  # noqa: E402  (jev-use helper)

    wt = Path(args.wt).resolve()
    tdir = work / f"{variant}-{index:03d}"
    tdir.mkdir(parents=True, exist_ok=True)
    journal = tdir / "journal.jsonl"
    release = tdir / "release.txt"
    state = tdir / "state.json"
    rec: dict[str, Any] = {"lane": "OWN-09R", "route": "mcp_stdio", "arm": args.arm, "row": "R8",
                           "variant": variant, "iter": index, "loadavg": loadavg(),
                           "utc_start": time.time()}
    fenv = dict(os.environ)
    fenv.update({"CUA_GTK3_TASK_STATE": str(state), "OWN09R_JOURNAL": str(journal),
                 "OWN09R_RELEASE": str(release), "OWN09R_HOLD_MAX_MS": "2500"})
    flog = open(tdir / "fixture.log", "w", encoding="utf-8")
    fixture = subprocess.Popen(["/usr/bin/python3", str(HERE / "fixture_barrier.py"), str(wt / FIXTURE_REL)],
                               env=fenv, stdout=flog, stderr=subprocess.STDOUT)
    denv = {k: v for k, v in os.environ.items() if k in SESSION_VARS or k.startswith("CUA_DRIVER_")}
    rpc = None
    token = f"own09r-{args.arm}-{variant}-{index}-{uuid.uuid4().hex[:6]}!"
    rec["token"] = token
    try:
        deadline = time.monotonic() + 15
        while not state.exists():
            if time.monotonic() > deadline or fixture.poll() is not None:
                raise RuntimeError("fixture did not publish its state file")
            time.sleep(0.02)
        time.sleep(1.0)  # AT-SPI registration settle (as R2-04 / N-01R)
        rpc = Rpc([str(Path(args.driver).resolve()), "mcp"], denv, tdir / "driver.stderr")
        rpc.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "own09r-r8", "version": "0"}}})
        if rpc.wait(1, WAIT_S) is None:
            raise RuntimeError("initialize timed out")
        rpc.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        label = f"own09r-{uuid.uuid4().hex[:8]}"
        window_id = None
        for attempt in range(60):
            res = rpc.call(10 + attempt, "list_windows", {"pid": fixture.pid, "session": label})
            wins = structured(res).get("windows", [])
            hits = [w for w in wins if w.get("title") == WINDOW_TITLE and w.get("is_on_screen") is not False]
            if hits:
                window_id = int(hits[0]["window_id"])
                break
            time.sleep(0.25)
        if window_id is None:
            raise RuntimeError("task window did not appear")
        target = {"pid": fixture.pid, "window_id": window_id, "session": label}
        obs = rpc.call(100, "get_window_state", {**target, "include_accessibility_tree": True,
                                                 "include_screenshot": False})
        payload = structured(obs)
        controls = eligible_controls(
            NativeObservation.from_window_state(payload, expected_pid=fixture.pid,
                                                expected_window_id=window_id), "linux").controls
        notes = [c for c in controls if c.label == "Note"]
        if len(notes) != 1:
            raise RuntimeError(f"Note entry not found uniquely ({len(notes)})")
        rid = 200
        t_call = rpc.send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                           "params": {"name": "set_value", "arguments": {
                               **target, "element_token": notes[0].element_token, "value": token}}})
        # Phase proof: the fixture journals effect-enter from inside the
        # SetTextContents call; the Driver's native work is in flight.
        enter = None
        deadline = time.monotonic() + WAIT_S
        while enter is None and time.monotonic() < deadline:
            enter = next((e for e in read_journal(journal)
                          if e.get("event") == "effect-enter" and e.get("text") == token), None)
            if enter is None:
                time.sleep(0.002)
        if enter is None:
            raise RuntimeError("effect-enter never journaled")
        t_notify = None
        if variant == "notification_mid_native":
            t_notify = rpc.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                 "params": {"requestId": rid, "reason": "own09r R8 mid native work"}})
        early = rpc.wait(rid, NEGATIVE_WINDOW_S)
        t_release = time.monotonic_ns()
        release.write_text(token, encoding="utf-8")
        got = early or rpc.wait(rid, WAIT_S)
        rpc.send({"jsonrpc": "2.0", "id": rid + 1, "method": "tools/list"})
        alive = rpc.wait(rid + 1, WAIT_S)
        time.sleep(0.2)
        rpc.drain()
        entries = read_journal(journal)
        applied = [e for e in entries if e.get("event") == "effect-applied" and e.get("text") == token]
        entered = [e for e in entries if e.get("event") == "effect-enter" and e.get("text") == token]
        response = got[1] if got else None
        delivered_ok = bool(response and "result" in response
                            and (response["result"] or {}).get("isError") is not True)
        sent_ids = {entry["id"] for entry in rpc.sent if entry["id"] is not None}
        # Anything not answering one of our requests, e.g. an error reply to the
        # notification (id null) or a server-initiated message.
        stray = [m["msg"] for m in rpc.received if m["msg"].get("id") not in sent_ids]
        checks: dict[str, Any] = {
            "phase_enter_before_notify": (t_notify is None) or enter["mono_ns"] < t_notify,
            "phase_notify_before_applied": (t_notify is None) or bool(applied and t_notify < applied[0]["mono_ns"]),
            "response_within_negative_window": early is not None,
            "response_delivered_ok": delivered_ok,
            "response_is_error": bool(response and (response.get("result") or {}).get("isError") is True),
            "response_error_object": (response or {}).get("error"),
            "transport_alive_after": alive is not None and "result" in alive[1],
            "stray_messages": stray[:5],
            "effects_entered": len(entered),
            "effects_applied": len(applied),
            "barrier_released_by_harness": bool(applied and applied[0].get("released")),
        }
        rec["checks"] = checks
        rec["timeline_ns_from_call"] = {
            "effect_enter": enter["mono_ns"] - t_call,
            "notify": None if t_notify is None else t_notify - t_call,
            "release": t_release - t_call,
            "response": None if not got else got[0] - t_call,
            "applied": None if not applied else applied[0]["mono_ns"] - t_call,
        }
        duplicate = len(applied) > 1
        if variant == "notification_mid_native":
            if duplicate:
                rec["verdict"] = "DUPLICATE"
            elif len(applied) == 1 and delivered_ok:
                rec["verdict"] = "IGNORED"
            else:
                rec["verdict"] = "HONORED"
        else:
            ok = len(applied) == 1 and delivered_ok and checks["transport_alive_after"]
            rec["verdict"] = "PASS" if ok else "FAIL"
        rec["response"] = response
    except Exception as exc:  # every failure stays in the denominator
        rec["verdict"] = "HARNESS_ERROR"
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        if rpc is not None:
            rec["driver_exit"] = rpc.close()
            rec["sent"] = rpc.sent
        fixture.terminate()
        try:
            fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fixture.kill()
            fixture.wait()
        flog.close()
        rec["journal"] = read_journal(journal)
        rec["utc_end"] = time.time()
    return rec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wt", required=True, help="repository worktree (fixture + jev-use helper)")
    parser.add_argument("--driver", required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--variant", required=True, choices=["notification_mid_native", "control_no_cancel"])
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--out", required=True, help="raw JSONL output file (appended)")
    parser.add_argument("--work", required=True)
    args = parser.parse_args()
    host_runtime = Path(f"/run/user/{os.getuid()}")
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY") or not os.environ.get("AT_SPI_BUS_ADDRESS", "x")
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith(str(host_runtime))):
        raise SystemExit("refusing: not inside hostless + the isolated X11 session")
    sys.path.insert(0, str(Path(args.wt).resolve() / JEV_REL))
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with open(out, "a", encoding="utf-8") as stream:
        for index in range(args.n):
            rec = run_trial(args, args.variant, index, work)
            counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
            stream.write(json.dumps(rec, sort_keys=True) + "\n")
            stream.flush()
    print(f"OWN09R R8 arm={args.arm} variant={args.variant} n={args.n} verdicts={sorted(counts.items())}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""OWN-20Q: the mark-free stall trigger, the steal and the _NET_ACTIVE_WINDOW lag (measurement only).

A new file; OWN-20G's ``xstall_proxy.py`` stays blob-identical (its ``RequestParser`` is imported).

Trigger (pre-registered, PREREG.json ``r1m.trigger``): the reference R is the moment the AT-SPI
``DoAction`` reply, routed by the private accessibility bus from the fixture to the Driver, is observed
by this process's own bus monitor (``q_common.BusWatch``: ``dbus-monitor --binary``, BecomeMonitor),
for the first DoAction call made after the harness issued the click (the harness writes
``click <wall_ns>`` on this process's stdin just before the MCP call; ``set_value`` sends a DoAction
of its own before that). Nothing of the Driver is read: no phase trace, no mark. The Driver's X connections reach the private
Xvfb through this process (``--listen``, a filesystem socket ``/tmp/.X11-unix/X<M>`` on the session's
private tmpfs; the Driver gets ``DISPLAY=:M``).

Modes:

* ``stall``: on X connections accepted after the DoAction *call* was observed (the guard's restore
  connection; the snapshot connection is older), the guard's first new-client read (the second
  ``_NET_CLIENT_LIST_STACKING`` GetProperty after a GetInputFocus) issued at least ``hold_after_ms``
  after R has its reply held for ``pause_ms``. Client-to-server bytes are never held, so the server
  answers in real time: c08-017.
* ``lag``: every ``GetProperty(_NET_ACTIVE_WINDOW)`` reply to the Driver carries the value the property
  had ``lag_ms`` before the request. The history comes from this process's own PropertyNotify
  subscription on the root window, so the Driver sees the window manager's ``_NET_ACTIVE_WINDOW``
  updates late while the core focus and the stacking list stay live (the OWN-20G same_app_dialog
  mechanism, made deterministic).
* ``pass``: forward only.

``--steal-ms`` (optional): at R + steal_ms the decoy window is activated on this process's own X
connection (EWMH request, raise, XSetInputFocus: ``stealer.steal``'s three requests).
``--trace`` (calibration on the marked twins only): the Driver phase trace is tailed for the
``atspi_action do_action_replied`` mark, and the request the OWN-20P mark-keyed rule would have held is
recorded next to the one this rule holds; it never acts on the mark.

The bus address comes from the environment (``OWN20Q_A11Y_ADDRESS``) and is never printed.
Prints {"ready": true} once listening and one JSON summary on SIGTERM.
"""

from __future__ import annotations

import argparse
import array
import ctypes
import json
import os
import signal
import socket
import struct
import threading
import time
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q_common  # noqa: E402
import xprobe  # noqa: E402  (OWN-20G, blob-identical)
from xstall_proxy import RequestParser  # noqa: E402  (OWN-20G, blob-identical)

MAX_FDS = 16
GET_INPUT_FOCUS = 43
GET_PROPERTY = 20
PROPERTY_NOTIFY = 28
PROPERTY_CHANGE_MASK = 1 << 22
MARK = '"mark":"do_action_replied"'
SCOPE = '"scope":"atspi_action"'

X = xprobe.X
X.XSelectInput.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_long]
X.XPending.argtypes = [ctypes.c_void_p]
X.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(xprobe.XEvent)]


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.click_wall: int | None = None
        self.call_wall: int | None = None
        self.ref_wall: int | None = None
        self.ref_event = threading.Event()
        self.mark_wall: int | None = None
        self.release = threading.Event()
        self.release.set()
        self.hold: dict | None = None
        self.would_hold_mark: dict | None = None
        self.pause_started: int | None = None
        self.pause_ended: int | None = None
        self.held_bytes = 0
        self.held_chunks = 0
        self.fds_forwarded = 0
        self.conns: list[dict] = []
        self.history: list[list[int]] = []  # [wall_ns, _NET_ACTIVE_WINDOW]
        self.rewrites: list[list[int]] = []  # [request wall_ns, served, live]
        self.steal: dict = {}


def lagged_active(st: State, at_wall: int, lag_ns: int) -> int | None:
    with st.lock:
        hist = list(st.history)
    target = at_wall - lag_ns
    value = None
    for t, v in hist:
        if t <= target:
            value = v
        else:
            break
    if value is None and hist:
        value = hist[0][1]
    return value


def watch_requests(data: bytes, st: State, conn: dict, args: argparse.Namespace) -> None:
    parser = conn.setdefault("_parser", RequestParser())
    for opcode, body in parser.feed(data):
        conn["_seq"] = (conn.get("_seq", 0) + 1) & 0xFFFF
        now = time.time_ns()
        if args.mode == "lag":
            if opcode == GET_PROPERTY and len(body) >= 8 and int.from_bytes(body[4:8], "little") == args.active_atom:
                conn.setdefault("_active_reads", {})[conn["_seq"]] = now
            continue
        if args.mode != "stall":
            continue
        if opcode == GET_INPUT_FOCUS:
            conn["_stacking_reads"] = 0
            continue
        if not (opcode == GET_PROPERTY and len(body) >= 8
                and int.from_bytes(body[4:8], "little") == args.stacking_atom):
            continue
        conn["_stacking_reads"] = conn.get("_stacking_reads", 0) + 1
        if conn["_stacking_reads"] != 2:
            continue
        # calibration: the OWN-20P mark-keyed rule, recorded only
        mw = st.mark_wall
        if mw is not None and st.would_hold_mark is None and conn["accepted_wall_ns"] >= mw \
                and now >= mw + int(args.hold_after_ms * 1e6):
            st.would_hold_mark = {"wall_ns": now, "after_mark_ms": round((now - mw) / 1e6, 3), "conn": conn["id"]}
        # the mark-free rule, acted on
        ref, call = st.ref_wall, st.call_wall
        if st.hold is None and ref is not None and call is not None and conn["accepted_wall_ns"] >= call \
                and now >= ref + int(args.hold_after_ms * 1e6):
            st.release.clear()
            st.pause_started = now
            st.hold = {"wall_ns": now, "after_ref_ms": round((now - ref) / 1e6, 3), "conn": conn["id"]}
            conn["held"] = True
            threading.Thread(target=release_later, args=(st, args.pause_ms), daemon=True).start()


def release_later(st: State, pause_ms: float) -> None:
    time.sleep(pause_ms / 1000)
    st.release.set()
    st.pause_ended = time.time_ns()


class ServerFramer:
    """Splits the server-to-client stream into setup reply / replies / events / errors (lag mode)."""

    def __init__(self) -> None:
        self.buf = b""
        self.setup_done = False

    def feed(self, data: bytes) -> list[bytes]:
        self.buf += data
        out = []
        if not self.setup_done:
            if len(self.buf) < 8:
                return out
            size = 8 + int.from_bytes(self.buf[6:8], "little") * 4
            if len(self.buf) < size:
                return out
            out.append(self.buf[:size])
            self.buf = self.buf[size:]
            self.setup_done = True
        while len(self.buf) >= 32:
            kind = self.buf[0] & 0x7F
            size = 32
            if self.buf[0] == 1 or kind == 35:  # reply, GenericEvent
                size = 32 + int.from_bytes(self.buf[4:8], "little") * 4
            if len(self.buf) < size:
                break
            out.append(self.buf[:size])
            self.buf = self.buf[size:]
        return out


def rewrite_reply(msg: bytes, st: State, conn: dict, args: argparse.Namespace) -> bytes:
    if msg[0] != 1 or len(msg) < 36:
        return msg
    seq = int.from_bytes(msg[2:4], "little")
    reads = conn.get("_active_reads") or {}
    req_wall = reads.pop(seq, None)
    if req_wall is None or msg[1] != 32 or int.from_bytes(msg[16:20], "little") != 1:
        return msg
    live = int.from_bytes(msg[32:36], "little")
    served = lagged_active(st, req_wall, int(args.lag_ms * 1e6))
    if served is None:
        served = live
    with st.lock:
        st.rewrites.append([req_wall, served, live])
    return msg[:32] + struct.pack("<I", served) + msg[36:]


def pump(src: socket.socket, dst: socket.socket, st: State, conn: dict, downstream: bool,
         args: argparse.Namespace) -> None:
    fd_size = socket.CMSG_LEN(MAX_FDS * array.array("i").itemsize)
    framer = ServerFramer() if (downstream and args.mode == "lag") else None
    try:
        while True:
            data, anc, _flags, _addr = src.recvmsg(65536, fd_size)
            fds: list[int] = []
            for level, kind, payload in anc:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    arr = array.array("i")
                    arr.frombytes(payload[: len(payload) - (len(payload) % arr.itemsize)])
                    fds.extend(arr)
            if not data and not fds:
                break
            if not downstream:
                watch_requests(data, st, conn, args)
            if downstream and not st.release.is_set() and conn["held"]:
                with st.lock:
                    conn["held_chunks"] += 1
                    st.held_bytes += len(data)
                    st.held_chunks += 1
                st.release.wait()
            if framer is not None:
                data = b"".join(rewrite_reply(m, st, conn, args) for m in framer.feed(data))
                if not data and not fds:
                    continue
            if fds:
                dst.sendmsg([data], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))])
                with st.lock:
                    st.fds_forwarded += len(fds)
                for fd in fds:
                    os.close(fd)
            else:
                dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def tail_mark(trace: Path, st: State) -> None:
    offset, buf = 0, ""
    while st.mark_wall is None and not st.stop.is_set():
        try:
            with open(trace, encoding="utf-8") as stream:
                stream.seek(offset)
                chunk = stream.read()
                offset = stream.tell()
        except OSError:
            chunk = ""
        if chunk:
            buf += chunk
            *lines, buf = buf.split("\n")
            for line in lines:
                if MARK in line and SCOPE in line:
                    st.mark_wall = int(json.loads(line)["wall_ns"])
                    break
        time.sleep(0.0005)


def watch_active(st: State) -> None:
    """History of the root's _NET_ACTIVE_WINDOW from PropertyNotify on this process's connection."""
    conn = xprobe.Conn()
    try:
        X.XSelectInput(conn.dpy, conn.root, PROPERTY_CHANGE_MASK)
        with st.lock:
            st.history.append([time.time_ns(), conn.active()])
        ev = xprobe.XEvent()
        while not st.stop.is_set():
            if X.XPending(conn.dpy) == 0:
                time.sleep(0.0005)
                continue
            X.XNextEvent(conn.dpy, ctypes.byref(ev))
            if (ev.pad[0] & 0x7F) == PROPERTY_NOTIFY and int(ev.pad[5]) == conn.a_active:
                now = time.time_ns()
                value = conn.active()
                with st.lock:
                    if not st.history or st.history[-1][1] != value:
                        st.history.append([now, value])
    finally:
        conn.close()


def steal_later(st: State, args: argparse.Namespace, conn: xprobe.Conn) -> None:
    if not st.ref_event.wait(timeout=args.deadline_s):
        st.steal["error"] = "reference not seen"
        return
    target = st.ref_wall + int(args.steal_ms * 1e6)  # type: ignore[operator]
    st.steal["late_at_schedule"] = time.time_ns() > target
    while True:
        remaining = (target - time.time_ns()) / 1e9
        if remaining <= 0:
            break
        time.sleep(min(remaining, 0.0005) if remaining < 0.003 else remaining - 0.002)
    st.steal["issued_wall_ns"] = time.time_ns()
    window = int(args.decoy_window)
    conn.request_activate(window)
    X.XRaiseWindow(conn.dpy, window)
    X.XSetInputFocus(conn.dpy, window, xprobe.REVERT_TO_PARENT, 0)
    X.XFlush(conn.dpy)
    st.steal["flushed_wall_ns"] = time.time_ns()
    st.steal["after_ref_ms"] = round((st.steal["issued_wall_ns"] - st.ref_wall) / 1e6, 3)  # type: ignore[operator]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", required=True)
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--mode", choices=("stall", "lag", "pass"), required=True)
    ap.add_argument("--hold-after-ms", type=float, default=80.0)
    ap.add_argument("--pause-ms", type=float, default=2000.0)
    ap.add_argument("--lag-ms", type=float, default=1500.0)
    ap.add_argument("--steal-ms", type=float, default=None)
    ap.add_argument("--decoy-window", type=int, default=0)
    ap.add_argument("--deadline-s", type=float, default=20.0)
    ap.add_argument("--trace", default=None)
    args = ap.parse_args()
    if not args.listen.startswith("/tmp/.X11-unix/X"):
        raise SystemExit("refusing: --listen must be a filesystem socket under the private /tmp/.X11-unix")
    address = os.environ.get("OWN20Q_A11Y_ADDRESS", "")
    if not address:
        raise SystemExit("refusing: no private a11y bus address")
    probe = xprobe.Conn()
    args.stacking_atom = int(X.XInternAtom(probe.dpy, b"_NET_CLIENT_LIST_STACKING", 0))
    args.active_atom = int(X.XInternAtom(probe.dpy, b"_NET_ACTIVE_WINDOW", 0))
    probe.close()
    st = State()

    def after_click(rec: dict) -> bool:
        return st.click_wall is not None and rec["wall_ns"] >= st.click_wall

    def on_call(rec: dict) -> None:
        if st.call_wall is None and after_click(rec):
            st.call_wall = rec["wall_ns"]

    def on_reply(rec: dict) -> None:
        if st.ref_wall is None and after_click(rec):
            st.ref_wall = rec["reply_wall_ns"]
            st.ref_event.set()

    def read_stdin() -> None:
        for line in sys.stdin:
            parts = line.split()
            if len(parts) == 2 and parts[0] == "click" and st.click_wall is None:
                st.click_wall = int(parts[1])

    threading.Thread(target=read_stdin, daemon=True).start()

    watch = q_common.BusWatch(address, "trigger", on_reply=on_reply, on_call=on_call, attribute_pids=False)
    watch.start()
    watch.ready.wait(timeout=5)
    if args.trace:
        threading.Thread(target=tail_mark, args=(Path(args.trace), st), daemon=True).start()
    if args.mode == "lag":
        threading.Thread(target=watch_active, args=(st,), daemon=True).start()
    steal_conn = None
    if args.steal_ms is not None:
        steal_conn = xprobe.Conn()
        threading.Thread(target=steal_later, args=(st, args, steal_conn), daemon=True).start()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(args.listen)
    server.listen(64)
    server.settimeout(0.2)
    signal.signal(signal.SIGTERM, lambda *_: st.stop.set())
    print(json.dumps({"ready": True, "monitor_ready": watch.ready.is_set()}), flush=True)
    n = 0
    while not st.stop.is_set():
        try:
            client, _ = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        n += 1
        conn = {"id": n, "accepted_wall_ns": time.time_ns(), "held_chunks": 0, "held": False}
        st.conns.append(conn)
        try:
            up = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            up.connect(args.upstream)
        except OSError as exc:
            conn["error"] = str(exc)[:80]
            client.close()
            continue
        client.settimeout(None)
        threading.Thread(target=pump, args=(client, up, st, conn, False, args), daemon=True).start()
        threading.Thread(target=pump, args=(up, client, st, conn, True, args), daemon=True).start()
    st.release.set()
    server.close()
    try:
        os.unlink(args.listen)
    except OSError:
        pass
    bus = watch.stop()
    if steal_conn is not None:
        steal_conn.close()
    out = {
        "mode": args.mode, "hold_after_ms": args.hold_after_ms, "pause_ms_set": args.pause_ms,
        "lag_ms": args.lag_ms if args.mode == "lag" else None, "steal_ms": args.steal_ms,
        "click_wall_ns": st.click_wall, "call_wall_ns": st.call_wall, "ref_wall_ns": st.ref_wall, "mark_wall_ns": st.mark_wall,
        "hold": st.hold, "would_hold_mark": st.would_hold_mark,
        "pause_started_wall_ns": st.pause_started, "pause_ended_wall_ns": st.pause_ended,
        "held_bytes": st.held_bytes, "held_chunks": st.held_chunks, "fds_forwarded": st.fds_forwarded,
        "steal": st.steal, "do_action": bus["do_action"], "monitor_messages": bus["messages"],
        "monitor_error": bus["error"],
        "active_history": st.history[:200], "rewrites": len(st.rewrites),
        "rewrites_stale": sum(1 for r in st.rewrites if r[1] != r[2]), "rewrite_rows": st.rewrites[:400],
        "connections": [{k: v for k, v in c.items() if not k.startswith("_")} for c in st.conns],
    }
    if st.ref_wall and st.mark_wall:
        out["ref_minus_mark_ms"] = round((st.ref_wall - st.mark_wall) / 1e6, 3)
    if st.hold and st.would_hold_mark:
        out["hold_minus_markrule_ms"] = round((st.hold["wall_ns"] - st.would_hold_mark["wall_ns"]) / 1e6, 3)
    if st.pause_started:
        out["pause_ms"] = round(((st.pause_ended or st.pause_started) - st.pause_started) / 1e6, 3)
    print(json.dumps(out, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""OWN-20G: reply-delay stall for the Driver's X connections (measurement harness only).

Reproduces the mechanism of N-02 trial c08-017: the focus guard's X read is answered
by the server with the focus as it was, but the reply reaches the guard only after the
settle watch's deadline, while the focus is stolen in between (the sampler and the
decoy talk to the server directly and are never delayed).

It is a transparent forwarder (bytes and SCM_RIGHTS file descriptors, which MIT-SHM
uses) between a filesystem unix socket (``--listen``, ``/tmp/.X11-unix/X<M>`` on the
session's private tmpfs, with no abstract @/tmp/.X11-unix/X<M> anywhere; the Driver
gets ``DISPLAY=:M``) and the private Xvfb's own socket (``--upstream``). It tails the
trial's Driver phase trace for the ``atspi_action do_action_replied`` mark. On
connections accepted after that mark (the guard's restore connection, opened at the
guard's start) it parses the client's X requests. Each settle poll of the guard is
GetInputFocus, GetProperty(_NET_ACTIVE_WINDOW), then two
GetProperty(_NET_CLIENT_LIST_STACKING): the stacking top, then the new-client list.
The first new-client read issued at least ``hold_after_ms`` after the mark (the read
right after a poll's focus diff) has its reply held for ``pause_ms``: exactly c08-017,
where the X call after the 90 ms poll's diff stalled until 2.4 s. Client-to-server
data is never held, so the server answers in real time. ``--mode passthrough`` never
holds anything.

It prints one JSON line ("ready") on start and one JSON summary on exit (SIGTERM).
"""

from __future__ import annotations

import argparse
import array
import json
import os
import signal
import socket
import threading
import time
from pathlib import Path

MARK = '"mark":"do_action_replied"'
SCOPE = '"scope":"atspi_action"'
MAX_FDS = 16


class State:
    def __init__(self) -> None:
        self.mark_wall: int | None = None
        self.release = threading.Event()
        self.release.set()
        self.lock = threading.Lock()
        self.conns: list[dict] = []
        self.held_bytes = 0
        self.held_chunks = 0
        self.fds_forwarded = 0
        self.pause_started: int | None = None
        self.pause_ended: int | None = None
        self.stop = threading.Event()
        self.armed_at: int | None = None
        self.hold_request: dict | None = None


class RequestParser:
    """Little-endian X11 request stream parser (x11rb sends 'l'): skips the connection
    setup, then reports (opcode, body) per request."""

    def __init__(self) -> None:
        self.buf = b""
        self.setup_done = False

    def feed(self, data: bytes):
        self.buf += data
        out = []
        if not self.setup_done:
            if len(self.buf) < 12:
                return out
            n, d = int.from_bytes(self.buf[6:8], "little"), int.from_bytes(self.buf[8:10], "little")
            size = 12 + n + (-n % 4) + d + (-d % 4)
            if len(self.buf) < size:
                return out
            self.buf = self.buf[size:]
            self.setup_done = True
        while len(self.buf) >= 4:
            length = int.from_bytes(self.buf[2:4], "little") * 4
            header = 4
            if length == 0:  # BIG-REQUESTS
                if len(self.buf) < 8:
                    break
                length = int.from_bytes(self.buf[4:8], "little") * 4
                header = 8
            if len(self.buf) < length:
                break
            out.append((self.buf[0], self.buf[header:length]))
            self.buf = self.buf[length:]
        return out


GET_INPUT_FOCUS = 43
GET_PROPERTY = 20


def watch_requests(data: bytes, st: State, conn: dict, args: argparse.Namespace) -> None:
    if args.mode != "stall":
        return
    parser = conn.setdefault("_parser", RequestParser())  # every connection, from its first byte
    for opcode, body in parser.feed(data):
        if st.armed_at is not None or st.mark_wall is None or conn["accepted_wall_ns"] < st.mark_wall:
            continue
        if opcode == GET_INPUT_FOCUS:
            conn["_stacking_reads"] = 0
        elif opcode == GET_PROPERTY and len(body) >= 8 and int.from_bytes(body[4:8], "little") == args.stacking_atom:
            conn["_stacking_reads"] = conn.get("_stacking_reads", 0) + 1
            now = time.time_ns()
            if conn["_stacking_reads"] == 2 and now >= st.mark_wall + int(args.hold_after_ms * 1e6):
                st.release.clear()
                st.armed_at = now
                st.pause_started = now
                st.hold_request = {"after_mark_ms": round((now - st.mark_wall) / 1e6, 3)}
                conn["held"] = True
                threading.Thread(target=release_later, args=(st, args.pause_ms), daemon=True).start()
                return


def release_later(st: State, pause_ms: float) -> None:
    time.sleep(pause_ms / 1000)
    st.release.set()
    st.pause_ended = time.time_ns()


def pump(src: socket.socket, dst: socket.socket, st: State, conn: dict, downstream: bool,
         args: argparse.Namespace) -> None:
    fd_size = socket.CMSG_LEN(MAX_FDS * array.array("i").itemsize)
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


def tail(args: argparse.Namespace, st: State) -> None:
    offset = 0
    buf = ""
    trace = Path(args.trace)
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", required=True)
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--mode", choices=("stall", "passthrough"), required=True)
    ap.add_argument("--hold-after-ms", type=float, default=80.0)
    ap.add_argument("--stacking-atom", type=int, required=True)
    ap.add_argument("--pause-ms", type=float, default=2000.0)
    args = ap.parse_args()
    if not args.listen.startswith("/tmp/.X11-unix/X"):
        raise SystemExit("refusing: --listen must be a filesystem socket under the private /tmp/.X11-unix")
    st = State()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(args.listen)
    server.listen(64)
    server.settimeout(0.2)
    signal.signal(signal.SIGTERM, lambda *_: st.stop.set())
    threading.Thread(target=tail, args=(args, st), daemon=True).start()
    print(json.dumps({"ready": True}), flush=True)
    while not st.stop.is_set():
        try:
            client, _ = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        conn = {"accepted_wall_ns": time.time_ns(), "held_chunks": 0, "held": False}
        st.conns.append(conn)
        try:
            up = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            up.connect(args.upstream)
        except OSError as exc:
            conn["error"] = str(exc)
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
    out = {"mode": args.mode, "mark_wall_ns": st.mark_wall, "pause_started_wall_ns": st.pause_started,
           "pause_ended_wall_ns": st.pause_ended, "held_bytes": st.held_bytes, "held_chunks": st.held_chunks,
           "fds_forwarded": st.fds_forwarded, "hold_request": st.hold_request,
           "connections": [{k: v for k, v in c.items() if not k.startswith("_")} for c in st.conns]}
    if st.mark_wall and st.pause_started:
        out["pause_started_after_mark_ms"] = round((st.pause_started - st.mark_wall) / 1e6, 3)
        out["pause_ms"] = round(((st.pause_ended or st.pause_started) - st.pause_started) / 1e6, 3)
    print(json.dumps(out, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""OWN-16 independent capture oracle: X server RECORD of image-read requests.

Runs INSIDE the isolated X11 session, as its own X client (python-xlib, a
temp venv outside the repo). It asks the X server's RECORD extension to
intercept, from ALL clients, the core ``GetImage`` request (opcode 73) and
the MIT-SHM ``ShmGetImage`` request (MIT-SHM major, minor 4): the requests
any window/root capture must send to read pixels. Each intercepted request
is written as one JSON line ``{"t_ns","op","minor","id_base"}`` with the
receive wall clock, so a harness can attribute captures to tool-call windows
without trusting anything the Driver reports about itself.

Measurement only: it never sends input, never changes a window, and the
Driver does not know it exists. Stop it with SIGTERM.
"""

from __future__ import annotations

import json
import signal
import struct
import sys
import time

from Xlib import display
from Xlib.ext import record

GET_IMAGE = 73
SHM_GET_IMAGE_MINOR = 4


def main() -> int:
    out = open(sys.argv[1], "w", encoding="utf-8", buffering=1)
    ctrl = display.Display()
    data = display.Display()
    if not ctrl.has_extension("RECORD"):
        out.write(json.dumps({"event": "error", "reason": "no RECORD extension"}) + "\n")
        return 2
    shm = ctrl.query_extension("MIT-SHM")
    shm_major = shm.major_opcode if shm is not None else 0
    ranges = [{
        "core_requests": (GET_IMAGE, GET_IMAGE),
        "core_replies": (0, 0),
        "ext_requests": (shm_major, shm_major, SHM_GET_IMAGE_MINOR, SHM_GET_IMAGE_MINOR)
        if shm_major else (0, 0, 0, 0),
        "ext_replies": (0, 0, 0, 0),
        "delivered_events": (0, 0),
        "device_events": (0, 0),
        "errors": (0, 0),
        "client_started": False,
        "client_died": False,
    }]
    ctx = ctrl.record_create_context(0, [record.AllClients], ranges)
    out.write(json.dumps({"event": "ready", "shm_major": shm_major, "t_ns": time.time_ns()}) + "\n")

    def on_reply(reply) -> None:
        if reply.category != record.FromClient:
            return
        t_ns = time.time_ns()
        raw = reply.data
        fmt = ">H" if reply.client_swapped else "=H"
        i = 0
        while i + 4 <= len(raw):
            op, minor = raw[i], raw[i + 1]
            length = struct.unpack(fmt, raw[i + 2:i + 4])[0] * 4
            out.write(json.dumps({"t_ns": t_ns, "op": op, "minor": minor,
                                  "id_base": reply.id_base}) + "\n")
            if length <= 0:
                break
            i += length

    def stop(*_args) -> None:
        out.write(json.dumps({"event": "stop", "t_ns": time.time_ns()}) + "\n")
        out.flush()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    ctrl.flush()
    data.record_enable_context(ctx, on_reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())

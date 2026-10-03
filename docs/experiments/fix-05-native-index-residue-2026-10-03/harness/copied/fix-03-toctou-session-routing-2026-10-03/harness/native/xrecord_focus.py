#!/usr/bin/env python3
"""FIX-03 Part C oracle: X server RECORD of focus / raise / configure traffic on the private display.

Runs INSIDE the private X11 session as its own X client (python-xlib 0.33 in a lane-temp venv
outside the repo). It asks the RECORD extension to intercept, from ALL clients:
  requests  MapWindow (8), ConfigureWindow (12), SendEvent (25), SetInputFocus (42)
  events    FocusIn (9), ConfigureNotify (22) as delivered
and writes one JSON line per item with the receive wall clock and the window ids it names, so a
harness can attribute activation / raise / restack traffic for a given X window (client or frame)
to a tool-call window without trusting anything the Driver reports. Measurement only: it never
sends input, never changes a window, and the Driver does not know it exists. Stop with SIGTERM.

  xrecord_focus.py record <out.jsonl>
  xrecord_focus.py tree <xid> [<xid> ...]   -> JSON {xid: [parent, grandparent, ...]} on stdout
"""

from __future__ import annotations

import json
import signal
import struct
import sys
import time

from Xlib import display
from Xlib.ext import record

REQUESTS = {8: "MapWindow", 12: "ConfigureWindow", 25: "SendEvent", 42: "SetInputFocus"}
EVENTS = {9: "FocusIn", 22: "ConfigureNotify"}


def _range(req=(0, 0), ev=(0, 0)) -> dict:
    return {"core_requests": req, "core_replies": (0, 0), "ext_requests": (0, 0, 0, 0),
            "ext_replies": (0, 0, 0, 0), "delivered_events": ev, "device_events": (0, 0),
            "errors": (0, 0), "client_started": False, "client_died": False}


def record_main(path: str) -> int:
    out = open(path, "w", encoding="utf-8", buffering=1)
    ctrl = display.Display()
    data = display.Display()
    if not ctrl.has_extension("RECORD"):
        out.write(json.dumps({"event": "error", "reason": "no RECORD extension"}) + "\n")
        return 2
    net_active = ctrl.intern_atom("_NET_ACTIVE_WINDOW")
    ranges = [_range(req=(op, op)) for op in REQUESTS] + [_range(ev=(ev, ev)) for ev in EVENTS]
    ctx = ctrl.record_create_context(0, [record.AllClients], ranges)
    out.write(json.dumps({"event": "ready", "t_ns": time.time_ns(), "net_active_window_atom": net_active}) + "\n")

    def u32(raw: bytes, offset: int, order: str) -> int:
        return struct.unpack(order + "I", raw[offset:offset + 4])[0]

    def on_reply(reply) -> None:
        t_ns = time.time_ns()
        raw = reply.data
        order = ">" if reply.client_swapped else "<"
        if reply.category == record.FromClient:
            i = 0
            while i + 8 <= len(raw):
                op = raw[i]
                length = struct.unpack(order + "H", raw[i + 2:i + 4])[0] * 4
                if length <= 0:
                    break
                body = raw[i:i + length]
                item = {"t_ns": t_ns, "kind": "request", "op": REQUESTS.get(op, op), "id_base": reply.id_base}
                if op in (8, 12, 42) and len(body) >= 8:
                    item["window"] = u32(body, 4, order)
                    if op == 12 and len(body) >= 10:
                        mask = struct.unpack(order + "H", body[8:10])[0]
                        item["value_mask"] = mask
                        item["stack_mode_set"] = bool(mask & 0x40)
                if op == 25 and len(body) >= 24:
                    item["destination"] = u32(body, 4, order)
                    event_type = body[12] & 0x7F
                    item["event_type"] = event_type
                    if event_type == 33:  # ClientMessage
                        item["window"] = u32(body, 16, order)
                        item["message_type"] = u32(body, 20, order)
                        item["net_active_window"] = item["message_type"] == net_active
                if op in REQUESTS:
                    out.write(json.dumps(item) + "\n")
                i += length
        elif reply.category == record.FromServer:
            i = 0
            while i + 32 <= len(raw):
                event_type = raw[i] & 0x7F
                body = raw[i:i + 32]
                if event_type in EVENTS:
                    item = {"t_ns": t_ns, "kind": "event", "op": EVENTS[event_type], "id_base": reply.id_base,
                            "window": u32(body, 4, order)}
                    if event_type == 9:
                        item["detail"] = body[1]
                        item["mode"] = body[8]
                    if event_type == 22:
                        item["configured"] = u32(body, 8, order)
                    out.write(json.dumps(item) + "\n")
                i += 32

    def stop(*_args) -> None:
        out.write(json.dumps({"event": "stop", "t_ns": time.time_ns()}) + "\n")
        out.flush()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    ctrl.sync()  # FIX-03 deviation 3: the context must exist server-side before the data connection enables it
    data.record_enable_context(ctx, on_reply)
    return 0


def tree_main(xids: list[str]) -> int:
    d = display.Display()
    root = d.screen().root.id
    result, children = {}, {}
    for raw in xids:
        chain = []
        window = d.create_resource_object("window", int(raw))
        try:
            children[raw] = [child.id for child in window.query_tree().children]
        except Exception:  # noqa: BLE001 - a vanished window has no children
            children[raw] = []
        for _ in range(8):
            try:
                parent = window.query_tree().parent
            except Exception:  # noqa: BLE001 - a vanished window ends the chain
                break
            if parent is None or parent.id in (0, root):
                break
            chain.append(parent.id)
            window = parent
        result[raw] = chain
    print(json.dumps({"root": root, "parents": result, "children": children}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "record":
        sys.exit(record_main(sys.argv[2]))
    if len(sys.argv) >= 3 and sys.argv[1] == "tree":
        sys.exit(tree_main(sys.argv[2:]))
    print(__doc__, file=sys.stderr)
    sys.exit(64)

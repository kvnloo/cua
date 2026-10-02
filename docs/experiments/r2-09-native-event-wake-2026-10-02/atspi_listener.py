#!/usr/bin/env python3
"""OWN-20 independent AT-SPI event listener (candidate invalidator source, never the oracle).

Runs INSIDE the isolated X11 session with system python3 + PyGObject (Gio only, no Gtk/Atk).
It connects to the private AT-SPI bus (address from org.a11y.Bus on the private session bus),
registers its own event interest with org.a11y.atspi.Registry (so applications emit for THIS
listener even without the Driver), subscribes to every broadcast signal on the bus, and writes
one JSON line per signal with the CLOCK_MONOTONIC arrival time, the sender bus name, the object
path, interface, member and the event payload summary. Sender bus names are resolved to pids
once (GetConnectionUnixProcessID), asynchronously, so the callback does no blocking round trip.

Timings it reports (all CLOCK_MONOTONIC, ns):
  subscription: address lookup, connect, RegisterEvent calls, signal_subscribe -> "ready" line
  cleanup (on SIGTERM/SIGINT): DeregisterEvent calls, signal_unsubscribe, close -> "cleanup" line

usage: atspi_listener.py <out.jsonl> [--tag TAG] [--events object:,window:,focus:,document:]
"""

from __future__ import annotations

import json
import signal
import sys
import time

from gi.repository import Gio, GLib

EVENTS_DEFAULT = "object:,window:,focus:,document:"


def mono() -> int:
    return time.monotonic_ns()


def summarize(value, depth=0):
    """A short, JSON-safe summary of an unpacked GVariant payload."""
    if depth > 3:
        return "..."
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, str):
        return value if len(value) <= 160 else value[:160] + "..."
    if isinstance(value, (list, tuple)):
        return [summarize(v, depth + 1) for v in list(value)[:8]]
    if isinstance(value, dict):
        return {str(k): summarize(v, depth + 1) for k, v in list(value.items())[:8]}
    return repr(value)[:160]


def main() -> int:
    out_path = sys.argv[1]
    tag = None
    events = EVENTS_DEFAULT
    args = sys.argv[2:]
    while args:
        flag = args.pop(0)
        if flag == "--tag":
            tag = args.pop(0)
        elif flag == "--events":
            events = args.pop(0)
    event_names = [e for e in events.split(",") if e]
    out = open(out_path, "a", encoding="utf-8", buffering=1)

    def write(rec):
        if tag is not None:
            rec["tag"] = tag
        out.write(json.dumps(rec, sort_keys=True) + "\n")

    t0 = mono()
    session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    reply = session.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress", None,
                              GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, 5000, None)
    address = reply.unpack()[0]
    t_addr = mono()
    conn = Gio.DBusConnection.new_for_address_sync(
        address,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)
    t_conn = mono()
    my_name = conn.get_unique_name()
    pid_of: dict[str, int | None] = {}

    def resolve(name: str) -> None:
        if not name or not name.startswith(":") or name in pid_of:
            return
        pid_of[name] = None

        def done(source, result, _data):
            try:
                pid = source.call_finish(result).unpack()[0]
            except GLib.Error as error:
                write({"event": "name_pid", "name": name, "pid": None, "error": error.message[:120],
                       "m_ns": mono()})
                return
            pid_of[name] = pid
            write({"event": "name_pid", "name": name, "pid": pid, "m_ns": mono()})

        conn.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                  "GetConnectionUnixProcessID", GLib.Variant("(s)", (name,)),
                  GLib.VariantType.new("(u)"), Gio.DBusCallFlags.NONE, 2000, None, done, None)

    def on_signal(_conn, sender, path, interface, member, params, _data):
        m_ns = mono()
        rec = {"event": "signal", "m_ns": m_ns, "sender": sender, "path": path,
               "interface": interface, "member": member}
        try:
            payload = params.unpack()
        except Exception as error:  # never lose the arrival record
            payload = None
            rec["unpack_error"] = repr(error)[:120]
        if interface and interface.startswith("org.a11y.atspi.Event.") and isinstance(payload, tuple):
            rec["detail"] = payload[0] if len(payload) > 0 else None
            rec["detail1"] = payload[1] if len(payload) > 1 else None
            rec["detail2"] = payload[2] if len(payload) > 2 else None
            rec["any_data"] = summarize(payload[3]) if len(payload) > 3 else None
            rec["sig"] = params.get_type_string()
        else:
            rec["payload"] = summarize(payload)
        write(rec)
        resolve(sender)
        if member == "NameOwnerChanged" and isinstance(payload, tuple) and len(payload) == 3:
            resolve(payload[2])

    sub_id = conn.signal_subscribe(None, None, None, None, None, Gio.DBusSignalFlags.NONE,
                                   on_signal, None)
    t_sub = mono()
    register_ms = []
    register_errors = []
    for name in event_names:
        r0 = mono()
        try:
            conn.call_sync("org.a11y.atspi.Registry", "/org/a11y/atspi/registry",
                           "org.a11y.atspi.Registry", "RegisterEvent", GLib.Variant("(s)", (name,)),
                           None, Gio.DBusCallFlags.NONE, 5000, None)
        except GLib.Error as error:
            register_errors.append({"event": name, "error": error.message[:160]})
        register_ms.append((mono() - r0) / 1e6)
    t_ready = mono()
    write({"event": "ready", "m_ns": t_ready, "m_start": t0, "my_name": my_name,
           "address_kind": address.split(":")[0], "events": event_names,
           "address_ms": (t_addr - t0) / 1e6, "connect_ms": (t_conn - t_addr) / 1e6,
           "subscribe_ms": (t_sub - t_conn) / 1e6, "register_ms": register_ms,
           "register_errors": register_errors, "subscription_ms": (t_ready - t0) / 1e6})

    loop = GLib.MainLoop()

    def stop(*_):
        c0 = mono()
        dereg_errors = []
        for name in event_names:
            try:
                conn.call_sync("org.a11y.atspi.Registry", "/org/a11y/atspi/registry",
                               "org.a11y.atspi.Registry", "DeregisterEvent", GLib.Variant("(s)", (name,)),
                               None, Gio.DBusCallFlags.NONE, 2000, None)
            except GLib.Error as error:
                dereg_errors.append({"event": name, "error": error.message[:160]})
        c1 = mono()
        conn.signal_unsubscribe(sub_id)
        try:
            conn.close_sync(None)
        except GLib.Error:
            pass
        c2 = mono()
        write({"event": "cleanup", "m_ns": c2, "deregister_ms": (c1 - c0) / 1e6,
               "close_ms": (c2 - c1) / 1e6, "cleanup_ms": (c2 - c0) / 1e6,
               "deregister_errors": dereg_errors})
        loop.quit()
        return False

    try:
        from gi.repository import GLibUnix
        add_signal = GLibUnix.signal_add
    except ImportError:  # older PyGObject
        add_signal = GLib.unix_signal_add
    add_signal(GLib.PRIORITY_HIGH, signal.SIGTERM, stop)
    add_signal(GLib.PRIORITY_HIGH, signal.SIGINT, stop)
    loop.run()
    out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

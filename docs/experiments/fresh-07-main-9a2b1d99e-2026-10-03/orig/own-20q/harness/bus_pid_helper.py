#!/usr/bin/python3
"""OWN-20Q: pid attribution for the bus monitor over ONE persistent connection (measurement only).

``q_common.BusWatch`` starts this helper once per watched bus (system python3 with GObject
introspection). It opens a single connection to the bus named by ``OWN20Q_BUS_ADDRESS`` (never
printed), prints ``self <its unique name>``, then answers every unique name read on stdin with
``<name> <pid>`` from the bus daemon's own ``GetConnectionUnixProcessID`` (``-1`` when the name is
already gone). A gdbus process per lookup would itself open a connection per lookup, which the
monitor would see as new names to attribute (a feedback loop).
"""

import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
conn = Gio.DBusConnection.new_for_address_sync(os.environ["OWN20Q_BUS_ADDRESS"], flags, None, None)
print("self", conn.get_unique_name(), flush=True)
for line in sys.stdin:
    name = line.strip()
    if not name:
        continue
    try:
        reply = conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                               "GetConnectionUnixProcessID", GLib.Variant("(s)", (name,)),
                               GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 1000, None)
        pid = reply.unpack()[0]
    except GLib.Error:
        pid = -1
    print(name, pid, flush=True)

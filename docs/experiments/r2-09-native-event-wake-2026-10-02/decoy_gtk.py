#!/usr/bin/env python3
"""R2-09 control (b) decoy window (test fixture): a separate GTK3 application
whose check button toggles every 5 ms, so a foreign application emits
object:state-changed events on the AT-SPI bus throughout the EW wait.

usage: decoy_gtk.py <ready-file>
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


def main() -> int:
    ready = sys.argv[1]
    win = Gtk.Window(title="R2-09 decoy")
    win.set_default_size(240, 80)
    win.move(1400, 40)
    check = Gtk.CheckButton(label="Decoy toggle")
    win.add(check)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    def toggle() -> bool:
        check.set_active(not check.get_active())
        return True

    def announce() -> bool:
        with open(ready, "w", encoding="ascii") as stream:
            stream.write("ready")
        return False

    GLib.timeout_add(5, toggle)
    GLib.timeout_add(500, announce)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())

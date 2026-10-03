#!/usr/bin/env python3
"""FIX-20O real-popup control fixture: the canonical GTK3 task window plus one "Open menu" button.

The canonical fixture (``libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py``) is imported, not
copied (as OWN-20Q's ``dlg_fixture.py``). Activating "Open menu" does what a toolkit does when a menu
opens from an unfocused application: it presents its own toplevel and pops up a real ``GtkMenu``,
which takes the seat (keyboard + pointer) grab. The menu toplevel is titled ``Cua.PopupControl`` and
its ``_NET_WM_PID`` is removed, so it looks exactly like the Driver's overlay to a title / pid rule;
only an exact-id rule tells them apart. The app-owned state file keeps the canonical schema and adds
``menu_open``, ``menu_window`` (the menu toplevel's X id), ``menu_grab`` (the GdkSeat grab status of
the popup, or null) and ``menu_pid_removed``. ``FIX20O_FIXTURE_MAIN`` names the canonical main.py.
"""

from __future__ import annotations

import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location("gtk3_task_main", os.environ["FIX20O_FIXTURE_MAIN"])
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)  # type: ignore[union-attr]
Gtk = main.Gtk
from gi.repository import Gdk  # noqa: E402

MENU_TITLE = "Cua.PopupControl"


class PopupTaskWindow(main.TaskWindow):
    def __init__(self, state_path: str) -> None:
        super().__init__(state_path)
        self.menu = Gtk.Menu()
        for label in ("First item", "Second item"):
            self.menu.append(Gtk.MenuItem(label=label))
        self.menu.set_title(MENU_TITLE)
        self.menu.show_all()
        self.menu.connect("map-event", self.on_menu_mapped)
        self.menu.get_toplevel().connect("map-event", self.on_menu_mapped)
        self.menu.connect("hide", self.on_menu_hidden)
        self.menu_button = self.button("Open menu", self.on_open_menu)
        self.get_child().pack_start(self.menu_button, False, False, 0)
        self.menu_open = False
        self.menu_window = 0
        self.menu_grab = None
        self.menu_pid_removed = False
        self.menu_requests = 0
        self.publish()

    def on_open_menu(self, *_):
        self.menu_requests += 1
        # A toolkit activates its toplevel when a menu opens (the focus_guard module docs).
        self.present()
        self.disguise_temp_windows()  # the menu toplevel, realized before it maps
        self.menu.popup_at_widget(self.menu_button, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)
        self.disguise_temp_windows()  # GtkMenu's grab-transfer window, created by the popup
        Gdk.Display.get_default().flush()

    def disguise_temp_windows(self) -> None:
        """Every override-redirect (TEMP) window of this process gets the title MENU_TITLE and loses
        _NET_WM_PID, so a title / pid rule cannot tell the real menu from the Driver's overlay."""
        self.menu.get_toplevel().realize()
        removed = True
        for gdk in Gdk.Screen.get_default().get_toplevel_windows():
            if gdk.get_window_type() != Gdk.WindowType.TEMP:
                continue
            try:
                gdk.set_title(MENU_TITLE)
                Gdk.property_delete(gdk, Gdk.Atom.intern("_NET_WM_PID", False))
            except Exception:  # noqa: BLE001
                removed = False
        self.menu_pid_removed = removed

    def on_menu_mapped(self, *_):
        toplevel = self.menu.get_toplevel()
        gdk = toplevel.get_window()
        if gdk is None:
            return False
        self.menu_window = int(gdk.get_xid()) if hasattr(gdk, "get_xid") else 0
        seat = Gdk.Display.get_default().get_default_seat()
        keyboard = seat.get_keyboard()
        self.menu_grab = bool(keyboard is not None and Gdk.Display.get_default().device_is_grabbed(keyboard))
        self.menu_open = True
        self.publish()
        return False

    def on_menu_hidden(self, *_):
        self.menu_open = False
        self.publish()

    def publish(self):
        super().publish()
        if not hasattr(self, "menu_requests"):
            return
        with open(self.state_path, encoding="utf-8") as stream:
            state = json.load(stream)
        state.update({"menu_open": self.menu_open, "menu_window": self.menu_window, "menu_grab": self.menu_grab,
                      "menu_pid_removed": self.menu_pid_removed, "menu_requests": self.menu_requests})
        temporary = f"{self.state_path}.{os.getpid()}.tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
        os.replace(temporary, self.state_path)


def run() -> None:
    win = PopupTaskWindow(os.environ[main.TASK_STATE_ENV])
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    run()

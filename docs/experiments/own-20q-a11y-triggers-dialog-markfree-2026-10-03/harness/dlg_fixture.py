#!/usr/bin/env python3
"""OWN-20Q DLG control fixture: the canonical GTK3 task window plus one "Open dialog" button.

The canonical fixture (``libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py``) is imported, not
copied; its ``TaskWindow`` gains a button that maps a transient, non-modal dialog of the same process
(the app's own window, which the window manager focuses). The app-owned state file keeps the
canonical schema and adds ``dialog_open`` and ``dialog_window`` (the dialog's X window id), written
when the dialog is mapped. ``OWN20Q_FIXTURE_MAIN`` names the canonical main.py.
"""

from __future__ import annotations

import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location("gtk3_task_main", os.environ["OWN20Q_FIXTURE_MAIN"])
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)  # type: ignore[union-attr]
Gtk = main.Gtk


class DialogTaskWindow(main.TaskWindow):
    def __init__(self, state_path: str) -> None:
        super().__init__(state_path)
        button = self.button("Open dialog", self.on_open_dialog)
        self.get_child().pack_start(button, False, False, 0)
        self.dialog_open = False
        self.dialog_window = 0
        self.publish()

    def on_open_dialog(self, *_):
        dialog = Gtk.Window(title="OWN-20Q dialog")
        dialog.set_transient_for(self)
        dialog.set_default_size(260, 120)
        dialog.add(Gtk.Label(label="dialog"))

        def mapped(widget, *_):
            self.dialog_open = True
            gdk = widget.get_window()
            self.dialog_window = int(gdk.get_xid()) if gdk is not None and hasattr(gdk, "get_xid") else 0
            self.publish()

        dialog.connect("map-event", mapped)
        dialog.show_all()

    def publish(self):
        super().publish()
        if not hasattr(self, "dialog_open"):
            return
        with open(self.state_path, encoding="utf-8") as stream:
            state = json.load(stream)
        state["dialog_open"] = self.dialog_open
        state["dialog_window"] = self.dialog_window
        temporary = f"{self.state_path}.{os.getpid()}.tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
        os.replace(temporary, self.state_path)


if __name__ == "__main__":
    win = DialogTaskWindow(os.environ[main.TASK_STATE_ENV])
    win.show_all()
    Gtk.main()

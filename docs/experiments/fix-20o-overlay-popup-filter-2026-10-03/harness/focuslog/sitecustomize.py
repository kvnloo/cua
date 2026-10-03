"""FIX-20O: the GTK3 fixture's own focus log (measurement only, packet harness, not Driver code).

Loaded by every Python started inside a FIX-20O row session (``PYTHONPATH`` points here), and a no-op
unless ``FIX20O_FOCUS_LOG=1``, ``CUA_GTK3_TASK_STATE`` is set and the process is one of the GTK3
task fixtures (the canonical ``gtk3/main.py``, OWN-20Q's ``dlg_fixture.py`` or this packet's
``popup_fixture.py``). In the fixture it hooks every GtkWindow toplevel (the task window, dialogs and
menu toplevels) and appends one JSON line per ``focus-in-event`` / ``focus-out-event`` /
``map-event`` / ``unmap-event`` to ``<state file>.focus.jsonl``: the fixture's own record of which of
its windows held the keyboard focus, stamped with CLOCK_MONOTONIC (the harness clock). The canonical
fixture source and the original harness files are not modified.
"""

from __future__ import annotations

import os
import sys


def _install() -> None:
    state = os.environ.get("CUA_GTK3_TASK_STATE", "")
    if os.environ.get("FIX20O_FOCUS_LOG") != "1" or not state:
        return
    argv = " ".join(getattr(sys, "orig_argv", None) or sys.argv or [])
    if not any(name in argv for name in ("gtk3/main.py", "dlg_fixture.py", "popup_fixture.py")):
        return
    import json
    import threading
    import time

    log_path = state + ".focus.jsonl"

    def emit(record: dict) -> None:
        record["mono_ns"] = time.monotonic_ns()
        record["pid"] = os.getpid()
        try:
            with open(log_path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            pass

    def attach() -> bool:
        from gi.repository import GLib, Gtk  # noqa: PLC0415

        hooked: list = []

        def xid(window) -> int:
            gdk = window.get_window()
            try:
                return int(gdk.get_xid()) if gdk is not None else 0
            except Exception:  # noqa: BLE001
                return 0

        def handler(event: str):
            def callback(window, *_args):
                kind = "popup" if window.get_window_type() == Gtk.WindowType.POPUP else "toplevel"
                emit({"event": event, "title": window.get_title() or "", "xid": xid(window), "kind": kind})
                return False
            return callback

        def scan() -> bool:
            for window in Gtk.Window.list_toplevels():
                if any(window is w for w in hooked):
                    continue
                hooked.append(window)
                for signal, event in (("focus-in-event", "focus_in"), ("focus-out-event", "focus_out"),
                                      ("map-event", "map"), ("unmap-event", "unmap")):
                    window.connect(signal, handler(event))
                emit({"event": "hooked", "title": window.get_title() or "", "xid": xid(window),
                      "kind": "popup" if window.get_window_type() == Gtk.WindowType.POPUP else "toplevel"})
            return True

        scan()
        GLib.timeout_add(20, scan)
        return False

    def wait_for_gtk() -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if "gi.repository.Gtk" in sys.modules:
                try:
                    from gi.repository import GLib  # noqa: PLC0415

                    GLib.idle_add(attach)
                except Exception as exc:  # noqa: BLE001
                    emit({"event": "hook_error", "error": f"{type(exc).__name__}: {exc}"[:200]})
                return
            time.sleep(0.005)

    threading.Thread(target=wait_for_gtk, name="fix20o-focuslog", daemon=True).start()


try:
    _install()
except Exception:  # noqa: BLE001 - never disturb the process it is loaded into
    pass

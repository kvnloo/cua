#!/usr/bin/env python3
"""Autoresearch GTK3 reference fixture with target-owned provenance (evaluator side).

One process per trial. The harness starts it with:

  ar_gtk3_app.py --task {checkbox,text,user} --seed N --variant V \
                 --nonce-fd A --ready-fd B --state-dir DIR

* The per-trial nonce arrives on the inherited descriptor ``--nonce-fd`` (read to
  EOF, then closed). It is never shown in the UI and never written anywhere the
  Driver can read: the state directory is masked out of the Driver sandbox.
* The app announces readiness (pid, layout, initial state, CLOCK_MONOTONIC) on the
  inherited descriptor ``--ready-fd`` and closes it. That is the only output
  besides the state journal.
* ``DIR/journal.jsonl`` is written ONLY from the task handler (checkbox ``toggled``
  or the ``Save note`` click; in the ``delayed`` variant from the GLib timeout the
  handler itself schedules). One JSON line per handler invocation, appended with a
  single ``write`` on an ``O_APPEND`` descriptor. Every line carries the nonce,
  the handler's own invocation count, and host ``CLOCK_MONOTONIC`` stamps taken in
  the handler (``t_handler_ns``) and when the effect was applied (``t_applied_ns``).
* Labels, accessible names, widget names (ids), control order, spacing and window
  geometry come from ``--seed`` (``layout_for``), so the same seed gives the same
  layout in both arms of a pair and no two seeds need share one. The task meaning
  never changes: toggle the checkbox named ``target_label`` once / save the given
  text into the field named ``note_label``.

Variants (``--variant``):
  normal          the effect lands in the handler.
  delayed         the handler schedules the effect 200-500 ms later (seeded).
  focus_steal     the handler applies the effect, then 30-200 ms later (seeded)
                  the app maps a "Notice" toplevel and takes the desktop focus
                  with it.
  disabled        the target is sensitive at observation time; the harness then
                  sends "disable" on ``--control-fd`` and the app makes it
                  insensitive before the Driver dispatches (canary: the token is
                  fresh, the action is impossible).
  absent          no control carries the target label (canary).
``--task user`` shows a plain "User notes" window from a different process: the
focus-steal control activates it before the trial so the target app is in the
background, as a user's own work would be.
"""

from __future__ import annotations

import argparse
import json
import os
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import GdkX11, GLib, Gtk  # noqa: E402

from ar_layout import TASKS, VARIANTS, layout_for  # noqa: E402

SCHEMA = "cua.ar.gtk3_journal_v1"
READY_SCHEMA = "cua.ar.gtk3_ready_v1"


def mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


class Journal:
    """Append-only, one ``write`` per record; opened lazily by the first handler call."""

    def __init__(self, state_dir: str, nonce: str, pid: int, variant: str) -> None:
        self.path = os.path.join(state_dir, "journal.jsonl")
        self.nonce = nonce
        self.pid = pid
        self.variant = variant
        self.fd: int | None = None
        self.seq = 0

    def append(self, record: dict) -> None:
        if self.fd is None:
            self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.seq += 1
        line = {"schema": SCHEMA, "nonce": self.nonce, "pid": self.pid, "variant": self.variant,
                "seq": self.seq, **record}
        os.write(self.fd, (json.dumps(line, sort_keys=True) + "\n").encode())


class FixtureWindow(Gtk.Window):
    def __init__(self, layout: dict, journal: Journal | None, ready_fd: int, nonce: str,
                 control_fd: int | None = None) -> None:
        super().__init__(title=layout["title"] if layout["task"] != "user" else "User notes")
        self.layout = layout
        self.journal = journal
        self.ready_fd = ready_fd
        self.handler_calls = 0
        self.variant = layout["variant"]
        self.notice: Gtk.Window | None = None
        self.target: Gtk.CheckButton | None = None
        self.note: Gtk.Entry | None = None
        width, height = layout["window_size"]
        self.set_default_size(width, height)
        self.move(*layout["window_pos"])
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=layout["spacing"])
        root.set_border_width(layout["border"])
        self.add(root)
        if layout["task"] == "user":
            entry = Gtk.Entry()
            entry.get_accessible().set_name("User notes field")
            root.pack_start(Gtk.Label(label="User notes", xalign=0), False, False, 0)
            root.pack_start(entry, False, False, 0)
        else:
            self._build(root)
        self.connect("destroy", Gtk.main_quit)
        self.control_fd = control_fd
        if control_fd is not None:
            GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, control_fd, GLib.IOCondition.IN, self._on_control)
        self._ready_sent = False
        self.connect("map-event", self._on_map)

    def _named(self, widget: Gtk.Widget, label: str) -> Gtk.Widget:
        widget.set_name(self.layout["widget_ids"][label])
        widget.get_accessible().set_name(label)
        return widget

    def _build(self, root: Gtk.Box) -> None:
        lay = self.layout
        for kind, label in lay["items"]:
            if kind in ("check", "target"):
                check = self._named(Gtk.CheckButton(label=label), label)
                if kind == "target":
                    check.set_active(lay["initial_checked"])
                    check.connect("toggled", self.on_toggled)
                    self.target = check
                root.pack_start(check, False, False, 0)
            elif kind == "button":
                button = self._named(Gtk.Button(label=label), label)
                button.set_halign(Gtk.Align.START)
                root.pack_start(button, False, False, 0)
            elif kind == "note":
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=lay["spacing"])
                self.note = self._named(Gtk.Entry(), label)
                self.note.set_width_chars(24)
                row.pack_start(self.note, False, False, 0)
                save = Gtk.Button(label=lay["save_label"])
                save.get_accessible().set_name(lay["save_label"])
                save.set_name(f"{lay['widget_ids'][label]}-save")
                save.connect("clicked", self.on_save)
                row.pack_start(save, False, False, 0)
                root.pack_start(row, False, False, 0)

    # -- readiness ---------------------------------------------------------
    def _on_map(self, *_):
        if not self._ready_sent:
            self._ready_sent = True
            # Two idle turns after the first map so the AT-SPI tree is published.
            GLib.timeout_add(300, self._send_ready)
        return False

    def _send_ready(self) -> bool:
        gdk_window = self.get_window()
        xid = gdk_window.get_xid() if gdk_window is not None and hasattr(gdk_window, "get_xid") else None
        msg = {"schema": READY_SCHEMA, "pid": os.getpid(), "xid": xid, "t_ready_ns": mono_ns(),
               "layout": self.layout,
               "initial": {"checked": self.target.get_active() if self.target is not None else None,
                           "note": self.note.get_text() if self.note is not None else None}}
        try:
            os.write(self.ready_fd, (json.dumps(msg, sort_keys=True) + "\n").encode())
        finally:
            os.close(self.ready_fd)
        return False

    def _on_control(self, fd: int, _cond) -> bool:
        """Harness commands (canary only). Never writes the journal."""
        data = os.read(fd, 256)
        if not data:
            return False
        for command in data.decode().split():
            if command == "disable" and self.target is not None:
                self.target.set_sensitive(False)
                # Reply after the main loop has flushed the change to ATK/AT-SPI.
                GLib.timeout_add(100, self._reply, f"disabled {mono_ns()}")
        return True

    def _reply(self, text: str) -> bool:
        os.write(self.control_fd, (text + "\n").encode())
        return False

    # -- task handlers: the ONLY writers of the journal ----------------------
    def on_toggled(self, check: Gtk.CheckButton) -> None:
        t_handler = mono_ns()
        self.handler_calls += 1
        calls = self.handler_calls
        checked = check.get_active()
        if self.variant == "delayed":
            def apply() -> bool:
                self.journal.append({"event": "toggle", "handler_calls": calls, "checked": checked,
                                     "t_handler_ns": t_handler, "t_applied_ns": mono_ns(),
                                     "delay_ms": self.layout["delay_ms"]})
                return False
            GLib.timeout_add(self.layout["delay_ms"], apply)
            return
        self.journal.append({"event": "toggle", "handler_calls": calls, "checked": checked,
                             "t_handler_ns": t_handler, "t_applied_ns": mono_ns()})
        if self.variant == "focus_steal" and calls == 1:
            GLib.timeout_add(self.layout["steal_map_ms"], self._steal_with_notice)

    def on_save(self, *_):
        t_handler = mono_ns()
        self.handler_calls += 1
        self.journal.append({"event": "save", "handler_calls": self.handler_calls,
                             "note_saved": self.note.get_text(), "t_handler_ns": t_handler,
                             "t_applied_ns": mono_ns()})

    # -- focus-steal variant -------------------------------------------------
    def _steal_with_notice(self) -> bool:
        """Map a new toplevel and take the desktop focus with it, as an app that
        pops a dialog on a settings change would: the steal the guard must undo."""
        notice = Gtk.Window(title="Notice")
        notice.set_default_size(220, 80)
        notice.add(Gtk.Label(label="Settings changed"))
        notice.move(self.layout["window_pos"][0] + 40, self.layout["window_pos"][1] + 40)
        notice.show_all()
        gdk_window = notice.get_window()
        if gdk_window is not None:
            # A fresh server timestamp so the WM's focus-stealing prevention does
            # not discard the request.
            gdk_window.focus(GdkX11.x11_get_server_time(gdk_window))
        self.notice = notice
        return False


def read_nonce(fd: int) -> str:
    chunks = []
    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(fd)
    return b"".join(chunks).decode().strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=TASKS, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--variant", choices=VARIANTS, default="normal")
    parser.add_argument("--nonce-fd", type=int, required=True)
    parser.add_argument("--ready-fd", type=int, required=True)
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--control-fd", type=int, default=None)
    args = parser.parse_args()
    nonce = read_nonce(args.nonce_fd)
    if args.task != "user" and (not nonce or not args.state_dir):
        raise SystemExit("a task fixture needs a nonce and a state dir")
    layout = layout_for(args.task, args.seed, args.variant)
    journal = Journal(args.state_dir, nonce, os.getpid(), args.variant) if args.task != "user" else None
    win = FixtureWindow(layout, journal, args.ready_fd, nonce, args.control_fd)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()

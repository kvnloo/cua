#!/usr/bin/env python3
"""N-03 Part B fixture variant: the repository GTK3 task fixture plus, behind an
env gate, two actionable controls that are scrolled out of view (test-fixture code
only; the Driver and the repository fixture are unchanged).

usage: fixture_axfg.py <path to libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py>

``CUA_N03_AXFG=1`` (any other value, or unset: the fixture is exactly the repository
one) appends a 60 px tall ``GtkScrolledWindow`` to the task window. Its content is a
1200 px spacer followed by a check box "Hidden agree" and a push button "Hidden save".
Both start scrolled out of the viewport, so GTK3 drops ``Showing`` for them while they
stay ``Visible``: the Driver lists them (marked off-screen) and its X11 foreground
element click routes them to ``ax_fg`` (``decide_foreground_element_placement``:
not showing, so no point to press; the observed object's AT-SPI action is fired with
the window activated).

The app's signal handlers record the effect: ``axfg_agreed`` (check box toggled) and
``axfg_clicks`` (button clicked) change, and ``axfg_effect_mono_ns`` is the app's own
CLOCK_MONOTONIC reading (``time.monotonic_ns()``) taken in the handler at the moment
the model changes, with ``axfg_effect_what`` naming the control. The state file is then
published as usual (atomic replace).

``CUA_N03_AXFG_APPLY_DELAY_MS=<ms>`` (> 0; positive control only) makes both handlers
apply the model change, take the effect timestamp and publish ``ms`` milliseconds after
GTK delivers the signal (``GLib.timeout_add``), instead of at once.
"""

import importlib.util
import json
import os
import sys
import time

ENV = "CUA_N03_AXFG"
DELAY_ENV = "CUA_N03_AXFG_APPLY_DELAY_MS"


def main():
    spec = importlib.util.spec_from_file_location("cua_gtk3_fixture", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if os.environ.get(ENV, "") == "1":
        install(module, int(os.environ.get(DELAY_ENV, "0") or 0))
    module.main()


def install(module, delay_ms):
    from gi.repository import GLib, Gtk

    window_cls = module.TaskWindow
    original_init = window_cls.__init__

    def publish(self):
        # The repository publish() plus the four axfg fields (same atomic replace).
        self.counter_label.set_text(f"counter={self.counter}")
        self.sequence += 1
        state = {
            "schema": module.TASK_STATE_SCHEMA,
            "pid": os.getpid(),
            "seq": self.sequence,
            "counter": self.counter,
            "agreed": self.agreed,
            "size": self.size,
            "note_saved": self.saved_note,
            "axfg_agreed": getattr(self, "axfg_agreed", False),
            "axfg_clicks": getattr(self, "axfg_clicks", 0),
            "axfg_effect_mono_ns": getattr(self, "axfg_effect_mono_ns", None),
            "axfg_effect_what": getattr(self, "axfg_effect_what", None),
        }
        if self.density is not None:
            state["density"] = self.density
            state["distractor_actions"] = self.distractor_actions
        temporary = f"{self.state_path}.{os.getpid()}.tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
        os.replace(temporary, self.state_path)

    def effect(self, what, apply):
        def run():
            apply()
            self.axfg_effect_mono_ns = time.monotonic_ns()
            self.axfg_effect_what = what
            self.publish()
            return False

        if delay_ms > 0:
            GLib.timeout_add(delay_ms, run)
        else:
            run()

    def on_axfg_agree(self, check):
        active = check.get_active()
        effect(self, "hidden_agree", lambda: setattr(self, "axfg_agreed", active))

    def on_axfg_save(self, *_):
        effect(self, "hidden_save", lambda: setattr(self, "axfg_clicks", getattr(self, "axfg_clicks", 0) + 1))

    def __init__(self, state_path, density=None):
        original_init(self, state_path, density)
        self.axfg_agreed = False
        self.axfg_clicks = 0
        self.axfg_effect_mono_ns = None
        self.axfg_effect_what = None
        root = self.get_child()
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_size_request(-1, 60)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        spacer = Gtk.Label(label="axfg spacer")
        spacer.set_size_request(-1, 1200)
        content.pack_start(spacer, False, False, 0)
        check = Gtk.CheckButton(label="Hidden agree")
        check.connect("toggled", self.on_axfg_agree)
        content.pack_start(check, False, False, 0)
        button = Gtk.Button(label="Hidden save")
        button.set_halign(Gtk.Align.START)
        button.connect("clicked", self.on_axfg_save)
        content.pack_start(button, False, False, 0)
        scroller.add(content)
        root.pack_start(scroller, False, False, 0)
        # Re-publish so the initial state file carries the axfg fields (seq 2).
        self.publish()

    window_cls.publish = publish
    window_cls.on_axfg_agree = on_axfg_agree
    window_cls.on_axfg_save = on_axfg_save
    window_cls.__init__ = __init__
    sys.stdout.write(json.dumps({"mono_ns": time.monotonic_ns(), "event": "axfg_installed",
                                 "delay_ms": delay_ms}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

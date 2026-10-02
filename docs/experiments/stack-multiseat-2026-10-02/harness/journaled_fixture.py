#!/usr/bin/env python3
"""journaled_fixture.py: the upstream GTK3 task fixture with an append-only journal.

Runs the unmodified CuaTestHarness GTK3 TaskWindow (libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py,
imported by path) and adds, without touching its behaviour or layout:
  * every state publish  -> one journal line (kind=state) with the fixture's own state dict;
  * every Note text edit -> one journal line (kind=note_text) with the current entry text;
  * window focus in/out   -> one journal line (kind=focus) (focus-stealing evidence inside the session).
The journal is the independent oracle input: it is written by the target app, never by Hermes or the Driver.
All instances share one window title ("CuaTestHarness GTK3 Tasks"), so instances in different sessions are
look-alike windows; identity lives only in the journal path and the instance id.

usage: journaled_fixture.py <gtk3-main.py> <journal.jsonl> <instance-id>
"""
import importlib.util
import json
import os
import sys
import time

main_py, journal_path, instance = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("cua_gtk3_fixture", main_py)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

journal = open(journal_path, "a", buffering=1, encoding="utf-8")


def record(kind, **fields):
    journal.write(json.dumps({"t": round(time.time(), 4), "instance": instance, "pid": os.getpid(),
                              "kind": kind, **fields}, sort_keys=True) + "\n")


class JournaledTaskWindow(fixture.TaskWindow):
    def __init__(self, state_path):
        self._journal_ready = False
        super().__init__(state_path, None)
        self.note.connect("changed", lambda e: record("note_text", text=e.get_text()))
        self.connect("focus-in-event", lambda *_: record("focus", focused=True) or False)
        self.connect("focus-out-event", lambda *_: record("focus", focused=False) or False)
        self._journal_ready = True
        record("state", **self._state())

    def _state(self):
        return {"seq": self.sequence, "counter": self.counter, "agreed": self.agreed, "size": self.size,
                "note_saved": self.saved_note}

    def publish(self):
        super().publish()
        if getattr(self, "_journal_ready", False):
            record("state", **self._state())


def run():
    state_path = journal_path + ".state.json"
    win = JournaledTaskWindow(state_path)
    win.show_all()
    record("mapped")
    fixture.Gtk.main()
    record("exit")


if __name__ == "__main__":
    run()

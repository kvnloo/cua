#!/usr/bin/env python3
"""OWN-09R R8 barrier fixture: the repository GTK3 task fixture with a
fixture-owned barrier on the Note entry (test-fixture code only; the Driver is
unchanged).

usage: fixture_barrier.py <path to libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py>

Environment:
  OWN09R_JOURNAL   JSONL effect journal written only by this process (the oracle).
  OWN09R_RELEASE   release file; the barrier opens when it contains the token.
  OWN09R_HOLD_MAX_MS  upper bound on one barrier hold (default 2500).

When the Note entry's text becomes a token ``own09r-...!`` (an AT-SPI
``SetTextContents`` from the Driver's ``set_value``), the GTK "changed" handler
runs synchronously inside that D-Bus call: it journals ``effect-enter`` and
then blocks the GTK main loop until the harness writes the token to the
release file (or the hold bound passes). The Driver's native ``set_value`` call
is therefore provably in flight between ``effect-enter`` and ``effect-applied``.
It then journals ``effect-applied`` (one line per landed effect; a duplicate
mutation shows up as a second line for the same token) and publishes the app
state file as the repository fixture does.
"""

import importlib.util
import json
import os
import sys
import time

MARKER = "own09r-"


def main():
    spec = importlib.util.spec_from_file_location("cua_gtk3_fixture", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    journal_path = os.environ["OWN09R_JOURNAL"]
    release_path = os.environ["OWN09R_RELEASE"]
    hold_max = int(os.environ.get("OWN09R_HOLD_MAX_MS", "2500")) / 1000.0
    journal = open(journal_path, "a", encoding="utf-8")

    def log(**fields):
        journal.write(json.dumps({"mono_ns": time.monotonic_ns(), "wall_ns": time.time_ns(), **fields}) + "\n")
        journal.flush()
        os.fsync(journal.fileno())

    def released(token):
        try:
            with open(release_path, encoding="utf-8") as stream:
                return stream.read().strip() == token
        except OSError:
            return False

    original_init = module.TaskWindow.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        def on_note_changed(entry):
            text = entry.get_text()
            if not (text.startswith(MARKER) and text.endswith("!")):
                return
            log(event="effect-enter", text=text)
            deadline = time.monotonic() + hold_max
            opened = False
            while time.monotonic() < deadline:
                if released(text):
                    opened = True
                    break
                time.sleep(0.002)
            self.saved_note = text
            self.publish()
            log(event="effect-applied", text=text, released=opened, seq=self.sequence)

        self.note.connect("changed", on_note_changed)

    module.TaskWindow.__init__ = init
    log(event="start", pid=os.getpid())
    module.main()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""N-01R late-effect control: the repository GTK3 task fixture with an
env-gated delay on the app's state application (test-fixture code only; the
Driver is unchanged).

usage: fixture_late.py <path to libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py>

With ``CUA_N01R_FIXTURE_APPLY_DELAY_MS=<ms>`` (> 0), the "I agree" toggle and
the "Save note" click update the app model and publish the state file ``ms``
milliseconds after GTK delivers the signal, instead of at once. The GTK widget
itself (the check box's checked state, the entry text) changes as usual; only
the app-owned state, which is the oracle, lands late. Unset or 0: the fixture
behaves exactly like the repository one. Each scheduled and applied publish is
logged as a JSON line on stdout (monotonic ns) so the analysis can check the
delay.
"""

import importlib.util
import json
import os
import sys
import time

ENV = "CUA_N01R_FIXTURE_APPLY_DELAY_MS"


def _log(**fields):
    sys.stdout.write(json.dumps({"mono_ns": time.monotonic_ns(), **fields}) + "\n")
    sys.stdout.flush()


def main():
    spec = importlib.util.spec_from_file_location("cua_gtk3_fixture", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    delay = int(os.environ.get(ENV, "0") or 0)
    if delay > 0:
        from gi.repository import GLib

        def later(self, label, apply):
            _log(event="scheduled", what=label, delay_ms=delay)

            def run():
                apply()
                self.publish()
                _log(event="applied", what=label, seq=self.sequence)
                return False

            GLib.timeout_add(delay, run)

        def on_agree(self, check):
            active = check.get_active()
            later(self, "agree", lambda: setattr(self, "agreed", active))

        def on_save_note(self, *_):
            text = self.note.get_text()
            later(self, "save_note", lambda: setattr(self, "saved_note", text))

        module.TaskWindow.on_agree = on_agree
        module.TaskWindow.on_save_note = on_save_note
    _log(event="start", delay_ms=delay)
    module.main()


if __name__ == "__main__":
    main()

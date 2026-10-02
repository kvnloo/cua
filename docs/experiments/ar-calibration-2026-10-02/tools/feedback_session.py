#!/usr/bin/env python3
"""Calibration positive control R8: feedback ON vs OFF on the evaluator's timer.

usage: same arguments as harness/ar/runner/session.py (--wt --chunk --out --work); run exactly where
session.py runs (hostless + quiet-timed + cua-x11-session.sh, plus session-pidns.sh for GTK chunks).

Both arms run the champion binary. The only difference is one RPC issued as the first call after MCP
initialize in every trial (the R2-01 design): set_agent_cursor_enabled {enabled: true} for the
"champion" arm (feedback ON, the product default made explicit) and {enabled: false} for the
"candidate" arm (feedback OFF). The frozen session runner and caller are imported unchanged; this
wrapper only substitutes a subclass of jev-use run.Driver that sends that one call, and records the
arm before each trial so the subclass knows which value to send. T, the oracle and every row field are
produced by the unmodified caller.
"""

from __future__ import annotations

import sys
from pathlib import Path

FEEDBACK = {"champion": True, "candidate": False}


def main() -> None:
    wt = Path(sys.argv[sys.argv.index("--wt") + 1]).resolve()
    sys.path.insert(0, str(wt / "libs/cua-driver/examples/jev-use/python"))
    sys.path.insert(0, str(wt / "harness/ar/runner"))
    import caller  # noqa: E402  (frozen; imported unchanged)
    import run  # noqa: E402  (jev-use)
    import session  # noqa: E402  (frozen; imported unchanged)

    current = {"arm": None}

    class FeedbackDriver(run.Driver):
        def __init__(self, client, label):
            super().__init__(client, label)
            self._feedback_sent = False

        async def call(self, name, arguments):
            if not self._feedback_sent:
                self._feedback_sent = True
                await run.Driver.call(self, "set_agent_cursor_enabled", {"enabled": FEEDBACK[current["arm"]]})
            return await super().call(name, arguments)

    frozen_run_trial = caller.run_trial

    async def run_trial(spec, ctx):
        current["arm"] = spec["arm"]
        row = await frozen_run_trial(spec, ctx)
        row["calibration_feedback_enabled"] = FEEDBACK[spec["arm"]]
        return row

    run.Driver = FeedbackDriver
    caller.run_trial = run_trial
    session.main()


if __name__ == "__main__":
    main()

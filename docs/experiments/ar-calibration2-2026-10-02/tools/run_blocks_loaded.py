#!/usr/bin/env python3
"""Calibration row R10 only: the harness's runner/run_blocks.py, imported unchanged, with every quiet-timed
block's command prefixed INSIDE the lock by tools/with-load.sh <AR_CAL_LOAD>:

    quiet-timed <label> with-load.sh <n> [session-pidns.sh] env ... cua-x11-session.sh ... session.py ...

so <n> CPU burners run for exactly the duration of each timed session and never outside the quiet-lane
lock. Same arguments as run_blocks.py; run under hostless.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    wt = Path(sys.argv[sys.argv.index("--wt") + 1]).resolve()
    sys.path.insert(0, str(wt / "harness/ar/runner"))
    import run_blocks  # noqa: E402  (frozen; imported unchanged)

    burners = str(int(os.environ["AR_CAL_LOAD"]))
    loader = str(Path(__file__).resolve().parent / "with-load.sh")
    frozen_popen = subprocess.Popen

    def popen(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and str(cmd[0]).endswith("/quiet-timed"):
            cmd = [cmd[0], cmd[1], loader, burners, *cmd[2:]]
        return frozen_popen(cmd, *args, **kwargs)

    run_blocks.subprocess.Popen = popen
    return run_blocks.main()


if __name__ == "__main__":
    sys.exit(main())

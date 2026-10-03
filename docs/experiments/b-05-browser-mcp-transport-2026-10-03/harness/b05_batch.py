"""Run several harness steps in one private session / one lock acquisition (sequential).

usage (through in_session.sh): b05_batch.py <plan.json>
plan.json: {"steps": [{"label": str, "script": "b05_browser.py" | "b05_floor.py", "args": [str, ...]}, ...],
            "deadline_s": <seconds>}; a step is not started after the deadline (then NOT_RUN). Paths in
args are passed through unchanged. Each step's rc and wall time are printed as one JSON line.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    plan = json.loads(Path(sys.argv[1]).read_text())
    t0 = time.monotonic()
    deadline = float(plan.get("deadline_s", 1380))
    for step in plan["steps"]:
        if time.monotonic() - t0 > deadline:
            print(json.dumps({"step": step["label"], "status": "NOT_RUN", "reason": "deadline"}), flush=True)
            continue
        s0 = time.monotonic()
        rc = subprocess.call([sys.executable, str(HERE / step["script"]), *step["args"]])
        print(json.dumps({"step": step["label"], "rc": rc, "seconds": round(time.monotonic() - s0, 1)}), flush=True)


if __name__ == "__main__":
    main()

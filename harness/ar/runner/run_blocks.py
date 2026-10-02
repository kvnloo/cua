#!/usr/bin/env python3
"""Run the sessions of a plan, each as ONE timed block on the shared quiet lane.

usage (under hostless):  run_blocks.py --plan plan.json --out-dir DIR --wt WORKTREE [--sessions 0,1,...]

For every session k this runs, and records a receipt for:

    $AR_LANES/bin/quiet-timed <label>-s<k> sandbox/session-pidns.sh env CUA_SESSION_ATSPI=1 \
        CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 \
        $AR_LANES/cua-x11-session.sh <jev-use venv python> runner/session.py --chunk ... --out DIR/raw/s<k>.jsonl

quiet-timed holds the exclusive quiet-lane lock for the session only (<= 48 paired trials plus
2 warm-ups and 4 controls, hard cap 10 minutes), so other tracks interleave between blocks.
Sessions with "pidns": false (browser spot sessions) omit session-pidns.sh. Every session is a fresh private
X11 + AT-SPI session (the "restart every 48 trials"). Raw rows are never filtered here.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

BLOCK_CAP_S = 600
PAIRED_CAP = 48  # paired or soak trials per session
EXTRA_CAP = 6    # 2 warm-ups + 4 controls
LOCK_WAIT_S = 7200  # the shared quiet lane can be held by other tracks for a long time


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--wt", required=True)
    p.add_argument("--sessions", default=None, help="comma-separated session indexes (default: all)")
    p.add_argument("--label", default=None)
    a = p.parse_args()
    if os.environ.get("CUA_HOSTLESS") != "1":
        raise SystemExit("refusing: run under the hostless wrapper")
    lanes = Path(os.environ["AR_LANES"])
    wt = Path(a.wt).resolve()
    plan = json.loads(Path(a.plan).read_text())
    out = Path(a.out_dir).resolve()
    for sub in ("chunks", "raw", "work", "logs"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    wanted = None if a.sessions is None else {int(x) for x in a.sessions.split(",")}
    label = a.label or plan["eval_id"]
    python = wt / "libs/cua-driver/examples/jev-use/.venv/bin/python"
    receipts = out / "blocks.jsonl"
    for chunk in plan["sessions"]:
        k = chunk["session"]
        if wanted is not None and k not in wanted:
            continue
        paired = sum(1 for t in chunk["trials"] if t.get("pair_id") is not None or t["kind"] == "soak")
        if paired > PAIRED_CAP or len(chunk["trials"]) > PAIRED_CAP + EXTRA_CAP:
            raise SystemExit(f"session {k} exceeds {PAIRED_CAP} paired trials + {EXTRA_CAP} warm-ups/controls")
        chunk_path = out / "chunks" / f"s{k:03d}.json"
        chunk_path.write_text(json.dumps(chunk))
        # GTK sessions run in their own pid namespace (the Driver sandbox shares it); browser spot
        # sessions cannot (user namespace hides root ownership of Chromium), see plan.py.
        pidns = [str(wt / "harness/ar/sandbox/session-pidns.sh")] if chunk.get("pidns", True) else []
        cmd = [str(lanes / "bin/quiet-timed"), f"{label}-s{k:03d}", *pidns, "env", "CUA_SESSION_ATSPI=1",
               "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1", str(lanes / "cua-x11-session.sh"), str(python),
               str(wt / "harness/ar/runner/session.py"), "--wt", str(wt), "--chunk", str(chunk_path),
               "--out", str(out / "raw" / f"s{k:03d}.jsonl"), "--work", str(out / "work" / f"s{k:03d}")]
        started = time.time()
        with open(out / "logs" / f"s{k:03d}.log", "w") as log:
            proc = subprocess.Popen(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                rc = proc.wait(timeout=BLOCK_CAP_S + LOCK_WAIT_S)  # + time spent waiting for the lock
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                rc = proc.wait()
        receipt = {"session": k, "label": f"{label}-s{k:03d}", "rc": rc, "trials": len(chunk["trials"]),
                   "wall_s": round(time.time() - started, 1),
                   "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))}
        with open(receipts, "a") as stream:
            stream.write(json.dumps(receipt) + "\n")
        print(json.dumps(receipt), flush=True)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())

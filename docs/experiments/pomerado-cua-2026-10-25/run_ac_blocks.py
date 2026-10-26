#!/usr/bin/env python3
"""Execute planned AC blocks (read-only) by calling the one-attempt runners, in plan order.

Never retries, never reorders, never falls back. A block is started only if the deadline
leaves room for four attempts; an attempt refused before action (exit 2) is logged and the
block is reported incomplete. Does not start the fixture or browsers.
Credit: Pomerado is MIT (Pomerado AI, Inc.); opencli is jackwener/opencli.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--pair", default="AC")
    p.add_argument("--start", type=int, required=True, help="index into the pair's blocks, sorted by id")
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--cdp-endpoint", required=True)
    p.add_argument("--cdp-target")
    p.add_argument("--opencli-cmd", required=True)
    p.add_argument("--opencli-sha", required=True)
    p.add_argument("--jev-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--deadline-s", type=float, required=True, help="wall seconds from now")
    p.add_argument("--attempt-timeout", type=float, default=60.0)
    p.add_argument("--mint-ms-c", type=float, default=0.0)
    p.add_argument("--mint-ms-a", type=float, default=0.0)
    p.add_argument("--browser-version", required=True)
    for n in ("fixture-sha", "caller-sha", "driver-sha", "pomerado-sha"):
        p.add_argument("--" + n, required=True)
    p.add_argument("--evidence-class", default="REAL")
    a = p.parse_args(argv)

    plan = json.loads(a.plan.read_text())
    blocks = sorted((b for b in plan["blocks"] if b["arm_pair"] == a.pair
                     and b["variant"] == "default"), key=lambda b: b["block_id"])
    chosen = blocks[a.start:a.start + a.count]
    t_end = time.monotonic() + a.deadline_s
    need = 4 * (a.attempt_timeout + 10)
    summary = {"requested": len(chosen), "started": 0, "complete": 0, "incomplete": []}
    log = a.log.open("a")

    def note(**kw):
        log.write(json.dumps(kw, sort_keys=True) + "\n"); log.flush()

    common = ["--base", a.base, "--workflow", "browser-fixture-form", "--variant", "default",
              "--effect", "read", "--evidence-class", a.evidence_class,
              "--fixture-sha", a.fixture_sha, "--caller-sha", a.caller_sha,
              "--driver-sha", a.driver_sha, "--pomerado-sha", a.pomerado_sha,
              "--browser-version", a.browser_version, "--out", str(a.out),
              "--timeout", str(a.attempt_timeout)]
    for b in chosen:
        remaining = t_end - time.monotonic()
        if remaining < need * 0.6:  # typical attempt is far below the timeout
            note(event="deadline_skip", block=b["block_id"], remaining=round(remaining, 1))
            break
        summary["started"] += 1
        ok = True
        for att in sorted(b["attempts"], key=lambda x: x["position"]):
            arm, pos = att["arm_assigned"], att["position"]
            ident = ["--block-id", b["block_id"], "--position", str(pos)]
            if arm == "A":
                cmd = ["uv", "run", "--frozen", "--project", str(a.jev_dir), "python",
                       str(HERE / "run_arm_a.py"), *common, *ident, "--mint-ms", str(a.mint_ms_a)]
            else:
                cmd = [sys.executable, str(HERE / "run_arm_c.py"), *common, *ident,
                       "--mint-ms", str(a.mint_ms_c), "--cdp-endpoint", a.cdp_endpoint,
                       "--opencli-cmd", a.opencli_cmd, "--opencli-sha", a.opencli_sha]
                if a.cdp_target:
                    cmd += ["--cdp-target", a.cdp_target]
            t0 = time.monotonic()
            try:
                done = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=a.attempt_timeout + 30)
                rc, err = done.returncode, done.stderr[-300:]
            except subprocess.TimeoutExpired:
                rc, err = 124, "runner timeout"
            note(event="attempt", block=b["block_id"], pos=pos, arm=arm, rc=rc,
                 wall_s=round(time.monotonic() - t0, 2), err=err if rc not in (0, 1) else "")
            if rc not in (0, 1):  # refused/crashed before a receipt: block incomplete
                ok = False
        if ok:
            summary["complete"] += 1
        else:
            summary["incomplete"].append(b["block_id"])
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

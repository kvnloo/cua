#!/usr/bin/env python3
"""RECERT-FIX a3 browser rows: F3 per runtime (py, ts) and F4, on U' and F'. New file.

Python cells (phase f3 / f4) call the wave-3 harness (harness/fix02-w3/browser/fix02_browser.py,
imported unchanged) with one override: the U runner is loaded from U' = 513e45fee instead of the
wave-3 U head (run.py blob is identical at both: ac8ca786c9157b298efa386e63dd39b7440ed5a1).
TypeScript cells (phase f3ts) run the arm's own `typescript/run.ts --provider mock` as a child
process; its Driver is `CUA_DRIVER_BIN` = a per-cell wrapper that execs seam_proxy.py around the
arm's real Driver, so the same injection reaches the TS runner at the process boundary.

Same rules as fix02_browser.py: run only inside cua-x11-session.sh under hostless, with the quiet-lane
lock held outside; provider cap 0 (mock chooser; socket guard counts non-loopback connects).

usage: fix02_browser_a3.py --phase f3|f3ts|f4 --examples <F' jev-use> --ts-examples <arm jev-use>
         --driver <bin> --arm U|F --out <dir> [--code stale|trust_unknown] [--reps N] [--start-rep K]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "fix02-w3" / "browser"))

import fix02_browser as w3  # noqa: E402  (wave-3 harness, unchanged; installs the socket guard)

U_PRIME_HEAD = "513e45fee0c5b02c7dd6d41a960f925a164b5066"  # 0f1955d2f + FIX-01 picks 0fd76ecc5, 513e45fee
w3.U_HEAD = U_PRIME_HEAD
base = w3.base
ft = w3.ft
SEAM = HERE / "seam_proxy.py"


def ts_cell(args, out: Path, *, rep: int, code: str) -> dict:
    injection, mode = w3.CODES[code]
    cell_id = f"f3ts-{code}-{args.arm}-rep{rep:02d}"
    token = f"fix02-{uuid.uuid4().hex[:12]}"
    tmp = Path(os.environ["TMPDIR"]) / f"a3-ts-{uuid.uuid4().hex[:8]}"
    tmp.mkdir(parents=True)
    seam_journal = tmp / "seam.jsonl"
    runner_log = tmp / "run.jsonl"
    wrapper = tmp / "cua-driver-seam"
    wrapper.write_text("#!/usr/bin/env bash\n"
                       f"exec {sys.executable} {SEAM} --real {args.driver} --code {injection or 'none'}"
                       f" --journal {seam_journal} -- \"$@\"\n")
    wrapper.chmod(0o700)
    fixture = w3.start_fixture()
    fixture.configure(cell_id, token, variant="spa_submit", mode=mode)
    before = base.session_pids(os.environ["XDG_RUNTIME_DIR"])
    la = w3.loadavg()
    started = w3.now()
    env = dict(os.environ, CUA_DRIVER_BIN=str(wrapper))
    proc = subprocess.run(
        ["node", "--import", "tsx", "typescript/run.ts", "--provider", "mock", "--fixture-url", fixture.url,
         "--token", token, "--max-steps", "4", "--log", str(runner_log)],
        cwd=str(args.ts_examples), env=env, capture_output=True, text=True, timeout=300)
    wall = round((w3.now() - started) / 1e6, 3)
    fixture.journal.release_all("harness_release_after_caller_finished")
    fixture.journal.wait_quiescent(15)
    time.sleep(0.5)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = base.reap_cell_leftovers(before)
    seam = base.read_jsonl(seam_journal)
    events = base.read_jsonl(runner_log)
    click_requests = [e for e in seam if e.get("tool") == "browser_click"
                      and e.get("kind") in ("forwarded_request", "click_not_forwarded_refusal_injected")]
    injected = any(e.get("kind") in ("click_not_forwarded_refusal_injected",
                                     "driver_response_replaced_by_refusal") for e in seam)
    outcome_events = [e for e in events if e.get("event") == "outcome"]
    outcome = outcome_events[-1].get("outcome") if outcome_events else f"no_outcome_rc{proc.returncode}"
    first_click_t = click_requests[0]["t_ms"] if click_requests else None
    second_click_t = click_requests[1]["t_ms"] if len(click_requests) >= 2 else None
    observations_between = (sum(1 for e in seam if e.get("kind") == "forwarded_request"
                                and e.get("tool") == "get_browser_state"
                                and first_click_t < e["t_ms"] < second_click_t)
                            if second_click_t is not None else None)
    summary = w3.fix02_fixture.journal_summary(journal["events"])
    cell = {
        "cell_id": cell_id, "phase": "f3ts", "runtime": "ts", "rep": rep, "arm": args.arm, "code": code,
        "injection": injection, "journal_mode": mode, "variant": "spa_submit",
        "loadavg_start": la, "loadavg_end": w3.loadavg(), "outcome": outcome,
        "final_outcome_event": outcome_events[-1] if outcome_events else None,
        "runner_rc": proc.returncode, "runner_stderr_tail": proc.stderr[-600:],
        "injected": injected,
        "click_dispatches_by_caller": len(click_requests),
        "clicks_forwarded_to_driver": sum(1 for e in click_requests if e.get("kind") == "forwarded_request"),
        "redispatches_after_refusal": max(0, len(click_requests) - 1) if injected else 0,
        "observations_between_first_and_second_click": observations_between,
        "journal_received": journal["received"], "journal_applied": journal["applied"],
        "duplicate_submits": max(0, journal["applied"] - 1),
        "state_matches_token": journal["state_matches_token"],
        "independently_verified": journal["applied"] == 1 and journal["state_matches_token"],
        "journal_summary": summary, "seam_events": seam,
        "wall_ms_informational": wall, "nonloopback_refused_total": w3.NONLOOPBACK["refused"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    cell["unverified_success"] = cell["outcome"] == "verified" and not cell["independently_verified"]
    w3.write_cell(out, cell, events, journal["events"])
    return cell


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=("f3", "f3ts", "f4"))
    ap.add_argument("--examples", type=Path, required=True)
    ap.add_argument("--ts-examples", type=Path)
    ap.add_argument("--driver", type=Path, required=True)
    ap.add_argument("--arm", required=True, choices=("U", "F"))
    ap.add_argument("--code", default=None, choices=["stale", "trust_unknown"])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--start-rep", type=int, default=1)
    args = ap.parse_args()
    args.examples = args.examples.resolve()
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        print("refusing: not inside the private X11 session", file=sys.stderr)
        return 97
    args.out.mkdir(parents=True, exist_ok=False)
    check = w3.validity(args)
    check["u_runner_head"] = U_PRIME_HEAD
    if args.phase == "f3ts":
        args.ts_examples = args.ts_examples.resolve()
        wt = args.ts_examples.parents[2]
        check["ts_head"] = w3.git(wt, "rev-parse", "HEAD")
        check["ts_run_ts_blob"] = w3.git(wt, "rev-parse", "HEAD:libs/cua-driver/examples/jev-use/typescript/run.ts")
        check["ts_worktree_dirty"] = w3.git(wt, "status", "--porcelain", "--", "libs/cua-driver")
        check["node"] = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
        check["seam_proxy_sha256"] = w3.sha256_file(SEAM)
        check["ok"] = check["ok"] and not check["ts_worktree_dirty"]
    (args.out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "display": check["display"]}), flush=True)
    if not check["ok"]:
        return 2
    cells_out = (args.out / "cells.jsonl").open("a", encoding="utf-8")
    for rep in range(args.start_rep, args.start_rep + args.reps):
        if args.phase == "f3":
            cell = w3.runner_cell(args, args.out, phase="f3", rep=rep, code=args.code, variant="spa_submit")
            cell["runtime"] = "py"
        elif args.phase == "f3ts":
            cell = ts_cell(args, args.out, rep=rep, code=args.code)
        else:
            cell = w3.file_cell(args, args.out, rep=rep)
        slim = {k: v for k, v in cell.items()
                if k not in ("driver_calls", "seam_events", "steps", "journal_summary", "feedback_off")}
        cells_out.write(json.dumps(slim, sort_keys=True, default=str) + "\n")
        cells_out.flush()
        print(json.dumps({"event": "cell", "id": cell["cell_id"], "outcome": cell.get("outcome"),
                          "clicks": cell.get("click_dispatches_by_caller"), "applied": cell.get("journal_applied"),
                          "old": cell.get("old_ref_result"), "code": cell.get("old_ref_code")}), flush=True)
    (args.out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "loadavg_at_end": w3.loadavg(),
        "nonloopback_refused_in_process": w3.NONLOOPBACK["refused"]}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OWN-78L block harness: R1-lite on fork fix candidate F, plus its MOCK / CAP-0 / stub controls.

Reuses OWN-78A's cell harness and launcher BY IMPORT. Both files must be blob-identical to the
OWN-78A packet head (6f6c67955); the harness refuses to run otherwise. Nothing in OWN-78A's code is
edited: this wrapper only sets module constants (lane cap, launcher path) and calls its run_cell().

Run only inside cua-x11-session.sh (via harness/own78l_block.sh). One invocation runs ONE cell, so
each trial gets a fresh private Xvfb, Driver, Chrome, fixture server and token, and each shared
quiet-lane lock acquisition covers exactly one trial (held <= 300 s).

Modes (every cell is OWN-78A's arm C: F runner end to end, --max-steps 2, no dry run):
  stub  loopback stub speaking the TypeSafe wire format, dummy non-secret key (key-shape check)
  mock  lane cap forced to 0 and the runner's own --provider mock (MOCK control); no key in session
  cap0  lane cap forced to 0, dummy non-secret key, real TypeSafe host: the launcher guard must refuse
        before any HTTP attempt (CAP-0 control); no key in session
  live  lane cap 6 reached / 8 attempts, key forwarded by name (R1-lite)

usage: own78l_harness.py --mode <m> --block <name> --repo <worktree> --trees <dir> --f-sha <sha>
         --driver <bin> --driver-sha256 <sha256> --out <dir> --budget-file <json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
A_HARNESS_DIR = HERE.parents[1] / "own-78a-abstain-isolation-4394-2026-10-03" / "harness"
OWN78A_BLOBS = {  # git blob ids at the OWN-78A packet head 6f6c67955505e5b48f130a69feac9ea11c6e9ed6
    "own78a_harness.py": "01c08b1d1d206b9c4203f7acafb570e4a99364a6",
    "own78a_launcher.py": "e814b649116349718e4c1dde28bd423b4f6bb50c",
    "in_session.sh": "e7b2bcdc3a77499f13594ad3cb305afddcf0b6aa",
    "unit.sh": "05c87cd6ca825eb67952c084c234fc5357120ae7",
    "privacy_scan.py": "512412c9e49e54c3f5651d6285c9d19eb1bf8ab4",
}
LIVE_CAP = (6, 8)          # (reached, attempts) for the whole lane
LIVE_START_NEED = (2, 2)   # PREREG: stop before a trial if reached+2 or attempts+2 would exceed the cap
F_SHA = "61eec09092fd161f62651a890c882f276a642855"
DRIVER_SHA256 = "19bad35248702fd42f6aa372f1f4bebe4ca3728d9be0f67287f1c186a0b47df9"

sys.path.insert(0, str(A_HARNESS_DIR))
import own78a_harness as H  # noqa: E402  (blob-checked below before anything runs)


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def reuse_check() -> dict:
    found = {name: git_blob_sha(A_HARNESS_DIR / name) for name in OWN78A_BLOBS}
    return {"expected": OWN78A_BLOBS, "found": found, "ok": found == OWN78A_BLOBS,
            "imported_from": "../own-78a-abstain-isolation-4394-2026-10-03/harness"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("stub", "mock", "cap0", "live"), required=True)
    parser.add_argument("--block", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--trees", type=Path, required=True)
    parser.add_argument("--f-sha", required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget-file", type=Path, required=True)
    args = parser.parse_args()
    args.stub = args.mode == "stub"

    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        print(json.dumps({"event": "refused", "reason": "not inside the isolated X11 session"}))
        return 97
    args.out.mkdir(parents=True, exist_ok=False)
    args.fixture_examples = args.trees / "f" / H.EXAMPLES_REL
    reuse = reuse_check()
    tree = H.tree_matches(args.repo, args.f_sha, args.trees / "f")
    driver_version = subprocess.run([str(args.driver), "--version"], capture_output=True, text=True).stdout.strip()
    key_present = bool(os.environ.get("TYPESAFE_API_KEY", "").strip())
    check = {"block": args.block, "mode": args.mode, "reuse": reuse, "trees": {"f": tree},
             "f_sha_expected": F_SHA, "f_sha": args.f_sha,
             "driver_sha256": H.sha256_file(args.driver), "driver_sha256_expected": DRIVER_SHA256,
             "driver_sha256_arg": args.driver_sha256, "driver_version_in_session": driver_version,
             "forbidden_env_present": [n for n in H.FORBIDDEN_ENV if n in os.environ],
             "display_set": True, "typesafe_key_present": key_present,
             "typesafe_key_expected": args.mode == "live",
             "typesafe_base_url_preset": "TYPESAFE_BASE_URL" in os.environ,
             "telemetry_disabled": os.environ.get("CUA_DRIVER_RS_TELEMETRY_ENABLED") == "false",
             "harness_sha256": H.sha256_file(Path(__file__)),
             "launcher_sha256": H.sha256_file(HERE / "own78l_launcher.py"),
             "fixture_field": H.fixture_field_identity(args.fixture_examples),
             "python": sys.version.split()[0], "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "loadavg_at_start": H.loadavg()}
    check["ok"] = (reuse["ok"] and tree["ok"] and args.f_sha == F_SHA
                   and check["driver_sha256"] == DRIVER_SHA256 == args.driver_sha256
                   and not check["forbidden_env_present"] and not check["typesafe_base_url_preset"]
                   and key_present == (args.mode == "live") and check["telemetry_disabled"])
    (args.out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "mode": args.mode, "key_present": key_present,
                      "reuse_ok": reuse["ok"], "tree_ok": tree["ok"], "driver_version": driver_version}), flush=True)
    if not check["ok"]:
        return 2

    # Configure OWN-78A's module (constants only; its code is unchanged and blob-checked).
    H.LAUNCHER = HERE / "own78l_launcher.py"
    if args.mode == "live":
        H.LANE_CAP_REACHED, H.LANE_CAP_ATTEMPTS = LIVE_CAP
    else:
        H.LANE_CAP_REACHED, H.LANE_CAP_ATTEMPTS = 0, 0
    if args.mode == "mock":
        os.environ["OWN78L_PROVIDER_OVERRIDE"] = "mock"
    if args.mode == "cap0":
        os.environ["TYPESAFE_API_KEY"] = H.DUMMY_KEY  # non-secret; the guard must refuse before sending
    budget = H.Budget(args.budget_file)
    gate = {"mode": args.mode, "lane_cap": [H.LANE_CAP_REACHED, H.LANE_CAP_ATTEMPTS],
            "used_before": [budget.data["reached"], budget.data["attempts"]],
            "own78a_can_start_C": budget.can_start("C")}
    if args.mode == "live":
        reached_left, attempts_left = budget.remaining()
        gate["start"] = reached_left >= LIVE_START_NEED[0] and attempts_left >= LIVE_START_NEED[1]
    elif args.mode == "cap0":
        gate["start"] = True  # registered: the cell starts anyway so the LAUNCHER guard is exercised
        gate["note"] = "harness-level guard refuses (own78a_can_start_C false); cell started deliberately to test the launcher guard"
    else:
        gate["start"] = True
    with (args.out / "cells.jsonl").open("a", encoding="utf-8") as cells_log:
        if gate["start"]:
            try:
                cell = H.run_cell(args, args.out, budget, index=1, arm="C")
            except Exception as error:  # a broken cell is data
                cell = {"cell_id": f"{args.block}-01-C", "block": args.block, "arm": "C",
                        "harness_error": f"{type(error).__name__}: {error}"}
        else:
            cell = {"cell_id": f"{args.block}-01-C", "block": args.block, "arm": "C", "not_run": "budget",
                    "evidence_class": "NOT_RUN"}
        cell = {**cell, "own78l_mode": args.mode, "own78l_gate": gate}
        cells_log.write(json.dumps(cell, sort_keys=True) + "\n")
    print(json.dumps({"event": "cell", "id": cell["cell_id"], "mode": args.mode, "rc": cell.get("rc"),
                      "verified": cell.get("submitted_equals_token"), "inputs": cell.get("input_events"),
                      "submits": cell.get("submits"), "attempts": cell.get("http_attempts"),
                      "reached": cell.get("http_reached"), "guard_refused": cell.get("guard_refused"),
                      "lane_reached": budget.data["reached"], "lane_attempts": budget.data["attempts"],
                      "not_run": cell.get("not_run"), "error": cell.get("harness_error")}, sort_keys=True), flush=True)
    (args.out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lane_reached_after": budget.data["reached"], "lane_attempts_after": budget.data["attempts"],
        "loadavg_at_end": H.loadavg()}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""N-04: native one-source composition on R'n (R' + the N-02 marks): BASE vs X vs X+V vs X+V+HCL.

Runs the N-03 harness (``harness/n03/n03_harness.py``, copied blob-identically from the N-03 packet
at 63d419034, blob 6680473a26a9; its ``xprobe.py`` blob f17d83691faa) unchanged. Its per-trial code
(fresh fixture, fresh Driver, observation, jev-use ``eligible_controls`` lookup, forced background
element-token AT-SPI route, client stamps, the 2 ms state-file oracle thread, the lazy per-schema
validators HCL, the V-control and focus-steal kinds) is used as is. This wrapper adds only:

* arms, by adding entries to the N-03 module's ``ARMS`` table (no other module global changes):
  - ``BASE``    = N-03 arm ``B`` = product defaults: default cursor motion (reveal glide), default
                  50 ms post-action sleep, default focus-guard settle; phase trace on (measurement
                  only). This is R2-10's native BASE (R2-10's wrapper also sets BASE = N-01R arm B).
  - ``X+V+HCL`` = N-03 arm ``X+HCL+V`` (S0 + glide 1 ms + V knob + lazy validators), renamed.
  ``X``, ``X+V``, ``S0`` and ``D`` are the N-03 entries unchanged (X = R2-10R's native X knobs:
  CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS=0 + set_agent_cursor_motion {glide_duration_ms: 1}).
* the chunk loop: the plan's blocks are single rounds. For each requested round, in order, the
  wrapper (1) skips it when ``<runs>/<prefix>-<block>/DONE`` exists, (2) ends the chunk (exit 76)
  when the chunk has run longer than the soft cap, (3) applies the load rule: the round starts only
  when the 1-minute loadavg is <= 4.0; otherwise it re-reads /proc/loadavg every second for up to
  60 s and, if the load never drops, ends the chunk (exit 75) so the caller releases its locks and
  resumes later. Every check is appended to ``<runs>/load-gate.jsonl``. (4) It then runs the N-03
  ``run`` coroutine for that one block, writing ``<runs>/<prefix>-<block>/trials.jsonl``, and writes
  DONE. A round that a hard timeout interrupts has no DONE: it is kept and re-run under ``-r1``.

usage (inside hostless + hostless-strict + cua-x11-session.sh with AT-SPI, via run_block_n04.sh):
  n04_harness.py --wt <wt> --driver <bin> --driver-sha256 <sha> --plan <plan.json> --runs <dir>
                 --work <dir> --prefix <label-prefix> --chunk <chunk-label> [--soft-cap-s 420]
                 [--no-load-gate] <block> [<block> ...]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "n03"))
import n03_harness as H  # noqa: E402

H.ARMS["BASE"] = dict(H.ARMS["B"])
H.ARMS["X+V+HCL"] = dict(H.ARMS["X+HCL+V"])
LOAD_MAX = 4.0
LOAD_WAIT_S = 60.0


def load1() -> float:
    with open("/proc/loadavg", encoding="ascii") as stream:
        return float(stream.read().split()[0])


def log(path: Path, row: dict) -> None:
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


def refuse_outside_session() -> None:
    """The N-03 harness's own refusal rule (main() is bypassed because rounds are looped here)."""
    host_runtime = Path(f"/run/user/{os.getuid()}")
    names = sorted(p.name for p in host_runtime.iterdir()) if host_runtime.is_dir() else []
    host_sockets = [n for n in names if n.startswith(("wayland-", "hypr", "pipewire"))
                    or n in ("bus", "at-spi", "systemd")]
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY") or host_sockets
            or os.environ.get("XDG_RUNTIME_DIR", "/run/user").startswith("/run/user")):
        raise SystemExit(f"refusing: not inside hostless + the isolated X11 session ({host_sockets})")


def main() -> int:
    ap = argparse.ArgumentParser()
    for k in ("--wt", "--driver", "--driver-sha256", "--plan", "--runs", "--work", "--prefix", "--chunk"):
        ap.add_argument(k, required=True)
    ap.add_argument("--soft-cap-s", type=float, default=420.0)
    ap.add_argument("--no-load-gate", action="store_true", help="controls/pilot only (never measured blocks)")
    ap.add_argument("blocks", nargs="+")
    args = ap.parse_args()
    refuse_outside_session()
    plan_bytes = Path(args.plan).read_bytes()
    plan = json.loads(plan_bytes)
    by_name = {b["block"]: b for b in plan["blocks"]}
    runs = Path(args.runs)
    runs.mkdir(parents=True, exist_ok=True)
    gate_log = runs / "load-gate.jsonl"
    t_start = time.monotonic()
    for name in args.blocks:
        block = by_name[name]
        n = 0
        while True:
            # an interrupted earlier attempt of this round (directory without DONE) is kept as is and
            # the round is re-run under the next free label (-r1, -r2, ...)
            label = f"{args.prefix}-{name}" + (f"-r{n}" if n else "")
            out = runs / label
            if (out / "DONE").exists() or not out.exists():
                break
            n += 1
        if (out / "DONE").exists():
            continue
        elapsed = time.monotonic() - t_start
        if elapsed > args.soft_cap_s:
            log(gate_log, {"chunk": args.chunk, "block": name, "event": "chunk_end_cap", "elapsed_s": round(elapsed, 1),
                           "wall_ns": time.time_ns()})
            return 76
        if block.get("lock") == "exclusive" or not args.no_load_gate:
            w0 = time.monotonic()
            checks = []
            while True:
                la = load1()
                checks.append(la)
                if la <= LOAD_MAX or time.monotonic() - w0 >= LOAD_WAIT_S:
                    break
                time.sleep(1.0)
            ok = la <= LOAD_MAX
            log(gate_log, {"chunk": args.chunk, "block": name, "label": label, "event": "load_gate",
                           "pass": ok, "first_load1": checks[0], "last_load1": la, "checks": len(checks),
                           "waited_s": round(time.monotonic() - w0, 2), "wall_ns": time.time_ns()})
            if not ok:
                log(gate_log, {"chunk": args.chunk, "block": name, "event": "chunk_end_load", "wall_ns": time.time_ns()})
                return 75
        ns = argparse.Namespace(wt=args.wt, driver=args.driver, driver_sha256=args.driver_sha256, plan=args.plan,
                                plan_sha256=hashlib.sha256(plan_bytes).hexdigest(), block=name, label=label,
                                out=str(out), work=str(Path(args.work) / label))
        rc = asyncio.run(H.run(ns))
        (out / "DONE").write_text(json.dumps({"rc": rc, "chunk": args.chunk, "wall_ns": time.time_ns()}) + "\n",
                                  encoding="utf-8")
        log(gate_log, {"chunk": args.chunk, "block": name, "label": label, "event": "round_done", "rc": rc,
                       "wall_ns": time.time_ns()})
    return 0


if __name__ == "__main__":
    sys.exit(main())

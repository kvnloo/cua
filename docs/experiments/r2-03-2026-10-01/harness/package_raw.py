#!/usr/bin/env python3
"""Copy per-trial receipts from the lane artifact mirror into the packet raw/ directory.

usage: package_raw.py <artifact-mirror-dir> <packet-dir>

Copies only harness-written, content-free files (trial.jsonl, validity.json, end.json,
budget.json, main-lock.txt, unit step results). Runner stdout/stderr stay in the mirror only.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

src, packet = Path(sys.argv[1]), Path(sys.argv[2])
raw = packet / "raw"
phases = {
    "smoke-1": ("smoke", "smoke1-"),
    "smoke-2": ("smoke", "smoke2-"),
    "c1-decline": ("controls-c1-decline", ""),
    "c2-unreachable": ("controls-c2-unreachable", ""),
    "main": ("main", ""),
}
for run, (dest, prefix) in phases.items():
    run_dir = src / run
    if not run_dir.exists():
        continue
    (raw / dest).mkdir(parents=True, exist_ok=True)
    for cell in sorted((run_dir / "cells").iterdir()):
        trial = cell / "trial.jsonl"
        if trial.exists():
            shutil.copyfile(trial, raw / dest / f"{prefix}{cell.name}.jsonl")
    for name in ("validity", "end"):
        if (run_dir / f"{name}.json").exists():
            (raw / name).mkdir(exist_ok=True)
            shutil.copyfile(run_dir / f"{name}.json", raw / name / f"{run}.json")
for name in ("budget.json", "main-lock.txt"):
    if (src / name).exists():
        shutil.copyfile(src / name, raw / name)
unit = src / "unit"
if unit.exists():
    (raw / "unit").mkdir(exist_ok=True)
    for name in ("steps.txt", "env.txt"):
        shutil.copyfile(unit / name, raw / "unit" / name)
    tail = (unit / "python-unittest-discover.log").read_text().splitlines()[-4:]
    (raw / "unit" / "python-unittest-tail.txt").write_text("\n".join(tail) + "\n")
    for log in ("ts-npm-test.log", "ts-guarded-focused.log"):
        lines = [l for l in (unit / log).read_text().splitlines() if l.startswith("# ")]
        (raw / "unit" / log.replace(".log", "-totals.txt")).write_text("\n".join(lines) + "\n")
print("packaged", sorted(p.name for p in raw.iterdir()))

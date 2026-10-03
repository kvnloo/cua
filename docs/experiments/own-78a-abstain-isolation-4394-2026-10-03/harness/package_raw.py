#!/usr/bin/env python3
"""Copy the lane's raw outputs into the packet's raw/ (standard library only).

usage: package_raw.py <lane-artifacts-dir> <packet-dir>

Per block (smoke, L1, L2, L3): validity.json, end.json, cells.jsonl and one <cell>.jsonl per trial
(the harness's trial.jsonl). Runner stdout/stderr stay in the lane mirror only. Also budget.json,
locks.jsonl, the unit step tables, and raw/provider-ledger.jsonl built from the live http_attempt
receipts. Refuses to write any line holding an absolute local path.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

BLOCKS = ("smoke", "L1", "L2", "L3")
ABSOLUTE = re.compile(r"(/home/|/mnt/|/Users/|/tmp/)")


def checked_copy(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")
    if ABSOLUTE.search(text):
        raise SystemExit(f"absolute path in {src.name}; not packaged")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")


def unit_summary(row: Path) -> dict:
    """Counts and failing test names only (the full logs stay in the lane mirror)."""
    py = (row / "python-unittest-discover.log").read_text(errors="replace")
    ts = (row / "ts-npm-test.log").read_text(errors="replace")
    ran = re.search(r"^Ran (\d+) tests", py, re.M)
    status = re.search(r"^(OK.*|FAILED.*)$", py, re.M)
    ts_count = {key: int(value) for key, value in re.findall(r"^# (tests|pass|fail) (\d+)$", ts, re.M)}
    return {
        "python_ran": int(ran.group(1)) if ran else None,
        "python_status": status.group(1) if status else None,
        "python_failing": re.findall(r"^(?:FAIL|ERROR): (\S+ \([^)]*\))", py, re.M),
        "ts": ts_count,
        "ts_failing": re.findall(r"^not ok \d+ - (.+)$", ts, re.M),
        "typecheck_rc": next((int(m) for m in re.findall(r"ts-typecheck\s+rc=(\d+)", (row / "steps.txt").read_text())), None),
    }


def main() -> int:
    lane, packet = Path(sys.argv[1]), Path(sys.argv[2])
    raw = packet / "raw"
    ledger = []
    for block in BLOCKS:
        src = lane / "raw" / block
        if not src.is_dir():
            continue
        for name in ("validity.json", "end.json", "cells.jsonl"):
            checked_copy(src / name, raw / block / name)
        for cell in sorted((src / "cells").iterdir()):
            checked_copy(cell / "trial.jsonl", raw / block / f"{cell.name}.jsonl")
            if block == "smoke":
                continue
            for line in (cell / "trial.jsonl").read_text().splitlines():
                record = json.loads(line)
                if record.get("type") == "receipt" and record.get("kind") == "http_attempt":
                    ledger.append({key: record.get(key) for key in (
                        "trial", "host", "path", "method", "status", "loopback", "request_id_present",
                        "request_id_sha256_16", "latency_ms", "guard_refused", "error")})
    with (raw / "provider-ledger.jsonl").open("w", encoding="utf-8") as stream:
        for row in ledger:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    checked_copy(lane / "raw" / "budget.json", raw / "budget.json")
    checked_copy(lane / "raw" / "locks.jsonl", raw / "locks.jsonl")
    for row in ("pr", "f", "red", "attempt1-incomplete-export-pr", "attempt1-incomplete-export-f",
                "attempt1-incomplete-export-red"):
        for name in ("steps.txt", "env.txt"):
            src = lane / "unit" / row / name
            if src.exists():
                checked_copy(src, raw / "unit" / row / name)
        if (lane / "unit" / row / "ts-npm-test.log").exists():
            (raw / "unit" / row / "summary.json").write_text(
                json.dumps(unit_summary(lane / "unit" / row), indent=1, sort_keys=True) + "\n")
    print(f"packaged {len(ledger)} provider ledger rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

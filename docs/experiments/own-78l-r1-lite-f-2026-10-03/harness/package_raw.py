#!/usr/bin/env python3
"""Copy OWN-78L's lane outputs into the packet's raw/ (standard library only).

usage: package_raw.py <lane-artifacts-dir> <packet-dir>

Per block (one cell each): validity.json, end.json, cells.jsonl and <cell>.jsonl (the OWN-78A
harness's trial.jsonl). Runner stdout/stderr stay in the lane mirror. Also the budget files,
locks.jsonl, the unit step tables (+ summary.json via OWN-78A's unit_summary) and
raw/provider-ledger.jsonl built from every non-stub http_attempt receipt. checked_copy (imported from
OWN-78A's package_raw.py) refuses any file holding an absolute local path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "own-78a-abstain-isolation-4394-2026-10-03" / "harness"))
from package_raw import checked_copy, unit_summary  # noqa: E402  (OWN-78A, unchanged)

BLOCKS = ("STUBt1", "CAP0t1", "MOCKt1", "MOCKt2", "MOCKt3", "R1t1", "R1t2", "R1t3")
UNIT_ROWS = ("f", "attempt1-incomplete-export-f", "attempt2-incomplete-export-f")
LEDGER_KEYS = ("trial", "host", "path", "method", "status", "loopback", "request_id_present",
               "request_id_sha256_16", "latency_ms", "guard_refused", "error")


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
        for cell in sorted((src / "cells").iterdir()) if (src / "cells").is_dir() else []:
            checked_copy(cell / "trial.jsonl", raw / block / f"{cell.name}.jsonl")
            if block.startswith("STUB"):
                continue
            for line in (cell / "trial.jsonl").read_text().splitlines():
                record = json.loads(line)
                if record.get("type") == "receipt" and record.get("kind") == "http_attempt":
                    ledger.append({"block": block, **{key: record.get(key) for key in LEDGER_KEYS}})
    with (raw / "provider-ledger.jsonl").open("w", encoding="utf-8") as stream:
        for row in ledger:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    for name in ("budget.json", "budget-mock.json", "budget-cap0.json", "locks.jsonl"):
        checked_copy(lane / "raw" / name, raw / name)
    for row in UNIT_ROWS:
        for name in ("steps.txt", "env.txt"):
            checked_copy(lane / "unit" / row / name, raw / "unit" / row / name)
        (raw / "unit" / row / "summary.json").write_text(
            json.dumps(unit_summary(lane / "unit" / row), indent=1, sort_keys=True) + "\n")
    checked_copy(lane / "unit" / "runs.json", raw / "unit" / "runs.json")
    print(f"packaged {len(ledger)} ledger rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

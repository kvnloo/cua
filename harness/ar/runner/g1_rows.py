#!/usr/bin/env python3
"""Turn build and test logs into G1 rows (ar.build.v1 JSONL).

usage: g1_rows.py --build-out <build-driver.sh stdout> --test-log <in-session test log> [...] --out rows.jsonl

build-driver.sh stdout -> {"kind": "build", "ok", "label", "head", "sha256", "fresh_units"}
test log sections "### cargo test -p <pkg> --lib" + "test result: ..." + "rc=<n>" ->
    {"kind": "test", "suite": "<pkg> --lib", "ok", "passed", "failed", "ignored", "rc"}
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

START = re.compile(r"build start label=(\S+) head=([0-9a-f]{40})")
DONE = re.compile(r"build done label=(\S+) seconds=(\d+) sha256=([0-9a-f]{64})")
FRESH = re.compile(r"Fresh workspace units: (\d+)")
SUITE = re.compile(r"^### cargo test -p (\S+) --lib")
RESULT = re.compile(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored")
RC = re.compile(r"^rc=(\d+)")


def build_rows(text: str) -> list[dict]:
    start, done, fresh = START.search(text), DONE.search(text), FRESH.search(text)
    return [{"schema": "ar.build.v1", "kind": "build", "ok": bool(start and done and fresh and fresh.group(1) == "0"),
             "label": done.group(1) if done else None, "head": start.group(2) if start else None,
             "sha256": done.group(3) if done else None, "fresh_units": int(fresh.group(1)) if fresh else None}]


def test_rows(text: str) -> list[dict]:
    rows, current = [], None
    for line in text.splitlines():
        if m := SUITE.match(line):
            current = {"schema": "ar.build.v1", "kind": "test", "suite": f"{m.group(1)} --lib", "passed": 0,
                       "failed": 0, "ignored": 0, "rc": None, "ok": False}
            rows.append(current)
        elif current and (m := RESULT.search(line)):
            current["passed"] += int(m.group(2))
            current["failed"] += int(m.group(3))
            current["ignored"] += int(m.group(4))
        elif current and (m := RC.match(line)):
            current["rc"] = int(m.group(1))
            current["ok"] = current["rc"] == 0 and current["failed"] == 0 and current["passed"] > 0
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build-out", nargs="*", default=[])
    p.add_argument("--test-log", nargs="*", default=[])
    p.add_argument("--out", required=True)
    a = p.parse_args()
    rows = [r for f in a.build_out for r in build_rows(Path(f).read_text())]
    rows += [r for f in a.test_log for r in test_rows(Path(f).read_text())]
    Path(a.out).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    print(json.dumps(rows))


if __name__ == "__main__":
    main()

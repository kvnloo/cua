#!/usr/bin/env python3
"""Copy the content-free raw outputs of every OWN-78 block into the packet's raw/ directory.

usage: package_raw.py <runs-dir> <unit-dir> <unit-diag-dir> <build-out> <packet-dir>

Copies, per block: validity.json, end.json, cells.jsonl and each cell's trial.jsonl; plus the
lane budget file, the unit step table, the sanitized TypeScript failure summaries and the build
summary lines. Runner stderr/stdout and full unit logs stay in the local mirror only (they hold
absolute paths in stack traces). Refuses to write anything that matches a privacy pattern.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import sys
from pathlib import Path

PRIVACY = [re.compile(p) for p in (r"/home/", r"/mnt/", r"/tmp/", r"x11-session\.[A-Za-z0-9]{6}", r"Bearer ", r"tsk_[A-Za-z0-9]")]


def check(text: str, where: str) -> None:
    host = socket.gethostname()
    for pattern in PRIVACY:
        if pattern.search(text):
            raise SystemExit(f"privacy pattern {pattern.pattern!r} in {where}")
    if host and host in text:
        raise SystemExit(f"host name in {where}")


def copy_text(src: Path, dst: Path) -> None:
    text = src.read_text()
    check(text, str(dst))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)


def ts_failures(log: Path) -> list[dict]:
    """Extract only test names, failure types and error messages from a node --test TAP log."""
    out, current = [], None
    for line in log.read_text().splitlines():
        m = re.match(r"^not ok \d+ - (.*)$", line)
        if m:
            current = {"test": m.group(1)}
            out.append(current)
            continue
        if current is not None:
            for key in ("failureType", "error", "name"):
                m = re.match(rf"^\s+{key}: '(.*)'$", line)
                if m and key not in current:
                    current[key] = m.group(1)
    return out


def main() -> None:
    runs, unit, diag, build_out, packet = (Path(a) for a in sys.argv[1:6])
    raw = packet / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir()
    for block in sorted(p for p in runs.iterdir() if p.is_dir()):
        for name in ("validity.json", "end.json", "cells.jsonl"):
            if (block / name).exists():
                copy_text(block / name, raw / block.name / name)
        for cell in sorted((block / "cells").iterdir()):
            copy_text(cell / "trial.jsonl", raw / block.name / f"{cell.name}.jsonl")
    copy_text(runs / "budget.json", raw / "budget.json")
    copy_text(unit / "steps.txt", raw / "unit" / "steps.txt")
    copy_text(unit / "env.txt", raw / "unit" / "env.txt")
    summary = {
        "credential_free": {"log": "ts-npm-test.log (local mirror)", "failures": ts_failures(unit / "ts-npm-test.log")},
        "with_dummy_env": {
            "env": "CUA_S1_DECISION_URL=http://127.0.0.1:9/decide, TYPESAFE_API_KEY=<dummy non-secret>, TYPESAFE_BASE_URL=http://127.0.0.1:9",
            "log": "ts-npm-test-with-dummy-env.log (local mirror)",
            "failures": ts_failures(diag / "ts-npm-test-with-dummy-env.log"),
        },
    }
    for name, path in (("credential_free", unit / "ts-npm-test.log"), ("with_dummy_env", diag / "ts-npm-test-with-dummy-env.log")):
        tail = [l for l in path.read_text().splitlines() if re.match(r"^# (tests|pass|fail) ", l)]
        summary[name]["totals"] = tail
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    check(text, "raw/unit/ts-failures.json")
    (raw / "unit" / "ts-failures.json").write_text(text)
    lines = [l for l in build_out.read_text().splitlines() if l.strip()]
    copy_text_lines = "\n".join(lines) + "\n"
    check(copy_text_lines, "raw/build-driver.out")
    (raw / "build-driver.out").write_text(copy_text_lines)
    print(f"packaged {sum(1 for _ in raw.rglob('*.jsonl'))} jsonl files into {raw.name}/")


if __name__ == "__main__":
    main()

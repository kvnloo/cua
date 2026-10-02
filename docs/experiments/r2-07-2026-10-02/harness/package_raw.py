#!/usr/bin/env python3
"""Copy the content-free raw outputs from the lane mirror into the packet's raw/ (no stdout/stderr logs).

usage: python3 package_raw.py <mirror-dir> <packet-dir>
Fails if any copied file contains an absolute local path, the host name or a credential marker.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import sys
from pathlib import Path

MIRROR = Path(sys.argv[1]).resolve()
PACKET = Path(sys.argv[2]).resolve()
RAW = PACKET / "raw"
HOST = socket.gethostname()
BAD = [re.compile(p) for p in ("/" + "mnt/", "/" + "home/", "/" + "tmp/", "cua-lane" + "-tmp", "TYPESAFE_API_KEY" + "=", "Bearer" + " ")]
BAD.append(re.compile(r"\b" + re.escape(HOST) + r"\b"))
TAB_ID = re.compile(r"tab-[0-9a-f]{8}-[0-9a-f-]{27}")


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def phase(src: Path, dst: Path) -> None:
    for name in ("ENVIRONMENT.txt", "validity.json", "cells.jsonl", "end.json", "compile.json", "admission.json", "artifact.json",
                 "learning-trace.jsonl"):
        if (src / name).exists():
            copy(src / name, dst / name)
    cells = src / "cells"
    if not cells.exists():
        return
    for item in sorted(cells.iterdir()):
        if item.is_dir() and (item / "trial.jsonl").exists():
            copy(item / "trial.jsonl", dst / "trials" / f"{item.name}.jsonl")
        elif item.suffix == ".jsonl":
            copy(item, dst / "cells" / item.name)


def sanitize_probe(src: Path, dst: Path) -> None:
    data = json.loads(src.read_text())
    text = TAB_ID.sub("tab-<redacted>", json.dumps(data, indent=1, sort_keys=True))
    text = re.sub(r"http://127\.0\.0\.1:\d+/", "http://127.0.0.1:<port>/", text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text + "\n")


def main() -> None:
    if RAW.exists():
        shutil.rmtree(RAW)
    RAW.mkdir()
    # step 0
    for name in ("steps.txt",):
        copy(MIRROR / "step0-unit" / name, RAW / "step0" / name)
    for arm in ("plain", "guarded"):
        copy(MIRROR / "step0-smoke" / f"{arm}.jsonl", RAW / "step0" / f"smoke-{arm}.jsonl")
    # shakedown (mock only; disclosed in PREREG)
    for name in ("smoke1", "smoke2", "neg1", "neg2", "p6a", "p6b"):
        if (MIRROR / "shakedown" / name).exists():
            phase(MIRROR / "shakedown" / name, RAW / "shakedown" / name)
    for name in ("probe1.json", "probe2.json"):
        if (MIRROR / "shakedown" / name).exists():
            sanitize_probe(MIRROR / "shakedown" / name, RAW / "shakedown" / name)
    # measured phases
    phase(MIRROR / "learn", RAW / "learn")
    phase(MIRROR / "warm", RAW / "warm")
    for group in ("neg", "p6"):
        for block in sorted((MIRROR / group).glob("*")) if (MIRROR / group).exists() else []:
            phase(block, RAW / group / block.name)
    if (MIRROR / "livefallback").exists():
        phase(MIRROR / "livefallback", RAW / "livefallback")
    copy(MIRROR / "budget.json", RAW / "budget.json")
    locks = []
    for f in sorted(MIRROR.glob("*-lock.txt")):
        locks.append(f"## {f.stem}\n" + f.read_text())
    (RAW / "locks.txt").write_text("\n".join(locks))
    problems = []
    for f in RAW.rglob("*"):
        if f.is_file():
            text = f.read_text(errors="replace")
            for pattern in BAD:
                if pattern.search(text):
                    problems.append(f"{f.relative_to(PACKET)}: {pattern.pattern}")
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print(f"packaged {sum(1 for f in RAW.rglob('*') if f.is_file())} files; privacy scan clean")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Copy unit outputs into raw/unit/ and replace machine-local strings in every raw/ text file.

usage: package_raw.py <replacements.json> [<unit-src-dir>]
replacements.json (never committed): ordered list of [local_string, placeholder]; longest first.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw"
TEXT = {".json", ".jsonl", ".log", ".txt", ".out", ".patch", ".diff", ".md"}


def main() -> int:
    pairs = sorted(json.loads(Path(sys.argv[1]).read_text()), key=lambda p: -len(p[0]))
    if len(sys.argv) > 2:
        src = Path(sys.argv[2])
        dst = RAW / "unit"
        dst.mkdir(exist_ok=True)
        for d in sorted(src.iterdir()):
            if d.is_dir():
                shutil.copytree(d, dst / d.name, dirs_exist_ok=True)
    changed = 0
    for path in RAW.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT:
            continue
        text = path.read_text(errors="replace")
        new = text
        for local, placeholder in pairs:
            new = new.replace(local, placeholder)
        if new != text:
            path.write_text(new)
            changed += 1
    print(json.dumps({"files_rewritten": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

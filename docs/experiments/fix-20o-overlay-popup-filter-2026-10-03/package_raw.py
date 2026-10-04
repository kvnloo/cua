#!/usr/bin/env python3
"""FIX-20O: copy lane-local run outputs into raw/ with privacy redaction (stdlib only).

usage: package_raw.py <lane-tmp-dir> <quiet-lane-ledger> <redact.json>
Copies runs/<pass>/<label>/ (trials.jsonl or probe.jsonl -> .gz, session.log, focuslog/) into
raw/rows/<pass>/<label>/, the FIX-20O receipts of the quiet-lane ledger into raw/locks/receipts.jsonl,
unit logs into raw/unit/, build outputs into raw/build/. Redaction (also inside gz): local path
prefixes -> <lanes> / <tmp> / <home>, the user name -> <user>, 'localuser:<name>' grants ->
'localuser:<user>'. The machine-specific values are read from the environment, never written.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sys
from pathlib import Path

PKT = Path(__file__).resolve().parent
TMP = Path(sys.argv[1]).resolve()
LEDGER = Path(sys.argv[2])
USER = os.environ.get("USER", "")
HOME = os.environ.get("HOME", "")
SUBS = [tuple(x) for x in json.loads(Path(sys.argv[3]).read_text())]  # lane-local [[prefix, label], ...]
if HOME:
    SUBS.append((HOME, "<home>"))


def redact(text: str) -> str:
    for a, b in SUBS:
        text = text.replace(a, b)
    text = re.sub(r"/tmp/claude-\d+/[^\s\"']*", "<claude-tmp>", text)
    if USER:
        text = re.sub(rf"localuser:{re.escape(USER)}\b", "localuser:<user>", text)
        text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(USER)}(?![A-Za-z0-9_])", "<user>", text)
    return text


def put(src: Path, dst: Path, gz: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = redact(src.read_text(encoding="utf-8", errors="replace"))
    if gz:
        with gzip.open(dst, "wt", encoding="utf-8") as stream:
            stream.write(text)
    else:
        dst.write_text(text, encoding="utf-8")


def main() -> None:
    rows = PKT / "raw" / "rows"
    for pass_dir in sorted(p for p in (TMP / "runs").glob("*") if p.is_dir()):
        for block in sorted(p for p in pass_dir.iterdir() if p.is_dir()):
            out = rows / pass_dir.name / block.name
            for name in ("trials.jsonl", "probe.jsonl"):
                f = block / "raw" / name
                if f.exists():
                    put(f, out / (name + ".gz"), gz=True)
            for name in ("session.txt",):
                f = block / "raw" / name
                if f.exists():
                    put(f, out / name)
            if (block / "session.log").exists():
                put(block / "session.log", out / "session.log")
            fl = block / "raw" / "focuslog"
            if fl.is_dir():
                for f in sorted(fl.glob("*.jsonl")):
                    put(f, out / "focuslog" / f.name)
        log = TMP / "runs" / f"{pass_dir.name}.orchestrator.log"
        if log.exists():
            put(log, rows / pass_dir.name / "orchestrator.log")
    keep = [ln for ln in LEDGER.read_text(encoding="utf-8").splitlines() if '"lane":"FIX-20O"' in ln]
    (PKT / "raw" / "locks").mkdir(parents=True, exist_ok=True)
    (PKT / "raw" / "locks" / "receipts.jsonl").write_text(redact("\n".join(keep) + "\n"), encoding="utf-8")
    for sub in ("unit", "build", "smoke"):
        src = TMP / sub
        if src.is_dir():
            for f in sorted(src.rglob("*")):
                if f.is_file() and f.suffix in (".txt", ".log", ".diff", ".json", ".tsv", ".out"):
                    put(f, PKT / "raw" / sub / f.relative_to(src))
    for name in ("build-queue.log", "patch-ids.tsv", "chains.txt", "binaries.txt", "versions.txt"):
        if (TMP / name).exists():
            put(TMP / name, PKT / "raw" / "build" / name)
    for f in sorted(TMP.glob("build-fix20o-*.out")):
        put(f, PKT / "raw" / "build" / f.name)
    print("packaged", sum(1 for _ in (PKT / "raw").rglob("*") if _.is_file()), "files")


if __name__ == "__main__":
    main()

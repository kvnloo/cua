#!/usr/bin/env python3
"""Package the lane's run directories into raw/ (deterministic gzip, local paths and names redacted).

usage (under hostless):
  package_raw.py --runs <tmp>/runs --pilot-runs <tmp>/pilot-runs --ledger <locks>/quiet-lane-ledger.jsonl \
                 --redact PREFIX=TOKEN ... (local prefixes are passed at packaging time, never written here)

Per round/block label (<runs>/<label>/): trials.jsonl -> raw/runs/<label>/trials.jsonl.gz, tools-list.json,
output-schemas.json, hc-corpus.jsonl.gz, DONE -> done.json. Chunk session logs (<runs>/chunks/*.session.log)
-> raw/chunks/<chunk>-session-log.txt (the repository ignores *.log). Load-rule log -> raw/locks/load-gate.jsonl;
the lane's SHARED receipts -> raw/locks/lock-ledger-shared.jsonl; every shared-ledger line whose label is one of
this lane's chunks (n04-c*, n04c-c*, n04p-c*) -> raw/locks/quiet-lane-receipts.jsonl. Pilot blocks (excluded
from every number) -> raw/pilots/. Private names from the untracked CUA_PRIVACY_NAMES_FILE (if set) are
replaced by <name> as whole words. Writes raw/MANIFEST.json (sha256 + bytes of every packaged file).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
REDACT: list[tuple[str, str]] = []
NAMES: list[re.Pattern] = []
CHUNK_LABEL = re.compile(r"^n04[cp]?-c\d+$")


def redact(text: str) -> str:
    for a, b in sorted(REDACT + [(str(Path.home()), "<home>")], key=lambda p: -len(p[0])):
        text = text.replace(a, b)
    text = re.sub(r"/run/user/\d+", "/run/user/<uid>", text)
    for p in NAMES:
        text = p.sub("<name>", text)
    return text


def write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(str(path), "wb", mtime=0) as gz:
        gz.write(text.encode("utf-8"))


def package_block(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    if (src / "trials.jsonl").exists():
        write_gz(dst / "trials.jsonl.gz", redact((src / "trials.jsonl").read_text(encoding="utf-8")))
    if (src / "hc-corpus.jsonl").exists():
        write_gz(dst / "hc-corpus.jsonl.gz", redact((src / "hc-corpus.jsonl").read_text(encoding="utf-8")))
    for name in ("tools-list.json", "output-schemas.json"):
        if (src / name).exists():
            (dst / name).write_text(redact((src / name).read_text(encoding="utf-8")), encoding="utf-8")
    if (src / "DONE").exists():
        (dst / "done.json").write_text((src / "DONE").read_text(encoding="utf-8"), encoding="utf-8")


def package_runs(runs: Path, dst_root: Path, chunk_dst: Path) -> None:
    for src in sorted(runs.iterdir()):
        if src.is_dir() and src.name != "chunks":
            package_block(src, dst_root / src.name)
    chunk_dst.mkdir(parents=True, exist_ok=True)
    for log in sorted((runs / "chunks").glob("*.session.log")):
        (chunk_dst / log.name.replace(".session.log", "-session-log.txt")).write_text(
            redact(log.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--pilot-runs")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--redact", action="append", default=[], help="PREFIX=TOKEN")
    args = ap.parse_args()
    for item in args.redact:
        prefix, token = item.split("=", 1)
        REDACT.append((prefix, token))
    names_file = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if names_file:
        for n in Path(names_file).read_text(encoding="utf-8").splitlines():
            if n.strip():
                NAMES.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(n.strip()) + r"(?![A-Za-z0-9])", re.I))
    runs = Path(args.runs)
    package_runs(runs, RAW / "runs", RAW / "chunks")
    (RAW / "locks").mkdir(parents=True, exist_ok=True)
    for name, dst in (("load-gate.jsonl", "load-gate.jsonl"), ("lock-ledger-shared.jsonl", "lock-ledger-shared.jsonl")):
        if (runs / name).exists():
            (RAW / "locks" / dst).write_text(redact((runs / name).read_text(encoding="utf-8")), encoding="utf-8")
    if args.pilot_runs:
        package_runs(Path(args.pilot_runs), RAW / "pilots", RAW / "pilots" / "chunks")
        for name in ("load-gate.jsonl", "lock-ledger-shared.jsonl"):
            p = Path(args.pilot_runs) / name
            if p.exists():
                (RAW / "pilots" / name).write_text(redact(p.read_text(encoding="utf-8")), encoding="utf-8")
    lines = []
    for line in Path(args.ledger).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if CHUNK_LABEL.match(str(rec.get("label", ""))):
            lines.append(json.dumps(rec, sort_keys=True))
    (RAW / "locks" / "quiet-lane-receipts.jsonl").write_text(redact("\n".join(lines) + "\n"), encoding="utf-8")
    manifest = {}
    for p in sorted(RAW.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            data = p.read_bytes()
            manifest[str(p.relative_to(RAW))] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (RAW / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"packaged {len(manifest)} files")


if __name__ == "__main__":
    main()

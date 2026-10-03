#!/usr/bin/env python3
"""Package the lane's run directories into raw/ (deterministic gzip, local paths redacted).

usage (under hostless): package_raw.py --runs <runs-dir> [--runs <pilot-runs-dir> --pilot] ...
    package_raw.py --runs <tmp>/runs --pilot-runs <tmp>/runs-pilot --ledger <locks>/quiet-lane-ledger.jsonl

Per block label: trials.jsonl -> raw/runs/<label>/trials.jsonl.gz, tools-list.json,
output-schemas.json, hc-corpus.jsonl.gz, session.log (redacted). Pilot blocks (excluded from
analysis) go to raw/pilots/<label>/. Lock receipts: every shared-ledger line whose label starts with
n03a2 (this attempt) or n03p- (attempt 1, disclosed) -> raw/locks/quiet-lane-receipts.jsonl.
Writes raw/MANIFEST.json (sha256 + bytes of every packaged file).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"


REDACT: list[tuple[str, str]] = []


def redactions() -> list[tuple[str, str]]:
    """Local prefixes come from --redact PREFIX=TOKEN at packaging time (longest first); none are
    written in this file."""
    return sorted(REDACT + [(str(Path.home()), "<home>")], key=lambda p: -len(p[0]))


def redact(text: str) -> str:
    for a, b in redactions():
        text = text.replace(a, b)
    return re.sub(r"/run/user/\d+", "/run/user/<uid>", text)


def write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(str(path), "wb", mtime=0) as gz:
        gz.write(text.encode("utf-8"))


def package_block(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    raw = src / "raw"
    if (raw / "trials.jsonl").exists():
        write_gz(dst / "trials.jsonl.gz", redact((raw / "trials.jsonl").read_text(encoding="utf-8")))
    if (raw / "hc-corpus.jsonl").exists():
        write_gz(dst / "hc-corpus.jsonl.gz", redact((raw / "hc-corpus.jsonl").read_text(encoding="utf-8")))
    for name in ("tools-list.json", "output-schemas.json"):
        if (raw / name).exists():
            (dst / name).write_text(redact((raw / name).read_text(encoding="utf-8")), encoding="utf-8")
    if (src / "session.log").exists():
        (dst / "session.log").write_text(redact((src / "session.log").read_text(encoding="utf-8", errors="replace")),
                                         encoding="utf-8")


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
    aborted = []
    for src in sorted(Path(args.runs).iterdir()):
        if src.is_dir() and src.name.startswith("n03a2-"):
            if not (src / "raw" / "trials.jsonl").exists():
                # stopped before any trial started (no session, no lock receipt): kept as a record
                log = src / "session.log"
                aborted.append({"label": src.name, "session_log_bytes": log.stat().st_size if log.exists() else None})
                continue
            package_block(src, RAW / "runs" / src.name)
    (RAW / "locks").mkdir(parents=True, exist_ok=True)
    (RAW / "locks" / "aborted-blocks.json").write_text(json.dumps(aborted, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if args.pilot_runs:
        for src in sorted(Path(args.pilot_runs).iterdir()):
            if src.is_dir() and src.name.startswith("n03a2p-"):
                package_block(src, RAW / "pilots" / src.name)
    lines = []
    for line in Path(args.ledger).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        label = str(rec.get("label", ""))
        if label.startswith(("n03a2", "n03p-")):
            lines.append(json.dumps(rec, sort_keys=True))
    (RAW / "locks").mkdir(parents=True, exist_ok=True)
    (RAW / "locks" / "quiet-lane-receipts.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {}
    for p in sorted(RAW.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            data = p.read_bytes()
            manifest[str(p.relative_to(RAW))] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (RAW / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"packaged {len(manifest)} files")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Copy the lane's raw run outputs into the packet's raw/ (stdlib only), scrubbing local
path prefixes and the host name. No local path is written in this script: the prefixes
to scrub are arguments.

Copied from the N-02 package.py (../n-02-native-transport-2026-10-02/package.py); OWN-20G keeps
every lock receipt in the global quiet-lane ledger (shared and exclusive), so --shared-ledger is
optional, and drops the HC corpus files.

usage: package.py --runs <runs-dir> --global-ledger <file> --label-prefix own20g- \
                  [--shared-ledger <file>] [--scrub PREFIX=TOKEN ...] [--extra SRC=DEST ...]

* runs/<label>/raw/trials.jsonl -> raw/<label>/trials.jsonl.gz (JSON lines kept byte-for-byte
  apart from the scrubbed strings); likewise hc-corpus.jsonl -> hc-corpus.jsonl.gz and
  output-schemas.json -> output-schemas.json when present;
* runs/<label>/session.log -> raw/<label>/session.txt (session/harness lines only);
* lock receipts for the packet's labels (global quiet-timed ledger + this lane's shared-lock
  ledger) -> raw/lock-ledger.jsonl;
* --extra SRC=DEST copies one text file (scrubbed) to raw/DEST.
"""

from __future__ import annotations

import argparse
import gzip
import json
import socket
from pathlib import Path

HERE = Path(__file__).resolve().parent


def scrubber(pairs: list[str]):
    rules = sorted((p.split("=", 1) for p in pairs), key=lambda r: -len(r[0]))
    host = socket.gethostname()

    def scrub(text: str) -> str:
        for prefix, token in rules:
            text = text.replace(prefix, token)
        if host and len(host) > 2:
            text = text.replace(host, "<host>")
        return text
    return scrub


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--shared-ledger", default=None)
    ap.add_argument("--global-ledger", required=True)
    ap.add_argument("--label-prefix", required=True)
    ap.add_argument("--scrub", action="append", default=[])
    ap.add_argument("--extra", action="append", default=[])
    args = ap.parse_args()
    scrub = scrubber(args.scrub)
    raw = HERE / "raw"
    raw.mkdir(exist_ok=True)
    labels = []
    for run in sorted(Path(args.runs).iterdir()):
        trials = run / "raw" / "trials.jsonl"
        if not run.is_dir() or not run.name.startswith(args.label_prefix):
            continue
        out = raw / run.name
        out.mkdir(exist_ok=True)
        labels.append(run.name)
        if trials.exists():
            text = scrub(trials.read_text(encoding="utf-8"))
            for line in text.splitlines():
                if line.strip():
                    json.loads(line)  # still valid JSON after scrubbing
            with gzip.GzipFile(out / "trials.jsonl.gz", "wb", compresslevel=9, mtime=0) as stream:
                stream.write(text.encode("utf-8"))
        log = run / "session.log"
        if log.exists():
            keep = [scrub(x) for x in log.read_text(encoding="utf-8", errors="replace").splitlines()
                    if x.startswith(("[session]", "done:", "refusing", "Traceback", "=== ")) or "Error" in x]
            (out / "session.txt").write_text("\n".join(keep) + "\n", encoding="utf-8")
    rows = []
    for path in [x for x in (args.global_ledger, args.shared_ledger) if x]:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("label") in labels:
                rows.append(scrub(json.dumps(row, sort_keys=True)))
    (raw / "lock-ledger.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    for pair in args.extra:
        src, dest = pair.split("=", 1)
        target = raw / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(scrub(Path(src).read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    print(f"packaged {len(labels)} runs, {len(rows)} lock receipts")


if __name__ == "__main__":
    main()

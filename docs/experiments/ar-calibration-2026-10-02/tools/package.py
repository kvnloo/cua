#!/usr/bin/env python3
"""Copy the calibration run into the packet directory with host paths replaced (<lanes>, <tmp>, <mnt>,
<home>) and raw JSONL gzipped. Run under hostless.

usage: package.py --run-dir D --packet P --quiet-ledger LEDGER --repo CANDIDATE_REPO
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
from pathlib import Path

SUBS = [("<lanes>", "<lanes>"), ("<tmp>", "<tmp>"),
        ("<mnt>", "<mnt>"), ("<home>", "<home>")]
CH = "457bc65d45b2a87ac080b281ea777f8914002c29"


def clean(text: str) -> str:
    for a, b in SUBS:
        text = text.replace(a, b)
    return text


def put(src: Path, dst: Path, gz: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = clean(src.read_text(encoding="utf-8", errors="replace"))
    if gz:
        with gzip.GzipFile(filename="", mode="wb", fileobj=open(str(dst) + ".gz", "wb"), mtime=0) as f:
            f.write(data.encode())
    else:
        dst.write_text(data)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    p.add_argument("--packet", required=True)
    p.add_argument("--quiet-ledger", required=True)
    p.add_argument("--repo", required=True)
    a = p.parse_args()
    D, P = Path(a.run_dir), Path(a.packet)
    raw = P / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    for name in ("CALIB-PREREG.json", "CALIB-PREREG.sha256", "cal-results.jsonl", "summary.json", "diag.json",
                 "submit.log"):
        put(D / name, raw / name)
    for f in sorted((D / "requests").glob("*.json")):
        put(f, raw / "requests" / f.name)
    for f in sorted((D / "g0").glob("*")):
        put(f, raw / "g0" / f.name)
    for f in sorted((D / "g1").glob("*")):
        if f.suffix in (".jsonl", ".out", ".log", ".sh") and f.name != "g1-all.out":
            put(f, raw / "g1" / f.name)
    for e in sorted((D / "evals").iterdir()):
        if not (e / "final.json").exists():
            continue
        for f in sorted(e.rglob("*")):
            rel = f.relative_to(e)
            if not f.is_file() or rel.parts[0] in ("work", "chunks") or (len(rel.parts) > 1 and rel.parts[1] in ("work", "chunks")):
                continue
            if f.name == "scratch-ledger.jsonl":
                continue
            gz = f.suffix == ".jsonl" and "raw" in rel.parts
            put(f, raw / "evals" / e.name / rel, gz=gz)
    for kind in ("browser", "gtk"):
        base = D / "feedback" / kind
        for f in sorted(base.rglob("*")):
            rel = f.relative_to(base)
            if f.is_file() and rel.parts[0] in ("raw", "logs") or f.name in ("plan.json", "blocks.jsonl"):
                if f.is_file():
                    put(f, raw / "feedback" / kind / rel, gz=(rel.parts[0] == "raw"))
    lines = [x for x in Path(a.quiet_ledger).read_text().splitlines()
             if '"label":"ar-20261002-cal-' in x or '"label":"cal-feedback-' in x]
    (raw / "quiet-lane-receipts.jsonl").write_text("\n".join(lines) + "\n")
    cands = P / "candidates"
    cands.mkdir(parents=True, exist_ok=True)
    refs = subprocess.run(["git", "-C", a.repo, "for-each-ref", "--format=%(refname:short) %(objectname)",
                           "refs/heads/ar/calib/"], capture_output=True, text=True, check=True).stdout.split("\n")
    index = []
    for line in filter(None, refs):
        ref, sha = line.split()
        diff = subprocess.run(["git", "-C", a.repo, "diff", "--no-color", f"{CH}..{ref}"], capture_output=True,
                              text=True, check=True).stdout
        name = ref.split("/", 2)[2]
        (cands / f"{name}.diff").write_text(diff)
        index.append({"branch": ref, "commit": sha, "diff": f"candidates/{name}.diff"})
    (cands / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"packaged {sum(1 for _ in raw.rglob('*') if _.is_file())} raw files, {len(index)} candidate diffs")


if __name__ == "__main__":
    main()

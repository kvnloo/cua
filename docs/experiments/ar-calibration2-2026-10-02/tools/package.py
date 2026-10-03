#!/usr/bin/env python3
"""Copy the calibration-2 run into the packet directory with host paths replaced (<lanes>, <tmp>, <mnt>,
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
        with open(str(dst) + ".gz", "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as f:
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
    keep = {"CALIB2-PREREG.json", "CALIB2-PREREG.sha256",  # committed before any trial; never rewritten
            "CALIB2-AMEND-R10B.json", "CALIB2-AMEND-R10B.sha256"}  # committed before any R10b trial
    if raw.exists():
        for child in raw.iterdir():
            if child.name in keep:
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    for name in sorted(keep):
        if (raw / name).read_bytes() != (D / name).read_bytes():
            raise SystemExit(f"{name} in the run dir differs from the committed pre-registration")
    for name in ("cal2-results.jsonl", "cal2-amend-results.jsonl", "summary.json", "calibration-ledger.jsonl",
                 "submit.log", "run_all.log", "run_r10b.log"):
        put(D / name, raw / name)
    # diagnostics (not gate results): G1 flake reruns + diagnostic screens, the failed first R8 launch
    dg = D / "diag"
    for f in ("flake-full.txt", "flake-history.txt", "full-1.log", "run-1.log"):
        if (dg / f).exists():
            put(dg / f, raw / "diag" / "g1flake-earlier" / f)
    g = dg / "g1flake"
    for f in sorted(g.rglob("*")):
        rel = f.relative_to(g)
        if not f.is_file() or "work" in rel.parts or "chunks" in rel.parts or f.name == "done":
            continue
        if f.name.startswith("core-run-") and f.name != "core-run-1.log":
            continue
        put(f, raw / "diag" / "g1flake" / rel, gz=(f.suffix == ".jsonl" and "raw" in rel.parts))
    for f in sorted((dg / "feedback-relpath-attempt").rglob("*")):
        rel = f.relative_to(dg / "feedback-relpath-attempt")
        if f.is_file() and (rel.parts[0] in ("browser", "gtk") and ("logs" in rel.parts or f.name in ("blocks.jsonl", "plan.json"))):
            put(f, raw / "diag" / "feedback-relpath-attempt" / rel)
    dlines = [x for x in Path(a.quiet_ledger).read_text().splitlines() if '"label":"ar-20261002-cal2diag-' in x]
    (raw / "diag" / "quiet-lane-receipts-diag.jsonl").write_text("\n".join(dlines) + "\n")
    for f in sorted((D / "requests").glob("*.json")):
        put(f, raw / "requests" / f.name)
    for f in sorted((D / "g1").glob("*")):
        if f.suffix in (".jsonl", ".out", ".log") and f.name != "g1-all.out":
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
            if f.is_file() and (rel.parts[0] in ("raw", "logs") or f.name in ("plan.json", "blocks.jsonl")):
                put(f, raw / "feedback" / kind / rel, gz=(rel.parts[0] == "raw"))
    lines = [x for x in Path(a.quiet_ledger).read_text().splitlines()
             if '"label":"ar-20261002-cal2-' in x or '"label":"cal2-feedback-' in x]
    (raw / "quiet-lane-receipts.jsonl").write_text("\n".join(lines) + "\n")
    tools = P / "tools"
    if tools.exists():
        shutil.rmtree(tools)
    for f in sorted((D / "tools").glob("*")):
        if f.is_file() and f.suffix in (".py", ".sh") and f.name != "verify_artifacts.py":
            put(f, tools / f.name)
    cands = P / "candidates"
    if cands.exists():
        shutil.rmtree(cands)
    cands.mkdir(parents=True)
    refs = subprocess.run(["git", "-C", a.repo, "for-each-ref", "--format=%(refname:short) %(objectname)",
                           "refs/heads/ar/calib2/"], capture_output=True, text=True, check=True).stdout.split("\n")
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

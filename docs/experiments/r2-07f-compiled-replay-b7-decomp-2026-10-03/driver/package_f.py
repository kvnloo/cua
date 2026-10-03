"""Package the lane's run outputs into the packet raw/ layout (run under hostless).

usage: python package_f.py --src <run root> --dst <packet>/raw --blocks <srcdir>=<block>,...
       [--ledger <lane lock ledger>] [--global-ledger <quiet-lane ledger>] [--unit <file>]... [--ident <file>]...

Uses the R2-07c harness/package_raw.py (bundle + privacy scan) and the R2-07d driver/package_d.py ``clean``
(drops private-session noise lines) unchanged, by import. Per block: <block>-trials.tar.gz, <block>-manifests/,
<block>-routines/, artifacts/<block>-artifact-*.json, <block>-load-gate.jsonl, <block>-progress-*.json,
<block>-chunk-logs/ and <block>-loop.log. Lock receipts: the lane ledger, and the quiet-lane ledger lines whose
label starts with "r207f-". Every text file is privacy-scanned; any hit aborts packaging.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path[:0] = [str(EXP / "r2-07c-toggle-modal-compiled-2026-10-03" / "harness"),
                str(EXP / "r2-07d-quiet-timing-phase-l-2026-10-03" / "driver")]
import package_raw as pr  # noqa: E402
import package_d as pd  # noqa: E402


def copy_text(src: Path, dst: Path, clean: bool = False) -> None:
    text = src.read_text()
    if clean:
        text = pd.clean(text, src.name)
    pr.scan(text, src.name)
    dst.write_text(text)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--dst", required=True)
    p.add_argument("--blocks", required=True)
    p.add_argument("--ledger")
    p.add_argument("--global-ledger")
    p.add_argument("--unit", action="append", default=[])
    p.add_argument("--ident", action="append", default=[])
    a = p.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "artifacts").mkdir(exist_ok=True)
    report: dict[str, object] = {"blocks": {}}
    for item in a.blocks.split(","):
        sname, bname = item.split("=")
        bdir = src / sname
        if not bdir.exists():
            continue
        entry: dict[str, list[str] | int] = {"trial_files": pr.bundle(bdir, dst / f"{bname}-trials.tar.gz"),
                                             "manifests": [], "routines": [], "artifacts": [], "extra": []}
        for sub, pattern, key in (("manifests", "run-manifest-*.json", "manifests"),):
            d = dst / f"{bname}-{sub}"
            d.mkdir(exist_ok=True)
            for f in sorted(bdir.glob(pattern)):
                copy_text(f, d / f.name)
                entry[key].append(f.name)
        if (bdir / "routines").exists():
            d = dst / f"{bname}-routines"
            d.mkdir(exist_ok=True)
            for f in sorted((bdir / "routines").glob("*.json")):
                copy_text(f, d / f.name)
                entry["routines"].append(f.name)
        for f in sorted(bdir.glob("artifact-*.json")):
            copy_text(f, dst / "artifacts" / f"{bname}-{f.name}")
            entry["artifacts"].append(f"{bname}-{f.name}")
        for f in sorted(bdir.glob("progress-*.json")) + [bdir / "load-gate.jsonl"]:
            if f.exists():
                copy_text(f, dst / f"{bname}-{f.name}")
                entry["extra"].append(f"{bname}-{f.name}")
        if (bdir / "loop.log").exists():
            copy_text(bdir / "loop.log", dst / f"{bname}-loop.log", clean=True)
            entry["extra"].append(f"{bname}-loop.log")
        logs = sorted(bdir.glob("chunk-*.log"))
        if logs:
            d = dst / f"{bname}-chunk-logs"
            d.mkdir(exist_ok=True)
            for f in logs:
                copy_text(f, d / f.name, clean=True)
                entry["extra"].append(f"{bname}-chunk-logs/{f.name}")
        report["blocks"][bname] = entry
    if a.unit:
        d = dst / "unit"
        d.mkdir(exist_ok=True)
        for u in a.unit:
            copy_text(Path(u), d / Path(u).name, clean=True)
    if a.ident:
        d = dst / "ident"
        d.mkdir(exist_ok=True)
        for u in a.ident:
            copy_text(Path(u), d / Path(u).name)
    if a.ledger and Path(a.ledger).exists():
        copy_text(Path(a.ledger), dst / "lock-receipts-lane.jsonl")
    if a.global_ledger and Path(a.global_ledger).exists():
        lines = [x for x in Path(a.global_ledger).read_text().splitlines()
                 if x.strip() and json.loads(x).get("label", "").startswith("r207f-")]
        text = "\n".join(lines) + "\n"
        pr.scan(text, "global ledger")
        (dst / "lock-receipts-global.jsonl").write_text(text)
    report["dropped_noise_lines"] = pd.DROPPED
    (dst / "package-report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: (v if k != "blocks" else {b: e["trial_files"] for b, e in v.items()}) for k, v in report.items()
                      if k != "dropped_noise_lines"}))


if __name__ == "__main__":
    main()

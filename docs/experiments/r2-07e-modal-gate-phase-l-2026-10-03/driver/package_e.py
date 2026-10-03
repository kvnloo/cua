"""Package the lane's run outputs into the packet raw/ layout (run under hostless).

usage: python package_e.py --src <run root> --dst <packet>/raw --blocks <srcdir>=<block>,...
       [--ledger <lane lock ledger>] [--global-ledger <quiet-lane ledger>] [--provider-ledger <file>]
       [--unit <file>]... [--log <file>]...

The R2-07d driver/package_d.py layout and noise filter (``clean``), and the R2-07c harness/package_raw.py
bundle + privacy scan, both imported unchanged. Differences from package_d: global lock receipts are
the lines whose label starts with "R2-07e-"; per-block extras also include live-progress.json; lane
loop logs (--log) are filtered with ``clean`` and kept under raw/loop-logs/. Every text file is
privacy-scanned; any hit aborts packaging.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent / "r2-07d-quiet-timing-phase-l-2026-10-03" / "driver"),
                str(HERE.parent.parent / "r2-07c-toggle-modal-compiled-2026-10-03" / "harness")]
import package_d as pd  # noqa: E402
import package_raw as pr  # noqa: E402

PREFIX = "R2-07e-"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--dst", required=True)
    p.add_argument("--blocks", required=True)
    p.add_argument("--ledger")
    p.add_argument("--global-ledger")
    p.add_argument("--provider-ledger")
    p.add_argument("--unit", action="append", default=[])
    p.add_argument("--log", action="append", default=[])
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
        entry: dict[str, object] = {"trial_files": pr.bundle(bdir, dst / f"{bname}-trials.tar.gz"), "manifests": [],
                                    "routines": [], "artifacts": [], "extra": []}
        d = dst / f"{bname}-manifests"
        d.mkdir(exist_ok=True)
        for f in sorted(bdir.glob("run-manifest-*.json")):
            pr.scan(f.read_text(), f.name)
            shutil.copyfile(f, d / f.name)
            entry["manifests"].append(f.name)
        if (bdir / "routines").exists():
            d = dst / f"{bname}-routines"
            d.mkdir(exist_ok=True)
            for f in sorted((bdir / "routines").glob("*.json")):
                pr.scan(f.read_text(), f.name)
                shutil.copyfile(f, d / f.name)
                entry["routines"].append(f.name)
        for f in sorted(bdir.glob("artifact-*.json")):
            pr.scan(f.read_text(), f.name)
            shutil.copyfile(f, dst / "artifacts" / f"{bname}-{f.name}")
            entry["artifacts"].append(f"{bname}-{f.name}")
        for name, out in (("load-gate.jsonl", f"{bname}-load-gate.jsonl"), ("progress.json", f"{bname}-progress.json"),
                          ("live-progress.json", f"{bname}-live-progress.json")):
            f = bdir / name
            if f.exists():
                text = f.read_text()
                pr.scan(text, name)
                (dst / out).write_text(text)
                entry["extra"].append(out)
        report["blocks"][bname] = entry
    for group, files in (("unit", a.unit), ("loop-logs", a.log)):
        if files:
            d = dst / group
            d.mkdir(exist_ok=True)
            for u in files:
                text = pd.clean(Path(u).read_text(), f"{group}/{Path(u).name}")
                pr.scan(text, Path(u).name)
                (d / Path(u).name).write_text(text)
    if a.ledger and Path(a.ledger).exists():
        text = Path(a.ledger).read_text()
        pr.scan(text, "lane ledger")
        (dst / "lock-receipts-lane.jsonl").write_text(text)
    if a.global_ledger and Path(a.global_ledger).exists():
        lines = [x for x in Path(a.global_ledger).read_text().splitlines()
                 if x.strip() and json.loads(x).get("label", "").startswith(PREFIX)]
        text = "\n".join(lines) + "\n"
        pr.scan(text, "global ledger")
        (dst / "lock-receipts-global.jsonl").write_text(text)
    if a.provider_ledger and Path(a.provider_ledger).exists():
        text = Path(a.provider_ledger).read_text()
        pr.scan(text, "provider ledger")
        (dst / "provider-ledger.jsonl").write_text(text)
    report["dropped_noise_lines"] = pd.DROPPED
    (dst / "package-report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

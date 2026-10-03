#!/usr/bin/env python3
"""Package the lane's run directories into the packet's raw/ (standard library only).

Machine-specific strings never live in this file: every text file copied into raw/ is scrubbed
with the ``--scrub OLD=NEW`` pairs given on the command line at packaging time (lane dir, temp
root, home, host name). Trial bundles are tar.gz files with arcname ``trials/<file>``.

usage: package_raw.py --runs <runs-root> --raw <packet>/raw --scrub OLD=NEW [--scrub ...]
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import shutil
import tarfile
from pathlib import Path

SCRUB: list[tuple[str, str]] = []


def scrub(text: str) -> str:
    for old, new in SCRUB:
        text = text.replace(old, new)
    return text


def put_text(dst: Path, text: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(scrub(text))


def bundle(src_dirs: list[Path], dst: Path, only_prefix: str | None = None) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with tarfile.open(dst, "w:gz", compresslevel=9) as tar:
        for src in src_dirs:
            if not src.is_dir():
                continue
            for f in sorted(src.glob("*.jsonl")):
                if only_prefix and not f.name.startswith(only_prefix):
                    continue
                data = scrub(f.read_text()).encode()
                info = tarfile.TarInfo(name=f"trials/{f.name}")
                info.size = len(data)
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
                n += 1
    return n


def copy_jsonl_gz(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dst, "wt", encoding="utf-8") as out:
        out.write(scrub(src.read_text()))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", required=True)
    p.add_argument("--raw", required=True)
    p.add_argument("--scrub", action="append", default=[])
    p.add_argument("--lane-ledger", required=True)
    p.add_argument("--global-ledger", required=True)
    args = p.parse_args()
    for pair in args.scrub:
        old, new = pair.split("=", 1)
        SCRUB.append((old, new))
    SCRUB.sort(key=lambda kv: -len(kv[0]))
    runs, raw = Path(args.runs), Path(args.raw)
    report: dict[str, object] = {}
    m = runs / "m"
    # browser measured layers + controls
    for layer in ("scripted", "live", "controls"):
        d = m / layer
        if not d.is_dir():
            continue
        report[f"browser/{layer}"] = bundle([d / "trials"], raw / "browser" / f"{layer}-trials.tar.gz")
        for f in sorted(d.glob("run-manifest-*.json")):
            put_text(raw / "browser" / f"{layer}-manifests" / f.name, f.read_text())
        for f in sorted((d / "routines").glob("*.json")) if (d / "routines").is_dir() else []:
            put_text(raw / "browser" / f"{layer}-routines" / f.name, f.read_text())
    # native measured blocks
    for d in sorted(m.glob("native-*")):
        src = d / "raw" / "trials.jsonl"
        if src.exists():
            copy_jsonl_gz(src, raw / "native" / d.name.removeprefix("native-") / "trials.jsonl.gz")
            report[f"native/{d.name}"] = sum(1 for _ in src.open())
    # R2-10R drift row D1 (and its pre-PREREG shakedown d1k)
    for d in sorted(m.glob("drift-*")):
        src = d / "raw" / "trials.jsonl"
        if src.exists():
            copy_jsonl_gz(src, raw / "drift" / d.name.removeprefix("drift-") / "trials.jsonl.gz")
            report[f"drift/{d.name}"] = sum(1 for _ in src.open())
    for d in sorted(runs.glob("d1k*")):
        if (d / "raw" / "trials.jsonl").exists():
            copy_jsonl_gz(d / "raw" / "trials.jsonl", raw / "shakedown" / f"{d.name}-trials.jsonl.gz")
    if (runs / "versions.txt").exists():
        put_text(raw / "provenance" / "versions.txt", (runs / "versions.txt").read_text())
    # phase 0
    p0 = runs / "p0"
    a = runs / "p0a-unit"
    if a.is_dir():
        put_text(raw / "phase0" / "a-unit" / "steps.txt", (a / "steps.txt").read_text())
        put_text(raw / "phase0" / "a-unit" / "env.txt", (a / "env.txt").read_text())
        lines = []
        for name in ("core-browser", "core-phase-trace", "core-tool-schema", "core-snapshot-store"):
            log = (a / f"{name}.log").read_text()
            res = [x for x in log.splitlines() if x.startswith("test result:")]
            lines.append(f"{name}: {res[-1] if res else 'missing'}")
            put_text(raw / "phase0" / "a-unit" / f"{name}-tests.txt",
                     "\n".join(x for x in log.splitlines() if x.startswith("test ")) + "\n")
        for name in ("py-unittest", "py-runner-refusal", "py-guarded-runner"):
            log = (a / f"{name}.log").read_text().splitlines()
            ran = [x for x in log if x.startswith("Ran ")]
            lines.append(f"{name}: {ran[-1] if ran else 'missing'} {log[-1] if log else ''}")
        for name in ("ts-npm-test", "ts-run-refusal"):
            log = (a / f"{name}.log").read_text().splitlines()
            lines.append(f"{name}: " + " ".join(x.strip() for x in log if re.match(r"^# (tests|pass|fail) ", x)))
        put_text(raw / "phase0" / "a-unit" / "test-results.txt", "\n".join(lines) + "\n")
    for lab in ("R", "U"):
        d = p0 / f"b-c1-{lab}"
        if d.is_dir():
            for f in ("cells.jsonl", "validity.json", "end.json"):
                if (d / f).exists():
                    put_text(raw / "phase0" / f"b-c1-{lab}" / f, (d / f).read_text())
            bundle([d / "cells"], raw / "phase0" / f"b-c1-{lab}-cells.tar.gz")
        d = p0 / f"c-nw2-{lab}"
        if d.is_dir():
            report[f"phase0/c-nw2-{lab}"] = bundle([d / "trials"], raw / "phase0" / f"c-nw2-{lab}-trials.tar.gz")
    for lab in ("R", "C"):
        d = p0 / f"d-tools-{lab}"
        if d.is_dir():
            put_text(raw / "phase0" / f"d-tools-{lab}.json", (d / f"D{lab}-toolslist.json").read_text())
            shutil.copyfile(d / f"D{lab}-toolslist-0.json", raw / "phase0" / f"d-tools-{lab}-reply.json")
        d = p0 / f"d-smoke-{lab}"
        if d.is_dir():
            report[f"phase0/d-smoke-{lab}"] = bundle([d / "trials"], raw / "phase0" / f"d-smoke-{lab}-trials.tar.gz")
            man = next(iter(sorted(d.glob("run-manifest-*.json"))), None)
            if man:
                put_text(raw / "phase0" / f"d-smoke-{lab}-manifest.json", man.read_text())
        d = p0 / f"d-native-{lab}"
        if d.is_dir():
            put_text(raw / "phase0" / f"d-native-{lab}" / "trials.jsonl", (d / "raw" / "trials.jsonl").read_text())
            files = sorted((d / "work").glob("*/phase.jsonl"))
            put_text(raw / "phase0" / f"d-native-{lab}" / "phase-files.json",
                     json.dumps({"files": len(files), "nonempty": sum(1 for f in files if f.stat().st_size > 0)}) + "\n")
    d = p0 / "e-train"
    if d.is_dir():
        report["phase0/e-train"] = bundle([d / "trials"], raw / "phase0" / "e-train-trials.tar.gz")
        for f in sorted((d / "routines").glob("*.json")):
            put_text(raw / "phase0" / "e-train-routines" / f.name, f.read_text())
    d = p0 / "e-g5"
    if d.is_dir():
        for f in ("cells.jsonl", "validity.json", "end.json"):
            if (d / f).exists():
                put_text(raw / "phase0" / "e-g5" / f, (d / f).read_text())
        bundle([d / "cells"], raw / "phase0" / "e-g5-cells.tar.gz")
    # shakedowns before the PREREG (disclosed, not analysed)
    for d in sorted(list(runs.glob("shake*")) + list(runs.glob("lshake*"))):
        if d.is_dir():
            report[f"shakedown/{d.name}"] = bundle([d / "trials"], raw / "shakedown" / f"{d.name}-trials.tar.gz")
    for d in sorted(runs.glob("nshake*")):
        if (d / "raw" / "trials.jsonl").exists():
            copy_jsonl_gz(d / "raw" / "trials.jsonl", raw / "shakedown" / f"{d.name}-trials.jsonl.gz")
    # provider ledger, lock receipts, chunk logs
    if (runs / "provider-ledger.jsonl").exists():
        put_text(raw / "provider-ledger.jsonl", (runs / "provider-ledger.jsonl").read_text())
    put_text(raw / "lock-receipts-lane.jsonl", Path(args.lane_ledger).read_text())
    glines = [x for x in Path(args.global_ledger).read_text().splitlines()
              if '"label":"r2-10r-a2-' in x or '"label": "r2-10r-a2-' in x]  # attempt 2 only
    put_text(raw / "lock-receipts-global.jsonl", "\n".join(glines) + "\n")
    # R2-10R attempt 2: failed session-start blocks (display probe rc 97) keep their logs here
    fails = sorted((runs / "failed-sessions").glob("*.log")) if (runs / "failed-sessions").is_dir() else []
    # R2-10R attempt 2: the first S2 acquisition, cut by its own outer timeout after 165 of 192 trials (not
    # analysed; disclosed and summarised in the README; S2 re-run in full as S2r)
    for d in sorted((runs / "interrupted").glob("*/")) if (runs / "interrupted").is_dir() else []:
        report[f"interrupted/{d.name}"] = bundle([d / "trials"], raw / "interrupted" / f"{d.name}-trials.tar.gz")
    fails += sorted((runs / "interrupted").glob("*.log")) if (runs / "interrupted").is_dir() else []
    for f in sorted(list(runs.glob("*.log")) + list(m.glob("*.log")) + list(p0.glob("*.log"))) + fails:
        text = "\n".join(x for x in f.read_text(errors="replace").splitlines() if "WARN" not in x)
        put_text(raw / "logs" / f"{f.parent.name}-{f.name}", text + "\n")
    put_text(raw / "package-report.json", json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()

"""Package the lane's raw outputs into the packet raw/ layout (run under hostless).

usage: python package_raw.py --src <run root with one dir per block> --dst <packet>/raw [--ledger <lane lock ledger>]
       [--global-ledger <quiet-lane ledger>] [--provider-ledger <file>]

Per block dir B: raw/B-trials.tar.gz (trials/*.jsonl incl. Driver traces, deterministic member order and
mtimes), raw/B-manifests/*.json, raw/B-routines/*.json, raw/artifacts/B-<artifact>.json. Lock receipts:
the lane ledger, and the global quiet-lane ledger lines whose label starts with "R2-07c-a2-". Every text
file is scanned for absolute paths, the host name and key-like strings; any hit aborts packaging.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import socket
import tarfile
from pathlib import Path

BAD = [re.compile(p) for p in (r"/mnt/", r"/home/", r"/tmp/", r"x11-session\.[A-Za-z0-9]{6}",r"sk-[A-Za-z0-9]{12,}",
                               r"(?i)bearer\s+[a-z0-9]")]


def scan(text: str, where: str) -> None:
    host = socket.gethostname()
    for p in BAD:
        if p.search(text):
            raise SystemExit(f"privacy: {p.pattern} in {where}")
    if host and re.search(rf"\b{re.escape(host)}\b", text):
        raise SystemExit(f"privacy: host name in {where}")


def bundle(block_dir: Path, out: Path) -> int:
    files = sorted((block_dir / "trials").glob("*.jsonl"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        for f in files:
            data = f.read_bytes()
            scan(data.decode(), f"{block_dir.name}/trials/{f.name}")
            info = tarfile.TarInfo(name=f"trials/{f.name}")
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    out.write_bytes(buf.getvalue())
    return len(files)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--dst", required=True)
    p.add_argument("--blocks", required=True, help="comma list: <srcdir>=<packet block name>")
    p.add_argument("--ledger")
    p.add_argument("--global-ledger")
    p.add_argument("--provider-ledger")
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
        n = bundle(bdir, dst / f"{bname}-trials.tar.gz")
        entry = {"trial_files": n, "manifests": [], "routines": [], "artifacts": []}
        for sub, pattern in (("manifests", "run-manifest-*.json"),):
            d = dst / f"{bname}-{sub}"
            d.mkdir(exist_ok=True)
            for f in sorted(bdir.glob(pattern)):
                scan(f.read_text(), str(f.name))
                shutil.copyfile(f, d / f.name)
                entry["manifests"].append(f.name)
        if (bdir / "routines").exists():
            d = dst / f"{bname}-routines"
            d.mkdir(exist_ok=True)
            for f in sorted((bdir / "routines").glob("*.json")):
                scan(f.read_text(), f.name)
                shutil.copyfile(f, d / f.name)
                entry["routines"].append(f.name)
        for f in sorted(bdir.glob("artifact-*.json")):
            scan(f.read_text(), f.name)
            shutil.copyfile(f, dst / "artifacts" / f"{bname}-{f.name}")
            entry["artifacts"].append(f"{bname}-{f.name}")
        report["blocks"][bname] = entry
    if a.ledger and Path(a.ledger).exists():
        text = Path(a.ledger).read_text()
        scan(text, "lane ledger")
        (dst / "lock-receipts-lane.jsonl").write_text(text)
    if a.global_ledger and Path(a.global_ledger).exists():
        lines = [x for x in Path(a.global_ledger).read_text().splitlines()
                 if x.strip() and json.loads(x).get("label", "").startswith("R2-07c-a2-")]
        text = "\n".join(lines) + "\n"
        scan(text, "global ledger")
        (dst / "lock-receipts-global.jsonl").write_text(text)
    if a.provider_ledger and Path(a.provider_ledger).exists():
        text = Path(a.provider_ledger).read_text()
        scan(text, "provider ledger")
        (dst / "provider-ledger.jsonl").write_text(text)
    (dst / "package-report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

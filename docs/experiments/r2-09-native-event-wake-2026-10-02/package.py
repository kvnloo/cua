#!/usr/bin/env python3
"""R2-09 packaging: copy raw outputs into the packet with local paths, the user
name and the host name scrubbed. stdlib only.

usage: package.py <lane-artifacts-dir> <packet-dir> <lane-tmp-root> <quiet-lane-ledger>
  (no local path is hard-coded: the scrub rules are derived from these arguments,
  the home directory, the user name and the host name at run time)
  <lane-artifacts-dir>/runs/<label>/{raw/trials.jsonl,raw/driver-version.txt,session.log}
  <lane-artifacts-dir>/pilots/<name>/trials.jsonl, pilot-plan-*.json, *.session.log
  <lane-artifacts-dir>/unit/*.txt, <lane-artifacts-dir>/build/build-driver.txt
  the shared quiet-lane ledger lines whose label starts with r2-09-
"""

from __future__ import annotations

import gzip
import os
import re
import socket
import sys
from pathlib import Path

def scrubber(lanes: Path, tmp_root: Path):
    host = socket.gethostname()
    user = os.environ.get("USER") or Path.home().name
    mount_top = "/" + lanes.parts[1] + "/" if len(lanes.parts) > 1 else None
    rules = [
        (re.compile(re.escape(str(lanes))), "<lanes>"),
        (re.compile(re.escape(str(tmp_root))), "<tmp>"),
        (re.compile(re.escape(str(Path.home()))), "<home>"),
        (re.compile("/" + "home" + r"/[A-Za-z0-9_.-]+"), "<home>"),
        (re.compile("/" + "tmp" + r"/dbus-[A-Za-z0-9]+"), "<tmp>/dbus-x"),
    ]
    if mount_top:
        # any other absolute path under the same top-level mount as the lanes dir
        rules.append((re.compile(re.escape(mount_top) + r"[A-Za-z0-9_.-]+"), "<data>"))
    if host:
        rules.append((re.compile(r"\b" + re.escape(host) + r"\b"), "<host>"))
    if user:
        rules.append((re.compile(r"\b" + re.escape(user) + r"\b"), "<user>"))

    def scrub(text: str) -> str:
        for rx, rep in rules:
            text = rx.sub(rep, text)
        return text

    return scrub


def main() -> None:
    src, dst = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    tmp_root, ledger = Path(sys.argv[3]).resolve(), Path(sys.argv[4])
    lanes = src.parents[2]  # <lanes>/artifacts/r2/R2-09
    scrub = scrubber(lanes, tmp_root)
    raw = dst / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    def put_text(path: Path, text: str, gz: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = scrub(text)
        if gz:
            with gzip.GzipFile(filename="", mode="wb", fileobj=open(path, "wb"), mtime=0) as stream:
                stream.write(data.encode())
        else:
            path.write_text(data, encoding="utf-8")

    for run in sorted((src / "runs").glob("r209-*")):
        out = raw / run.name
        trials = run / "raw" / "trials.jsonl"
        if trials.exists():
            put_text(out / "trials.jsonl.gz", trials.read_text(encoding="utf-8"), gz=True)
        ver = run / "raw" / "driver-version.txt"
        if ver.exists():
            put_text(out / "driver-version.txt", ver.read_text(encoding="utf-8"))
        log = run / "session.log"
        if log.exists():
            lines = [x for x in log.read_text(encoding="utf-8", errors="replace").splitlines()
                     if "dbus-daemon[" not in x]
            put_text(out / "session.txt", "\n".join(lines[-80:]) + "\n")
    g = src / "runs" / "groups.jsonl"
    if g.exists():
        put_text(raw / "groups.jsonl", g.read_text(encoding="utf-8"))
    for f in sorted(list((src / "runs").glob("run_all-*.log")) + list((src / "runs").glob("run_group-*.log"))):
        put_text(raw / "run_all" / f.name.replace(".log", ".txt"), f.read_text(encoding="utf-8"))
    pil = src / "pilots"
    for f in sorted(pil.glob("pilot-plan-*.json")):
        put_text(raw / "pilots" / f.name, f.read_text(encoding="utf-8"))
    for d in sorted(p for p in pil.iterdir() if p.is_dir()):
        t = d / "trials.jsonl"
        if t.exists():
            put_text(raw / "pilots" / d.name / "trials.jsonl.gz", t.read_text(encoding="utf-8"), gz=True)
    for f in sorted(pil.glob("*.session.log")):
        lines = [x for x in f.read_text(encoding="utf-8", errors="replace").splitlines() if "dbus-daemon[" not in x]
        put_text(raw / "pilots" / f.name.replace(".session.log", ".session.txt"), "\n".join(lines[-60:]) + "\n")
    for f in sorted((src / "unit").glob("*.txt")):
        lines = [x for x in f.read_text(encoding="utf-8", errors="replace").splitlines() if "dbus-daemon[" not in x]
        put_text(raw / "unit" / f.name, "\n".join(lines) + "\n")
    b = src / "build" / "build-driver.txt"
    if b.exists():
        put_text(raw / "driver-build" / "build-driver.txt", b.read_text(encoding="utf-8"))
    led = [x for x in ledger.read_text(encoding="utf-8").splitlines() if '"label":"r2-09-' in x]
    put_text(raw / "lock-ledger.jsonl", "\n".join(led) + "\n")
    print(f"packaged into {dst}")


if __name__ == "__main__":
    main()

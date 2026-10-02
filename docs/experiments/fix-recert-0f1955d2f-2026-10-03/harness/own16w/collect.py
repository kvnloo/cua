#!/usr/bin/env python3
"""Copy one batch's session outputs into the packet's raw/, sanitised (no local paths, no host name).

usage: collect.py <runs-dir> <packet-dir> <ledger-jsonl> [--host NAME] [--map PREFIX=TOKEN ...]
Layout: <runs>/<MODE>/<BIN>/<ID>/{raw,work,session.log} and <runs>/SW/D1/... ->
        <packet>/raw/<MODE>/<BIN>/<ID>/ and <packet>/raw/SW/D1/.
Kept per session: calls.jsonl, session-env.txt, session.log, phase-*.jsonl.gz, oracle/xrecord.jsonl,
oracle/wayland-capture-lines.log, oracle/dbus-monitor.log.gz. Also the quiet-lane ledger receipts
whose label starts with own16w-.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
from pathlib import Path

# Generic fallbacks; the caller passes the concrete local prefixes with --map PREFIX=TOKEN so that no
# local path is ever written into this file.
SUBS = [
    (re.compile(r"/mnt/[^\s'\"]*"), "<MNT>"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+"), "<HOME>"),
    (re.compile(r"/tmp" + r"/dbus-[A-Za-z0-9]+"), "<TMPDBUS>"),
    (re.compile(r"guid=[0-9a-f]{32}"), "guid=<GUID>"),
    (re.compile(r"\x1b\[[0-9;]*m"), ""),
]
MAPS: list[tuple[str, str]] = []


def sanitize(text: str, host: str | None) -> str:
    for prefix, token in MAPS:
        text = text.replace(prefix, token)
    for pattern, repl in SUBS:
        text = pattern.sub(repl, text)
    if host:
        text = re.sub(re.escape(host), "<HOST>", text)
    return text


def copy_text(src: Path, dst: Path, host: str | None, gz: bool = False) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = sanitize(src.read_text(errors="replace"), host)
    if gz:
        with gzip.open(dst.with_name(dst.name + ".gz"), "wt", encoding="utf-8", compresslevel=9) as stream:
            stream.write(text)
    else:
        dst.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("packet")
    ap.add_argument("ledger")
    ap.add_argument("--host", default=None)
    ap.add_argument("--map", action="append", default=[], help="PREFIX=TOKEN, applied before the fallbacks")
    a = ap.parse_args()
    for item in a.map:
        prefix, token = item.split("=", 1)
        MAPS.append((prefix, token))
    MAPS.sort(key=lambda m: -len(m[0]))
    runs, packet = Path(a.runs), Path(a.packet)
    raw = packet / "raw"
    sessions = sorted(p.parent for p in runs.glob("*/*/*/raw")) + sorted(p.parent for p in runs.glob("*/D*/raw"))
    for s in sessions:
        rel = s.relative_to(runs)
        dst = raw / rel
        if dst.exists():
            shutil.rmtree(dst)
        copy_text(s / "raw" / "calls.jsonl", dst / "calls.jsonl", a.host)
        copy_text(s / "raw" / "session-env.txt", dst / "session-env.txt", a.host)
        copy_text(s / "session.log", dst / "session.log", a.host)
        for phase in sorted((s / "work").glob("phase-*.jsonl")):
            copy_text(phase, dst / phase.name, a.host, gz=True)
        copy_text(s / "raw" / "oracle" / "xrecord.jsonl", dst / "oracle" / "xrecord.jsonl", a.host)
        copy_text(s / "raw" / "oracle" / "wayland-capture-lines.log", dst / "oracle" / "wayland-capture-lines.log", a.host)
        copy_text(s / "raw" / "oracle" / "dbus-monitor.log", dst / "oracle" / "dbus-monitor.log", a.host, gz=True)
        print(f"collected {rel}")
    receipts = [json.loads(x) for x in Path(a.ledger).read_text().splitlines()
                if x.strip() and '"label":"own16w-' in x]
    (raw / "quiet-lane-receipts.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in receipts))
    print(f"receipts {len(receipts)}")


if __name__ == "__main__":
    main()

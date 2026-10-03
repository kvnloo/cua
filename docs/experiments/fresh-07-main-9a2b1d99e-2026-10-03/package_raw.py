#!/usr/bin/env python3
"""FRESH-07: copy lane outputs into the packet's raw/ with machine paths redacted.

usage: package_raw.py <src> <dst> [<src> <dst> ...]
Each <src> is a file or a directory (copied recursively; .gz kept byte-for-byte after redaction of
its decompressed text). Redaction is driven by the environment so no machine path is written in
this file: FRESH07_REDACT is a ';'-separated list of 'prefix=<token>' pairs, applied longest first;
the host name (socket.gethostname()) becomes <host>; /tmp/<name> session paths become <tmp>/<name>.
Exits non-zero if any redaction prefix or the host name still appears in the output.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import socket
import sys
from pathlib import Path


def rules() -> list[tuple[str, str]]:
    pairs = []
    for item in (os.environ.get("FRESH07_REDACT") or "").split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            if k:
                pairs.append((k, v))
    pairs.sort(key=lambda kv: -len(kv[0]))
    return pairs


RULES = rules()
HOST = socket.gethostname()
TMP_RX = re.compile(r"/tmp/([A-Za-z0-9._-]+)")


def redact(text: str) -> str:
    for k, v in RULES:
        text = text.replace(k, v)
    if HOST and len(HOST) >= 3:
        text = re.sub(rf"\b{re.escape(HOST)}\b", "<host>", text)
    return TMP_RX.sub(r"<tmp>/\1", text)


def leaks(text: str) -> list[str]:
    found = [k for k, _ in RULES if k in text]
    if HOST and len(HOST) >= 3 and re.search(rf"\b{re.escape(HOST)}\b", text):
        found.append("<hostname>")
    return found


def copy_one(src: Path, dst: Path) -> list[str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix == ".gz":
        text = gzip.decompress(src.read_bytes()).decode("utf-8", "replace")
        out = redact(text)
        with gzip.GzipFile(dst, "wb", mtime=0) as f:
            f.write(out.encode("utf-8"))
        return leaks(out)
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        shutil.copyfile(src, dst)
        return []
    out = redact(text)
    dst.write_text(out, encoding="utf-8")
    return leaks(out)


def main() -> int:
    args = sys.argv[1:]
    bad = []
    for src_s, dst_s in zip(args[0::2], args[1::2]):
        src, dst = Path(src_s), Path(dst_s)
        files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
        for f in files:
            target = dst if src.is_file() else dst / f.relative_to(src)
            hit = copy_one(f, target)
            if hit:
                bad.append((str(target), hit))
    for target, hit in bad:
        print(f"LEAK {target}: {hit}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

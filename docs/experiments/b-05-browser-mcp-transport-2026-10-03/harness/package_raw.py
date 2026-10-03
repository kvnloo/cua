#!/usr/bin/env python3
"""Package one run directory into raw/browser/<chunk>.tar.gz (deterministic: sorted, mtime 0).

usage: package_raw.py <run-dir> <out.tar.gz>
Includes trials/, frames/, routines/ and run-manifest-*.json. Refuses (exit 3) if any member, after
gzip decoding, contains an absolute home/mount path or a secret-like value.
"""

from __future__ import annotations

import gzip
import io
import re
import sys
import tarfile
from pathlib import Path

BAD = [re.compile(p) for p in (r"/home/[A-Za-z0-9_.-]+/", r"/mnt/[A-Za-z0-9_.-]+/", r"sk-[A-Za-z0-9_-]{20,}",
                               r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    members = sorted(p for p in src.rglob("*") if p.is_file() and (
        p.relative_to(src).parts[0] in ("trials", "frames", "routines") or p.name.startswith("run-manifest-")))
    bad = []
    for p in members:
        data = p.read_bytes()
        text = (gzip.decompress(data) if p.suffix == ".gz" else data).decode("utf-8", "replace")
        for rx in BAD:
            if rx.search(text):
                bad.append(f"{p.relative_to(src)}: {rx.pattern}")
    if bad:
        print("\n".join(bad[:20]), file=sys.stderr)
        sys.exit(3)
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for p in members:
            info = tarfile.TarInfo(str(p.relative_to(src)))
            data = p.read_bytes()
            info.size, info.mtime, info.mode, info.uid, info.gid = len(data), 0, 0o644, 0, 0
            tar.addfile(info, io.BytesIO(data))
    with open(out, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as gz:
            gz.write(buf.getvalue())
    print(f"{out.name}: {len(members)} files, {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()

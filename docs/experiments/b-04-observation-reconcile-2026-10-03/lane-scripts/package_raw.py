"""Package B-04 raw outputs into the packet (standard library only; run under hostless).

    python3 package_raw.py --lane-tmp <lane-tmp>/w4a2-b04 --ledger <locks>/quiet-lane-ledger.jsonl --packet <packet> \
        --scrub <lanes>=<lanes> --scrub <lane-tmp>=<lane-tmp> --scrub <repo>=<repo> --scrub <home>=<home>

- raw/measured-trials.tar.gz: every measured trial file (event log + summary + Driver trace), sorted
  member order, mtime 0, uid/gid 0 (deterministic);
- raw/measured/run-manifest-*.json: measured run manifests;
- raw/pilot-trials.tar.gz + raw/pilot/run-manifest-*.json: the attempt-2 pilot (excluded);
- raw/lock-ledger.jsonl: verbatim quiet-lane ledger lines whose label starts with 'b04a2-';
- raw/logs/*.log: session logs with local path prefixes replaced by placeholders.
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

SCRUB: list[tuple[re.Pattern, str]] = [(re.compile(r"/tmp/dbus-[A-Za-z0-9]+"), "<tmp>/dbus-XXXX")]


def det_tar(files: list[Path], arc_prefix: str, out: Path) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for f in sorted(files, key=lambda p: p.name):
            data = f.read_bytes()
            info = tarfile.TarInfo(f"{arc_prefix}/{f.name}")
            info.size, info.mtime, info.uid, info.gid, info.mode = len(data), 0, 0, 0, 0o644
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    with open(out, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0, compresslevel=9) as gz:
            gz.write(buf.getvalue())


def scrub(text: str) -> str:
    for pat, rep in SCRUB:
        text = pat.sub(rep, text)
    return text


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lane-tmp", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--packet", required=True)
    p.add_argument("--scrub", action="append", default=[],
                   help="PREFIX=PLACEHOLDER; local path prefixes to replace in logs (longest first)")
    a = p.parse_args()
    for item in sorted(a.scrub, key=lambda x: len(x.split("=", 1)[0])):  # insert(0): longest ends up first
        prefix, placeholder = item.split("=", 1)
        SCRUB.insert(0, (re.compile(re.escape(prefix)), placeholder))
    lt, pk = Path(a.lane_tmp), Path(a.packet)
    raw = pk / "raw"
    for sub in ("measured", "pilot", "logs"):
        (raw / sub).mkdir(parents=True, exist_ok=True)
    det_tar(list((lt / "measured" / "trials").glob("*.jsonl")), "trials", raw / "measured-trials.tar.gz")
    for m in sorted((lt / "measured").glob("run-manifest-*.json")):
        shutil.copyfile(m, raw / "measured" / m.name)
    det_tar(list((lt / "pilot" / "trials").glob("*.jsonl")), "trials", raw / "pilot-trials.tar.gz")
    for m in sorted((lt / "pilot").glob("run-manifest-*.json")):
        shutil.copyfile(m, raw / "pilot" / m.name)
    lines = [x for x in Path(a.ledger).read_text().splitlines()
             if x.strip() and json.loads(x).get("label", "").startswith("b04a2-")]
    (raw / "lock-ledger.jsonl").write_text("\n".join(lines) + "\n")
    for log in sorted((lt / "logs").glob("*.log")):
        (raw / "logs" / log.name).write_text(scrub(log.read_text(errors="replace")))
    print(json.dumps({"measured_files": len(list((lt / "measured" / "trials").glob("*.jsonl"))),
                      "ledger_lines": len(lines), "logs": len(list((lt / "logs").glob("*.log")))}))


if __name__ == "__main__":
    main()

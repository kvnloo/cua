"""Package B-06 raw outputs into the packet (standard library only; run under hostless).

    python3 package_raw.py --lane-tmp <lane-tmp> --ledger <locks>/quiet-lane-ledger.jsonl --packet <packet> \
        --scrub <path>=<placeholder> [--scrub ...] [--names-file <untracked names file>]

- raw/{main,wn,x,pilot}-trials.tar.gz: every trial file (event log +
  summary + Driver trace), cut attempts included; sorted members, mtime 0, uid/gid 0 (deterministic);
- raw/{main,wn,x,pilot}/run-manifest-*.json: chunk manifests (scrubbed);
- raw/lock-ledger.jsonl: this lane's quiet-lane ledger lines (labels starting b06-), verbatim;
- raw/logs/*.log: session and chunk logs with local paths and private names replaced by placeholders.
Trial files are scrubbed too (paths only) before archiving.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import tarfile
from pathlib import Path

SCRUB: list[tuple[str, str]] = []
NAMES: list[re.Pattern] = []


def scrub(text: str) -> str:
    for a, b in SCRUB:
        text = text.replace(a, b)
    for p in NAMES:
        text = p.sub("<name>", text)
    return text


def det_tar(files: list[Path], arcdir: str, dest: Path) -> int:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for f in sorted(files, key=lambda p: p.name):
            data = scrub(f.read_text(errors="replace")).encode()
            info = tarfile.TarInfo(f"{arcdir}/{f.name}")
            info.size, info.mtime, info.uid, info.gid, info.mode = len(data), 0, 0, 0, 0o644
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    import gzip
    dest.write_bytes(gzip.compress(buf.getvalue(), mtime=0))
    return len(files)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lane-tmp", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--scrub", action="append", default=[])
    ap.add_argument("--names-file")
    a = ap.parse_args()
    for s in a.scrub:
        k, v = s.split("=", 1)
        SCRUB.append((k, v))
    SCRUB.sort(key=lambda kv: -len(kv[0]))
    if a.names_file:
        for n in Path(a.names_file).read_text().splitlines():
            if n.strip():
                NAMES.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(n.strip()) + r"(?![A-Za-z0-9])", re.I))
    lt, pk = Path(a.lane_tmp), Path(a.packet)
    raw = pk / "raw"
    counts = {}
    for plan in ("main", "wn", "x", "pilot"):
        d = lt / plan
        if not (d / "trials").is_dir():
            continue
        (raw / plan).mkdir(parents=True, exist_ok=True)
        counts[plan] = det_tar(list((d / "trials").glob("*.jsonl")), "trials", raw / f"{plan}-trials.tar.gz")
        for m in sorted(d.glob("run-manifest-*.json")):
            (raw / plan / m.name).write_text(scrub(m.read_text()))
    lines = [x for x in Path(a.ledger).read_text().splitlines()
             if x.strip() and json.loads(x).get("label", "").startswith("b06-")]
    (raw / "lock-ledger.jsonl").write_text("\n".join(lines) + "\n")
    (raw / "logs").mkdir(parents=True, exist_ok=True)
    for log in sorted((lt / "logs").glob("*.log")):
        (raw / "logs" / log.name).write_text(scrub(log.read_text(errors="replace")))
    print(json.dumps({"trial_files": counts, "ledger_lines": len(lines),
                      "logs": len(list((lt / "logs").glob("*.log")))}))


if __name__ == "__main__":
    main()

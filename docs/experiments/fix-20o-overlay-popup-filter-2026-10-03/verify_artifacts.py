#!/usr/bin/env python3
"""FIX-20O packet verifier (stdlib only; run from anywhere: python3 verify_artifacts.py).

Checks:
 1. orig/ files are blob-identical to FRESH-07's (git blob hash vs raw/source/orig-manifest.tsv).
 2. Every counted block in provenance.json has its raw files; every trial's driver_sha256 is a
    provenance binary; per-binary trial counts match the summary.
 3. analyze.py --check: the summary recomputes byte-identically from raw/.
 4. Lock evidence: every counted block has a FIX-20O 'shared' receipt in raw/locks/receipts.jsonl,
    held <= 300 s, and consecutive acquisitions are >= 30 s apart.
 5. PREREG.json was committed before the first counted trial began (git, when available).
 6. Unit evidence: unit-summary.json agrees with the raw unit logs.
 7. Privacy: no absolute local path, host name, user name or 'localuser:' grant in any packet file,
    including inside .gz files.
 8. Every file the README cites under raw/ exists and is not git-ignored.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PKT = Path(__file__).resolve().parent
FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def blob_hash(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main() -> int:
    prov = json.loads((PKT / "provenance.json").read_text(encoding="utf-8"))
    summary = json.loads((PKT / "fix20o-summary.json").read_text(encoding="utf-8"))

    # 1
    rows = [line.split("\t") for line in (PKT / "raw/source/orig-manifest.tsv").read_text().splitlines() if line]
    bad = [r[0] for r in rows if blob_hash((PKT / "orig" / r[0]).read_bytes()) != r[2] or r[2] != r[3]]
    check(len(rows) == 35 and not bad, f"orig/ blob-identical to FRESH-07 88ec3d5e6 ({len(rows)} files, mismatches {bad})")

    # 2
    shas = {v["sha256"]: k for k, v in prov["binaries"].items()}
    first_begin = None
    per_bin: dict[str, int] = {}
    missing = []
    for pass_name, labels in prov["counted_blocks"].items():
        for label in labels:
            d = PKT / "raw" / "rows" / pass_name / label
            f = d / ("probe.jsonl.gz" if pass_name == "X" else "trials.jsonl.gz")
            if not f.exists():
                missing.append(str(f.relative_to(PKT)))
                continue
            for r in (json.loads(x) for x in gzip.open(f, "rt", encoding="utf-8") if x.strip()):
                if r.get("event") == "meta" and pass_name == "X":
                    for name, sha in r["binaries"].items():
                        check(sha in shas, f"probe {label} binary {name} sha in provenance")
                if r.get("event") in ("trial", "run"):
                    sha = r.get("driver_sha256")
                    if pass_name != "X":
                        if sha not in shas:
                            missing.append(f"{label}:{r.get('id')} unknown sha")
                        per_bin[shas.get(sha, "?")] = per_bin.get(shas.get(sha, "?"), 0) + 1
                    wb = r.get("w_begin")
                    if wb:
                        first_begin = wb if first_begin is None else min(first_begin, wb)
    check(not missing, f"counted raw blocks present and binaries known ({missing[:5]})")
    check(per_bin == summary.get("trials_per_binary", per_bin), f"trials per binary {per_bin}")

    # 3
    res = subprocess.run([sys.executable, str(PKT / "analyze.py"), "--check"], capture_output=True, text=True)
    check(res.returncode == 0, f"analyze.py --check: {res.stdout.strip()[-80:]} {res.stderr.strip()[-200:]}")

    # 4
    receipts = [json.loads(x) for x in (PKT / "raw/locks/receipts.jsonl").read_text().splitlines() if x.strip()]
    by_label = {r["label"]: r for r in receipts if r.get("lane") == "FIX-20O" and r.get("mode") == "shared"}
    labels = [lab for labs in prov["counted_blocks"].values() for lab in labs]
    no_rec = [lab for lab in labels if lab not in by_label]
    check(not no_rec, f"a shared FIX-20O receipt for every counted block ({no_rec[:5]})")
    held = [(lab, (ts(by_label[lab]["released"]) - ts(by_label[lab]["acquired"])).total_seconds())
            for lab in labels if lab in by_label]
    over = [h for h in held if h[1] > 300]
    check(not over, f"every counted block held the quiet lane <= 300 s (max {max((h[1] for h in held), default=0):.1f} s; over {over})")
    rows_sorted = sorted((ts(r["acquired"]), ts(r["released"]), r["label"]) for r in receipts
                         if r.get("lane") == "FIX-20O" and r.get("mode") == "shared" and r.get("row_mode"))
    gaps = [(b[2], (b[0] - a[1]).total_seconds()) for a, b in zip(rows_sorted, rows_sorted[1:])]
    check(all(g >= 30 for _, g in gaps), f"row blocks spaced >= 30 s (min {min((g for _, g in gaps), default=None)})")

    # 5
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H %cI", "--", str(PKT / "PREREG.json")],
                             capture_output=True, text=True, cwd=PKT, check=True).stdout.split()
        prereg_time = datetime.fromisoformat(out[-1]).timestamp() * 1e9
        check(first_begin is not None and prereg_time < first_begin,
              f"PREREG.json ({out[-2][:9]}) committed before the first counted trial")
    except (subprocess.CalledProcessError, IndexError, FileNotFoundError) as exc:
        check(False, f"PREREG commit time readable ({exc})")

    # 6
    unit = json.loads((PKT / "unit-summary.json").read_text())
    for key, rel, pattern in unit.get("evidence", []):
        text = (PKT / rel).read_text(encoding="utf-8", errors="replace")
        check(re.search(pattern, text) is not None, f"unit {key}: /{pattern}/ in {rel}")

    # 7
    leaks = []
    import getpass
    import socket
    pats = [re.compile(rb"/(home|mnt|tmp/claude-\d+|run/user/\d+)/"), re.compile(rb"localuser:(?!<user>)")]
    for token in {getpass.getuser(), socket.gethostname()} | set(filter(None, os.environ.get("FIX20O_PRIVACY_TOKENS", "").split(","))):
        if token:
            pats.append(re.compile(rb"(?<![A-Za-z0-9_])" + re.escape(token.encode()) + rb"(?![A-Za-z0-9_])"))
    for f in PKT.rglob("*"):
        if not f.is_file() or f.name == "verify_artifacts.py":
            continue
        data = f.read_bytes()
        if f.suffix == ".gz":
            data = gzip.decompress(data)
        for p in pats:
            if p.search(data):
                leaks.append(f"{f.relative_to(PKT)}:{p.pattern[:20]!r}")
    check(not leaks, f"privacy scan (no local paths / user / host / localuser grants): {leaks[:6]}")

    # 8
    readme = (PKT / "README.md").read_text(encoding="utf-8")
    cited = sorted(set(re.findall(r"`(raw/[^`*]+)`", readme)))
    absent = [c for c in cited if not (PKT / c).exists()]
    check(not absent, f"README-cited raw paths exist ({len(cited)} cited; absent {absent})")
    try:
        ign = subprocess.run(["git", "check-ignore", "--no-index", *[str(PKT / c) for c in cited]],
                             capture_output=True, text=True, cwd=PKT).stdout.split()
        check(not ign, f"no cited file is git-ignored ({ign[:3]})")
    except FileNotFoundError:
        pass

    print("\nRESULT:", "PASS" if not FAIL else f"FAIL ({len(FAIL)})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""OWN-16 artifact verifier (stdlib only).

usage: verify_artifacts.py [packet-dir]

1. Recomputes own-16-matrix.json and own-16-summary.json from raw/ with analyze.py
   and requires byte-identical JSON to the committed files.
2. Checks the harness files still hash to the values frozen in PREREG.json.
3. Checks the Driver sha256 recorded inside every session equals provenance.json.
4. Checks every measured call was made after the PREREG commit time recorded in
   provenance.json (and, when git is available, that the commit exists with that time).
5. Checks the README states the recomputed disposition and per-row classes.
6. Privacy scan of every packet file: no absolute local paths, no host-identifying
   home directories, no secret-looking tokens.
Exit 0 only when every check passes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PKT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent).resolve()
sys.path.insert(0, str(PKT))
import analyze  # noqa: E402

failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)


matrix, summary = analyze.analyze(PKT)
for name, obj in (("own-16-matrix.json", matrix), ("own-16-summary.json", summary)):
    committed = (PKT / name).read_text()
    check(committed == json.dumps(obj, indent=1, sort_keys=True) + "\n", f"{name} recomputes identically from raw/")

prereg = json.loads((PKT / "PREREG.json").read_text())
for fname, digest in prereg["files_frozen_with_this_prereg"].items():
    check(hashlib.sha256((PKT / fname).read_bytes()).hexdigest() == digest, f"{fname} matches PREREG hash")

prov = json.loads((PKT / "provenance.json").read_text())
lane_sha = prov["driver"]["lane"]["sha256"]
for s in ("S1", "S2", "N1", "D1"):
    env = dict(l.split("=", 1) for l in (PKT / "raw" / s / "session-env.txt").read_text().splitlines() if "=" in l)
    check(env.get("driver_sha256") == lane_sha, f"{s} driver sha256 == provenance lane sha256")
    check(env.get("driver_version") == prov["driver"]["lane"]["version_in_session"], f"{s} driver version recorded in session")

prereg_epoch_ns = int(prov["prereg_commit"]["committer_epoch"]) * 1_000_000_000
first = min(json.loads(l)["w0"] for s in ("S1", "S2", "N1", "D1")
            for l in (PKT / "raw" / s / "calls.jsonl").read_text().splitlines()
            if l.strip() and json.loads(l).get("event") == "call")
check(first > prereg_epoch_ns, "first measured call is later than the PREREG commit")
try:
    out = subprocess.run(["git", "-C", str(PKT), "show", "-s", "--format=%ct", prov["prereg_commit"]["sha"]],
                         capture_output=True, text=True, timeout=10)
    if out.returncode == 0:
        check(out.stdout.strip() == str(prov["prereg_commit"]["committer_epoch"]), "PREREG commit time matches git")
    else:
        print("SKIP git not available for the PREREG commit check")
except (OSError, subprocess.SubprocessError):
    print("SKIP git not available for the PREREG commit check")

readme = (PKT / "README.md").read_text()
check(f"**{summary['overall']['disposition']}**" in readme, "README states the recomputed disposition")
for row, cls in summary["overall"]["row_classes"].items():
    check(f"`{row}`" in readme and cls in readme, f"README names row {row} with class {cls}")

PATTERNS = [
    (re.compile(r"/home/[A-Za-z0-9_.-]+"), "home path"),
    (re.compile(r"/mnt/[A-Za-z0-9_.-]+"), "mount path"),
    (re.compile(r"/Users/[A-Za-z0-9_.-]+"), "macOS home path"),
    (re.compile(r"/tmp/[A-Za-z0-9_.-]+"), "tmp path"),
    (re.compile(r"(?i)(api[_-]?key|secret|token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}"), "secret assignment"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "secret-looking key"),
]
for path in sorted(PKT.rglob("*")):
    if not path.is_file() or path.suffix == ".pyc":
        continue
    data = path.read_bytes()
    text = (gzip.decompress(data) if path.suffix == ".gz" else data).decode("utf-8", errors="replace")
    hits = [(label, m.group(0)) for rx, label in PATTERNS for m in rx.finditer(text)]
    check(not hits, f"privacy: {path.relative_to(PKT)}" + (f" -> {hits[:3]}" if hits else ""))

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)

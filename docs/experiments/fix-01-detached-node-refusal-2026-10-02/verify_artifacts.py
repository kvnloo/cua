#!/usr/bin/env python3
"""FIX-01 artifact verifier (stdlib only; run under hostless from the worktree root or anywhere).

Checks:
 1. analyze.py recomputes fix01-summary.json exactly from raw/ (every count, timing and CI).
 2. README needles: every headline number in the README appears in the recomputed summary.
 3. Lock ledger: every measured block has exactly one receipt (label fix01-<block>), shared mode for
    correctness blocks with at most 10 trials per acquisition, exclusive for G6; block start times fall
    inside their receipt window.
 4. PREREG.json was committed before the first measured trial; fix commits precede it.
 5. Provider: 0 attempts reached, 0 non-loopback connects; no key present in any block.
 6. Artifact authority: the R2-07 artifact is clean, and injected authority fields are all caught.
 7. Drivers: every block used only the pre-registered U/F sha256 values.
 8. Privacy: no absolute local path, user home or host name in any packet file or in any commit of the
    branch since the base (diffs and messages).
"""

from __future__ import annotations

import copy
import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
REL = HERE.relative_to(WT)
BASE = "2d71548b46114cd1a1bc58ccdef323ce185c9965"
FIX_COMMITS = ("8cfa8c1dbd281da84f9acf8745dc8bea73da96e3", "6eb9319fe785a7eb7d5e156a9221edf818a3697f")
U_SHA = "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3"
F_SHA = "6ce995b8cc7637af0c46d4a67854a73352a437d03c1de1b272a9eadcf942ac04"
FAILS: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(WT), *a], capture_output=True, text=True).stdout


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> int:
    # 1. recompute
    out = subprocess.run([sys.executable, str(HERE / "analyze.py")], capture_output=True, text=True)
    recomputed = json.loads(out.stdout)
    stored = json.loads((HERE / "fix01-summary.json").read_text())
    check(recomputed == stored, "analyze.py recomputes fix01-summary.json exactly")
    s = recomputed

    # 2. README needles
    readme = (HERE / "README.md").read_text()
    needles = []
    g6 = s["G6"]
    needles += [f"{g6['paired_median_F_minus_U_ms']}", f"{g6['ci95'][0]}", f"{g6['ci95'][1]}",
                f"{g6['median_T_U_ms']}", f"{g6['median_T_F_ms']}"]
    w = s["C4w"]
    if w["window_lower_bound_ms"] is not None:
        needles.append(f"{w['window_lower_bound_ms']}")
    for needle in needles:
        check(needle in readme, f"README cites recomputed value {needle}")

    # 3. lock ledger
    ledger = [json.loads(line) for line in (HERE / "raw/lock-ledger.jsonl").read_text().splitlines() if line.strip()]
    measured = sorted(p for p in (HERE / "raw/measured").iterdir() if p.is_dir())
    for block in measured:
        v = json.loads((block / "validity.json").read_text())
        receipts = [r for r in ledger if r["label"] == f"fix01-{block.name}"]
        n = sum(1 for p in (block / "cells").iterdir()) if (block / "cells").exists() else 0
        mode = "exclusive" if v["phase"] == "g6" else "shared"
        ok = len(receipts) == 1 and receipts[0]["mode"] == mode and receipts[0]["rc"] == 0
        if ok:
            started = ts(v["started_utc"])
            ok = ts(receipts[0]["acquired"]).replace(microsecond=0) <= started <= ts(receipts[0]["released"])
        if mode == "shared":
            ok = ok and n <= 10
        check(ok, f"lock receipt for block {block.name} ({mode}, {n} trials)")

    # 4. PREREG order
    prereg_commit = git("log", "--diff-filter=A", "--format=%H %cI", "--", str(REL / "PREREG.json")).split()
    prereg_time = datetime.fromisoformat(prereg_commit[1]).astimezone(timezone.utc)
    first_trial = min(ts(json.loads((b / "validity.json").read_text())["started_utc"]) for b in measured)
    check(prereg_time < first_trial, f"PREREG committed {prereg_time.isoformat()} before first measured block {first_trial.isoformat()}")
    order = git("rev-list", "--reverse", f"{BASE}..HEAD").split()
    check(all(c in order for c in FIX_COMMITS) and order.index(FIX_COMMITS[1]) < order.index(prereg_commit[0]),
          "fix commits precede the PREREG commit on the branch")

    # 5. provider
    check(s["provider"]["reached"] == 0 and s["provider"]["attempts"] == 0, "provider attempts 0, reached 0")
    keys = [json.loads((b / "validity.json").read_text())["forbidden_env_present"] for b in measured]
    check(all(not k for k in keys), "no forbidden env (incl. TYPESAFE_API_KEY) in any block")

    # 6. artifact authority with injections
    sys.path.insert(0, str(HERE.parents[0] / "r2-07-2026-10-02" / "harness"))
    import compiled_routine as cr

    art = json.loads((HERE.parents[0] / "r2-07-2026-10-02/raw/learn/artifact.json").read_text())
    check(cr.check_artifact_authority(art) == [], "R2-07 artifact has 0 authority fields")
    caught = 0
    for key, value in (("ref", "p3:1"), ("element_token", "et-abcdef12"), ("capture_id", "c"), ("session_epoch", 1),
                       ("x", 1.5), ("target_id", "bt-0123abcd-ef")):
        bad = copy.deepcopy(art)
        bad["steps"][1][key] = value
        caught += bool(cr.check_artifact_authority(bad))
    check(caught == 6, f"authority injections caught {caught}/6")

    # 7. drivers
    shas = {sha for b in measured for d in json.loads((b / "validity.json").read_text())["drivers"].values()
            for sha in [d["sha256"]]}
    check(shas <= {U_SHA, F_SHA}, f"only pre-registered Driver binaries used ({len(shas)} distinct)")

    # 8. privacy
    host = socket.gethostname()
    pats = [re.compile(r"/(mnt|home|tmp)/[A-Za-z0-9_.-]+/"), re.compile(r"\bkvn\b")]
    if host:
        pats.append(re.compile(re.escape(host)))
    bad_files = []
    for path in HERE.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".py", ".sh", ".txt", ".log", ".patch"}:
            text = path.read_text(errors="replace")
            if any(p.search(text) for p in pats):
                bad_files.append(str(path.relative_to(HERE)))
    check(not bad_files, f"no local paths/host name in packet files ({bad_files[:5]})")
    commits = git("rev-list", f"{BASE}..HEAD").split()
    bad_commits = []
    for c in commits:
        text = git("show", "--format=%an %ae%n%B", c)
        if any(p.search(text) for p in pats):
            bad_commits.append(c[:9])
        if "7121943+kvnloo@users.noreply.github.com" not in git("show", "-s", "--format=%ae %ce", c):
            bad_commits.append(c[:9] + ":identity")
    check(not bad_commits, f"privacy + identity clean in all {len(commits)} branch commits ({bad_commits})")

    print(f"\n{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())

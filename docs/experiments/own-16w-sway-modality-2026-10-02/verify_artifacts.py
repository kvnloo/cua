#!/usr/bin/env python3
"""OWN-16W packet verifier (stdlib only).

Checks:
  1. own-16w-summary.json equals a fresh recomputation from raw/ (analyze.py).
  2. Files frozen with PREREG.json still have their recorded sha256.
  3. Every session's in-session Driver sha256 / version matches PREREG's U / F binaries.
  4. PREREG was committed before the first measured call (provenance prereg_commit_utc < min call
     time; with git available, the commit's own timestamp is checked too).
  5. Every session ran under quiet-timed: a receipt (label own16w-<MODE>-<BIN>-<ID>, rc 0) whose
     [acquired, released] window contains every call of that session.
  6. README's disposition lines match the summary's per-mode dispositions.
  7. Privacy: no absolute local paths, no host name (when --host is given), no secret-like strings
     in any packet file, gzip members included.
Prints RESULT PASS / RESULT FAIL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_any(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
            return stream.read()
    return path.read_text(errors="replace")


def iso(ts: str) -> int:
    return int(dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1e9)


def sessions(raw: Path) -> list[Path]:
    return sorted(p.parent for p in raw.rglob("calls.jsonl"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None, help="host name to scan for (never stored in the packet)")
    a = ap.parse_args()
    raw = HERE / "raw"
    prereg = json.loads((HERE / "PREREG.json").read_text())
    prov = json.loads((HERE / "provenance.json").read_text())

    # 1. summary recomputation
    out = subprocess.run([sys.executable, str(HERE / "analyze.py"), "--packet", str(HERE)],
                         capture_output=True, text=True, check=False)
    committed = json.loads((HERE / "own-16w-summary.json").read_text())
    check(out.returncode == 0 and json.loads(out.stdout) == committed, "summary recomputes from raw/ exactly")

    # 1b. pre-registered n: 42 counted calls per row, mode and binary (2 sessions x 21), 0 exceptions
    for mode, m in committed["modes"].items():
        for binary, rows in m["rows"].items():
            for row, ent in rows.items():
                p = ent["pooled"]
                check(p["n"] == 42 and p["exceptions"] == 0 and p["oracle_windows"] == 42,
                      f"{mode} {binary} {row}: n={p['n']} exceptions={p['exceptions']} oracle_windows={p['oracle_windows']}")

    # 2. frozen files
    deviated = prov.get("frozen_file_deviations", {})
    for name, digest in prereg["files_frozen_with_this_prereg"].items():
        now = sha(HERE / name) if (HERE / name).exists() else None
        if name in deviated:
            dev = deviated[name]
            check(dev["prereg_sha256"] == digest and now == dev["final_sha256"] and (HERE / dev["diff"]).exists()
                  and dev["readme_ref"] in (HERE / "README.md").read_text(),
                  f"frozen {name}: changed only as disclosed ({dev['readme_ref']}, {dev['diff']})")
        else:
            check(now == digest, f"frozen {name} sha256 matches PREREG")

    # 3. in-session binaries
    want = {"U": prereg["binaries"]["U"]["sha256"], "F": prereg["binaries"]["F"]["sha256"]}
    for s in sessions(raw):
        env = dict(line.split("=", 1) for line in (s / "session-env.txt").read_text().splitlines() if "=" in line)
        rel = s.relative_to(raw).parts
        binary = "U" if rel[-1].startswith("D") else rel[1]
        check(env.get("driver_sha256") == want[binary] and env.get("driver_version", "").startswith("cua-driver 0.32.0"),
              f"{'/'.join(rel)}: in-session Driver is {binary} ({env.get('driver_version')})")

    # 4. PREREG before trials
    first_ns = min(json.loads(line)["w0"] for s in sessions(raw) for line in (s / "calls.jsonl").read_text().splitlines()
                   if line.strip() and json.loads(line).get("event") == "call")
    check(iso(prov["prereg_commit_utc"]) < first_ns, "PREREG committed before the first measured call (provenance)")
    try:
        ct = subprocess.run(["git", "-C", str(HERE), "show", "-s", "--format=%ct", prov["prereg_commit"]],
                            capture_output=True, text=True, check=True).stdout.strip()
        check(int(ct) * 10**9 < first_ns, "PREREG commit timestamp precedes the first measured call (git)")
    except (subprocess.SubprocessError, OSError, ValueError):
        print("skip git check of the PREREG commit (git or commit unavailable)")

    # 5. quiet-lane receipts
    receipts = [json.loads(x) for x in (raw / "quiet-lane-receipts.jsonl").read_text().splitlines() if x.strip()]
    for s in sessions(raw):
        rel = s.relative_to(raw).parts
        label = "own16w-" + "-".join(rel)
        calls = [json.loads(x) for x in (s / "calls.jsonl").read_text().splitlines() if x.strip()]
        calls = [c for c in calls if c.get("event") == "call"]
        rec = [r for r in receipts if r["label"] == label and r["rc"] == 0]
        inside = bool(rec) and all(any(iso(r["acquired"]) <= c["w0"] and c["w1"] <= iso(r["released"]) for r in rec)
                                   for c in calls)
        check(inside, f"{label}: {len(calls)} calls inside an rc-0 quiet-timed receipt")

    # 6. README dispositions
    readme = (HERE / "README.md").read_text()
    for mode, m in committed["modes"].items():
        token = f"<!-- disposition {mode}: {m['disposition']['disposition']} -->"
        check(token in readme, f"README carries {token}")

    # 7. privacy
    patterns = [re.compile(r"/mnt/[A-Za-z0-9]"), re.compile(r"/home/[a-z]"), re.compile(r"/tmp/[A-Za-z]"),
                re.compile(r"/run/user/"), re.compile(r"sk-[A-Za-z0-9]{16,}"), re.compile(r"(?i)api[_-]?key\s*[=:]\s*\S{8,}"),
                re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}")]
    if a.host:
        patterns.append(re.compile(re.escape(a.host)))
    hits = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or path.name == "verify_artifacts.py":
            continue
        text = read_any(path)
        for p in patterns:
            if p.search(text):
                hits.append(f"{path.relative_to(HERE)}: {p.pattern}")
    check(not hits, f"privacy scan clean ({len(hits)} hits){': ' + '; '.join(hits[:5]) if hits else ''}")

    print("RESULT " + ("PASS" if not FAILS else f"FAIL ({len(FAILS)})"))
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()

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
  8. Completeness: every raw file the README cites (concrete `raw/...` paths) and every per-session
     file the README's Files list promises exists (session.log, session-env.txt, phase trace, and for
     truth sessions the oracle logs). With git available, no packet file is git-ignored and untracked.
  9. Raw compositor oracle: for every S-W / S-X truth session, the capture requests in
     oracle/wayland-capture-lines.log are re-attributed to the recorded call / idle windows (same
     grace rule as the harness) and must equal each window's wl_capture_requests and the session's
     wl_capture_requests_total, with 0 outside any call window. Omitted-screenshot rows must be 0.
 10. Per-session timing: the per-session median paired differences printed in README match raw/.
Prints RESULT PASS / RESULT FAIL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILS: list[str] = []
# Same capture-request signatures, line format and grace as the harness (modality_truth.py).
WL_CAPTURE_REQ = re.compile(
    r"^(zwlr_screencopy_manager_v1\.capture_output(_region)?"
    r"|ext_image_copy_capture_manager_v1\.create_session"
    r"|ext_output_image_capture_source_manager_v1\.create_source"
    r"|ext_foreign_toplevel_image_capture_source_manager_v1\.create_source)$")
WL_LINE = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.(\d{6})\]\s+(->\s+)?([A-Za-z0-9_]+)#(\d+)\.([A-Za-z0-9_]+)\(")
GRACE_NS = 30_000_000
OMIT_SCREENSHOT = {"accessibility_only", "neither"}


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

    # 8. completeness
    readme_paths = sorted(set(re.findall(r"`(raw/[^`<>*\s]+)`", readme)))
    fixed = ["raw/batch.log", "raw/quiet-lane-receipts.jsonl", "raw/unit/unit-red.log", "raw/unit/unit-green.log",
             "raw/unit/unit-all.log", "raw/build/build-u.log", "raw/build/build-f.log",
             "raw/aborted/SX-U-T2/calls.partial.jsonl", "raw/aborted/SX-U-T2/session.log",
             "raw/aborted/SX-U-T2/session-env.txt"]
    missing = [p for p in readme_paths + fixed if not (HERE / p).exists()]
    for s in sessions(raw):
        rel = s.relative_to(raw).parts
        need = ["session.log", "session-env.txt"]
        if not list(s.glob("phase-*.jsonl.gz")):
            missing.append(f"raw/{'/'.join(rel)}/phase-*.jsonl.gz")
        if rel[-1].startswith("T"):
            need += ["oracle/dbus-monitor.log.gz", "oracle/xrecord.jsonl"]
            if rel[0] in ("SW", "SX"):
                need.append("oracle/wayland-capture-lines.log")
        missing += [f"raw/{'/'.join(rel)}/{n}" for n in need if not (s / n).exists()]
    check(not missing, f"every cited / promised raw file is present ({len(readme_paths)} README paths, "
          f"{len(sessions(raw))} sessions){': missing ' + '; '.join(missing[:8]) if missing else ''}")
    try:
        ignored = subprocess.run(["git", "-C", str(HERE), "ls-files", "-o", "-i", "--exclude-standard", "--", "."],
                                 capture_output=True, text=True, check=True).stdout.split()
        check(not ignored, f"no packet file is git-ignored and untracked ({len(ignored)}){': ' + '; '.join(ignored[:5]) if ignored else ''}")
    except (subprocess.SubprocessError, OSError):
        print("skip git-ignore check (not a git checkout)")

    # 9. raw compositor capture log re-attribution
    for s in sessions(raw):
        rel = s.relative_to(raw).parts
        if rel[0] not in ("SW", "SX") or not rel[-1].startswith("T") or not (s / "oracle/wayland-capture-lines.log").exists():
            continue
        recs = [json.loads(x) for x in (s / "calls.jsonl").read_text().splitlines() if x.strip()]
        wins = [r for r in recs if r.get("event") == "oracle_window"]
        summ = next(r for r in recs if r.get("event") == "oracle_summary")
        anchor = min(w["w0"] for w in wins)
        day0 = (anchor // 10**9) // 86400 * 86400
        reqs = []
        for line in (s / "oracle/wayland-capture-lines.log").read_text().splitlines():
            m = WL_LINE.match(line)
            if not m or m.group(5) or not WL_CAPTURE_REQ.match(f"{m.group(6)}.{m.group(8)}"):
                continue
            t = (day0 + int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))) * 10**9 + int(m.group(4)) * 1000
            reqs.append(t + 86400 * 10**9 if t < anchor - 43200 * 10**9 else t)
        bad = []
        for w in wins:
            hi = w["w1"] + (GRACE_NS if w["kind"] == "call" else 0)
            n = sum(1 for t in reqs if w["w0"] <= t <= hi)
            if n != w["wl_capture_requests"] or (w.get("row") in OMIT_SCREENSHOT and n):
                bad.append(f"{w['kind']} {w.get('index')} {w.get('row')}: raw {n} vs {w['wl_capture_requests']}")
        calls_w = [w for w in wins if w["kind"] == "call"]
        outside = sum(1 for t in reqs if not any(w["w0"] <= t <= w["w1"] + GRACE_NS for w in calls_w))
        check(not bad and len(reqs) == summ["wl_capture_requests_total"] and outside == 0
              == summ["wl_capture_requests_unattributed"],
              f"{'/'.join(rel)}: raw compositor log re-attributes to the recorded windows ({len(reqs)} requests, "
              f"{outside} outside calls){': ' + '; '.join(bad[:3]) if bad else ''}")

    # 10. per-session timing medians
    for mode in ("SW", "SX"):
        for comp in ("screenshot_only", "accessibility_only"):
            meds = []
            for sid in ("B1", "B2"):
                timed = [json.loads(x) for x in (raw / mode / "U" / sid / "calls.jsonl").read_text().splitlines() if x.strip()]
                pairs: dict[int, dict[str, float]] = {}
                for r in timed:
                    if r.get("event") == "call" and r.get("phase") == "timed" and r.get("comparison") == comp and "exception" not in r:
                        pairs.setdefault(r["pair"], {})[r["row"]] = r["wall_ms"]
                diffs = [p[comp] - p["both"] for p in pairs.values() if comp in p and "both" in p]
                meds.append(f"{sid} {statistics.median(diffs):.2f} (n={len(diffs)})")
            token = f"<!-- per-session {mode} {comp}: {' / '.join(meds)} -->"
            check(token in readme, f"README carries {token}")

    print("RESULT " + ("PASS" if not FAILS else f"FAIL ({len(FAILS)})"))
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()

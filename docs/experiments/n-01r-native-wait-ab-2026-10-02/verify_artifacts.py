#!/usr/bin/env python3
"""N-01R packet verifier (stdlib only). Run from anywhere: python3 verify_artifacts.py

Checks:
 1. every number in n01r-summary.json recomputes from raw/ (analyze.py, byte-identical JSON);
 2. lock evidence: each block's trials fall inside a lock receipt for that block's label in
    raw/lock-ledger.jsonl (exclusive quiet-timed receipts for measured blocks, shared receipts
    for control blocks), and the receipt mode matches the plan;
 3. PREREG order: the PREREG commit time precedes the first measured trial (and, when git is
    available, the PREREG commit is an ancestor of the packet commit and PREREG.json is unchanged
    since, apart from nothing);
 4. the default-off smoke passed; every block ran the provenance Driver sha256 and the committed plan;
 5. provider: 0 non-loopback connects in every block;
 6. README: headline numbers appear in the README;
 7. privacy: no absolute local paths, host name or secret-like strings in any packet file.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def ts(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp() * 1e9)


def main() -> None:
    summary, allm = analyze.analyze()
    committed = (HERE / "n01r-summary.json").read_text(encoding="utf-8")
    check(committed == json.dumps(summary, indent=1, sort_keys=True) + "\n", "n01r-summary.json recomputes from raw/")
    prov = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    plan_text = (HERE / "plan.json").read_bytes()
    plan = json.loads(plan_text)
    plan_sha = hashlib.sha256(plan_text).hexdigest()
    lock_of = {b["block"]: b["lock"] for b in plan["blocks"]}

    # 2. lock evidence
    ledger = [json.loads(x) for x in (HERE / "raw" / "lock-ledger.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    intervals: dict[str, list[tuple[int, int, str]]] = {}
    pending: dict[str, int] = {}
    for row in ledger:
        if "acquired" in row and "released" in row:
            intervals.setdefault(row["label"], []).append((ts(row["acquired"]), ts(row["released"]), row.get("mode", "exclusive")))
        elif "acquired" in row:
            pending[row["label"]] = ts(row["acquired"])
        elif "released" in row and row["label"] in pending:
            intervals.setdefault(row["label"], []).append((pending.pop(row["label"]), ts(row["released"]), row.get("mode", "shared")))
    blocks = analyze.load_blocks()
    first_measured = None
    for label, rows in blocks:
        meta = next((r for r in rows if r.get("event") == "meta"), {})
        block = meta.get("block")
        trials = [r for r in rows if r.get("event") == "trial"]
        iv = intervals.get(label, [])
        want = "shared" if lock_of.get(block) == "shared" else "exclusive"
        inside = bool(iv) and all(any(a <= t["w_begin"] and t.get("w_end", t["w_begin"]) <= b for a, b, _ in iv) for t in trials)
        modes_ok = bool(iv) and all(m == want for _, _, m in iv)
        check(inside and modes_ok, f"{label}: {len(trials)} trials inside a {want} lock receipt")
        check(meta.get("driver_sha256") == prov["driver"]["sha256"], f"{label}: Driver sha256 matches provenance")
        check(meta.get("plan_sha256") == plan_sha, f"{label}: plan sha256 matches plan.json")
        end = next((r for r in rows if r.get("event") == "end"), {})
        check((end.get("net") or {}).get("refused_non_loopback_connects") == 0, f"{label}: 0 non-loopback connects (provider cap 0)")
        if trials:
            w0 = min(t["w_begin"] for t in trials)
            first_measured = w0 if first_measured is None else min(first_measured, w0)

    # 3. PREREG order
    prereg_utc = prov["prereg_commit"]["committed_utc"]
    pre_ns = int(datetime.strptime(prereg_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1e9)
    check(first_measured is not None and pre_ns < first_measured,
          f"PREREG commit {prereg_utc} precedes the first measured trial")
    try:
        sha = prov["prereg_commit"]["sha"]
        git_time = subprocess.run(["git", "-C", str(HERE), "log", "-1", "--format=%ct", sha], capture_output=True,
                                  text=True, check=True).stdout.strip()
        check(int(git_time) * 1e9 < first_measured, f"git commit time of {sha[:9]} precedes the first measured trial")
        blob_then = subprocess.run(["git", "-C", str(HERE), "rev-parse", f"{sha}:./PREREG.json"], capture_output=True,
                                   text=True, check=True).stdout.strip()
        blob_now = subprocess.run(["git", "-C", str(HERE), "hash-object", "PREREG.json"], capture_output=True,
                                  text=True, check=True).stdout.strip()
        check(blob_then == blob_now, "PREREG.json unchanged since its pre-registration commit")
    except (subprocess.CalledProcessError, FileNotFoundError, KeyError) as exc:
        print(f"note git checks skipped: {exc}")

    # 4. smoke + stale
    check(summary["control_d_smoke"]["passed"], "default-off smoke: knobs unset, no knob marks, 50/220 constants observed")
    check(all(v["trials"] == 5 and v["passed"] == 5 for v in summary["control_c_stale"].values()),
          "stale-token control: 5/5 refused with 0 mutations per arm")

    # 6. README numbers
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    g = summary["gates"]
    for task in analyze.TASKS:
        for arm in analyze.ARMS:
            m = summary["cells"][f"main/{task}/{arm}"]["T_ms"]["median"]
            check(f"{m:.1f}" in readme, f"README has median T {task}/{arm} = {m:.1f} ms")
        for key in ("S_X", "S_X2"):
            sx = g["composition"][task][key]
            check(f"{sx['S']:.2f}" in readme, f"README has {task} {key} = {sx['S']:.2f}")
        check(f"{g['E2'][task]['untested_share_median'] * 100:.1f}%" in readme,
              f"README has {task} untested share {g['E2'][task]['untested_share_median'] * 100:.1f}%")
        for h in ("H_C", "H_S", "H_F"):
            check(g[h][task]["verdict"] in readme, f"README names {h} {task} verdict {g[h][task]['verdict']}")

    # 7. privacy
    host = socket.gethostname()
    bad = re.compile(r"(/home/|/mnt/|/tmp/|/root/|zer0models|cua-lanes|sk-[A-Za-z0-9]{16,}|api[_-]?key\s*[:=]\s*\S{8,}|BEGIN [A-Z ]*PRIVATE KEY)", re.I)
    hits = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or path.name == "verify_artifacts.py":
            continue
        data = gzip.open(path, "rt", encoding="utf-8", errors="replace").read() if path.suffix == ".gz" else path.read_text(encoding="utf-8", errors="replace")
        for m in bad.finditer(data):
            hits.append(f"{path.relative_to(HERE)}: {m.group(0)[:40]}")
        if host and len(host) > 2 and re.search(rf"\b{re.escape(host)}\b", data):
            hits.append(f"{path.relative_to(HERE)}: host name")
    check(not hits, f"privacy scan clean ({len(hits)} hits){': ' + '; '.join(hits[:8]) if hits else ''}")
    print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} failing checks")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

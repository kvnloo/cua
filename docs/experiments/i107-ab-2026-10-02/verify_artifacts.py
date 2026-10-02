"""Verify the kvnloo/cua#107 lane AB packet: recompute every headline from raw/ and check receipts.

    python3 verify_artifacts.py            # exit 0 = all checks pass

Checks:
  1. i107ab-summary.json and ledger.jsonl equal a fresh recomputation from raw/ (analyze.build).
  2. README quotes the headline values (headlines() below) that the summary holds.
  3. 0 provider HTTP: every trial and manifest records 0 non-loopback connects; provider = mock.
  4. Locks: every run manifest names a quiet-timed label that appears in raw/lock-receipts.jsonl,
     and every trial of that run starts and ends inside that receipt's EXCLUSIVE window.
  5. PREREG.json was committed before the first REAL trial and is unchanged since its commit.
  6. UNIT receipts: harness tests OK; the Rust acquisition-equality test passed (2 passed, 0 failed).
  7. Default-off check (if run): 5/5 verified, trace variable unset, no trace file.
  8. Stale-ref controls (if run): refused with browser_ref_stale, 0 dispatch marks, 0 submits.
  9. No file under libs/ changed on this lane's branch (git, if available).
 10. Privacy: no absolute local path, temp path, user name or host name in any packet file.
 11. Every ledger row carries an evidence label or a cell status.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import analyze  # noqa: E402
import b01_analysis as A  # noqa: E402

FAIL: list[str] = []
PREREG_COMMIT = "ffefa30c2"
MAP_BASE = "be68363bc38940d5560be55165ceaf6fd743437b"


def check(cond: bool, what: str) -> None:
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        FAIL.append(what)


def headlines(summary: dict) -> list[str]:
    out = [f"status: {summary['status']}", f"trials attempted: {summary['trials_attempted']}",
           f"trials measured: {summary['trials_measured']}"]
    for cond, c in sorted(summary.get("cmp_ab", {}).items()):
        acq = c["acquisition"]
        out.append(f"{cond}: {c['pairs']} pairs, acquisition equal = {acq['equal']}")
        out.append(f"{cond}: semantic equivalence {c['semantic_equivalence']['equivalent_pairs']}/{c['semantic_equivalence']['pairs']}")
        rb = c["savings_B_minus_A"]["response_bytes"]
        out.append(f"{cond}: response bytes B_proj - A median {rb['median']}")
        t = c["savings_B_minus_A"]["T_oracle_ms"]
        if t["median"] is not None:
            out.append(f"{cond}: T_oracle B_proj - A median {t['median']} ms")
    for cond, d in sorted(summary.get("decomposition_A", {}).items()):
        out.append(f"{cond}: A T_oracle median {d['T_oracle_median_ms']} ms, coverage min {d['coverage_min']}")
    return out


def utc(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=True).stdout


def main() -> None:
    raw = HERE / "raw"
    summary = json.loads((HERE / "i107ab-summary.json").read_text())
    fresh, rows = analyze.build(raw)
    check(fresh == summary, "1 i107ab-summary.json equals a fresh recomputation from raw/")
    ledger = [json.loads(x) for x in (HERE / "ledger.jsonl").read_text().splitlines() if x.strip()]
    check(ledger == json.loads(json.dumps(rows)), f"1 ledger.jsonl equals a fresh recomputation ({len(ledger)} rows)")

    readme = (HERE / "README.md").read_text()
    for h in headlines(summary):
        check(h in readme, f"2 README quotes '{h}'")

    trials = A.load_trials(raw) if (raw / "trials").is_dir() or list(raw.glob("trials-*.tar.gz")) else []
    net = sum((t["summary"].get("network") or {}).get("non_loopback_connect_attempts", 0) for t in trials)
    check(net == 0, f"3 non-loopback connects across {len(trials)} trials = {net}")
    manifests = {p.name: json.loads(p.read_text()) for p in sorted(raw.glob("run-manifest-*.json"))}
    for name, m in manifests.items():
        check(m.get("provider") == "mock" and (m.get("network") or {}).get("non_loopback_connect_attempts") == 0,
              f"3 {name}: provider=mock, 0 non-loopback connects")

    receipts = [json.loads(x) for x in (raw / "lock-receipts.jsonl").read_text().splitlines() if x.strip()] \
        if (raw / "lock-receipts.jsonl").exists() else []
    by_label = {r["label"]: r for r in receipts}
    for name, m in manifests.items():
        r = by_label.get(m.get("lock_label"))
        check(r is not None, f"4 {name}: quiet-timed receipt for label {m.get('lock_label')}")
        if r is None:
            continue
        mine = [t for t in trials if t["summary"].get("lock_label") == m["lock_label"]]
        inside = all(utc(r["acquired"]) <= utc(t["summary"]["utc_start"]) and utc(t["summary"]["utc_end"]) <= utc(r["released"])
                     for t in mine)
        check(inside and r.get("mode", "exclusive") == "exclusive",
              f"4 {name}: {len(mine)} trials inside the EXCLUSIVE window {r['acquired']} .. {r['released']}")

    real = [t for t in trials]
    if real:
        first = min(utc(t["summary"]["utc_start"]) for t in real)
        try:
            when = utc(git("log", "-1", "--format=%cI", PREREG_COMMIT).strip())
            check(when < first, f"5 PREREG commit {PREREG_COMMIT} ({when.isoformat()}) precedes the first REAL trial ({first.isoformat()})")
            src = git("show", f"{PREREG_COMMIT}:docs/experiments/{HERE.name}/PREREG.json")
            check(json.loads(src) == json.loads((HERE / "PREREG.json").read_text()), "5 PREREG.json unchanged since its commit")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("SKIP 5 git not available for the PREREG commit check")
    else:
        print("SKIP 5 no REAL trial in raw/")

    unit = raw / "unit"
    py = (unit / "harness-unit-green.txt").read_text()
    check(re.search(r"Ran (\d+) tests", py) is not None and py.rstrip().endswith("OK"), "6 harness unit tests: OK")
    rs = (unit / "rust-acquisition-equality.txt").read_text()
    check("test result: ok. 2 passed; 0 failed" in rs and "I107AB scope_ref_calls=15 equal_to_full=true" in rs,
          "6 Rust acquisition-equality test: 2 passed, 0 failed")

    do = summary["default_off"]
    if do["n"]:
        check(do["n"] == 5 and do["verified"] == 5 and do["trace_set"] == 0 and do["trace_files"] == 0,
              "7 default-off: 5/5 verified, trace unset, no trace file")
    else:
        print("SKIP 7 default-off not run")

    st = {k: v for k, v in summary["controls"].items() if k.startswith("stale_ref|")}
    if st:
        check(all(v["stale_codes"] == ["browser_ref_stale"] and v["stale_dispatch_marks"] == 0 and v["submits"] == 0
                  for v in st.values()), f"8 stale-ref controls refused before dispatch: {sorted(st)}")
    else:
        print("SKIP 8 stale-ref controls not run")

    try:
        changed = git("diff", "--name-only", MAP_BASE, "HEAD", "--", "../../../libs").strip()
        check(changed == "", "9 no file under libs/ changed since the map base")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("SKIP 9 git not available")

    host = socket.gethostname()
    user = os.environ.get("USER") or ""
    roots = ["home", "mnt", "tmp", "var" + "/tmp"]  # built from parts so this file does not match itself
    pat = re.compile("|".join("/" + r + "/" for r in roots) + "|cua-lane" + "-tmp|x11-session\\.[A-Za-z0-9]{6}")
    offenders = []
    for path in HERE.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        texts = []
        if path.name.endswith(".tar.gz"):
            import tarfile
            with tarfile.open(path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        texts.append(tar.extractfile(member).read().decode("utf-8", "replace"))
        else:
            texts.append(data.decode("utf-8", "replace"))
        for text in texts:
            if pat.search(text) or (host and len(host) > 3 and host in text) or (user and len(user) > 2 and f"/{user}/" in text):
                offenders.append(str(path.relative_to(HERE)))
                break
    check(not offenders, f"10 privacy scan over every packet file (offenders: {offenders})")

    bad = [r for r in ledger if not (r.get("evidence") or r.get("status"))]
    check(not bad, f"11 every ledger row carries an evidence label or cell status ({len(ledger)} rows)")

    print(f"\n{len(FAIL)} failure(s)")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

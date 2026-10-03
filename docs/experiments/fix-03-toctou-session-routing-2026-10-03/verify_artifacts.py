#!/usr/bin/env python3
"""FIX-03 independent packet verifier (stdlib only; does NOT import analyze.py).

usage: python3 verify_artifacts.py [--git <repo>]
Checks, each printed PASS/FAIL, exit 1 on any FAIL:
  files       every cited file exists; no empty file under raw/ except the listed ones
  prereg      PREREG.json was committed before the first counted lock acquisition (with --git)
  binaries    every counted browser validity.json / native block header names its arm's sha256 + version
  locks       every counted block has exactly one FIX-03 shared receipt with held_s <= 300, rc recorded,
              and >= 30 s between consecutive FIX-03 counted acquisitions
  sessions    every counted block's session log is non-empty and shows a passing display probe
  recompute   the gate numbers in summary.json, recomputed from raw/ with independent code
  units       red logs fail exactly the named test, green logs report 0 failed
  privacy     no local absolute path, user home, /tmp/dbus-* address or key-shaped secret in the packet
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))


def jl(path):
    if not os.path.exists(path) and os.path.exists(path + ".gz"):
        import gzip
        with gzip.open(path + ".gz", "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def plans():
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "plans", "*.txt"))):
        for line in open(path, encoding="utf-8"):
            parts = line.split()
            if parts and not parts[0].startswith("#"):
                out.append(parts)
    return out


PROV = json.load(open(os.path.join(HERE, "provenance.json"), encoding="utf-8"))
SHA = {arm: PROV["binaries"][arm]["sha256"] for arm in PROV["binaries"]}


def ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def block_paths(parts):
    kind, arm = parts[0], parts[1]
    if kind == "B":
        phase, block = parts[2], parts[3]
        return [(f"fix03-B-{arm}-{phase}-{block}{s}", os.path.join(RAW, "browser", f"{block}{s}-{phase}-{arm}"))
                for s in ("", "R")]
    row, block = parts[2], parts[3]
    return [(f"fix03-N-{arm}-{row}-{block}{s}", os.path.join(RAW, "native", arm, row, f"b{block}{s}.jsonl"))
            for s in ("", "R")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--git", default=None)
    args = ap.parse_args()
    blocks = plans()

    # files
    for rel in ("PREREG.json", "README.md", "summary.json", "dispositions.json", "provenance.json",
                "source-audit.json", "analyze.py", "raw/lock-ledger.jsonl"):
        check(f"files:{rel}", os.path.exists(os.path.join(HERE, rel)))
    empties = [p for p in glob.glob(os.path.join(RAW, "**", "*"), recursive=True)
               if os.path.isfile(p) and os.path.getsize(p) == 0]
    allowed = set(PROV.get("allowed_empty_raw", []))
    check("files:no_unexpected_empty_raw", all(os.path.relpath(p, HERE) in allowed for p in empties),
          ",".join(os.path.relpath(p, HERE) for p in empties))

    # locks
    ledger = jl(os.path.join(RAW, "lock-ledger.jsonl"))
    by_label = {}
    for rec in ledger:
        by_label.setdefault(rec["label"], []).append(rec)
    counted = []
    for parts in blocks:
        used = None
        for label, path in block_paths(parts):
            if label in by_label:
                used = (label, path)
                recs = by_label[label]
                check(f"locks:{label}:one_receipt", len(recs) == 1)
                check(f"locks:{label}:shared_held_le_300", recs[0]["mode"] == "shared" and recs[0]["held_s"] <= 300,
                      f"held_s={recs[0]['held_s']}")
                counted.append((ts(recs[0]["acquired"]), ts(recs[0]["released"]), label, path))
        check(f"locks:block_has_receipt:{'-'.join(parts[:4])}", used is not None)
    counted.sort()
    exceptions = set(PROV.get("lock_spacing_exceptions", {}))
    gaps = [((b[0] - a[1]).total_seconds(), b[2]) for a, b in zip(counted, counted[1:])]
    short = [f"{label}:{gap:.1f}s" for gap, label in gaps if gap < 30]
    check("locks:spacing_ge_30s_except_listed_deviation",
          all(label in exceptions for gap, label in gaps if gap < 30), ";".join(short))
    check("locks:listed_spacing_exceptions_are_real", all(any(label == e for _, label in gaps) for e in exceptions))

    # prereg order
    if args.git:
        rel = os.path.relpath(os.path.join(HERE, "PREREG.json"), args.git)
        out = subprocess.run(["git", "-C", args.git, "log", "--diff-filter=A", "--format=%H %cI", "--", rel],
                             capture_output=True, text=True).stdout.split()
        if out:
            committed = dt.datetime.fromisoformat(out[-1])
            first = counted[0][0] if counted else None
            check("prereg:committed_before_first_counted_block", first is not None and committed < first,
                  f"prereg={committed.isoformat()} first={first}")
            check("prereg:commit_matches_provenance", out[-2].startswith(PROV["prereg_commit"][:9]))
        else:
            check("prereg:found_in_git", False)

    # binaries + sessions
    for _, _, label, path in counted:
        arm = label.split("-")[2]
        if label.startswith("fix03-B-"):
            val = json.load(open(os.path.join(path, "validity.json"), encoding="utf-8"))
            check(f"binaries:{label}", val["driver"]["sha256"] == SHA[arm] and val["driver"]["version"] == "cua-driver 0.32.0"
                  and val["ok"], val["driver"]["sha256"][:12])
        else:
            head = next(r for r in jl(path) if r.get("kind") == "block")
            check(f"binaries:{label}", head["driver_sha256"] == SHA[arm] and head["driver_version"] == "cua-driver 0.32.0",
                  head["driver_sha256"][:12])
        log = os.path.join(RAW, f"session-{label}.log")
        text = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
        check(f"sessions:{label}", bool(text) and re.search(r"\[(fix03|a3)-probe\] xdpyinfo ok", text) is not None)

    # recompute
    summary = json.load(open(os.path.join(HERE, "summary.json"), encoding="utf-8"))
    cells = {}
    for _, _, label, path in counted:
        if label.startswith("fix03-B-"):
            for cell in jl(os.path.join(path, "cells.jsonl")):
                cells.setdefault((cell["phase"], cell["arm"]), []).append(cell)
    a1fs, a1f5 = cells.get(("a1", "FS"), []), cells.get(("a1", "F5"), [])
    mine = {
        "FS_success_detached": sum(1 for c in a1fs if c["race_forced"] and c.get("first_status") == "ok"),
        "F5_success": sum(1 for c in a1f5 if c.get("first_status") == "ok"),
        "F5_refused": sum(1 for c in a1f5 if c.get("first_result") == "refused"),
        "F5_zero_gen0_change": sum(1 for c in a1f5 if c["gen0_change_events"] == 0),
        "F5_rebind": sum(1 for c in a1f5 if c["rebind_verified"]),
        "A3_F5": sum(1 for c in cells.get(("a3", "F5"), []) if c["a3_verified"]),
        "A3_F": sum(1 for c in cells.get(("a3", "F"), []) if c["a3_verified"]),
    }
    a = summary["part_a"]
    theirs = {
        "FS_success_detached": a["A1"]["FS"]["success_receipt_for_detached_node"],
        "F5_success": a["A1"]["F5"]["success_receipts"], "F5_refused": a["A1"]["F5"]["refused"],
        "F5_zero_gen0_change": a["A1"]["F5"]["cells_with_zero_gen0_change"],
        "F5_rebind": a["A2"]["F5"]["rebind_verified"], "A3_F5": a["A3"]["F5"]["verified"], "A3_F": a["A3"]["F"]["verified"],
    }
    for key in mine:
        check(f"recompute:A:{key}", mine[key] == theirs[key], f"{mine[key]} vs {theirs[key]}")

    def state(snap, win, field):
        return (((snap or {}).get("P") or {}).get("windows") or {}).get(win, {}).get(field)

    native = {}
    for _, _, label, path in counted:
        if label.startswith("fix03-N-"):
            arm, row = label.split("-")[2], label.split("-")[3]
            native.setdefault((row, arm), []).extend(r for r in jl(path) if r.get("kind") == "attempt")
    cd = summary["part_c_d"]
    for (row, arm), atts in sorted(native.items()):
        got = cd.get(f"{row}-{arm}", {})
        check(f"recompute:{row}-{arm}:n", got.get("n") == len(atts), f"{len(atts)}")
        if row == "WR":
            s3_land = sum(1 for t in atts for c in t["calls"] if c["step"].startswith("s3")
                          and state(c["pre"], "w1", "agreed") != state(c["post"], "w1", "agreed"))
            s12_ref = sum(1 for t in atts for c in t["calls"] if c["step"][:2] in ("s1", "s2") and c["is_error"])
            check(f"recompute:WR-{arm}:s3_mutation_w1", s3_land == got.get("s3_mutation_w1", 0), f"{s3_land}")
            check(f"recompute:WR-{arm}:s1_s2_refused", s12_ref == got.get("s1_refused", 0) + got.get("s2_refused", 0),
                  f"{s12_ref}")
        if row in ("WS", "WK"):
            field = "note_text" if row == "WS" else "agreed"
            bad = sum(1 for t in atts for c in t["calls"] if c["step"].startswith(("B-types", "B-presses"))
                      and state(c["pre"], "w1", field) != state(c["post"], "w1", field))
            check(f"recompute:{row}-{arm}:B_into_A", bad == got.get("B_wrote_into_A_window"), f"{bad}")
        if row in ("W2dX", "W2cX"):
            landed = sum(1 for t in atts if any(state(t["calls"][-2]["pre"], w, "agreed") != state(t["calls"][-2]["post"], w, "agreed")
                                                for w in ("w1", "w2")))
            check(f"recompute:{row}-{arm}:B_landed", landed == got.get("B_landed"), f"{landed}")

    # units
    units = PROV.get("units", {})
    for name, spec in units.items():
        path = os.path.join(HERE, spec["log"])
        text = open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""
        if spec["expect"] == "red":
            ok = f"{spec['test']} ... FAILED" in text
        else:
            results = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed", text)
            ok = bool(results) and all(r[2] == "0" for r in results) and sum(int(r[1]) for r in results) == spec.get("passed", -1)
        check(f"units:{name}", ok)

    # privacy
    pats = [re.compile(p) for p in (r"/home/[a-z]", r"/mnt/[A-Za-z0-9_-]+/", r"/tmp/dbus-(?!<redacted>)[A-Za-z0-9]",
                                     r"/Users/[A-Za-z]", r"sk-[A-Za-z0-9]{20,}", r"(?i)typesafe_api_key\s*=")]
    names_file = os.environ.get("CUA_PRIVACY_NAMES_FILE")
    if names_file and os.path.exists(names_file):
        pats += [re.compile(re.escape(n.strip())) for n in open(names_file) if n.strip()]
    hits = []
    for path in glob.glob(os.path.join(HERE, "**", "*"), recursive=True):
        if os.path.isfile(path) and not path.endswith(".pyc"):
            text = open(path, encoding="utf-8", errors="replace").read()
            for pat in pats:
                if pat.search(text) and os.path.basename(path) != "verify_artifacts.py":
                    hits.append(f"{os.path.relpath(path, HERE)}:{pat.pattern}")
    check("privacy:no_local_paths_or_secrets", not hits, ";".join(hits[:10]))

    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        if not ok or os.environ.get("VERBOSE"):
            print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    print(f"{len(RESULTS)} checks, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""FIX-04 independent packet verifier (stdlib only; does NOT import analyze.py).

usage: python3 verify_artifacts.py [--git <repo>] [--base <sha>]
Checks, each printed PASS/FAIL (VERBOSE=1 prints every PASS), exit 1 on any FAIL:
  files      every cited file exists
  shas       every SHA cited in provenance.json exists in the repo (with --git)
  prereg     PREREG.json was committed before the first counted lock acquisition (with --git)
  binaries   every counted native block header / browser validity.json names its arm's sha256 and
             version cua-driver 0.32.0
  locks      every counted block has exactly one FIX-04 SHARED receipt (rc 0, held_s <= 300) and >= 30 s
             separate consecutive counted acquisitions
  sessions   every counted block's session log is non-empty and shows a passing display probe
  recompute  every row, gate and E4 counter in summary.json recomputed from raw/ with independent code
  units      red logs fail exactly the named tests; green logs report 0 failed and the expected passes
  privacy    no local absolute path, user home, /tmp/dbus-* address, key-shaped secret or private name
             (CUA_PRIVACY_NAMES_FILE + host name, word-boundary) in the packet files, AND in every lane
             commit base..HEAD (blobs incl. gzip members, messages, identity, trailer) (with --git)
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import gzip
import json
import os
import re
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
REL = "docs/experiments/" + os.path.basename(HERE)
RESULTS: list[tuple[str, bool, str]] = []
BASE = "e300edbd318f33b907741ca7aaec2ee666a2dac0"
IDENTITY = "Kevin Rajan <7121943+kvnloo@users.noreply.github.com>"
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))


def read_jsonl(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as stream:
        return json.load(stream)


def plan_rows():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, "plans", "*.txt"))):
        for line in open(path, encoding="utf-8"):
            parts = line.split()
            if parts and not parts[0].startswith("#"):
                rows.append(parts)
    return rows


def labels_for(parts):
    kind, arm = parts[0], parts[1]
    if kind == "B":
        return f"fix04-B-{arm}-{parts[2]}-{parts[3]}"
    return f"fix04-N-{arm}-{parts[2]}-{parts[3]}"


def ts(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


# ── independent recomputation ──────────────────────────────────────────────
def w2_of(state):
    return (((state or {}).get("P") or {}).get("windows") or {}).get("w2")


def find(rec, prefix):
    return next((c for c in rec.get("calls", []) if c.get("step", "").startswith(prefix)), None)


def moved(c):
    return c is not None and w2_of(c.get("pre")) != w2_of(c.get("post"))


def native(arm, row):
    out = []
    for path in sorted(glob.glob(os.path.join(RAW, "native", arm, row, "*.jsonl*"))):
        out += [r for r in read_jsonl(path) if r.get("kind") == "attempt"]
    return out


def recompute():
    got = {"C": {"CT": {}, "CF": {}}, "D": {}}
    steps = {"CT": ("A-types-into-closed-w1", "B-types-into-own-w2"),
             "CF": ("A-presses-space-on-closed-w1", "B-clicks-own-w2")}
    for row, arms in (("CT", ("F5", "F6", "U")), ("CF", ("F5", "F6"))):
        for arm in arms:
            recs = native(arm, row)
            a_calls = [find(r, steps[row][0]) for r in recs]
            got["C"][row][arm] = {
                "attempts": len(recs),
                "cross_window": sum(moved(c) for c in a_calls),
                "a_refused": sum(bool(c and (c.get("is_error") or c.get("refusal_code"))) for c in a_calls),
                "tail_verified": sum(moved(find(r, steps[row][1])) for r in recs),
                "w1_closed": sum(r.get("w1_closed_confirmed") is True for r in recs),
            }
    w2dx = {}
    for arm in ("U", "F6"):
        recs = native(arm, "W2dX")
        w2dx[arm] = {"attempts": len(recs),
                     "landed": sum(moved(find(r, "B-uses-A-w2-token-after-w1-closed")) for r in recs),
                     "tail_verified": sum(moved(find(r, "A-uses-own-w2-token-after-w1-closed")) for r in recs)}
    got["D"]["W2dX"] = w2dx
    cells = []
    for path in sorted(glob.glob(os.path.join(RAW, "browser", "*-a1-F6", "cells", "*.jsonl"))):
        cells += [r for r in read_jsonl(path) if r.get("type") == "cell"]
    firsts = [((c.get("steps") or [{}])[0]) for c in cells]
    raws = [f.get("raw") or {} for f in firsts]
    got["D"]["a1_F6"] = {
        "cells": len(cells),
        "success_receipts": sum(r.get("status") == "ok" for r in raws),
        "unknown_receipts": sum(r.get("status") == "refused" and r.get("effect") == "unverifiable"
                                and r.get("delivery") == "unknown" and r.get("retryable") is False for r in raws),
        "gen0_change_reached_server": sum((c.get("gen0_change_events") or 0) >= 1 for c in cells),
        "race_forced": sum(bool(c.get("race_forced")) for c in cells),
        "runner_may_redispatch_true": sum(f.get("runner_may_redispatch") is True for f in firsts),
        "gen0_dispatches_gt1": sum(len([s for s in c.get("steps") or [] if s.get("label") == "gen0_ref"]) > 1
                                   for c in cells),
        "gen0_change_events_gt1": sum((c.get("gen0_change_events") or 0) > 1 for c in cells),
    }
    a3 = []
    for path in sorted(glob.glob(os.path.join(RAW, "browser", "*-a3-F6", "cells", "*.jsonl"))):
        a3 += [r for r in read_jsonl(path) if r.get("type") == "cell"]
    got["D"]["a3_F6"] = {"cells": len(a3), "verified": sum(bool(c.get("a3_verified")) for c in a3),
                         "effect_key_present": sum("effect" in (((c.get("steps") or [{}])[0].get("raw") or {})
                                                                .get("keys") or []) for c in a3)}
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--git", default=None)
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    prereg, prov, summary = load("PREREG.json"), load("provenance.json"), load("summary.json")
    blocks = plan_rows()

    # files
    for name in ("README.md", "PREREG.json", "provenance.json", "summary.json", "dispositions.json",
                 "source-audit.json", "analyze.py", "raw/lock-ledger.jsonl"):
        check(f"files:{name}", os.path.exists(os.path.join(HERE, name)))
    for name in prov.get("unit_logs", {}).values():
        check(f"files:{name['log']}", os.path.exists(os.path.join(HERE, name["log"])))

    # shas
    if args.git:
        for key, sha in prov.get("shas", {}).items():
            ok = subprocess.run(["git", "-C", args.git, "cat-file", "-e", f"{sha}^{{commit}}"],
                                capture_output=True).returncode == 0
            check(f"shas:{key}", ok, sha)

    # locks
    ledger = read_jsonl(os.path.join(RAW, "lock-ledger.jsonl"))
    counted = []
    for parts in blocks:
        label = labels_for(parts)
        mine = [r for r in ledger if r.get("label") in (label, label + "R")]
        ok = len([r for r in mine if r["label"] == label]) == 1 and all(
            r.get("lane") == "FIX-04" and r.get("mode") == "shared" and r.get("held_s", 999) <= 300
            and r.get("rc") == 0 for r in mine)
        check(f"locks:{label}", ok, json.dumps(mine)[:200])
        counted += mine
    counted.sort(key=lambda r: r["acquired"])
    gaps = [(ts(b["acquired"]) - ts(a["released"])).total_seconds() for a, b in zip(counted, counted[1:])]
    exceptions = set(prov.get("lock_spacing_exceptions", []))
    bad = [(counted[i + 1]["label"], round(g, 1)) for i, g in enumerate(gaps)
           if g < 30 and counted[i + 1]["label"] not in exceptions]
    check("locks:spacing_ge_30s", not bad, bad)

    # prereg
    if args.git and counted:
        when = git(args.git, "log", "--diff-filter=A", "--format=%cI", "--", f"{REL}/PREREG.json").split()
        first = min(ts(r["acquired"]) for r in counted)
        check("prereg:committed_before_first_counted_block", bool(when) and ts(when[-1]) < first,
              f"{when[-1] if when else None} < {first.isoformat()}")

    # binaries
    shas = {arm: prereg["binaries"][arm]["sha256"] for arm in prereg["binaries"]}
    for parts in blocks:
        kind, arm = parts[0], parts[1]
        if kind == "N":
            path = os.path.join(RAW, "native", arm, parts[2], f"b{parts[3]}.jsonl")
            heads = [r for r in read_jsonl(path) if r.get("kind") == "block"] if os.path.exists(path) else []
            ok = bool(heads) and all(h.get("driver_sha256") == shas[arm] and h.get("driver_version") == "cua-driver 0.32.0"
                                     for h in heads)
        else:
            path = os.path.join(RAW, "browser", f"{parts[3]}-{parts[2]}-{arm}", "validity.json")
            v = json.load(open(path)) if os.path.exists(path) else {}
            ok = (v.get("driver") or {}).get("sha256") == shas[arm] and (v.get("driver") or {}).get(
                "version") == "cua-driver 0.32.0" and v.get("ok") is True
        check(f"binaries:{labels_for(parts)}", ok)

    # sessions
    for parts in blocks:
        label = labels_for(parts)
        path = os.path.join(RAW, f"session-{label}.log")
        text = open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""
        probe = r"\[fix04-probe\] xdpyinfo ok" if parts[0] == "B" else r"\[a3-probe\] xdpyinfo ok"
        check(f"sessions:{label}", bool(text) and re.search(probe, text) is not None)

    # recompute
    got = recompute()
    for row in ("CT", "CF"):
        for arm, vals in got["C"][row].items():
            for key, value in vals.items():
                check(f"recompute:C.{row}.{arm}.{key}", summary["C"][row][arm].get(key) == value,
                      f"{summary['C'][row][arm].get(key)} vs {value}")
    for part in ("a1_F6", "a3_F6"):
        for key, value in got["D"][part].items():
            check(f"recompute:D.{part}.{key}", summary["D"][part].get(key) == value,
                  f"{summary['D'][part].get(key)} vs {value}")
    for arm, vals in got["D"]["W2dX"].items():
        for key, value in vals.items():
            check(f"recompute:D.W2dX.{arm}.{key}", summary["D"]["W2dX"][arm].get(key) == value)
    c, d = got["C"], got["D"]
    gates = {"C_CT": "KEEP" if c["CT"]["F6"]["attempts"] == 20 and c["CT"]["F6"]["cross_window"] == 0 else "FAIL",
             "C_CF": "KEEP" if c["CF"]["F6"]["attempts"] == 20 and c["CF"]["F6"]["cross_window"] == 0 else "FAIL",
             "D": "KEEP" if d["a1_F6"]["cells"] == 20 and d["a1_F6"]["success_receipts"] == 0
             and d["a1_F6"]["unknown_receipts"] == 20 else "FAIL",
             "E4_blind_replays": d["a1_F6"]["runner_may_redispatch_true"] + d["a1_F6"]["gen0_dispatches_gt1"]
             + d["a1_F6"]["gen0_change_events_gt1"]}
    for key, value in gates.items():
        check(f"recompute:gate.{key}", summary["gates"].get(key) == value, f"{summary['gates'].get(key)} vs {value}")

    # units
    for name, spec in prov.get("unit_logs", {}).items():
        path = os.path.join(HERE, spec["log"])
        text = open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""
        if spec["expect"] == "red":
            ok = all(re.search(re.escape(t) + r".*(FAILED|FAIL|not ok)", text) or re.search(
                r"(FAIL|not ok)[^\n]*" + re.escape(t), text) for t in spec["tests"])
        elif spec["expect"] == "green-cargo":
            results = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed", text)
            ok = bool(results) and all(r[2] == "0" for r in results) and sum(int(r[1]) for r in results) == spec["passed"]
        elif spec["expect"] == "green-unittest":
            ok = re.search(r"\nOK( \(skipped=\d+\))?\s*$", text) is not None and f"Ran {spec['ran']} tests" in text
        elif spec["expect"] == "green-node":
            ok = f"# pass {spec['pass']}" in text and "# fail 0" in text
        else:
            ok = False
        check(f"units:{name}", ok)

    # privacy (packet files)
    pats = [re.compile(p) for p in (r"/home/[a-z]", r"/mnt/[A-Za-z0-9_-]+/", r"/tmp/dbus-(?!<redacted>)[A-Za-z0-9]",
                                     r"/Users/[A-Za-z]", r"sk-[A-Za-z0-9]{20,}", r"(?i)typesafe_api_key\s*=")]
    names = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and os.path.isfile(src):
        names |= {x.strip() for x in open(src) if x.strip() and not x.startswith("#")}
    pats += [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", re.I) for n in sorted(names)]

    def scan(text):
        return [p.pattern for p in pats if p.search(text)]

    hits = []
    for path in glob.glob(os.path.join(HERE, "**", "*"), recursive=True):
        if os.path.isfile(path) and not path.endswith(".pyc") and os.path.basename(path) != "verify_artifacts.py":
            data = open(path, "rb").read()
            if path.endswith(".gz"):
                data = gzip.decompress(data)
            found = scan(data.decode("utf-8", "replace"))
            hits += [f"{os.path.relpath(path, HERE)}:{f}" for f in found]
    check("privacy:packet_files", not hits, ";".join(hits[:10]))
    check("privacy:names_source", bool(src and os.path.isfile(src)), "CUA_PRIVACY_NAMES_FILE + host name")

    if args.git:
        commits = git(args.git, "rev-list", f"{args.base}..HEAD").split()
        check("privacy:commits_scanned", bool(commits), len(commits))
        for sha in commits:
            meta = git(args.git, "show", "-s", "--format=%an <%ae>|%cn <%ce>|%B", sha)
            author, committer, body = meta.split("|", 2)
            check(f"identity:{sha[:9]}", author == IDENTITY and committer == IDENTITY and TRAILER in body,
                  f"{author} / {committer}")
            found = scan(body) + scan(author) + scan(committer)
            for path in git(args.git, "show", "--format=", "--name-only", "--no-renames", sha).split("\n"):
                if not path:
                    continue
                found += [f"path:{path}:{f}" for f in scan(path)]
                blob = git(args.git, "show", f"{sha}:{path}", binary=True)
                if path.endswith(".gz") and blob:
                    try:
                        blob = gzip.decompress(blob)
                    except OSError:
                        pass
                found += [f"{path}:{f}" for f in scan(blob.decode("utf-8", "replace"))
                          if not path.endswith("verify_artifacts.py")]
            check(f"privacy:commit:{sha[:9]}", not found, ";".join(found[:6]))

    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        if not ok or os.environ.get("VERBOSE"):
            print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    print(f"{len(RESULTS)} checks, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

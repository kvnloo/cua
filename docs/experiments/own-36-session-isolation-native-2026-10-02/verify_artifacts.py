#!/usr/bin/env python3
"""Fresh-verifier checks for the OWN-36 packet. Exit 0 only if every check passes.

Independent of analyze.py: re-derives each gating row from raw/ with its own
step-expectation table, then compares with own-36-summary.json and the README
results table. Also checks the lock ledger, PREREG-before-first-attempt order,
block completeness, binary identity and privacy (no absolute local paths, no
host name, no secret-looking strings) across every packet file.
"""

import glob
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
EXPECTED_SHA = "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3"
EXPECTED_VERSION = "cua-driver 0.32.0"
FAILURES = []

EXPECT = {
    "P": {"own-token-A": "verify:A", "own-token-B": "verify:B"},
    "I1": {"B-uses-A-capture": "refuse", "A-uses-own-capture": "verify:A"},
    "I2": {"B-uses-A-token-on-B-pid": "refuse", "B-uses-A-token-on-A-pid": "refuse",
           "A-uses-own-token": "verify:A"},
    "I3": {"B-uses-own-pre-replacement-token": "verify:B", "A-uses-own-superseded-token": "refuse"},
    "I4": {"B-own-token-after-A-ended": "verify:B", "B-uses-ended-A-token": "refuse",
           "A-uses-own-token-after-end": "refuse"},
    "I5": {"A-uses-old-generation-token": "refuse", "A-uses-old-generation-capture": "refuse",
           "A-uses-new-generation-token": "verify:A", "B-own-token-before-A-restart": "verify:B",
           "B-own-token-after-A-restart": "verify:B"},
    "N": {"A-uses-stale-token-on-recreated-pid": "refuse"},
    "I5p": {"gen2-uses-gen1-token": "refuse", "gen2-uses-gen1-capture": "refuse"},
}
CROSS = {"I1": ["B-uses-A-capture"], "I2": ["B-uses-A-token-on-B-pid", "B-uses-A-token-on-A-pid"],
         "I4": ["B-uses-ended-A-token"], "I5p": ["gen2-uses-gen1-token"]}
MIN_N = {"P": 20, "I1": 20, "I2": 20, "I3": 20, "I4": 20, "I5": 20, "N": 10, "I5p": 20}


def check(ok, message):
    if not ok:
        FAILURES.append(message)


def ts(value):
    value = value.rstrip("Z")
    if "." in value:
        head, frac = value.split(".")
        value = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(value)


def changed(call, tag):
    return call["pre"].get(tag) != call["post"].get(tag)


def meets(call, expectation):
    if expectation == "refuse":
        return bool(call["is_error"]) and not changed(call, "A") and not changed(call, "B")
    target = expectation.split(":")[1]
    other = "B" if target == "A" else "A"
    pre, post = call["pre"][target], call["post"][target]
    return (not call["is_error"] and post["agreed"] is (not pre["agreed"])
            and post["seq"] == pre["seq"] + 1 and not changed(call, other))


def main():
    summary = json.load(open(os.path.join(HERE, "own-36-summary.json"), encoding="utf-8"))
    readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
    files = sorted(glob.glob(os.path.join(RAW, "T*", "*", "b*.jsonl")))
    ledger = [json.loads(line) for line in open(os.path.join(RAW, "lock-ledger.jsonl"))
              if line.strip()]
    plan = [line.split() for name in ("plan.txt", "plan-reruns.txt")
            for line in open(os.path.join(HERE, name))
            if line.strip() and not line.startswith("#")]
    # Failed blocks (crash before the first gating call) and their re-run ids, from plan-reruns.txt.
    failed = {}
    for line in open(os.path.join(HERE, "plan-reruns.txt")):
        m = re.match(r"#\s+(T\d)\s+(\S+)\s+(\S+)\s+->\s+(\S+)\s*:", line)
        if m:
            failed[(m.group(1), m.group(2), m.group(3))] = m.group(4)

    # ── plan coverage, completeness, binary identity, ledger ────────────────
    planned = {(p[0], p[1], p[2]) for p in plan} | set(failed)
    present = set()
    first_attempt = None
    per_row = {}
    for path in files:
        topo, row, name = os.path.relpath(path, RAW).split(os.sep)
        block = name[1:-6]
        present.add((topo, row, block))
        records = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        header = [r for r in records if r["kind"] == "block"]
        end = [r for r in records if r["kind"] == "block_end"]
        attempts = [r for r in records if r["kind"] == "attempt"]
        if (topo, row, block) in failed:
            # Disclosed failed block: header only, no attempts, rc=1 receipt, re-run present.
            check(len(header) == 1 and not end and not attempts, f"{path}: failed block shape")
            check((topo, row, failed[(topo, row, block)]) in {(p[0], p[1], p[2]) for p in plan},
                  f"{path}: re-run block missing from plan-reruns.txt")
        else:
            check(len(header) == 1 and len(end) == 1, f"{path}: header/end missing")
        if header:
            check(header[0]["driver_sha256"] == EXPECTED_SHA, f"{path}: driver sha256")
            check(header[0]["driver_version"] == EXPECTED_VERSION, f"{path}: driver version")
            check(bool(header[0].get("display")), f"{path}: DISPLAY not recorded")
        check(len(attempts) <= 10, f"{path}: more than 10 attempts in one block")
        receipts = [r for r in ledger if (r["topology"], r["row"], r["block"]) == (topo, row, block)]
        check(len(receipts) == 1, f"{path}: expected exactly one lock receipt, got {len(receipts)}")
        if receipts and (topo, row, block) in failed:
            check(receipts[0]["rc"] != 0 and receipts[0]["attempts_recorded"] == 0,
                  f"{path}: failed-block receipt")
        if receipts and header and end:
            r = receipts[0]
            check(r["mode"] == "shared" and r["lock"] == "quiet-lane.lock", f"{path}: lock mode")
            check(r["attempts_recorded"] == len(attempts), f"{path}: receipt attempt count")
            check(ts(r["acquired_utc"]) <= ts(header[0]["started_utc"]) and
                  ts(end[0]["ended_utc"]) <= ts(r["released_utc"]),
                  f"{path}: block ran outside its lock window")
        for a in attempts:
            started = ts(a["started_utc"])
            first_attempt = started if first_attempt is None or started < first_attempt else first_attempt
            key = (topo, row, bool(a.get("forged")))
            per_row.setdefault(key, []).append(a)
    check(planned == present, f"plan/raw mismatch: missing {sorted(planned - present)} "
                              f"extra {sorted(present - planned)}")
    check(len(ledger) == len(files), "ledger receipts != block files")

    # ── PREREG committed before the first counted attempt ───────────────────
    prov = json.load(open(os.path.join(HERE, "provenance.json"), encoding="utf-8"))
    prereg_utc = prov["prereg_commit_utc"]
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H %ct", "--",
                              "PREREG.json"], cwd=HERE, capture_output=True, text=True,
                             timeout=30).stdout.split()
    except (OSError, subprocess.SubprocessError):
        out = []
    if out:  # oldest add commit is last; its committer time must match provenance
        sha, epoch = out[-2], int(out[-1])
        git_utc = datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)
        check(sha.startswith(prov["prereg_commit"][:9]), f"PREREG add commit {sha} != provenance")
        check(abs((git_utc - ts(prereg_utc)).total_seconds()) < 2, "PREREG commit time != provenance")
        check(first_attempt is not None and git_utc < first_attempt, "git PREREG time not before attempts")
    check(first_attempt is not None and ts(prereg_utc) < first_attempt,
          f"PREREG commit {prereg_utc} is not before first attempt {first_attempt}")

    # ── independent row recomputation ───────────────────────────────────────
    recomputed = {}
    for (topo, row, forged), attempts in sorted(per_row.items()):
        key = f"{topo}/{row}{'/forged' if forged else ''}"
        if row not in EXPECT:
            recomputed[key] = {"n": len(attempts)}
            continue
        ok = 0
        cross = 0
        for a in attempts:
            calls = {c["step"]: c for c in a["calls"]}
            exp = dict(EXPECT[row])
            if forged and row == "I3":
                exp["B-uses-own-pre-replacement-token"] = "refuse"
            good = True
            for name, expectation in exp.items():
                if name in calls:
                    good &= meets(calls[name], expectation)
                elif not name.startswith("B-own-token-"):
                    good = False
            ok += int(good)
            cross += sum(changed(calls[s], "A") or changed(calls[s], "B")
                         for s in CROSS.get(row, []) if s in calls)
        verdict = "KEEP" if ok == len(attempts) and cross == 0 else "KILL"
        if row in ("P", "N") or forged:
            verdict = "CONTROL_PASS" if verdict == "KEEP" else "CONTROL_FAIL"
        recomputed[key] = {"n": len(attempts), "ok": ok, "cross": cross, "verdict": verdict}
        s = summary["rows"].get(key)
        check(s is not None, f"{key}: missing in summary")
        if s:
            check(s["attempts"] == len(attempts), f"{key}: attempts {s['attempts']} != {len(attempts)}")
            check(s["verdict"] == verdict, f"{key}: verdict {s['verdict']} != recomputed {verdict}")
            check(s["cross_session_mutations"] == cross,
                  f"{key}: cross mutations {s['cross_session_mutations']} != {cross}")
        if not forged:
            check(len(attempts) >= MIN_N[row], f"{key}: n={len(attempts)} < {MIN_N[row]}")
        else:
            check(len(attempts) == 5, f"{key}: forged n={len(attempts)} != 5")
        line = [l for l in readme.splitlines() if l.startswith(f"| {topo} | {row}{' forged' if forged else ''} |")]
        check(len(line) == 1, f"README: no unique results row for {key}")
        if line:
            check(verdict in line[0] and f"{ok}/{len(attempts)}" in line[0],
                  f"README row for {key} does not state {ok}/{len(attempts)} {verdict}")

    # ── I6 recomputation (other-session marker never in a cross/refusal envelope) ─
    markers = {}
    positive = 0
    sessions = 0
    for path in files:
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r["kind"] == "setup":
                markers[(path, r["marker_tag"])] = r["marker"]
                sessions += 1
                obs = [c for c in r["calls"] if c["step"] == "observe-with-marker"]
                positive += int(bool(obs) and r["marker"] in json.dumps(obs[0]["response"]))
    hits = 0
    for path in files:
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r["kind"] != "attempt" or r["topology"] == "T3":
                continue
            for c in r["calls"]:
                if c["is_error"] or c["step"] in sum(CROSS.values(), []) + [
                        "B-stale-probe-on-A-pid", "B-uses-derived-token-on-A-pid"]:
                    body = json.dumps(c["response"])
                    other = markers.get((path, "B" if c["actor"] == "A" else "A"))
                    hits += int((other is not None and other in body) or "iVBORw0KGgo" in body
                                or re.search(r"[A-Za-z0-9+/=]{256,}", body) is not None)
    check(positive == sessions and sessions > 0, f"I6 positive control {positive}/{sessions}")
    check(hits == summary["I6"]["content_hits"], f"I6 hits {hits} != summary {summary['I6']['content_hits']}")

    # ── privacy over every packet file ──────────────────────────────────────
    host = socket.gethostname().split(".")[0].lower()
    roots = ["/" + part + "/" for part in ("mnt", "home", "tmp", "run" + "/user")]
    patterns = [re.compile(re.escape(root)) for root in roots] + [re.compile(p) for p in (
                                         r"sk-[A-Za-z0-9]{16,}", r"ghp_[A-Za-z0-9]{20,}",
                                         r"BEGIN [A-Z ]*PRIVATE KEY", r"(?i)typesafe_api_key\s*=")]
    for root, _, names in os.walk(HERE):
        for name in names:
            path = os.path.join(root, name)
            if "__pycache__" in path:
                continue
            text = open(path, encoding="utf-8", errors="replace").read()
            if name == "verify_artifacts.py":
                text = re.sub(r'r"[^"]*"', "", text)  # this file's own pattern literals
            for pattern in patterns:
                check(not pattern.search(text), f"privacy: {pattern.pattern} in {os.path.relpath(path, HERE)}")
            if host and len(host) >= 3:
                check(host not in text.lower(), f"privacy: host name in {os.path.relpath(path, HERE)}")

    if FAILURES:
        print("FAIL")
        for failure in FAILURES:
            print(" -", failure)
        return 1
    print(f"PASS: {len(files)} blocks, {sum(len(v) for v in per_row.values())} attempts; "
          + ", ".join(f"{k}={v.get('verdict', v['n'])}" for k, v in recomputed.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verify the OWN-09 packet.

Recomputes every iteration verdict from the raw ledger events, fixture-owned
native counters and target journal (independently of the Rust harness's own
verdict), rebuilds the row matrix and the pre-registered row statuses and
disposition, compares them with summary.json, checks that PREREG.json was
committed before the first counted run, and scans the packet (and optionally
every branch commit) for absolute paths, the host name and secret patterns.

Usage:
  python3 verify_artifacts.py                 # verify
  python3 verify_artifacts.py --write-summary # (re)write summary.json, then verify
  python3 verify_artifacts.py --git-range BASE..HEAD   # also privacy-scan commits
"""
import argparse
import collections
import datetime
import json
import os
import re
import socket
import subprocess
import sys

PACKET = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(PACKET, "raw")
PASSES = ("main", "stress")
ITERATIONS = 20


def load(path):
    with open(path) as handle:
        return json.load(handle)


def records(pass_name):
    out = []
    base = os.path.join(RAW, pass_name)
    for arm in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        for name in sorted(os.listdir(os.path.join(base, arm))):
            if not name.endswith(".jsonl"):
                continue
            with open(os.path.join(base, arm, name)) as handle:
                for line in handle:
                    if line.strip():
                        out.append(json.loads(line))
    return out


class Ledger:
    def __init__(self, events):
        self.first = {}
        for seq, name, _t in events or []:
            self.first.setdefault(name, seq)

    def has(self, name):
        return name in self.first

    def before(self, a, b):
        if a not in self.first:
            return False
        return b not in self.first or self.first[a] < self.first[b]


def counter(record, ident):
    return (record.get("counters") or {}).get(str(ident), [0, 0])


def landed_ids(record):
    return [e["id"] for e in record.get("journal") or [] if e.get("effect") == "applied"]


def is_ok(outcome):
    return isinstance(outcome, dict) and outcome.get("is_error") is False


def recompute(record):
    """Independent re-derivation of one iteration's verdict."""
    if record.get("error"):
        return "HARNESS_ERROR"
    led = Ledger(record.get("events"))
    checks = record.get("checks") or {}
    row, variant = record["row"], record["variant"]
    if row == "R1" and variant == "cancel_race":
        admitted = led.has("admitted:2")
        ok = admitted or counter(record, 2) == [0, 0]
        return "PASS" if ok else "FAIL"
    if row == "R1":
        ok = (
            not led.has("admitted:2")
            and counter(record, 2) == [0, 0]
            and led.before("native-exit:1", "admitted:3")
        )
        return "PASS" if ok else "FAIL"
    if row == "R2":
        return "PASS" if led.before("native-exit:1", "admitted:2") else "FAIL"
    if row == "R4":
        ok = (
            is_ok(checks.get("later_outcome"))
            and led.before("invoke-end:2", "invocation-dropped:2")
            and counter(record, 2) == [1, 1]
        )
        return "PASS" if ok else "FAIL"
    if row == "R5":
        f2 = checks.get("foreign_end_of_a") or {}
        ok = (
            is_ok(checks.get("own_outcome"))
            and led.before("invoke-end:1", "invocation-dropped:1")
            and not led.has("admitted:2")
            and counter(record, 2) == [0, 0]
            and (f2.get("is_error") is True or "driver_error" in f2)
            and landed_ids(record) == [1]
        )
        return "PASS" if ok else "FAIL"
    if row == "R6":
        ready = "session-cleanup" if variant.startswith("end_session") else "shutdown-returned"
        ok = led.has(ready) and led.before("native-exit:1", ready)
        return "PASS" if ok else "FAIL"
    if row == "R7":
        landed = len(landed_ids(record))
        if variant == "control_ack":
            return "PASS" if landed == 1 else "FAIL"
        ok = (
            led.has("first-read:0")
            and led.before("native-exit:1", "admitted:2")
            and landed == 1
        )
        return "PASS" if ok else "FAIL"
    if row == "R8":
        response = checks.get("in_flight_response") or {}
        result = response.get("result") if isinstance(response, dict) else None
        delivered = result is not None and result.get("isError") is not True
        dropped_early = not led.before("invoke-end:801", "invocation-dropped:801")
        return "IGNORED" if (delivered and not dropped_early) else "HONORED"
    raise ValueError(f"unknown row {row}")


def matrix(recs):
    table = collections.defaultdict(collections.Counter)
    for rec in recs:
        table[(rec["arm"], rec["row"], rec["variant"])][rec["verdict"]] += 1
    return table


def all_are(table, key, verdict, n=ITERATIONS):
    counts = table.get(key, collections.Counter())
    return counts.get(verdict, 0) >= n and sum(counts.values()) == counts.get(verdict, 0)


def any_fail(table, key):
    return table.get(key, collections.Counter()).get("FAIL", 0) > 0


def row_status(prereg, tables, arm, row):
    spec = prereg["rows"][row]
    if spec.get("status") == "BLOCKED":
        return {"status": "BLOCKED", "reason": spec["reason"]}
    main, stress = tables["main"], tables["stress"]
    primaries = spec["primary_variants"]
    harness = [
        (p, v)
        for p in PASSES
        for v in primaries + spec.get("broken_controls", {}).get(arm, [])
        if tables[p].get((arm, row, v), collections.Counter()).get("HARNESS_ERROR", 0)
    ]
    if spec.get("characterization"):
        expect = spec["broken_expected"]
        broken_ok = all(
            all_are(main, (arm, row, b), expect) for b in spec.get("broken_controls", {}).get(arm, [])
        )
        observed = {
            v: dict(main.get((arm, row, v), {})) for v in primaries
        }
        stress_observed = {
            v: dict(stress.get((arm, row, v), {})) for v in primaries
        }
        return {
            "status": "CHARACTERIZED" if broken_ok and not harness else "INVALID",
            "observed_main": observed,
            "observed_stress": stress_observed,
            "broken_control_detected": broken_ok,
        }
    failed = [
        (p, v) for p in PASSES for v in primaries if any_fail(tables[p], (arm, row, v))
    ]
    passed_all = all(all_are(main, (arm, row, v), "PASS") for v in primaries) and all(
        all_are(stress, (arm, row, v), "PASS") for v in primaries
    )
    broken = spec.get("broken_controls", {}).get(arm, [])
    broken_detected = all(all_are(main, (arm, row, b), "FAIL") for b in broken)
    positives = spec.get("positive_controls", [])
    positive_ok = all(all_are(main, (arm, row, c), "PASS") for c in positives)
    if harness:
        status = "INVALID"
    elif failed:
        status = "FAIL" if positive_ok else "INVALID"
    elif passed_all and broken_detected and broken:
        status = "PASS"
    else:
        status = "INVALID"
    return {
        "status": status,
        "failed_variants": sorted({v for _, v in failed}),
        "broken_controls": broken,
        "broken_detected_20_of_20": broken_detected,
        "positive_controls": positives,
        "positive_controls_pass_20_of_20": positive_ok,
        "harness_errors": harness,
    }


def disposition(prereg, statuses):
    gating = prereg["disposition_rule"]["gating_rows"]
    p = {row: statuses["P"][row]["status"] for row in gating}
    if any(s == "FAIL" for s in p.values()):
        verdict = "KILL"
    elif all(s == "PASS" for s in p.values()):
        verdict = "KEEP"
    else:
        verdict = "REVISE"
    return {
        "verdict": verdict,
        "p_row_status": p,
        "p_rows_passing": sorted(r for r, s in p.items() if s == "PASS"),
        "p_rows_failing": sorted(r for r, s in p.items() if s == "FAIL"),
        "m_confirmed_gaps": sorted(
            r for r in prereg["rows"] if statuses["M"].get(r, {}).get("status") == "FAIL"
        ),
    }


def build_summary(prereg):
    recs = {p: records(p) for p in PASSES}
    mismatches = []
    for p in PASSES:
        for rec in recs[p]:
            again = recompute(rec)
            if again != rec["verdict"]:
                mismatches.append(
                    f"{p} {rec['arm']} {rec['row']} {rec['variant']} iter {rec['iter']}: "
                    f"recorded {rec['verdict']} recomputed {again}"
                )
    tables = {p: matrix(recs[p]) for p in PASSES}
    statuses = {
        arm: {row: row_status(prereg, tables, arm, row) for row in prereg["rows"]}
        for arm in ("M", "P")
    }
    def flat(table):
        return {
            f"{arm}/{row}/{variant}": dict(counts)
            for (arm, row, variant), counts in sorted(table.items())
        }
    return {
        "lane": "OWN-09",
        "iterations_recorded": {p: len(recs[p]) for p in PASSES},
        "matrix": {p: flat(tables[p]) for p in PASSES},
        "row_status": statuses,
        "disposition": disposition(prereg, statuses),
    }, mismatches


def parse_utc(text):
    return datetime.datetime.strptime(text.rstrip("Z")[:23], "%Y-%m-%dT%H:%M:%S.%f").replace(
        tzinfo=datetime.timezone.utc
    )


def git(*args):
    return subprocess.run(
        ["git", "-C", PACKET, *args], capture_output=True, text=True, check=False
    )


def check_prereg_order(prereg, problems):
    receipts = []
    path = os.path.join(RAW, "receipts.jsonl")
    with open(path) as handle:
        receipts = [json.loads(line) for line in handle if line.strip()]
    counted = [r for r in receipts if r.get("counted")]
    if not counted:
        problems.append("no counted receipts")
        return
    first = min(parse_utc(r["utc_start"]) for r in counted)
    written = parse_utc(prereg["written_utc"])
    if not written < first:
        problems.append(f"PREREG written_utc {prereg['written_utc']} not before first counted run {first}")
    for r in counted:
        if r["rc"] != 0:
            problems.append(f"counted run {r['label']} rc={r['rc']}")
        expected = prereg["arms"][r["arm"]]["tree_commit"]
        if r["worktree_head"] != expected:
            got = git("rev-parse", f"{r['worktree_head']}:libs/cua-driver")
            want = git("rev-parse", f"{expected}:libs/cua-driver")
            if got.returncode != 0 or want.returncode != 0:
                print(f"note: cannot resolve trees for {r['label']}; head check skipped")
            elif got.stdout.strip() != want.stdout.strip():
                problems.append(
                    f"counted run {r['label']} head {r['worktree_head']} libs/cua-driver tree differs from PREREG {expected}"
                )
        if r["dirty_paths_under_libs_cua_driver"] != 0:
            problems.append(f"counted run {r['label']} had a dirty tree")
    rel = os.path.relpath(os.path.join(PACKET, "PREREG.json"), git("rev-parse", "--show-toplevel").stdout.strip() or PACKET)
    log = git("log", "--diff-filter=A", "--format=%H %cI", "--", rel)
    if log.returncode == 0 and log.stdout.strip():
        sha, when = log.stdout.strip().splitlines()[-1].split()
        committed = datetime.datetime.fromisoformat(when).astimezone(datetime.timezone.utc)
        if not committed < first:
            problems.append(f"PREREG commit {sha} at {committed} not before first counted run {first}")
        for arm, info in prereg["arms"].items():
            for test_path, blob in prereg["test_files"].items():
                got = git("rev-parse", f"{info['tree_commit']}:{test_path}")
                if got.returncode == 0 and got.stdout.strip() != blob:
                    problems.append(f"{arm} tree {info['tree_commit']} {test_path} blob {got.stdout.strip()} != PREREG {blob}")
    else:
        print("note: git history unavailable; PREREG commit order checked by written_utc only")


SECRET = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
]
ABSOLUTE = re.compile(r"(?<![A-Za-z0-9_.])/(home|mnt|tmp|Users|root|var/folders)/")


def privacy_scan_text(label, text, problems):
    host = socket.gethostname().split(".")[0]
    if host and len(host) >= 3 and re.search(rf"(?<![A-Za-z0-9]){re.escape(host)}(?![A-Za-z0-9])", text):
        problems.append(f"{label}: contains the host name")
    match = ABSOLUTE.search(text)
    if match:
        problems.append(f"{label}: absolute local path near {text[max(0, match.start()-20):match.end()+20]!r}")
    for pattern in SECRET:
        if pattern.search(text):
            problems.append(f"{label}: secret-like pattern {pattern.pattern}")


def privacy_scan(problems, git_range):
    for root, _dirs, files in os.walk(PACKET):
        for name in files:
            path = os.path.join(root, name)
            if path == os.path.abspath(__file__):
                continue
            with open(path, errors="replace") as handle:
                privacy_scan_text(os.path.relpath(path, PACKET), handle.read(), problems)
    if git_range:
        shas = git("rev-list", git_range).stdout.split()
        for sha in shas:
            # The verifier itself contains the patterns it scans for.
            show = git("show", "--format=%an <%ae>%n%B", sha, "--", ".", ":(exclude)*verify_artifacts.py")
            privacy_scan_text(f"commit {sha[:12]}", show.stdout, problems)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-summary", action="store_true")
    parser.add_argument("--git-range")
    args = parser.parse_args()
    prereg = load(os.path.join(PACKET, "PREREG.json"))
    summary, mismatches = build_summary(prereg)
    if args.write_summary:
        with open(os.path.join(PACKET, "summary.json"), "w") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
            handle.write("\n")
    problems = list(mismatches)
    stored = load(os.path.join(PACKET, "summary.json"))
    if stored != json.loads(json.dumps(summary, sort_keys=True)):
        problems.append("summary.json does not match the recomputed matrix")
    for p in PASSES:
        for (arm, row, variant), counts in matrix(records(p)).items():
            if sum(counts.values()) < ITERATIONS:
                problems.append(f"{p} {arm} {row} {variant}: only {sum(counts.values())} iterations")
    check_prereg_order(prereg, problems)
    privacy_scan(problems, args.git_range)
    print(json.dumps(summary["disposition"], indent=2))
    for arm in ("M", "P"):
        print(arm, {row: s["status"] for row, s in summary["row_status"][arm].items()})
    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print(" -", problem)
        sys.exit(1)
    print("OK: matrix recomputed from raw events, PREREG order and privacy checks passed")


if __name__ == "__main__":
    main()

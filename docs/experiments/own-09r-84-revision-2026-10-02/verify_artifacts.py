#!/usr/bin/env python3
"""Verify the OWN-09R packet (stdlib only).

- Recomputes every iteration verdict from raw ledger events, fixture-owned
  native counters, the target journal and (C ABI) the callback journal, and
  for the stdio rows from the fixture's own effect journal and the recorded
  response, independently of the harness's own verdict; any mismatch fails.
- Audits that a recorded PASS never relies on an absent later event.
- Rebuilds the matrix, row status per arm and the disposition from the rules
  in PREREG.json and compares them with summary.json.
- Checks PREREG.json was committed before the first counted run (receipts),
  that the copied harness blobs equal the OWN-09 originals, that every cited
  commit exists, and that every packet file is tracked and unmodified.
- Scans the packet (and with --git-range every commit's added lines) for
  absolute paths, the host name and secret patterns.

Usage:
  python3 verify_artifacts.py [--write-summary] [--git-range BASE..HEAD]
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
ARMS = ("M", "P")
SDK_PASSES = ("main", "stress")
OWN09_HARNESS_COMMIT = "bf07c8fe3"
HARNESS_FILES = (
    "libs/cua-driver/rust/crates/cua-driver-sdk/tests/own09_arm_m.rs",
    "libs/cua-driver/rust/crates/cua-driver-sdk/tests/own09_arm_p.rs",
    "libs/cua-driver/rust/crates/cua-driver-sdk/tests/own09_harness/mod.rs",
    "libs/cua-driver/rust/crates/cua-driver-sdk/tests/own09_harness/rows.rs",
)
problems = []


def problem(msg):
    problems.append(msg)


def git(*args):
    return subprocess.run(["git", "-C", PACKET, *args], capture_output=True, text=True)


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    return out


def records(route, pass_name=None):
    base = os.path.join(RAW, route, pass_name) if pass_name else os.path.join(RAW, route)
    out = []
    for arm in ARMS:
        directory = os.path.join(base, arm)
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith(".jsonl"):
                for rec in load_jsonl(os.path.join(directory, name)):
                    rec["_route"] = route
                    rec["_pass"] = pass_name or route
                    rec["_arm_dir"] = arm
                    out.append(rec)
    return out


class Ledger:
    def __init__(self, events):
        self.first = {}
        for seq, name, _t in events or []:
            self.first.setdefault(name, seq)

    def has(self, name):
        return name in self.first

    def before(self, a, b):  # OWN-09 semantics: absent b counts as "after"
        if a not in self.first:
            return False
        return b not in self.first or self.first[a] < self.first[b]

    def strictly_before(self, a, b):
        return a in self.first and b in self.first and self.first[a] < self.first[b]


def counter(rec, ident):
    return (rec.get("counters") or {}).get(str(ident), [0, 0])


def landed_ids(rec):
    return [e.get("id") for e in rec.get("journal") or [] if e.get("effect") == "applied"]


def is_ok(outcome):
    return isinstance(outcome, dict) and outcome.get("is_error") is False


# ------------------------------------------------------------ SDK rows ---
# Rules identical to the OWN-09 verifier (bf07c8fe3), plus the presence audit.

def recompute_sdk(rec):
    if rec.get("error"):
        return "HARNESS_ERROR"
    led = Ledger(rec.get("events"))
    checks = rec.get("checks") or {}
    row, variant = rec["row"], rec["variant"]
    if row == "R1" and variant == "cancel_race":
        return "PASS" if (led.has("admitted:2") or counter(rec, 2) == [0, 0]) else "FAIL"
    if row == "R1":
        ok = not led.has("admitted:2") and counter(rec, 2) == [0, 0] and led.before("native-exit:1", "admitted:3")
        return "PASS" if ok else "FAIL"
    if row == "R2":
        return "PASS" if led.before("native-exit:1", "admitted:2") else "FAIL"
    if row == "R4":
        ok = (is_ok(checks.get("later_outcome")) and led.before("invoke-end:2", "invocation-dropped:2")
              and counter(rec, 2) == [1, 1])
        return "PASS" if ok else "FAIL"
    if row == "R5":
        f2 = checks.get("foreign_end_of_a") or {}
        ok = (is_ok(checks.get("own_outcome")) and led.before("invoke-end:1", "invocation-dropped:1")
              and not led.has("admitted:2") and counter(rec, 2) == [0, 0]
              and (f2.get("is_error") is True or "driver_error" in f2) and landed_ids(rec) == [1])
        return "PASS" if ok else "FAIL"
    if row == "R6":
        ready = "session-cleanup" if variant.startswith("end_session") else "shutdown-returned"
        return "PASS" if (led.has(ready) and led.before("native-exit:1", ready)) else "FAIL"
    if row == "R7":
        landed = len(landed_ids(rec))
        if variant == "control_ack":
            return "PASS" if landed == 1 else "FAIL"
        ok = led.has("first-read:0") and led.before("native-exit:1", "admitted:2") and landed == 1
        return "PASS" if ok else "FAIL"
    if row == "R8":
        response = checks.get("in_flight_response") or {}
        result = response.get("result") if isinstance(response, dict) else None
        delivered = result is not None and result.get("isError") is not True
        dropped_early = not led.before("invoke-end:801", "invocation-dropped:801")
        return "IGNORED" if (delivered and not dropped_early) else "HONORED"
    raise ValueError(f"unknown SDK row {row}")


def presence_audit(rec):
    """A PASS whose ordering check uses a later event must contain it."""
    if rec.get("verdict") != "PASS":
        return
    led = Ledger(rec.get("events"))
    need = {("R1", "cancel_while_queued"): "admitted:3", ("R2", "cancel_after_admission"): "admitted:2",
            ("R2", "control_no_cancel"): "admitted:2", ("R7", "ack_lost_guarded_retry"): "admitted:2"}
    event = need.get((rec["row"], rec["variant"]))
    if event and not led.has(event):
        problem(f"vacuous PASS: {rec['_pass']} {rec['arm']} {rec['row']} {rec['variant']} iter {rec['iter']} lacks {event}")


# --------------------------------------------------------- C ABI rows ---

def recompute_cabi(rec):
    if rec.get("error"):
        return "HARNESS_ERROR"
    led = Ledger(rec.get("events"))
    cbs = rec.get("callbacks") or {}
    ids = landed_ids(rec)
    row, variant = rec["row"], rec["variant"]
    if row == "R4C":
        later = cbs.get("2", [])
        ok = (len(later) == 1 and later[0].get("status") == "Ok" and later[0].get("is_error") is False
              and len(cbs.get("1", [])) == 1
              and led.strictly_before("invoke-end:2", "invocation-dropped:2")
              and counter(rec, 2) == [1, 1] and ids.count(2) == 1)
        return "PASS" if ok else "FAIL"
    if row == "R1D":
        base = len(cbs.get("2", [])) == 1 and led.strictly_before("native-exit:1", "admitted:3")
        if variant == "flag_before_admission":
            ok = base and not led.has("admitted:2") and counter(rec, 2) == [0, 0] and 2 not in ids
        else:
            ok = base and led.strictly_before("native-exit:1", "admitted:2") and ids == [2]
        return "PASS" if ok else "FAIL"
    raise ValueError(f"unknown C ABI row {row}")


# --------------------------------------------------------- stdio rows ---

def recompute_stdio(rec):
    if rec.get("error") or rec.get("verdict") == "HARNESS_ERROR":
        return "HARNESS_ERROR"
    token = rec.get("token")
    applied = [e for e in rec.get("journal") or [] if e.get("event") == "effect-applied" and e.get("text") == token]
    response = rec.get("response") or {}
    delivered = "result" in response and (response.get("result") or {}).get("isError") is not True
    if rec["variant"] == "notification_mid_native":
        if len(applied) > 1:
            return "DUPLICATE"
        return "IGNORED" if (len(applied) == 1 and delivered) else "HONORED"
    alive = (rec.get("checks") or {}).get("transport_alive_after") is True
    return "PASS" if (len(applied) == 1 and delivered and alive) else "FAIL"


def stdio_phase_audit(rec):
    checks = rec.get("checks") or {}
    if rec.get("variant") == "notification_mid_native" and rec.get("verdict") != "HARNESS_ERROR":
        if not (checks.get("phase_enter_before_notify") and checks.get("phase_notify_before_applied")):
            problem(f"R8 stdio {rec['arm']} iter {rec['iter']}: notification not provably mid native work")


# ------------------------------------------------------------- matrix ---

def key(rec):
    route = rec["_route"]
    return (rec["arm"], f"{route}/{rec['variant']}" if route != "sdk" else f"sdk/{rec['variant']}", rec["row"])


def build():
    table = collections.defaultdict(collections.Counter)
    by_pass = collections.defaultdict(collections.Counter)
    all_recs = []
    for pass_name in SDK_PASSES:
        for rec in records("sdk", pass_name):
            all_recs.append(rec)
    all_recs += records("cabi")
    all_recs += records("r8_stdio")
    for rec in all_recs:
        if rec["arm"] != rec["_arm_dir"]:
            problem(f"arm label {rec['arm']} in directory {rec['_arm_dir']}")
        route = rec["_route"]
        if route == "sdk":
            verdict = recompute_sdk(rec)
            presence_audit(rec)
        elif route == "cabi":
            verdict = recompute_cabi(rec)
        else:
            verdict = recompute_stdio(rec)
            stdio_phase_audit(rec)
        if verdict != rec.get("verdict"):
            problem(f"verdict mismatch {route} {rec['_pass']} {rec['arm']} {rec['row']} {rec['variant']} "
                    f"iter {rec['iter']}: recorded {rec.get('verdict')} recomputed {verdict}")
        row = rec["row"]
        if route == "cabi":
            row = "R1" if row == "R1D" else "R4" if row == "R4C" else row
        variant = f"{'c_abi' if route == 'cabi' else 'mcp_stdio' if route == 'r8_stdio' else 'sdk'}/{rec['variant']}"
        table[(rec["arm"], row, variant)][verdict] += 1
        by_pass[(rec["arm"], row, variant, rec["_pass"])][verdict] += 1
    return table, by_pass, all_recs


def counts(table, arm, row, variant):
    return table.get((arm, row, variant), collections.Counter())


def zero_fail(table, arm, row, variant, n):
    c = counts(table, arm, row, variant)
    total = sum(c.values())
    return total == n and c.get("PASS", 0) == n


def all_verdict(table, arm, row, variant, verdict, n):
    c = counts(table, arm, row, variant)
    return sum(c.values()) == n and c.get(verdict, 0) == n


def evaluate(prereg, table):
    rows = prereg["rows"]
    status = {}
    for arm in ARMS:
        st = {}
        for row in ("R1", "R2", "R4", "R5", "R6", "R7"):
            gating = [(v, spec["n_per_arm"]) for v, spec in rows[row]["variants"].items()
                      if spec.get("gating") and spec.get("arm", arm + " only").startswith(arm)]
            results = {v: dict(counts(table, arm, row, v.replace("R1D ", "").replace("R4C ", "")))
                       for v, _ in gating}
            ok = all(zero_fail(table, arm, row, v.replace("R1D ", "").replace("R4C ", ""), n) for v, n in gating)
            st[row] = {"status": "PASS" if ok else "FAIL", "gating_variants": results}
        st["R3"] = {"status": "BLOCKED", "reason": rows["R3"]["reason"]}
        st["R8"] = {
            "status": "OWNER_DECISION",
            "sdk_notification_in_flight": dict(counts(table, arm, "R8", "sdk/notification_in_flight")),
            "mcp_stdio_notification_mid_native": dict(counts(table, arm, "R8", "mcp_stdio/notification_mid_native")),
            "mcp_stdio_control_no_cancel": dict(counts(table, arm, "R8", "mcp_stdio/control_no_cancel")),
        }
        status[arm] = st
    controls = {
        "negative_no_cancel_zero_failures": {
            arm: all([
                zero_fail(table, arm, "R1", "c_abi/control_no_cancel", 40),
                zero_fail(table, arm, "R2", "sdk/control_no_cancel", 40),
                zero_fail(table, arm, "R6", "sdk/shutdown_no_cancel", 40),
                zero_fail(table, arm, "R6", "sdk/end_session_no_cancel", 40),
                zero_fail(table, arm, "R7", "sdk/control_ack", 40),
                zero_fail(table, arm, "R8", "mcp_stdio/control_no_cancel", 10),
            ]) for arm in ARMS},
        "M_reproduces_gaps": {
            "R1D_flag_before_admission": counts(table, "M", "R1", "c_abi/flag_before_admission").get("FAIL", 0),
            "R2_cancel_after_admission": counts(table, "M", "R2", "sdk/cancel_after_admission").get("FAIL", 0),
            "R6_shutdown_after_cancel": counts(table, "M", "R6", "sdk/shutdown_after_cancel").get("FAIL", 0),
            "R6_end_session_after_cancel": counts(table, "M", "R6", "sdk/end_session_after_cancel").get("FAIL", 0),
            "R7_ack_lost_guarded_retry": counts(table, "M", "R7", "sdk/ack_lost_guarded_retry").get("FAIL", 0),
        },
        "broken_controls_detected": {
            arm: {
                "R1 sdk/broken_detach_on_cancel": all_verdict(table, arm, "R1", "sdk/broken_detach_on_cancel", "FAIL", 40),
                "R4 sdk/broken_name_keyed": all_verdict(table, arm, "R4", "sdk/broken_name_keyed", "FAIL", 40),
                "R4 c_abi/broken_latest_token": all_verdict(table, arm, "R4", "c_abi/broken_latest_token", "FAIL", 40),
                "R5 sdk/broken_session_keyed": all_verdict(table, arm, "R5", "sdk/broken_session_keyed", "FAIL", 40),
                "R6 sdk/broken_ready_on_cancel": all_verdict(table, arm, "R6", "sdk/broken_ready_on_cancel", "FAIL", 40),
                "R7 sdk/broken_blind_retry": all_verdict(table, arm, "R7", "sdk/broken_blind_retry", "FAIL", 40),
                "R8 sdk/broken_honoring_transport": all_verdict(table, arm, "R8", "sdk/broken_honoring_transport", "HONORED", 40),
                **({
                    "R2 sdk/broken_plain_closure": all_verdict(table, arm, "R2", "sdk/broken_plain_closure", "FAIL", 40),
                    "R6 sdk/broken_plain_closure_shutdown_after_cancel": all_verdict(
                        table, arm, "R6", "sdk/broken_plain_closure_shutdown_after_cancel", "FAIL", 40),
                    "R7 sdk/broken_plain_closure": all_verdict(table, arm, "R7", "sdk/broken_plain_closure", "FAIL", 40),
                } if arm == "P" else {}),
            } for arm in ARMS},
    }
    controls["M_reproduces_gaps_ok"] = all(v > 0 for v in controls["M_reproduces_gaps"].values())
    p = status["P"]
    duplicate = (counts(table, "P", "R7", "sdk/ack_lost_guarded_retry").get("FAIL", 0) > 0
                 or counts(table, "P", "R5", "sdk/foreign_session_and_transport").get("FAIL", 0) > 0
                 or any(counts(table, a, "R8", "mcp_stdio/notification_mid_native").get("DUPLICATE", 0)
                        for a in ARMS))
    readiness = (counts(table, "P", "R6", "sdk/shutdown_after_cancel").get("FAIL", 0) > 0
                 or counts(table, "P", "R6", "sdk/end_session_after_cancel").get("FAIL", 0) > 0)
    unit = load_unit()
    gating_rows = ("R1", "R2", "R4", "R6", "R7")
    failing = [r for r in gating_rows + ("R5",) if p[r]["status"] != "PASS"]
    controls_ok = (controls["negative_no_cancel_zero_failures"]["M"]
                   and controls["negative_no_cancel_zero_failures"]["P"]
                   and controls["M_reproduces_gaps_ok"]
                   and all(all(v.values()) for v in controls["broken_controls_detected"].values()))
    if duplicate or readiness:
        disposition = "KILL"
    elif not failing and unit.get("gate_green") and controls_ok:
        disposition = "KEEP"
    else:
        disposition = "REVISE"
    return status, controls, {
        "question": prereg["disposition_rule"]["question"],
        "disposition": disposition,
        "failing_rows": failing,
        "p_duplicate_effect": duplicate,
        "p_readiness_while_running": readiness,
        "unit_gate_green": unit.get("gate_green"),
        "controls_ok": controls_ok,
    }


def load_unit():
    path = os.path.join(RAW, "unit", "unit-summary.json")
    if not os.path.exists(path):
        problem("raw/unit/unit-summary.json missing")
        return {}
    unit = json.load(open(path, encoding="utf-8"))
    for crate in ("cua-driver-core", "cua-driver-sdk", "cua-driver"):
        log = os.path.join(RAW, "unit", f"{crate}.txt")
        if not os.path.exists(log):
            problem(f"unit log missing for {crate}")
            continue
        text = open(log, encoding="utf-8").read()
        passed = sum(int(m) for m in re.findall(r"^test result: ok\. (\d+) passed", text, re.M))
        failed = len(re.findall(r"^test result: FAILED", text, re.M))
        if unit["crates"][crate]["passed"] != passed or failed:
            problem(f"unit summary mismatch for {crate}: {passed} passed, {failed} FAILED results")
    return unit


# ------------------------------------------------------- provenance ---

def check_git(prereg):
    for name, sha in list(prereg["sources"]["revision_commits"].items()) + [
            ("merge", prereg["sources"]["merge_commit"]), ("harness", prereg["sources"]["harness_commit"]),
            ("base", prereg["sources"]["base_upstream_main"]), ("pr84", prereg["sources"]["pr84_head"])]:
        if re.fullmatch(r"[0-9a-f]{7,40}", str(sha)) and git("cat-file", "-e", f"{sha}^{{commit}}").returncode:
            problem(f"cited commit {name} {sha} does not exist")
    for path in HARNESS_FILES:
        orig = git("rev-parse", f"{OWN09_HARNESS_COMMIT}:{path}").stdout.strip()
        here = git("rev-parse", f"HEAD:{path}").stdout.strip()
        if path.endswith("own09_arm_m.rs"):
            continue  # arm M runs on the base tree (raw/m-tree.patch records it)
        if not orig or orig != here:
            problem(f"harness blob differs from OWN-09 original: {path}")
    log = git("log", "--diff-filter=A", "--format=%cI", "--", "PREREG.json").stdout.split()
    if not log:
        problem("PREREG.json is not committed")
        return
    prereg_time = datetime.datetime.fromisoformat(log[-1]).astimezone(datetime.timezone.utc)
    receipts = os.path.join(RAW, "receipts.jsonl")
    if os.path.exists(receipts):
        for rec in load_jsonl(receipts):
            start = datetime.datetime.fromisoformat(rec["utc_start"].replace("Z", "+00:00"))
            if start <= prereg_time:
                problem(f"counted run {rec['label']} started before the PREREG commit")
    else:
        problem("raw/receipts.jsonl missing")


def check_tree():
    rel = os.path.relpath(PACKET, git("rev-parse", "--show-toplevel").stdout.strip())
    status = git("status", "--porcelain", "--ignored", "--", ".").stdout.strip()
    for line in status.splitlines():
        if "__pycache__" in line:
            continue
        problem(f"packet file not committed as verified: {line}")
    _ = rel


SECRET = re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY|"
                    r"(?:API|SECRET)_?KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,})")


def privacy_patterns():
    host = socket.gethostname()
    pats = [re.compile(r"/(?:home|mnt|tmp|root|Users)/[A-Za-z0-9_.\-]+"), SECRET]
    if host and len(host) > 2:
        pats.append(re.compile(re.escape(host)))
    return pats


def scan_text(label, text, pats):
    for pat in pats:
        m = pat.search(text)
        if m:
            problem(f"privacy: {label} matches {pat.pattern[:30]!r}: {m.group(0)[:40]!r}")


def scan_packet(pats):
    for root, _dirs, files in os.walk(PACKET):
        if "__pycache__" in root:
            continue
        for name in files:
            path = os.path.join(root, name)
            try:
                text = open(path, encoding="utf-8").read()
            except UnicodeDecodeError:
                continue
            if name == "verify_artifacts.py":
                text = text.replace("/(?:home|mnt|tmp|root|Users)/", "")
            scan_text(os.path.relpath(path, PACKET), text, pats)


def scan_range(rng, pats):
    for sha in git("rev-list", rng).stdout.split():
        diff = git("show", "--format=%an %ae%n%B", "--unified=0", sha).stdout
        added = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
        added = added.replace("/(?:home|mnt|tmp|root|Users)/", "")
        header = diff.split("\ndiff --git")[0]
        scan_text(f"commit {sha[:9]}", header + "\n" + added, pats)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-summary", action="store_true")
    parser.add_argument("--git-range")
    args = parser.parse_args()
    prereg = json.load(open(os.path.join(PACKET, "PREREG.json"), encoding="utf-8"))
    table, by_pass, recs = build()
    status, controls, disposition = evaluate(prereg, table)
    summary = {
        "lane": "OWN-09R",
        "matrix": {f"{a}|{r}|{v}": dict(c) for (a, r, v), c in sorted(table.items())},
        "matrix_by_pass": {f"{a}|{r}|{v}|{p}": dict(c) for (a, r, v, p), c in sorted(by_pass.items())},
        "row_status": status,
        "controls": controls,
        "disposition": disposition,
        "iterations_total": len(recs),
        "harness_errors": sum(1 for r in recs if r.get("verdict") == "HARNESS_ERROR"),
        "provider": {"attempts": 0, "reached": 0},
    }
    path = os.path.join(PACKET, "summary.json")
    if args.write_summary:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=1, sort_keys=True)
            handle.write("\n")
    recorded = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    if recorded != json.loads(json.dumps(summary, sort_keys=True)):
        problem("summary.json differs from the recomputation")
    check_git(prereg)
    pats = privacy_patterns()
    scan_packet(pats)
    if args.git_range:
        scan_range(args.git_range, pats)
    if not args.write_summary:
        check_tree()
    print(json.dumps({"disposition": disposition, "iterations": len(recs),
                      "harness_errors": summary["harness_errors"]}, indent=1))
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems[:60]:
            print(" -", p)
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()

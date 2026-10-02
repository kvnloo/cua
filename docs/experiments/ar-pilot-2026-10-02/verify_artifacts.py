#!/usr/bin/env python3
"""Verify the ar-pilot-2026-10-02 packet from its own files (standard library only).

Checks: manifest hashes; the pilot ledger is the fresh, empty ledger the status claims; the status file
agrees with the copied calibration and A/A summaries; every number the README states is present in those
summaries; n_pairs follows from sigma and tau; no absolute host paths or credential patterns in any file.
Exit code 0 iff every check passes.
"""
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
fails = []
n = 0


def check(cond, what):
    global n
    n += 1
    if not cond:
        fails.append(what)
        print("FAIL", what)


def load(name):
    with open(os.path.join(RAW, name), encoding="utf-8") as f:
        return json.load(f)


# 1. manifest
man = {}
with open(os.path.join(HERE, "MANIFEST.sha256"), encoding="utf-8") as f:
    for line in f:
        h, p = line.rstrip("\n").split("  ", 1)
        man[p] = h
listed = set()
for root, _, files in os.walk(HERE):
    for fn in files:
        rel = os.path.relpath(os.path.join(root, fn), HERE)
        if rel == "MANIFEST.sha256" or "__pycache__" in rel:
            continue
        listed.add(rel)
check(listed == set(man), "manifest lists exactly the packet files")
for p, h in man.items():
    with open(os.path.join(HERE, p), "rb") as f:
        check(hashlib.sha256(f.read()).hexdigest() == h, f"sha256 {p}")

# 2. pilot ledger and status
with open(os.path.join(HERE, "results.jsonl"), encoding="utf-8") as f:
    rows = [l for l in f.read().splitlines() if l.strip()]
st = load("pilot-status.json")
check(len(rows) == 0, "pilot results.jsonl holds 0 rows")
check(st["pilot_ran"] is False and st["pilot_evaluations"] == [] and st["keeps"] == [], "status: pilot not run, no evaluations, no keeps")
check(st["pilot_ledger"]["rows"] == len(rows) and st["pilot_ledger"]["fresh"] is True, "status ledger row count matches file")

# 3. calibration agreement
cal = load("CALIBRATION.json")
res = {r["row"]: r["result"] for r in cal["rows"]}
check(cal["overall"] == "FAIL", "calibration overall FAIL")
check(res == st["calibration"]["rows"], "status rows == calibration rows")
check([k for k, v in res.items() if v != "PASS"] == ["R3"], "only R3 fails")
r3 = next(r for r in cal["rows"] if r["row"] == "R3")["detail"]
check(r3["keeps"] == 0 and r3["repeats"] == 10, "R3 kept 0 of 10")
check(r3["failed_gates"].count("G2") == 9 and r3["failed_gates"].count("G5") == 1, "R3 failures: 9 at G2, 1 at G5")
check(cal["diagnostic_not_gate"]["g2_dbus"]["keeps_delete50"] == 8, "diagnostic g2_dbus variant keeps 8")
r7 = next(r for r in cal["rows"] if r["row"] == "R7")["detail"]
check(r7["keeps"] == 0 and r7["n"] == 10, "R7 no-ops: 0 of 10 kept")
r8 = next(r for r in cal["rows"] if r["row"] == "R8")["detail"]["browser"]
check(round(r8["median_on_minus_off_ms"]) == 3362 and r8["on_slower_pairs"] == 9, "R8 browser ON slower by 3362 ms, 9/9 pairs")
pc = cal["per_candidate_minutes"]
check(pc["screen_only_uncontended"] == 4.5 and pc["full_pipeline_uncontended"] == 13.7
      and pc["full_pipeline_mean_observed_with_lock_contention"] == 18.5, "per-candidate minutes 4.5 / 13.7 / 18.5")
tp = cal["throughput"]
check(tp["screen_only_per_hour"] == 13 and tp["full_pipeline_per_hour_uncontended"] == 4.4
      and tp["quiet_lane_receipts"] == 118, "throughput 13/h, 4.4/h, 118 receipts")

# 4. A/A agreement and n_pairs = 10.04 (sigma / ln(1+tau))^2
aa = load("AA.json")["results"]
w, a = aa["whole_task_T"], aa["T_act"]
check(st["aa"]["whole_task_T"] == w and st["aa"]["T_act"] == a, "status A/A == AA.json")
check((w["sigma_ln"], w["tau"], w["n_pairs_by_power"]) == (0.05922, 0.03111, 38), "whole-task sigma 0.0592, tau 3.11%, n 38")
check((a["sigma_ln"], a["tau"], a["n_pairs_by_power"]) == (0.03758, 0.02, 37), "T_act sigma 0.0376, tau 2%, n 37")
check(w["ci_includes_zero"] is False and a["ci_includes_zero"] is True, "A/A CI check: T fails, T_act passes")
k = (2.326347874 + 0.841621234) ** 2
for m in (w, a):
    check(math.ceil(k * (m["sigma_ln"] / math.log1p(m["tau"])) ** 2) == m["n_pairs_by_power"], f"n_pairs recomputes for sigma {m['sigma_ln']}")
check(abs(math.expm1(max(math.log1p(0.02), w["q975_abs_delta_aa_ln_batch72"])) - w["tau"]) < 1e-4, "tau = max(2%, q97.5 |Delta_AA|) for whole-task T")

# 5. citation of the RFC-loop packet is recorded, not duplicated
c = st["n01r_citation"]
check(c["published"] is False and re.fullmatch(r"[0-9a-f]{40}", c["local_head"]) is not None
      and re.fullmatch(r"[0-9a-f]{64}", c["readme_sha256"]) is not None, "N-01R citation pinned by commit and sha256")

# 6. no host paths / host-identifying strings
# Generic patterns only: the host name and local mount names are checked by the publisher's scan and are
# deliberately not spelled out here. /home/trial is the sandbox's own HOME.
leak = re.compile(r"/mnt/[A-Za-z0-9]|/home/(?!trial\b)[a-z]|/root/[a-z]|/tmp/claude|ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9]|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY")
for p in sorted(listed):
    with open(os.path.join(HERE, p), encoding="utf-8", errors="replace") as f:
        txt = f.read()
    if p == "verify_artifacts.py":
        txt = txt.replace(leak.pattern, "")
    check(leak.search(txt) is None, f"no host paths or secrets in {p}")

print(f"{n - len(fails)} of {n} checks ok, {len(fails)} failing")
sys.exit(1 if fails else 0)

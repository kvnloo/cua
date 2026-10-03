#!/usr/bin/env python3
"""Verify the ar-pilot2-2026-10-02 packet from its own files (standard library only).

Checks: manifest hashes; the pilot ledger is the fresh, empty ledger the status claims; the status file
agrees with the copied calibration 2 and fix-round summaries; the numbers the README states are present in
those summaries; tau and n_pairs follow from the A/A figures; no absolute host paths or credential patterns
in any file. Exit code 0 iff every check passes.
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
check(st["pilot_ran"] is False and st["pilot_evaluations"] == [] and st["keeps"] == [],
      "status: pilot not run, no evaluations, no keeps")
check(st["pilot_ledger"]["rows"] == len(rows) and st["pilot_ledger"]["fresh"] is True,
      "status ledger row count matches file")

# 3. calibration 2 agreement
cal = load("CALIBRATION2.json")
res = {r["row"]: r["result"] for r in cal["rows"]}
amd = {r["row"]: r["result"] for r in cal["amendment_rows"]}
row = {r["row"]: r["detail"] for r in cal["rows"]}
check(cal["overall"] == "FAIL" and st["calibration2"]["overall"] == "FAIL", "calibration 2 overall FAIL")
check(res == st["calibration2"]["rows"] and amd == st["calibration2"]["amendment_rows"],
      "status rows == calibration 2 rows")
check(len(res) == 12 and [k for k, v in res.items() if v != "PASS"] == ["R10"], "11 of 12 rows pass, only R10 fails")
check(cal["rows_passed"] == "11/12", "rows_passed 11/12")
check(amd == {"R10b": "PASS"}, "amendment R10b PASS")
check(cal["evaluator"]["harness_commit"].startswith("f56422868") and cal["evaluator"]["modified_by_calibration"] is False
      and cal["evaluator"]["manifest_sha256"].startswith("836a646e"), "evaluator f56422868, manifest 836a646e, unchanged")
check(cal["prereg"]["commit"] == "ca7b2882d" and cal["amendment_prereg"]["commit"] == "afeb75ffa", "prereg commits")
check(cal["decision_metric"] == "T_act" and cal["tau"] == 0.02, "T_act decides, tau 2%")
r3 = row["R3"]
check(r3["keeps"] == 10 and r3["repeats"] == 10, "R3 KEEP 10 of 10")
check(any("-17.8..-18.6%" in x for x in cal["findings"]), "R3 confirm Delta -17.8..-18.6% stated in findings")
check(row["R1"]["verdicts"] == ["REJECT"] and row["R2"]["verdicts"] == ["REVERT"], "R1 REJECT (G1), R2 REVERT")
check(round(row["R2"]["screen"][0] * 100, 1) == 15.4, "R2 screen Delta +15.4%")
check(row["R4"]["failed_gate"] == "G2" and all(r.startswith("unverified_success") for r in row["R4"]["reasons"]),
      "R4 G2 unverified_success")
r7 = row["R7"]
d7 = [v for v in r7["screen_delta"].values() if v is not None]
check(r7["keeps"] == 0 and r7["n"] == 10 and r7["verdicts"]["noop05"] == "REJECT", "R7 0 of 10 kept; noop05 REJECT")
check(round(min(d7) * 100, 2) == -0.61 and round(max(d7) * 100, 2) == 0.21, "R7 Delta -0.61% to +0.21%")
r8 = row["R8"]["browser"]
check(round(r8["median_on_minus_off_ms"]) == 2990 and r8["on_slower_pairs"] == 10 and r8["complete_pairs"] == 10,
      "R8 browser ON slower by 2990 ms, 10/10 pairs")
g8 = row["R8"]["gtk_diagnostic"]
check(g8["ci95"][0] < 0 < g8["ci95"][1], "R8 GTK checkbox CI includes 0")
check(row["R9"]["failed_gate"] == "G2" and row["R9"]["new_socket_reason"] is True, "R9 REJECT at G2 with new_socket")
r10 = row["R10"]["repeats"]
check(all(r["g7_pass"] and r["verdict"] == "KEEP" and r["manipulation_ok"] is False for r in r10),
      "R10: G7 pass and KEEP on both repeats, manipulation check failed")
check([round(r["cpu_some_share_median"], 4) for r in r10] == [0.0017, 0.0011]
      and round(row["R10"]["unloaded_R3_cpu_some_share_median"], 4) == 0.0035, "R10 PSI 0.0017/0.0011 vs 0.0035")
r10b = cal["amendment_rows"][0]["detail"]["repeats"]
check([r["verdict"] for r in r10b] == ["KEEP", "INFRA"] and all(r["g7_pass"] and r["manipulation_ok"] for r in r10b),
      "R10b r01 KEEP, r02 INFRA; G7 and manipulation pass on both")
check([round(r["g7_metrics"]["share"], 3) for r in r10b] == [0.985, 1.008], "R10b G7 share 0.985/1.008")
check(all(b[0] <= r["g7_metrics"]["delta_off"] <= b[1] for r in r10b for b in [r["g7_metrics"]["trace_off_band"]]),
      "R10b trace-off Delta inside band")
lead = [l for l in cal["lord"]["ledger_tests"] if l["eval_id"].startswith("ar-20261002-cal2-delete50-r")]
check(len(lead) == 10 and all(l["rejected"] and l["p_value"] < l["alpha_i"] for l in lead), "R3 LORD++: p below alpha_i on all 10")
alphas = [l["alpha_i"] for l in cal["lord"]["ledger_tests"]] + [l["alpha_i"] for l in cal["amendment_lord"]]
check(round(min(alphas), 5) == 0.00125 and round(max(alphas), 4) == 0.0057, "alpha_i range 1.25e-3..5.7e-3")
dg = cal["diagnostics_not_gate"]["g1_flake"]
check(dg["g1_runs_total"] == 15 and dg["g1_test_failures"] == 2 and sorted(dg["rejects"]) == ["noop05", "sleep20"],
      "F7: G1 flake 2 of 15 (noop05, sleep20)")
ds = dg["diagnostic_screens"]
check(round(ds["sleep20"]["delta"] * 100, 1) == 6.2 and round(ds["sleep20"]["median_diff_ms"]) == 21
      and round(ds["noop05"]["delta"] * 100, 2) == 0.27, "diagnostic screens: sleep20 +6.2% +21 ms, noop05 +0.27%")
pc = cal["per_candidate_minutes"]
check((pc["g0_reject"], pc["screen_only_uncontended_incl_g1"], pc["screen_only_observed"],
       pc["full_pipeline_uncontended_incl_g1"], pc["full_pipeline_observed_with_lock_waits"]) == (0.01, 8.0, 9.1, 16.6, 37.8),
      "per-candidate minutes 0.01 / 8.0 / 9.1 / 16.6 / 37.8")
tp = cal["throughput"]
check((tp["screen_only"]["per_hour_uncontended"], tp["screen_only"]["per_hour_observed"],
       tp["full_pipeline"]["per_hour_uncontended"], tp["full_pipeline"]["per_hour_observed"]) == (7.5, 6.6, 3.6, 1.6),
      "throughput 7.5/6.6/3.6/1.6 per hour")
check(tp["quiet_lane_receipts"] == 166 and round(tp["quiet_lane_held_min"]) == 155 and tp["calibration_wall_h"] == 12.25,
      "166 blocks, 155 min held, 12.3 h wall")
check(st["calibration2"]["packet_commit"].startswith("651405c1b"), "calibration 2 packet commit 651405c1b")

# 4. fix round and A/A under the chosen design
fx = load("FIX.json")
check(fx["overall"] == "PASS" and fx["git"]["commits"]["harness_fix"].startswith("f56422868"), "fix round PASS at f56422868")
pr = fx["aa_rerun"]["primary"]
check(pr["ci_includes_zero"] is True and round(pr["T_act_delta_aa_ln"] * 100, 2) == 0.23
      and [round(x * 100, 2) for x in pr["ci95_ln"]] == [-0.26, 0.71], "A/A T_act +0.23% (CI -0.26..+0.71%) PASS")
check(st["fix_round"]["aa_primary_T_act"] == pr, "status A/A primary == FIX.json")
check("96/96 task, 24/24 soak verified" in fx["aa_rerun"]["secondary"]["correctness"], "A/A 96/96 + 24/24 verified")
aa = st["aa_chosen_design"]
tau = max(math.log1p(0.02), aa["q975_abs_delta_aa_ln"])
check(abs(math.expm1(tau) - aa["tau"]) < 1e-9, "tau = max(2%, q97.5 |Delta_AA|) = 2% floor")
k = (2.326347874 + 0.841621234) ** 2
check(math.ceil(k * (aa["sigma_ln"] / math.log1p(aa["tau"])) ** 2) == aa["n_pairs_by_power"] == 8, "n_pairs 8 recomputes from sigma 0.0173")
check(round(aa["sigma_ln"], 4) == 0.0173 and round(aa["guardrail"]["sigma_ln"], 4) == 0.0963
      and round(aa["guardrail"]["tau"] * 100, 2) == 4.18, "A/A sigma 0.0173 / 0.0963, guardrail tau 4.18%")

# 5. citation of the RFC-loop packet is pinned, not duplicated
c = st["n01r_citation"]
check(re.fullmatch(r"[0-9a-f]{40}", c["commit"]) is not None and c["commit"].startswith("3bb4a7fc7")
      and re.fullmatch(r"[0-9a-f]{64}", c["readme_sha256"]) is not None, "N-01R citation pinned by commit and sha256")

# 6. no host paths / host-identifying strings / credentials (generic patterns; the publisher's scan
# checks the host name separately). /home/trial is the sandbox's own HOME.
leak = re.compile(r"/mnt/[A-Za-z0-9]|/home/(?!trial\b)[a-z]|/root/[a-z]|/tmp/claude|ghp_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9]|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY")
for p in sorted(listed):
    with open(os.path.join(HERE, p), encoding="utf-8", errors="replace") as f:
        txt = f.read()
    if p == "verify_artifacts.py":
        txt = txt.replace(leak.pattern, "")
    check(leak.search(txt) is None, f"no host paths or secrets in {p}")

print(f"{n - len(fails)} of {n} checks ok, {len(fails)} failing")
sys.exit(1 if fails else 0)

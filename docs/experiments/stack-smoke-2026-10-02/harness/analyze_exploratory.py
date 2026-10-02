"""Exploratory delay-control analysis (EXPLORATORY_PREREG.json). stdlib only.

usage: analyze_exploratory.py <raw dir> <plan.json> <plan_exploratory.json> <out json>
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import sign_test, wilson  # noqa: E402

raw, plan_p, xplan_p, out_p = map(Path, sys.argv[1:5])
runs = json.loads(plan_p.read_text())["runs"] + json.loads(xplan_p.read_text())["runs"]
S = {}
for r in runs:
    p = raw / "runs" / r["run_id"] / "run_summary.json"
    if p.exists():
        S[r["run_id"]] = json.loads(p.read_text())
cell = {}
by_pair = {}
for r in runs:
    if r["task"] != "browser" or r["driver_key"] != "pinned_0_21_0" or r["run_id"] not in S:
        continue
    s = S[r["run_id"]]
    v = s["oracle"].get("verdict")
    c = cell.setdefault(r["arm"], {"n": 0, "pass": 0, "unknown": 0, "hermes_rc_nonzero": 0})
    c["n"] += 1
    c["pass"] += v == "pass"
    c["unknown"] += v not in ("pass", "fail")
    c["hermes_rc_nonzero"] += s["hermes_rc"] != 0
    by_pair.setdefault(r["pair"], {})[r["arm"]] = s
for c in cell.values():
    c["pass_rate"] = round(c["pass"] / c["n"], 4)
    c["pass_wilson95"] = wilson(c["pass"], c["n"])


def fisher_two_sided(a, b, c, d):
    """Exact two-sided Fisher p for [[a,b],[c,d]]."""
    n = a + b + c + d
    r1, c1 = a + b, a + c
    def p(x):
        return math.comb(r1, x) * math.comb(n - r1, c1 - x) / math.comb(n, c1)
    obs = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if p(x) <= obs + 1e-12))


def paired(arm_a, arm_b):
    pa = [(p[arm_a], p[arm_b]) for p in by_pair.values() if arm_a in p and arm_b in p]
    b = sum(x["oracle"]["verdict"] == "pass" and y["oracle"]["verdict"] != "pass" for x, y in pa)
    c = sum(y["oracle"]["verdict"] == "pass" and x["oracle"]["verdict"] != "pass" for x, y in pa)
    same = sum(x["state_db"]["tool_sequence"] == y["state_db"]["tool_sequence"] for x, y in pa)
    return {"pairs": len(pa), f"{arm_a}_only_pass": b, f"{arm_b}_only_pass": c, "sign_test_p": sign_test(b, c),
            "tool_sequence_identical": same}


def unpaired(arm_a, arm_b):
    A, B = cell.get(arm_a), cell.get(arm_b)
    return {"table": [[A["pass"], A["n"] - A["pass"]], [B["pass"], B["n"] - B["pass"]]],
            "fisher_two_sided_p": round(fisher_two_sided(A["pass"], A["n"] - A["pass"], B["pass"], B["n"] - B["pass"]), 4)}


shadow_present = [a for a in ("on", "onnowait", "outage") if a in cell]
shadow_absent = [a for a in ("off", "offdelay") if a in cell]
sp = (sum(cell[a]["pass"] for a in shadow_present), sum(cell[a]["n"] for a in shadow_present))
sa = (sum(cell[a]["pass"] for a in shadow_absent), sum(cell[a]["n"] for a in shadow_absent))
out = {
    "schema": "stack_smoke.exploratory.v1", "browser_cells": cell,
    "E1_offdelay_vs_off": paired("offdelay", "off"), "E2_onnowait_vs_on": paired("onnowait", "on"),
    "E1u_offdelay_vs_on": unpaired("offdelay", "on"), "E2u_onnowait_vs_off": unpaired("onnowait", "off"),
    "pooled_shadow_present_vs_absent": {"present": {"arms": shadow_present, "pass": sp[0], "n": sp[1]},
                                        "absent": {"arms": shadow_absent, "pass": sa[0], "n": sa[1]},
                                        "fisher_two_sided_p": round(fisher_two_sided(sp[0], sp[1] - sp[0], sa[0], sa[1] - sa[0]), 4)},
}
out_p.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps(out, indent=1, sort_keys=True))

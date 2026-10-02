"""Replication analysis (REPLICATION_PREREG.json): browser on vs off on fresh pairs, alone and pooled.

usage: analyze_replication.py <raw dir> <plan.json> <plan_replication.json> <out json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import fisher_two_sided, sign_test, wilson  # noqa: E402


def load(raw, plan):
    S = {}
    for r in plan:
        p = raw / "runs" / r["run_id"] / "run_summary.json"
        if p.exists():
            S[r["run_id"]] = json.loads(p.read_text())
    return S


def stats(plan, S):
    pairs = {}
    for r in plan:
        if r["task"] == "browser" and r["arm"] in ("on", "off") and r["driver_key"] == "pinned_0_21_0" and r["run_id"] in S:
            pairs.setdefault(r["pair"], {})[r["arm"]] = S[r["run_id"]]
    comp = [p for p in pairs.values() if set(p) == {"on", "off"}]
    on_pass = sum(p["on"]["oracle"].get("verdict") == "pass" for p in comp)
    off_pass = sum(p["off"]["oracle"].get("verdict") == "pass" for p in comp)
    b = sum(p["on"]["oracle"].get("verdict") == "pass" and p["off"]["oracle"].get("verdict") != "pass" for p in comp)
    c = sum(p["off"]["oracle"].get("verdict") == "pass" and p["on"]["oracle"].get("verdict") != "pass" for p in comp)
    n = len(comp)
    return {"pairs": n, "on_pass": on_pass, "off_pass": off_pass, "on_wilson95": wilson(on_pass, n),
            "off_wilson95": wilson(off_pass, n), "discordant_on_only_pass": b, "discordant_off_only_pass": c,
            "sign_test_p": sign_test(b, c),
            "fisher_two_sided_p": round(fisher_two_sided(on_pass, n - on_pass, off_pass, n - off_pass), 4),
            "tool_sequence_identical": sum(p["on"]["state_db"]["tool_sequence"] == p["off"]["state_db"]["tool_sequence"] for p in comp),
            "hermes_rc_nonzero": sum((p["on"]["hermes_rc"] != 0) + (p["off"]["hermes_rc"] != 0) for p in comp)}


if __name__ == "__main__":
    raw, plan_p, rplan_p, out_p = map(Path, sys.argv[1:5])
    measured = [r for r in json.loads(plan_p.read_text())["runs"] if r["set"] == "measured"]
    rep = json.loads(rplan_p.read_text())["runs"]
    S = load(raw, measured + rep)
    out = {"schema": "stack_smoke.replication.v1", "replication_only": stats(rep, S), "measured_only": stats(measured, S),
           "pooled": stats(measured + rep, S), "runs_planned": len(rep), "runs_present": sum(r["run_id"] in S for r in rep)}
    r = out["replication_only"]
    out["R1_supported"] = r["sign_test_p"] < 0.05 and r["discordant_off_only_pass"] > r["discordant_on_only_pass"]
    out_p.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out, indent=1, sort_keys=True))

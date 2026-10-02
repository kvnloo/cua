#!/usr/bin/env python3
"""Summarise the Phase 1 calibration: per-evaluation verdicts, row PASS/FAIL, costs, positive control,
LORD++ trajectory and gate diagnostics. Pure function of the calibration run directory (and the
quiet-lane receipts); imports only the unmodified evaluator (areval) for statistics.

usage (under hostless): analyze.py --run-dir D --harness H/harness/ar --quiet-ledger LEDGER --out summary.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from statistics import fmean, median


def jl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    p.add_argument("--harness", required=True)
    p.add_argument("--quiet-ledger", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    sys.path.insert(0, a.harness)
    from areval import gates, lord, stats  # noqa: E402

    D = Path(a.run_dir)
    prereg = json.loads((D / "CALIB-PREREG.json").read_text())
    tau = prereg["evaluator"]["tau"]
    receipts = [r for r in jl(Path(a.quiet_ledger)) if r.get("label", "").startswith(("ar-20261002-cal-", "cal-feedback-"))]
    g1 = {r["name"]: r for r in jl(D / "g1" / "timing.jsonl")}
    g0t = {r["name"]: r for r in jl(D / "g0" / "timing.jsonl")}

    evals = []
    for e in sorted((D / "evals").iterdir()):
        fin = e / "final.json"
        if not fin.exists():
            continue
        f = json.loads(fin.read_text())
        st = jl(e / "stages.jsonl")
        stage_t = {s["stage"]: s["t_ms"] for s in st}
        rec = {**f, "wall_s": round((stage_t["done"] - stage_t["start"]) / 1000, 1)}
        mine = [r for r in receipts if r["label"].startswith(f["eval_id"] + "-")]
        rec["blocks"] = len(mine)
        rec["held_s"] = round(sum(ts(r["released"]) - ts(r["acquired"]) for r in mine), 1)
        blocks = jl(e / "screen" / "blocks.jsonl") + jl(e / "confirm" / "blocks.jsonl")
        rec["block_wall_s"] = round(sum(b["wall_s"] for b in blocks), 1)
        rec["lock_wait_s"] = round(rec["block_wall_s"] - rec["held_s"], 1)
        rec["block_rcs"] = [b["rc"] for b in blocks]
        if (e / "screen.json").exists():
            s = json.loads((e / "screen.json").read_text())
            rec["screen"] = {k: s.get(k) for k in ("verdict", "failed_gate", "n_pairs", "delta", "ci95", "sigma_ln",
                                                   "median_diff_ms", "median_T_ms", "mechanism_span_ms",
                                                   "pairs_trace_on_off")}
            rec["screen"]["gate_reasons"] = {g["gate"]: g["reasons"] for g in s["gates"] if not g["pass"]}
            rows = [r for f2 in sorted((e / "screen" / "raw").glob("*.jsonl")) for r in jl(f2)]
            ps = gates.pairs(rows, "task")
            if len(ps) >= 2:
                rec["screen"]["p_less"] = stats.bootstrap_p_less(gates.ln_pairs(ps), seed=1)
            rec["screen"]["trials"] = sum(1 for r in rows if r.get("schema") == "ar.trial.v1")
            rec["screen"]["failures"] = sorted({str(r.get("failure")) for r in rows
                                                if r.get("schema") == "ar.trial.v1" and r.get("failure")})
        if (e / "evaluate.json").exists():
            ev = json.loads((e / "evaluate.json").read_text())
            rec["confirm"] = ev
            rows = [r for f2 in sorted((e / "confirm" / "raw").glob("*.jsonl")) for r in jl(f2)]
            tr = [r for r in rows if r.get("schema") == "ar.trial.v1"]
            rec["confirm_trials"] = len(tr)
            rec["confirm_kinds"] = {k: sum(1 for r in tr if r["kind"] == k) for k in sorted({r["kind"] for r in tr})}
            rec["confirm_failures"] = [{"trial_id": r["trial_id"], "kind": r["kind"], "arm": r["arm"],
                                        "failure": r.get("failure")} for r in tr if r.get("failure")]
        evals.append(rec)

    ledger = jl(D / "cal-results.jsonl")
    for r in ledger:
        for e in evals:
            if e["eval_id"] == r["eval_id"]:
                e["ledger"] = {k: r.get(k) for k in ("verdict", "failed_gate", "delta", "ci95", "p_value", "power",
                                                     "n_pairs", "median_T_ms")}
                e["ledger"]["lord"] = r.get("lord")
                e["ledger"]["gates"] = {g["gate"]: {"pass": g["pass"], "reasons": g["reasons"][:6],
                                                    "metrics": {k: v for k, v in g["metrics"].items()
                                                                if k in ("share", "saving_ms", "phase_saving_ms",
                                                                         "abs_on_off", "delta_on", "delta_off",
                                                                         "pairs_on", "pairs_off", "p90_champion_ms",
                                                                         "p90_candidate_ms", "ln_ratio",
                                                                         "soak_trials", "failures", "spot")}}
                                        for g in r["gates"]}

    by = {}
    for e in evals:
        by.setdefault(e["name"], []).append(e)

    def verdicts(name):
        return [e["verdict"] for e in by.get(name, [])]

    rows_out = []

    def row(rid, name, expect, ok, detail):
        rows_out.append({"row": rid, "candidate": name, "expect": expect, "pass": bool(ok), "detail": detail})

    for rid, name in (("R1", "sleep20"), ("R2", "sleep50")):
        v = verdicts(name)
        row(rid, name, "REVERT", len(v) == 1 and v[0] != "KEEP", {"verdicts": v})
    v = verdicts("delete50")
    keeps = sum(1 for x in v if x == "KEEP")
    row("R3", "delete50", "KEEP in >= 8 of 10", len(v) == 10 and keeps >= 8,
        {"keeps": keeps, "repeats": len(v), "verdicts": v,
         "failed_gates": [e.get("failed_gate") for e in by.get("delete50", [])]})
    e = (by.get("success-early") or [{}])[0]
    row("R4", "success-early", "G2 fail", e.get("verdict") == "REJECT" and e.get("failed_gate") == "G2",
        {"verdict": e.get("verdict"), "failed_gate": e.get("failed_gate")})
    for rid, name in (("R5a", "g0-frozen-item"), ("R5b", "g0-test-item"), ("R5c", "g0-trace-line")):
        e = (by.get(name) or [{}])[0]
        g0 = json.loads((D / "evals" / e.get("eval_id", "x") / "g0.json").read_text()) if e else {}
        row(rid, name, "G0 fail", e.get("failed_gate") == "G0", {"reasons": g0.get("reasons")})
    e = (by.get("g0-scanner") or [{}])[0]
    g0 = json.loads((D / "evals" / e.get("eval_id", "x") / "g0.json").read_text()) if e else {}
    row("R6", "g0-scanner", "G0 fail (scanner)",
        e.get("failed_gate") == "G0" and any(r.startswith("scanner:") for r in g0.get("reasons", [])),
        {"reasons": g0.get("reasons")})
    noops = [x for n in sorted(by) if n.startswith("noop") for x in by[n]]
    nk = sum(1 for x in noops if x["verdict"] == "KEEP")
    row("R7", "noop01..10", "<= 1 false KEEP", len(noops) == 10 and nk <= 1,
        {"keeps": nk, "n": len(noops), "verdicts": {x["name"]: x["verdict"] for x in noops}})

    # R8 positive control
    fb = {}
    for kind in ("browser", "gtk"):
        rows = jl(D / "feedback" / kind / "raw" / "s0.jsonl")
        k = "spot_browser_fill_submit" if kind == "browser" else "task"
        ps = gates.pairs(rows, k)  # champion arm = ON, candidate arm = OFF
        tr = [r for r in rows if r.get("schema") == "ar.trial.v1" and not r.get("warmup")]
        info = {"trials": len(tr), "verified": sum(1 for r in tr if r.get("verified")), "complete_pairs": len(ps),
                "failures": [{"trial_id": r["trial_id"], "arm": r["arm"], "feedback": r.get("calibration_feedback_enabled"),
                              "failure": r.get("failure")} for r in tr if r.get("failure")],
                "gate_marks_match_arm": all(
                    all(m.get("detail", {}).get("cursor_enabled") == r.get("calibration_feedback_enabled")
                        for m in r.get("marks", []) if m.get("phase") == "platform.gate")
                    for r in tr)}
        if len(ps) >= 2:
            d = gates.ln_pairs(ps)
            lo, hi = stats.bootstrap_ci(d, 0.95, seed=20280013)
            diffs = [(on["T_ns"] - off["T_ns"]) / 1e6 for on, off in ps]
            info.update(delta_off_vs_on=fmean(d), ci95=[lo, hi], median_on_minus_off_ms=median(diffs),
                        on_slower_pairs=sum(1 for x in diffs if x > 0),
                        median_T_ms={"on": median(on["T_ns"] for on, _ in ps) / 1e6,
                                     "off": median(off["T_ns"] for _, off in ps) / 1e6})
        fb[kind] = info
    b = fb["browser"]
    row("R8", "feedback ON vs OFF", "large effect, ON slower",
        b.get("median_on_minus_off_ms", 0) >= 1000 and b.get("ci95", [0, 0])[1] < -math.log1p(tau),
        {"browser": b, "gtk_diagnostic": fb["gtk"]})

    # LORD++ trajectory of the calibration ledger and the p-value floor
    pmin = 1 / 4001
    lord_info = {"ledger_tests": [{"eval_id": r["eval_id"], **(r.get("lord") or {})} for r in ledger if r.get("lord")],
                 "bootstrap_p_floor": pmin,
                 "alpha_t_without_prior_rejection": {t: lord.gamma(t) * lord.W0 for t in range(1, 6)},
                 "first_unrejectable_index_without_rejection": next(t for t in range(1, 50) if lord.gamma(t) * lord.W0 < pmin)}

    # costs
    cost = {}
    for name, es in by.items():
        g = g1.get(name)
        build_s = round((g["build_ms"] + g["test_compile_ms"] + g["test_run_ms"]) / 1000, 1) if g else 0.0
        cost[name] = {"evaluations": len(es), "g0_ms": g0t.get(name, {}).get("wall_ms"), "g1_s": build_s,
                      "timed_held_s": round(sum(x["held_s"] for x in es), 1),
                      "lock_wait_s": round(sum(x["lock_wait_s"] for x in es), 1),
                      "blocks": sum(x["blocks"] for x in es),
                      "eval_wall_s": round(sum(x["wall_s"] for x in es), 1)}
        cost[name]["per_evaluation_minutes_excl_g1"] = round(cost[name]["eval_wall_s"] / len(es) / 60, 2)
        cost[name]["per_candidate_minutes_incl_g1"] = round((cost[name]["eval_wall_s"] / len(es) + build_s) / 60, 2)
    out = {"schema": "ar.calibration_summary.v1", "tau": tau, "rows": rows_out,
           "overall_pass": all(r["pass"] for r in rows_out) and len(rows_out) == 10,
           "evaluations": evals, "lord": lord_info, "cost": cost, "feedback": fb,
           "quiet_lane_receipts": len(receipts)}
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps([{k: r[k] for k in ("row", "candidate", "pass")} for r in rows_out]))
    print("overall_pass", out["overall_pass"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

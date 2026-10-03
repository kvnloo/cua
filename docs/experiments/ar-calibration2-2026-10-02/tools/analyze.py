#!/usr/bin/env python3
"""Summarise calibration 2: per-evaluation verdicts, row PASS/FAIL (R1-R10), the separate calibration
ledger (verdict, failed gate, cost per evaluation), costs per candidate, throughput, the positive control,
the LORD++ trajectory and the R10 manipulation check. Pure function of the calibration-2 run directory and
the quiet-lane receipts; imports only the unmodified evaluator (areval) for statistics and gates.

usage (under hostless): analyze.py --run-dir D --harness H/harness/ar --quiet-ledger LEDGER --out summary.json
        writes summary.json and calibration-ledger.jsonl next to it
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from statistics import fmean, median

PLANTED = "new_file:gtk:/tmp/dbus-ArSettleWatch"


def jl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def stall_share(r: dict) -> float | None:
    psi = r.get("psi") or {}
    dur = (r.get("t_exit_ns") or 0) - (r.get("t_spawn_ns") or 0)
    if "cpu_some_stall_us" not in psi or dur <= 0:
        return None
    return psi["cpu_some_stall_us"] * 1000 / dur


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
    prereg = json.loads((D / "CALIB2-PREREG.json").read_text())
    tau = prereg["evaluator"]["tau"]
    receipts = [r for r in jl(Path(a.quiet_ledger)) if r.get("label", "").startswith(("ar-20261002-cal2-", "cal2-feedback-"))]
    g1 = {r["name"]: r for r in jl(D / "g1" / "timing.jsonl")}

    evals = []
    for e in sorted((D / "evals").iterdir()):
        fin = e / "final.json"
        if not fin.exists():
            continue
        f = json.loads(fin.read_text())
        st = jl(e / "stages.jsonl")
        stage_t = {s["stage"]: s["t_ms"] for s in st}
        rec = {**f, "wall_s": round((stage_t["done"] - stage_t["start"]) / 1000, 1),
               "g0_s": round((stage_t.get("g0", stage_t["start"]) - stage_t["start"]) / 1000, 2),
               "g1_wait_s": round((stage_t["g1_ready"] - stage_t["g0"]) / 1000, 1) if "g1_ready" in stage_t else 0.0,
               "started_utc": next(s["utc"] for s in st if s["stage"] == "start"),
               "done_utc": next(s["utc"] for s in st if s["stage"] == "done")}
        mine = [r for r in receipts if r["label"].startswith(f["eval_id"] + "-")]
        rec["blocks"] = len(mine)
        rec["held_s"] = round(sum(ts(r["released"]) - ts(r["acquired"]) for r in mine), 1)
        blocks = jl(e / "screen" / "blocks.jsonl") + jl(e / "confirm" / "blocks.jsonl")
        rec["block_wall_s"] = round(sum(b["wall_s"] for b in blocks), 1)
        rec["lock_wait_s"] = round(rec["block_wall_s"] - rec["held_s"], 1)
        rec["block_rcs"] = [b["rc"] for b in blocks]
        if (e / "screen.json").exists():
            s = json.loads((e / "screen.json").read_text())
            rec["screen"] = {k: s.get(k) for k in ("verdict", "failed_gate", "metric", "n_pairs", "delta", "ci95", "sigma_ln",
                                                   "median_diff_ms", "median_ms", "whole_task", "mechanism_span_ms",
                                                   "pairs_trace_on_off")}
            rec["screen"]["gate_reasons"] = {g["gate"]: g["reasons"] for g in s["gates"] if not g["pass"]}
            rows = [r for f2 in sorted((e / "screen" / "raw").glob("*.jsonl")) for r in jl(f2)]
            rec["screen"]["trials"] = sum(1 for r in rows if r.get("schema") == "ar.trial.v1")
            rec["screen"]["failures"] = sorted({str(r.get("failure")) for r in rows
                                                if r.get("schema") == "ar.trial.v1" and r.get("failure")})
            rec["screen"]["loadavg_start"] = [r.get("loadavg") for r in rows if r.get("schema") == "ar.session.v1" and r.get("event") == "start"]
        # confirm-row statistics whenever confirm rows exist (R10/R10b pass_if: "whether or not an earlier
        # gate stopped the pipeline"; an INFRA stop after the confirm task sessions still has those rows)
        if (e / "evaluate.json").exists():
            rec["confirm"] = json.loads((e / "evaluate.json").read_text())
        if (e / "confirm" / "raw").exists():
            rows = [r for f2 in sorted((e / "confirm" / "raw").glob("*.jsonl")) for r in jl(f2)]
            tr = [r for r in rows if r.get("schema") == "ar.trial.v1"]
            rec["confirm_trials"] = len(tr)
            rec["confirm_kinds"] = {k: sum(1 for r in tr if r["kind"] == k) for k in sorted({r["kind"] for r in tr})}
            rec["confirm_failures"] = [{"trial_id": r["trial_id"], "kind": r["kind"], "arm": r["arm"],
                                        "failure": r.get("failure")} for r in tr if r.get("failure")]
            task = [r for r in tr if r["kind"] == "task" and not r.get("warmup")]
            shares = [x for x in (stall_share(r) for r in task) if x is not None]
            rec["confirm_task_cpu_some_share_median"] = median(shares) if shares else None
            rec["confirm_task_loadavg1_median"] = median(r["loadavg_end"][0] for r in task if r.get("loadavg_end")) if task else None
            pre = json.loads((e / "prereg.json").read_text())
            rec["g7_on_confirm_rows"] = gates.g7(rows, pre)
            dpa = gates.ln_pairs(gates.pairs(rows, "task", metric="T_act"), "T_act")
            rec["confirm_task_sigma_ln"] = stats.sd(dpa) if len(dpa) >= 2 else None
            rec["confirm_champion_median_ms"] = {m: gates._median_ms(gates.trials(rows, "task", "champion"), m)
                                                 for m in ("T", "T_act")}
        evals.append(rec)

    ledger = jl(D / "cal2-results.jsonl")
    amend_ledger = jl(D / "cal2-amend-results.jsonl")
    amend_only = amend_ledger[len(ledger):]
    for r in ledger + amend_only:
        for e in evals:
            if e["eval_id"] == r["eval_id"]:
                e["ledger"] = {k: r.get(k) for k in ("verdict", "failed_gate", "delta", "ci95", "p_value", "power",
                                                     "n_pairs", "metric", "median_T_ms", "median_T_act_ms")}
                e["ledger"]["lord"] = r.get("lord")
                e["ledger"]["gates"] = {g["gate"]: {"pass": g["pass"], "reasons": g["reasons"][:6],
                                                    "metrics": {k: v for k, v in g["metrics"].items()
                                                                if k in ("share", "saving_ms", "phase_saving_ms",
                                                                         "delta_on", "delta_off", "trace_off_band",
                                                                         "pairs_on", "pairs_off", "p90_champion_ms",
                                                                         "p90_candidate_ms", "ln_ratio", "whole_task_delta",
                                                                         "whole_task_limit", "p_resamples",
                                                                         "soak_trials", "failures", "spot")}}
                                        for g in r["gates"]}

    by: dict[str, list[dict]] = {}
    for e in evals:
        by.setdefault(e.get("tag", e["name"]), []).append(e)

    def verdicts(name):
        return [e["verdict"] for e in by.get(name, [])]

    rows_out = []

    def row(rid, name, expect, ok, detail):
        rows_out.append({"row": rid, "candidate": name, "expect": expect, "pass": bool(ok), "detail": detail})

    for rid, name in (("R1", "sleep20"), ("R2", "sleep50")):
        v = verdicts(name)
        row(rid, name, "REVERT", len(v) == 1 and v[0] != "KEEP",
            {"verdicts": v, "screen": [e.get("screen", {}).get("delta") for e in by.get(name, [])]})
    v = verdicts("delete50")
    keeps = sum(1 for x in v if x == "KEEP")
    row("R3", "delete50", "KEEP in >= 8 of 10", len(v) == 10 and keeps >= 8,
        {"keeps": keeps, "repeats": len(v), "verdicts": v,
         "failed_gates": [e.get("failed_gate") for e in by.get("delete50", [])]})
    e = (by.get("success-early") or [{}])[0]
    row("R4", "success-early", "G2 fail", e.get("verdict") == "REJECT" and e.get("failed_gate") == "G2",
        {"verdict": e.get("verdict"), "failed_gate": e.get("failed_gate"),
         "reasons": (e.get("screen") or {}).get("gate_reasons", {}).get("G2", [])[:4]})
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
        {"keeps": nk, "n": len(noops), "verdicts": {x["name"]: x["verdict"] for x in noops},
         "screen_delta": {x["name"]: (x.get("screen") or {}).get("delta") for x in noops}})

    # R8 positive control (whole-task T gates, as in calibration 1; T_act reported)
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
            pa = gates.pairs(rows, k, metric="T_act")
            if len(pa) >= 2:
                da = gates.ln_pairs(pa, "T_act")
                info["T_act"] = {"delta_off_vs_on": fmean(da), "ci95": list(stats.bootstrap_ci(da, 0.95, seed=20280013)),
                                 "median_on_minus_off_ms": median((gates.t_act_ns(on) - gates.t_act_ns(off)) / 1e6 for on, off in pa)}
        fb[kind] = info
    b = fb["browser"]
    row("R8", "feedback ON vs OFF", "large effect, ON slower",
        b.get("median_on_minus_off_ms", 0) >= 1000 and b.get("ci95", [0, 0])[1] < -math.log1p(tau),
        {"browser": b, "gtk_diagnostic": fb["gtk"]})

    # R9 planted socket
    e = (by.get("new-socket") or [{}])[0]
    reasons = []
    if e.get("stage") == "screen":
        reasons = (e.get("screen") or {}).get("gate_reasons", {}).get("G2", [])
    elif e.get("ledger"):
        reasons = e["ledger"]["gates"].get("G2", {}).get("reasons", [])
    row("R9", "new-socket", "G2 fail", e.get("verdict") == "REJECT" and e.get("failed_gate") == "G2"
        and PLANTED in reasons, {"verdict": e.get("verdict"), "failed_gate": e.get("failed_gate"), "stage": e.get("stage"),
                                 "g2_reasons": reasons, "new_socket_reason": any(r.startswith("new_socket:") for r in reasons)})

    # R10 deletion under planted load
    loaded = by.get("delete50-load", [])
    base = [x["confirm_task_cpu_some_share_median"] for x in by.get("delete50", [])
            if x.get("confirm_task_cpu_some_share_median") is not None]
    base_med = median(base) if base else None
    per = []
    for x in loaded:
        g7r = x.get("g7_on_confirm_rows")
        per.append({"eval_id": x["eval_id"], "verdict": x["verdict"], "failed_gate": x.get("failed_gate"),
                    "screen": (x.get("screen") or {}).get("verdict"),
                    "g7_pass": bool(g7r and g7r["pass"]), "g7_reasons": (g7r or {}).get("reasons"),
                    "g7_metrics": {k: (g7r or {}).get("metrics", {}).get(k) for k in ("share", "delta_on", "delta_off",
                                                                                       "trace_off_band", "pairs_on", "pairs_off")},
                    "cpu_some_share_median": x.get("confirm_task_cpu_some_share_median"),
                    "loadavg1_median": x.get("confirm_task_loadavg1_median"),
                    "manipulation_ok": base_med is not None and x.get("confirm_task_cpu_some_share_median") is not None
                    and x["confirm_task_cpu_some_share_median"] > base_med})
    row("R10", "delete50 under load", "trace-off agreement passes under load",
        len(per) == 2 and all(q["screen"] == "RANKS" and q["g7_pass"] and q["manipulation_ok"] for q in per),
        {"repeats": per, "unloaded_R3_cpu_some_share_median": base_med,
         "unloaded_R3_loadavg1_median": median([x["confirm_task_loadavg1_median"] for x in by.get("delete50", [])
                                                if x.get("confirm_task_loadavg1_median") is not None] or [float("nan")])})

    # Amendment row R10b (CALIB2-AMEND-R10B.json; pre-registered after R1-R10 ran, reported next to R10,
    # never counted in the calibration-2 overall verdict)
    def sigma_of(x: dict, stage: str) -> float | None:
        if stage == "screen":
            return (x.get("screen") or {}).get("sigma_ln")
        return x.get("confirm_task_sigma_ln")

    amend_rows = []
    l30 = by.get("delete50-load30", [])
    if l30 or (D / "CALIB2-AMEND-R10B.json").exists():
        per = []
        for x in l30:
            g7r = x.get("g7_on_confirm_rows")
            share = x.get("confirm_task_cpu_some_share_median")
            la = x.get("confirm_task_loadavg1_median")
            per.append({"eval_id": x["eval_id"], "verdict": x["verdict"], "failed_gate": x.get("failed_gate"),
                        "stage": x["stage"], "screen": (x.get("screen") or {}).get("verdict"),
                        "g7_pass": bool(g7r and g7r["pass"]), "g7_reasons": (g7r or {}).get("reasons"),
                        "g7_metrics": {k: (g7r or {}).get("metrics", {}).get(k) for k in ("share", "delta_on", "delta_off",
                                                                                           "trace_off_band", "pairs_on", "pairs_off")},
                        "cpu_some_share_median": share, "loadavg1_median": la,
                        "screen_sigma_ln": sigma_of(x, "screen"), "confirm_sigma_ln": sigma_of(x, "confirm"),
                        "champion_median_ms": x.get("confirm_champion_median_ms"),
                        "confirm_failures": x.get("confirm_failures"),
                        "manipulation_ok": base_med is not None and share is not None and share > base_med
                        and la is not None and la >= 14})
        amend_rows.append({"row": "R10b", "candidate": "delete50 under CPU contention (30 burners)",
                           "expect": "trace-off agreement passes under CPU contention",
                           "pass": len(per) == 2 and all(q["screen"] == "RANKS" and q["g7_pass"] and q["manipulation_ok"]
                                                         for q in per),
                           "detail": {"repeats": per, "unloaded_R3_cpu_some_share_median": base_med,
                                      "unloaded_R3_champion_median_ms": [x.get("confirm_champion_median_ms")
                                                                         for x in by.get("delete50", [])],
                                      "unloaded_R3_confirm_sigma_ln": [x.get("confirm_task_sigma_ln")
                                                                       for x in by.get("delete50", [])],
                                      "R10_confirm_sigma_ln": [x.get("confirm_task_sigma_ln") for x in loaded]}})

    # Diagnostics (not gate results): the G1 flake behind the sleep20/noop05 G1 REJECTs
    diag = {}
    gd = D / "diag" / "g1flake"
    if gd.exists():
        diag["g1_flake"] = {
            "rejects": {n: [r for r in jl(D / "g1" / f"{n}.rows.jsonl") if r.get("kind") == "test" and not r.get("ok")]
                        for n in ("sleep20", "noop05")},
            "core_reruns_after_run": jl(gd / "core-reruns.jsonl"),
            "earlier_reruns": [(D / "diag" / f).read_text().strip() for f in ("flake-full.txt", "flake-history.txt")
                               if (D / "diag" / f).exists()],
            "g1_runs_total": len(g1), "g1_test_failures": sum(1 for n in g1 if any(
                r.get("kind") == "test" and not r.get("ok") for r in jl(D / "g1" / f"{n}.rows.jsonl"))),
            "diagnostic_screens": {n: {k: json.loads((gd / n / "screen.json").read_text()).get(k)
                                       for k in ("verdict", "failed_gate", "delta", "ci95", "median_diff_ms",
                                                 "mechanism_span_ms", "seed", "n_pairs")}
                                   for n in ("sleep20", "noop05") if (gd / n / "screen.json").exists()}}

    # LORD++ trajectory and the p resolution
    lord_info = {"ledger_tests": [{"eval_id": r["eval_id"], **(r.get("lord") or {})} for r in ledger if r.get("lord")],
                 "p_resolution_rule": "sign-flip p floor 1/(b+1) with b = max(20000, ceil(20/alpha_i)) <= alpha_i/20"}
    lord_info["all_p_at_or_below_alpha_floor_resolvable"] = all(
        1 / (stats.sign_flip_resamples(t["alpha_i"]) + 1) <= t["alpha_i"] / 20 + 1e-15 for t in lord_info["ledger_tests"])

    # costs: per evaluation (calibration ledger) and per candidate
    cal_ledger = []
    for x in evals:
        g = g1.get(x["name"])
        cal_ledger.append({"schema": "ar.calibration_ledger.v1", "eval_id": x["eval_id"], "candidate": x.get("tag", x["name"]),
                           "branch": f"ar/calib2/{x['name']}", "repeat": x["repeat"], "load_burners": x.get("load_burners", 0),
                           "stage_reached": x["stage"], "verdict": x["verdict"], "failed_gate": x["failed_gate"],
                           "started_utc": x["started_utc"], "done_utc": x["done_utc"], "eval_wall_s": x["wall_s"],
                           "g0_s": x["g0_s"], "g1_wait_s": x["g1_wait_s"],
                           "build_s": round(g["build_ms"] / 1000, 1) if g else 0.0,
                           "test_compile_s": round(g["test_compile_ms"] / 1000, 1) if g else 0.0,
                           "test_run_s": round(g["test_run_ms"] / 1000, 1) if g else 0.0,
                           "blocks": x["blocks"], "timed_held_s": x["held_s"], "lock_wait_s": x["lock_wait_s"]})
    out_dir = Path(a.out).parent
    (out_dir / "calibration-ledger.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in cal_ledger))
    cost = {}
    for name, es in by.items():
        g = g1.get(es[0]["name"])
        build_s = round((g["build_ms"] + g["test_compile_ms"] + g["test_run_ms"]) / 1000, 1) if g else 0.0
        eval_s = sum(x["wall_s"] - x["g1_wait_s"] for x in es)
        cost[name] = {"evaluations": len(es), "g0_s": round(fmean(x["g0_s"] for x in es), 2), "g1_s": build_s,
                      "timed_held_s": round(sum(x["held_s"] for x in es), 1),
                      "lock_wait_s": round(sum(x["lock_wait_s"] for x in es), 1),
                      "blocks": sum(x["blocks"] for x in es),
                      "eval_wall_s_excl_g1_wait": round(eval_s, 1)}
        cost[name]["per_evaluation_minutes_excl_g1"] = round(eval_s / len(es) / 60, 2)
        cost[name]["per_candidate_minutes_incl_g1"] = round((eval_s / len(es) + build_s) / 60, 2)
        cost[name]["per_evaluation_minutes_uncontended_incl_g1"] = round(
            ((eval_s - sum(x["lock_wait_s"] for x in es)) / len(es) + build_s) / 60, 2)
    classes = {"g0_reject": [n for n in cost if n.startswith("g0-")],
               "screen_only": [n for n in cost if n.startswith(("noop", "sleep")) or n in ("success-early", "new-socket")],
               "full_pipeline": [n for n in cost if n.startswith("delete50")]}
    tput = {}
    for cls, names in classes.items():
        if not names:
            continue
        evs = [x for n in names for x in by[n]]
        incl = fmean(cost[x.get("tag", x["name"])]["g1_s"] / 60 + (x["wall_s"] - x["g1_wait_s"]) / 60 for x in evs)
        unc = fmean(cost[x.get("tag", x["name"])]["g1_s"] / 60 + (x["wall_s"] - x["g1_wait_s"] - x["lock_wait_s"]) / 60 for x in evs)
        excl_g1 = fmean((x["wall_s"] - x["g1_wait_s"]) / 60 for x in evs)
        tput[cls] = {"evaluations": len(evs), "mean_minutes_incl_g1_observed": round(incl, 2),
                     "mean_minutes_incl_g1_uncontended": round(unc, 2), "mean_minutes_excl_g1_observed": round(excl_g1, 2),
                     "per_hour_observed": round(60 / incl, 1) if incl > 0 else None,
                     "per_hour_uncontended": round(60 / unc, 1) if unc > 0 else None}
    t0 = min(ts(x["started_utc"]) for x in evals) if evals else 0
    t1 = max(ts(x["done_utc"]) for x in evals) if evals else 0
    tput["calibration_wall_h"] = round((t1 - t0) / 3600, 2)
    tput["quiet_lane_receipts"] = len(receipts)
    tput["quiet_lane_held_min"] = round(sum(ts(r["released"]) - ts(r["acquired"]) for r in receipts) / 60, 1)
    out = {"schema": "ar.calibration2_summary.v1", "tau": tau, "metric": prereg["evaluator"]["decision_metric"],
           "rows": rows_out, "overall_pass": all(r["pass"] for r in rows_out) and len(rows_out) == 12,
           "evaluations": evals, "lord": lord_info, "cost": cost, "throughput": tput, "feedback": fb,
           "quiet_lane_receipts": len(receipts), "amendment_rows": amend_rows, "diagnostics": diag,
           "amendment_lord": [{"eval_id": r["eval_id"], **(r.get("lord") or {})} for r in amend_only if r.get("lord")]}
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps([{k: r[k] for k in ("row", "candidate", "pass")} for r in rows_out]))
    print("overall_pass", out["overall_pass"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

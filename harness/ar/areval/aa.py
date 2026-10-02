"""A/A calibration summary: a pure function of AA raw rows (champion build vs champion rebuild).

Computes, for the decision metric and its pre-declared fallback:
  * whole-task T = t_done - t_spawn (the decision metric), and
  * T_act = t_done - m0 of the first dispatch call (the plan's fallback when whole-task T
    needs more than MAX_FEASIBLE_PAIRS pairs by power),
the per-pair ln ratio d = ln(T_rebuild / T_base), sigma_ln = sd(d), Delta_AA = mean(d) with a
pair-resampled bootstrap CI (must include 0), the pair-resampled |Delta_AA| distribution,
tau = max(2%, 97.5th pct |Delta_AA|), n_pairs by power at delta = ln(1+tau) and the PSI discard
threshold. It also runs G2, G3 and G4 on the AA rows (both arms are the champion, so they must
pass) and G5 with the calibrated tau and n (an A/A must not be kept).
"""

from __future__ import annotations

import math
from statistics import fmean, median
from typing import Any

from . import gates, lord, stats

MAX_FEASIBLE_PAIRS = 400
DISPATCH_TOOLS = ("click", "set_value", "browser_type", "browser_click")


def t_act_ns(row: dict) -> int | None:
    """First dispatch (m0 of the first mutating call) to the verified done."""
    first = next((c["m0"] for c in row.get("calls", []) if c.get("tool") in DISPATCH_TOOLS), None)
    if first is None or not row.get("t_done_ns"):
        return None
    return row["t_done_ns"] - first


def psi_cpu_fraction(row: dict) -> float | None:
    psi = row.get("psi") or {}
    stall = psi.get("cpu_some_stall_us")
    if stall is None or not row.get("t_exit_ns"):
        return None
    window_us = (row["t_exit_ns"] - row["t_spawn_ns"]) / 1e3
    return stall / window_us if window_us > 0 else None


def arm_stats(values_ns: list[int]) -> dict[str, Any]:
    ms = [v / 1e6 for v in values_ns]
    if not ms:
        return {"n": 0}
    sd = stats.sd(ms)
    return {"n": len(ms), "median_ms": median(ms), "mean_ms": fmean(ms), "sd_ms": sd,
            "cv": sd / fmean(ms), "p10_ms": stats.quantile(ms, 0.1), "p90_ms": stats.quantile(ms, 0.9),
            "min_ms": min(ms), "max_ms": max(ms)}


def metric_block(pairs: list[tuple[dict, dict]], metric, seed: int) -> dict[str, Any]:
    vals = [(metric(a), metric(c)) for a, c in pairs]
    vals = [(x, y) for x, y in vals if x and y]
    d = stats.ln_ratios(vals)
    n = len(d)
    if n < 2:
        return {"pairs": n, "feasible": False, "tau": None, "sigma_ln": None, "n_pairs_required": None,
                "ci_includes_zero": None, "abs_delta_aa_q975_ln": None}
    sigma = stats.sd(d)
    delta = fmean(d)
    lo, hi = stats.bootstrap_ci(d, 0.95, b=4000, seed=seed)
    tau_full = stats.tau_from_aa(d, n, b=4000, seed=seed + 1)
    tau_24 = stats.tau_from_aa(d, 24, b=4000, seed=seed + 2)
    tau = tau_full["tau"]
    need = stats.n_pairs_required(sigma, tau) if sigma > 0 else 2
    # Self-consistent reading: Delta_AA at the evaluation's own batch size n = n_required(tau).
    tau_sc, n_sc = tau, need
    for i in range(20):
        nxt = stats.tau_from_aa(d, max(2, n_sc), b=4000, seed=seed + 3 + i)["tau"]
        n_next = stats.n_pairs_required(sigma, nxt) if sigma > 0 else 2
        if n_next == n_sc:
            tau_sc = nxt
            break
        tau_sc, n_sc = nxt, n_next
    return {
        "pairs": n,
        "sigma_ln": sigma,
        "delta_aa_ln": delta,
        "delta_aa_ratio": math.exp(delta),
        "ci95_ln": [lo, hi],
        "ci_includes_zero": lo <= 0.0 <= hi,
        "abs_delta_aa_q975_ln": tau_full["q975_abs_delta_aa_ln"],
        "abs_delta_aa_q975_ln_batch24": tau_24["q975_abs_delta_aa_ln"],
        "tau": tau,
        "tau_at_batch24": tau_24["tau"],
        "tau_floor_binding": tau == stats.TAU_FLOOR,
        "delta_decision_ln": -math.log1p(tau),
        "n_pairs_required": need,
        "n_pairs_required_at_tau_batch24": stats.n_pairs_required(sigma, tau_24["tau"]) if sigma > 0 else 2,
        "tau_self_consistent": tau_sc,
        "n_pairs_required_self_consistent": stats.n_pairs_required(sigma, tau_sc) if sigma > 0 else 2,
        "feasible": need <= MAX_FEASIBLE_PAIRS,
        "power_at_aa_size": stats.achieved_power(sigma, tau, n),
        "base": arm_stats([x for x, _ in vals]),
        "rebuild": arm_stats([y for _, y in vals]),
        "d_quantiles_ln": {q: stats.quantile(d, q) for q in (0.025, 0.25, 0.5, 0.75, 0.975)},
    }


def psi_threshold(pairs: list[tuple[dict, dict]]) -> dict[str, Any]:
    """Per-pair PSI = max of the two trials' CPU-some stall fraction over spawn..exit.

    Discard rule (arm-blind, whole pairs only): a pair whose PSI exceeds the Tukey far-out
    fence Q3 + 3 IQR of the A/A distribution is discarded before any statistics, and the
    discard count per arm-order is reported. Calibrated here, frozen in the pre-registration.
    """
    per = []
    for a, c in pairs:
        fa, fc = psi_cpu_fraction(a), psi_cpu_fraction(c)
        if fa is not None and fc is not None:
            per.append((max(fa, fc), a, c))
    if len(per) < 4:
        return {"pairs_with_psi": len(per), "threshold": None}
    xs = [p for p, _, _ in per]
    q1, q3 = stats.quantile(xs, 0.25), stats.quantile(xs, 0.75)
    thr = q3 + 3 * (q3 - q1)
    kept = [(a, c) for p, a, c in per if p <= thr]
    d_all = stats.ln_ratios([(a["T_ns"], c["T_ns"]) for _, a, c in per])
    d_kept = stats.ln_ratios([(a["T_ns"], c["T_ns"]) for a, c in kept])
    absd = [abs(x) for x in d_all]
    return {
        "metric": "max over the pair of cpu_some_stall_us / (t_exit - t_spawn), 10 Hz /proc/pressure",
        "rule": "discard the whole pair when the metric > threshold (Tukey far-out fence Q3 + 3 IQR of the A/A pairs)",
        "pairs_with_psi": len(per),
        "quantiles": {q: stats.quantile(xs, q) for q in (0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0)},
        "threshold": thr,
        "aa_pairs_discarded": len(per) - len(kept),
        "sigma_ln_after_discard": stats.sd(d_kept),
        "delta_ln_after_discard": fmean(d_kept) if d_kept else None,
        "spearman_psi_vs_abs_d": _spearman(xs, absd),
    }


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = fmean(rx), fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def summarize(rows: list[dict], seed: int = 20261002) -> dict[str, Any]:
    ps = gates.pairs(rows, "task")
    task = gates.trials(rows, kind="task")
    whole = metric_block(ps, lambda r: r.get("T_ns"), seed)
    act = metric_block(ps, t_act_ns, seed + 10)
    decision = "whole_task_T" if whole["feasible"] else ("T_act" if act["feasible"] else "none_feasible")
    chosen = whole if decision == "whole_task_T" else act
    sessions = sorted({r["session"] for r in task})
    per_session = {}
    for s in sessions:
        sp = [(a, c) for a, c in ps if a["session"] == s]
        d = gates.ln_pairs(sp)
        if len(d) >= 2:
            lo, hi = stats.bootstrap_ci(d, 0.95, seed=seed + 20 + s)
            per_session[str(s)] = {"pairs": len(d), "delta_ln": fmean(d), "sigma_ln": stats.sd(d), "ci95_ln": [lo, hi],
                                   "median_T_ms_base": median(a["T_ns"] for a, _ in sp) / 1e6}
    # Position (order) effect: ln(T_second / T_first); AB/BA alternation cancels it in Delta.
    pos = [math.log((c if a["position"] == 0 else a)["T_ns"] / (a if a["position"] == 0 else c)["T_ns"]) for a, c in ps]
    on, off = gates.pairs(rows, "task", trace=True), gates.pairs(rows, "task", trace=False)
    d_on, d_off = gates.ln_pairs(on), gates.ln_pairs(off)
    t_on = [r["T_ns"] for r in task if r.get("verified") and r.get("trace")]
    t_off = [r["T_ns"] for r in task if r.get("verified") and not r.get("trace")]
    prereg = {"tau": {"value": chosen["tau"]}, "design": {"n_pairs": min(chosen["n_pairs_required"], len(ps)),
                                                          "seed": seed},
              "invariants": {"expected_route": "accessibility", "expected_path": None}}
    g5 = gates.g5(rows, prereg, [])
    attempted = len([r for r in task if not r.get("warmup")])
    return {
        "schema": "ar.aa.v1",
        "pairs_complete": len(ps),
        "task_trials_attempted": attempted,
        "task_trials_verified": sum(1 for r in task if r.get("verified")),
        "failures": sorted({str(r.get("failure")) for r in gates.trials(rows, warmup=None) if r.get("failure")}),
        "decision_metric": decision,
        "fallback_rule": f"switch to T_act when whole-task T needs > {MAX_FEASIBLE_PAIRS} pairs by power",
        "whole_task_T": whole,
        "T_act": act,
        "chosen": {"metric": decision, "sigma_ln": chosen["sigma_ln"], "tau": chosen["tau"],
                   "n_pairs": chosen["n_pairs_required"], "ci_includes_zero": chosen["ci_includes_zero"]},
        "per_session": per_session,
        "position_effect_ln": {"mean": fmean(pos), "sd": stats.sd(pos), "ci95": list(stats.bootstrap_ci(pos, seed=seed + 30))},
        "trace": {"pairs_on": len(on), "pairs_off": len(off),
                  "delta_on_ln": fmean(d_on) if d_on else None, "delta_off_ln": fmean(d_off) if d_off else None,
                  "median_T_ms_on": median(t_on) / 1e6 if t_on else None,
                  "median_T_ms_off": median(t_off) / 1e6 if t_off else None,
                  "trace_cost_ln": math.log(median(t_on) / median(t_off)) if t_on and t_off else None},
        "psi": psi_threshold(ps),
        "gates_on_aa": {"G2": gates.g2(rows, prereg | {"invariants": prereg["invariants"]}),
                        "G3": gates.g3(rows), "G4": gates.g4(rows),
                        "G5_false_keep_check": {k: g5[k] for k in ("pass", "reasons")} | {
                            "delta": g5["metrics"].get("delta"), "p_value": g5["metrics"].get("p_value"),
                            "n_pairs": g5["metrics"].get("n_pairs"),
                            "alpha_i": (g5["metrics"].get("lord") or {}).get("alpha_i")}},
        "lord_alpha_1": lord.decide([], 1.0)["alpha_i"],
    }

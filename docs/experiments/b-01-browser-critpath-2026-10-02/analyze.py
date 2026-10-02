"""Build b01-summary.json from raw/ (every headline in README comes from here).

    python3 analyze.py [--raw raw] [--out b01-summary.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

import b01_analysis as A

HERE = Path(__file__).resolve().parent
THRESH_MS, THRESH_SHARE = 50.0, 0.05
CHAINS = {
    "fill": [("K0n", "K0"), ("K0", "K1"), ("K0", "K2"), ("K1", "K2"), ("K2", "K3"), ("K3", "K4")],
    "toggle": [("K0", "K1"), ("K0", "K2"), ("K1", "K2"), ("K2", "K4")],
    "modal": [("K0", "K1"), ("K0", "K2"), ("K1", "K2"), ("K2", "K4")],
}


def rnd(x: Any, n: int = 3) -> Any:
    if isinstance(x, float):
        return round(x, n)
    if isinstance(x, list):
        return [rnd(v, n) for v in x]
    if isinstance(x, dict):
        return {k: rnd(v, n) for k, v in x.items()}
    return x


def arm_stats(trials: list[dict[str, Any]]) -> dict[str, Any]:
    valid, failures, decs = [], [], []
    for t in trials:
        ok, why = A.is_valid(t)
        if ok:
            valid.append(t)
            decs.append(A.decompose(t))
        else:
            failures.append({"trial": t["name"], "reasons": why})
    Tr = [d["T_runner_ms"] for d in decs]
    To = [d["T_oracle_ms"] for d in decs if d["T_oracle_ms"] is not None]
    comps = {c: [d["components"][c] for d in decs] for c in A.COMPONENTS}
    subs = {k: [d["sub"].get(k, 0.0) for d in decs] for k in sorted({k for d in decs for k in d["sub"]})}
    meanT = statistics.mean(Tr) if Tr else None
    loads = [float(t["summary"]["loadavg_before"].split()[0]) for t in trials
             if t["summary"].get("loadavg_before", "unavailable") != "unavailable"]
    obs_counts = [len(d["observations"]) for d in decs]
    obs_each = [x for d in decs for x in d["observations"]]
    first_excess = [max(0.0, d["observations"][0] - d["observations"][1]) for d in decs if len(d["observations"]) >= 2]
    return {
        "n": len(trials), "valid": len(valid), "valid_frac": (len(valid) / len(trials)) if trials else None,
        "failures": failures,
        "T_runner_ms": {"median": A.median(Tr), "p95": A.p95(Tr), "mean": meanT},
        "T_oracle_ms": {"median": A.median(To), "p95": A.p95(To), "n": len(To)},
        "components_mean_ms": {c: statistics.mean(v) if v else None for c, v in comps.items()},
        "components_median_ms": {c: A.median(v) for c, v in comps.items()},
        "shares": {c: (statistics.mean(v) / meanT) if (v and meanT) else None for c, v in comps.items()},
        "mcp_transport_mean_ms": sum(statistics.mean(comps[c]) for c in A.MCP_TRANSPORT) if Tr else None,
        "sub_mean_ms": {k: statistics.mean(v) for k, v in subs.items()},
        "coverage_mean": statistics.mean([d["coverage"] for d in decs]) if decs else None,
        "coverage_min": min([d["coverage"] for d in decs]) if decs else None,
        "sum_minus_T_max_abs_ms": max([abs(d["sum_ms"] - d["T_runner_ms"]) for d in decs]) if decs else None,
        "sleeps_entered_trials": sum(1 for d in decs if d["sleeps_entered"] > 0),
        "sleeps_entered_frac": (sum(1 for d in decs if d["sleeps_entered"] > 0) / len(decs)) if decs else None,
        "observations": {"count_median": A.median(obs_counts), "per_call_median_ms": A.median(obs_each),
                         "first_minus_second_median_ms": A.median(first_excess),
                         "first_minus_second_mean_ms": statistics.mean(first_excess) if first_excess else None},
        "effect_lag_from_final_send_median_ms": A.median([d["effect_lag_from_final_send_ms"] for d in decs
                                                          if d["effect_lag_from_final_send_ms"] is not None]),
        "post_return_effect_lag_median_ms": A.median([d["post_return_effect_lag_ms"] for d in decs
                                                      if d["post_return_effect_lag_ms"] is not None]),
        "post_return_effect_trials": sum(1 for d in decs if (d["post_return_effect_lag_ms"] or 0) > 0),
        "arrival_wait_median_ms": A.median([g["wait_ms"] for d in decs for g in d["glides"]]),
        "settle_ms_values": sorted({v for d in decs for v in d["settle_ms"]}),
        "loadavg_1m_range": [min(loads), max(loads)] if loads else None,
        "_per_trial": [{"trial": t["name"], "round": t["summary"].get("round"), "T_runner_ms": d["T_runner_ms"],
                        "T_oracle_ms": d["T_oracle_ms"]} for t, d in zip(valid, decs)],
        "_decs": decs,
    }


def by_round(stats: dict[str, Any], key: str = "T_runner_ms") -> dict[int, float]:
    return {r["round"]: r[key] for r in stats["_per_trial"] if r[key] is not None}


def paired(sa: dict[str, Any], sb: dict[str, Any], key: str = "T_runner_ms") -> dict[str, Any]:
    ra, rb = by_round(sa, key), by_round(sb, key)
    rounds = sorted(set(ra) & set(rb))
    out = A.paired_diff([ra[r] for r in rounds], [rb[r] for r in rounds])
    out["rounds_dropped"] = sorted((set(ra) | set(rb)) - set(rounds))
    return out


def ratio_ci(s0: dict, s1: dict, s2: dict, key: str = "T_runner_ms") -> dict[str, Any]:
    r0, r1, r2 = by_round(s0, key), by_round(s1, key), by_round(s2, key)
    rounds = sorted(set(r0) & set(r1) & set(r2))
    d1 = [r0[r] - r1[r] for r in rounds]
    d2 = [r0[r] - r2[r] for r in rounds]

    def stat(idx: list[int]) -> float | None:
        den = statistics.median([d2[i] for i in idx])
        return None if den == 0 else statistics.median([d1[i] for i in idx]) / den

    point = stat(list(range(len(rounds)))) if rounds else None
    return {"n": len(rounds), "R": point, "ci95": A.boot_ci(len(rounds), stat),
            "saving_K1_median_ms": A.median(d1), "saving_K2_median_ms": A.median(d2)}


def drop_check(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Dropped/reordered characters: a fill submit whose value is not the exact token."""
    drops = []
    for t in trials:
        s = t["summary"]
        subs = [e for e in s.get("journal", []) if e["event"] == "submit"]
        for e in subs:
            if e["value_sha16"] != s.get("token_sha16") or e.get("value_len") != s.get("token_len"):
                drops.append({"trial": t["name"], "value_len": e.get("value_len"), "token_len": s.get("token_len")})
    return {"trials": len(trials), "submits": sum(1 for t in trials for e in t["summary"].get("journal", [])
                                                  if e["event"] == "submit"), "drops": drops}


def build(raw: Path) -> dict[str, Any]:
    trials = A.load_trials(raw)
    blocks: dict[str, list] = {}
    for t in trials:
        blocks.setdefault(t["summary"]["block"], []).append(t)
    prim = [t for t in trials if t["summary"]["block"] == "m"]
    vblk = [t for t in trials if t["summary"]["block"] == "v"]
    tblk = [t for t in trials if t["summary"]["block"] == "t"]
    ctrl = [t for t in trials if t["summary"]["block"].startswith("c")]
    smoke = [t for t in trials if t["summary"]["block"] == "smoke"]

    out: dict[str, Any] = {"schema": "b01.summary.v1", "counts": {
        "trials_total": len(trials), "primary": len(prim), "k5_block": len(vblk), "t0_stress": len(tblk),
        "controls": len(ctrl), "smoke": len(smoke)}, "classes": {}, "hypotheses": {}}
    stats: dict[str, dict[str, Any]] = {}
    for cls in A.CLASSES:
        stats[cls] = {arm: arm_stats([t for t in prim if t["summary"]["cls"] == cls and t["summary"]["arm"] == arm])
                      for arm in A.CLASS_ARMS[cls]}
        v4 = arm_stats([t for t in vblk if t["summary"]["cls"] == cls and t["summary"]["arm"] == "K4"])
        v5 = arm_stats([t for t in vblk if t["summary"]["cls"] == cls and t["summary"]["arm"] == "K5"])
        stats[cls]["K4v"], stats[cls]["K5"] = v4, v5
        pairs = {f"{a}-{b}": paired(stats[cls][a], stats[cls][b]) for a, b in CHAINS[cls]}
        pairs_oracle = {f"{a}-{b}": paired(stats[cls][a], stats[cls][b], "T_oracle_ms") for a, b in CHAINS[cls]}
        pairs["K4v-K5"] = paired(v4, v5)
        pairs_oracle["K4v-K5"] = paired(v4, v5, "T_oracle_ms")
        out["classes"][cls] = {"arms": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                                        for k, v in stats[cls].items()},
                               "paired_T_runner": pairs, "paired_T_oracle": pairs_oracle}

    # Hypotheses.
    hv = {}
    for cls in A.CLASSES:
        s = stats[cls]
        r = ratio_ci(s["K0"], s["K1"], s["K2"])
        resid = paired(s["K1"], s["K2"])
        keep = r["ci95"] is not None and r["ci95"][0] >= 0.90
        hv[cls] = {"ratio": r, "residual_K1_minus_K2": resid, "verdict": "KEEP" if keep else "REVISE"}
    glides = [g for cls in A.CLASSES for arm in ("K0", "K0n") if arm in stats[cls]
              for d in stats[cls][arm]["_decs"] for g in d["glides"]]
    fast = [g for cls in A.CLASSES for d in stats[cls]["K1"]["_decs"] for g in d["glides"]]
    out["glide"] = {
        "on_glides": len(glides),
        "regression_distance": A.regression([g["distance_px"] for g in glides], [g["wait_ms"] for g in glides]),
        "regression_path_length": A.regression([g["path_length_px"] for g in glides], [g["wait_ms"] for g in glides]),
        "wait_median_ms": A.median([g["wait_ms"] for g in glides]),
        "distance_px_median": A.median([g["distance_px"] for g in glides]),
        "path_length_px_median": A.median([g["path_length_px"] for g in glides]),
        "predicted_median_ms": A.median([g["predicted_ms"] for g in glides]),
        "wait_minus_predicted_median_ms": A.median([g["wait_ms"] - g["predicted_ms"] for g in glides]),
        "frames_median": A.median([g["frames"] for g in glides if g["frames"] is not None]),
        "max_frame_ms_max": max([g["max_frame_ms"] for g in glides if g["max_frame_ms"] is not None], default=None),
        "frames_over_50ms_total": sum(g["frames_over_50ms"] or 0 for g in glides),
        "frame_wall_minus_wait_median_ms": A.median([g["frame_wall_ms"] - g["wait_ms"] for g in glides
                                                     if g["frame_wall_ms"] is not None]),
        "fast_glides": len(fast), "fast_wait_median_ms": A.median([g["wait_ms"] for g in fast]),
        "fast_wait_max_ms": max([g["wait_ms"] for g in fast], default=None),
        "timed_out": sum(1 for g in glides + fast if not g["arrived"]),
    }
    hv["glide_profile"] = "see glide"
    out["hypotheses"]["H_V"] = hv

    knob_trials = [t for t in prim + vblk + tblk if t["summary"]["cls"] == "fill" and t["summary"]["arm"] in A.KNOB_ARMS]
    unset_fill = [t for t in prim + vblk + tblk if t["summary"]["cls"] == "fill" and t["summary"]["arm"] not in A.KNOB_ARMS]
    t_stats = {arm: arm_stats([t for t in tblk if t["summary"]["arm"] == arm]) for arm in ("K3", "K2")}
    ht_pair = paired(stats["fill"]["K2"], stats["fill"]["K3"])
    t_pair = paired(t_stats["K2"], t_stats["K3"])
    dk, du = drop_check(knob_trials), drop_check(unset_fill)
    settle_k2 = stats["fill"]["K2"]["sub_mean_ms"].get("settle_focus")
    settle_k3 = stats["fill"]["K3"]["sub_mean_ms"].get("settle_focus")
    if dk["drops"]:
        ht_verdict = "KILL/IRREDUCIBLE"
    elif ht_pair["ci95"] and ht_pair["ci95"][0] > 0:
        ht_verdict = "OWNER_DECISION"
    else:
        ht_verdict = "NOT_MATERIAL"
    # Which settle site ran (the knob shortens both; only the insert_text replace site was exercised).
    sites: dict[str, int] = {}
    key_marks = 0
    for t in trials:
        for x in t["trace"]:
            if x["phase"] == "focus.settle_start":
                k = f"{x['detail']['site']}@{x['detail']['settle_ms']}ms"
                sites[k] = sites.get(k, 0) + 1
            elif x["phase"].startswith("key."):
                key_marks += 1
    out["hypotheses"]["H_T"] = {
        "settle_site_marks": dict(sorted(sites.items())), "key_marks": key_marks,
        "scope": "insert_text replace=true settle site only (enter_focus_emulation); the keystroke-site settle never ran: UNTESTED",
        "paired_K2_minus_K3": ht_pair, "t0_stress_paired_K2_minus_K3": t_pair,
        "t0_stress": {arm: {"n": s["n"], "valid": s["valid"], "failures": s["failures"],
                            "T_runner_median_ms": s["T_runner_ms"]["median"]} for arm, s in t_stats.items()},
        "drops_knob0": dk, "drops_knob_unset": du,
        "settle_focus_mean_ms": {"K2": settle_k2, "K3": settle_k3},
        "verdict": ht_verdict,
    }
    hp = {}
    for cls in A.CLASSES:
        prev = "K3" if cls == "fill" else "K2"
        sp, s4 = stats[cls][prev], stats[cls]["K4"]
        pr = paired(sp, s4)
        frac = sp["sleeps_entered_frac"] or 0.0
        unchanged = (s4["valid"] == s4["n"] or s4["valid_frac"] >= sp["valid_frac"])
        keep = frac >= 0.10 and pr["ci95"] is not None and pr["ci95"][0] > 0 and unchanged
        hp[cls] = {"prev_arm": prev, "sleep_entered_frac_prev": frac,
                   "sleep_entered_trials_prev": sp["sleeps_entered_trials"], "n_prev": sp["valid"],
                   "sleep_entered_frac_K4": s4["sleeps_entered_frac"], "paired_prev_minus_K4": pr,
                   "outcome_unchanged": unchanged,
                   "verdict": "KEEP" if keep else "no material component"}
    out["hypotheses"]["H_P"] = hp
    hc = {}
    for cls in A.CLASSES:
        v4, v5 = stats[cls]["K4v"], stats[cls]["K5"]
        pr = paired(v4, v5)
        unchanged = v5["valid_frac"] is not None and v5["valid_frac"] >= (v4["valid_frac"] or 0)
        keep = pr["ci95"] is not None and pr["ci95"][0] > 0 and unchanged
        hc[cls] = {"paired_K4_minus_K5": pr, "client_validation_mean_ms": {
            "K4": v4["components_mean_ms"]["client_validation"], "K5": v5["components_mean_ms"]["client_validation"]},
            "outcome_unchanged": unchanged, "verdict": "KEEP" if keep else "not material"}
    out["hypotheses"]["H_C"] = hc

    # Gates: validity and coverage.
    gates = {}
    for cls in A.CLASSES:
        arms = {**{a: stats[cls][a] for a in A.CLASS_ARMS[cls]}, "K4v": stats[cls]["K4v"], "K5": stats[cls]["K5"]}
        gates[cls] = {"validity_min_frac": min(s["valid_frac"] for s in arms.values() if s["n"]),
                      "validity_pass": all(s["valid_frac"] >= 0.95 for s in arms.values() if s["n"]),
                      "coverage_mean_min": min(s["coverage_mean"] for s in arms.values() if s["coverage_mean"] is not None),
                      "coverage_pass": all(s["coverage_mean"] >= 0.90 for s in arms.values() if s["coverage_mean"] is not None)}
    out["gates"] = gates

    # E2: decomposition of the best composed arm and the baseline, with verdicts.
    verdict_rules = {
        "visualization": "OWNER_DECISION",
        "settles": {"OWNER_DECISION": "OWNER_DECISION", "KILL/IRREDUCIBLE": "IRREDUCIBLE",
                    "NOT_MATERIAL": "IRREDUCIBLE"}[ht_verdict],
        "observation": "IRREDUCIBLE (one fresh semantic_v2 snapshot per action: refs are never durable authority); per-call cost UNTESTED",
        "revalidate": "IRREDUCIBLE (per-mutation binding re-proof, #73 invariant); endpoint re-proof cost UNTESTED",
        "driver_pre_dispatch": "UNTESTED (localized, not isolated: the mcp.line_read->admitted->inner_validated span holds two validate_tool_call runs against a freshly built tools_list plus JSON parsing, protocol_session.validate and session identity)",
        "driver_post_dispatch": "IRREDUCIBLE (JSON-RPC result handling)",
        "transport": "IRREDUCIBLE (stdio JSON-RPC)",
        "client_validation": None,
        "dispatch": "IRREDUCIBLE (the effectful CDP call)",
        "dispatch_post": "IRREDUCIBLE",
        "target_effect_lag": "IRREDUCIBLE (target-owned)",
        "verification_reads": "IRREDUCIBLE (independent oracle read; events are never the oracle)",
        "sleeps_polls": None,
        "decision": "live decision measured in R2-10 (mock here)",
        "resolution": "IRREDUCIBLE (ref resolution before dispatch)",
        "input_prep": "IRREDUCIBLE (trusted-input focus/selection proof)",
        "runner_overhead": "IRREDUCIBLE (caller glue)",
        "unattributed": "UNTESTED",
    }
    e2 = {}
    for cls in A.CLASSES:
        cands = {a: stats[cls][a] for a in ("K2", "K3", "K4") if a in stats[cls]}
        cands["K5"] = stats[cls]["K5"]
        ok = {a: s for a, s in cands.items() if s["valid_frac"] and s["valid_frac"] >= 0.95}
        if hc[cls]["verdict"] != "KEEP":
            ok.pop("K5", None)
        best = min(ok, key=lambda a: ok[a]["T_runner_ms"]["median"])
        base = "K0n" if cls == "fill" else "K0"
        e2[cls] = {"best_composed_arm": best, "baseline_arm": base}
        for label, arm in (("best", best), ("baseline", base)):
            s = stats[cls][arm]
            meanT = s["T_runner_ms"]["mean"]
            rows = []
            untested = 0.0
            for c in A.COMPONENTS:
                ms = s["components_mean_ms"][c]
                share = s["shares"][c]
                material = ms is not None and (ms >= THRESH_MS or (share or 0) >= THRESH_SHARE)
                v = verdict_rules[c]
                if c == "sleeps_polls":
                    v = "DELETED (H_P KEEP)" if hp[cls]["verdict"] == "KEEP" else \
                        "IRREDUCIBLE (H_P: no material component; P10 (K4) bounds the overshoot)"
                if c == "client_validation":
                    v = "DELETED (caller-side compiled validators, H_C KEEP)" if hc[cls]["verdict"] == "KEEP" else \
                        "DELETED (work only: no T_runner saving, the time moves to target-effect lag + poll)"
                rows.append({"component": c, "mean_ms": ms, "median_ms": s["components_median_ms"][c],
                             "share": share, "material": material, "verdict": v if material else "below threshold"})
            # Untested-but-plausibly-deletable portions (rule written after the runs; see README deviations).
            sub = s["sub_mean_ms"]
            parts = {
                "revalidate_endpoint_reproof": sub.get("reval_endpoint", 0.0),
                "mcp_admission_tool_list_validation": sub.get("pre_admission_validate", 0.0) + sub.get("pre_inner_validate", 0.0),
                "first_snapshot_cold_excess": s["observations"]["first_minus_second_mean_ms"] or 0.0,
                "unattributed": s["components_mean_ms"]["unattributed"],
            }
            untested = sum(parts.values())
            e2[cls][label] = {"arm": arm, "T_runner_mean_ms": meanT, "T_runner_median_ms": s["T_runner_ms"]["median"],
                              "rows": rows, "untested_plausibly_deletable_ms": parts,
                              "untested_share": untested / meanT if meanT else None,
                              "mcp_transport_mean_ms": s["mcp_transport_mean_ms"]}
    out["E2"] = e2

    # Sensitivity (not a gate): every gate recomputed on T_oracle, the spec's T (2 ms harness re-read).
    sens: dict[str, Any] = {}
    for cls in A.CLASSES:
        s = stats[cls]
        r = ratio_ci(s["K0"], s["K1"], s["K2"], "T_oracle_ms")
        prev = "K3" if cls == "fill" else "K2"
        hp_o = paired(s[prev], s["K4"], "T_oracle_ms")
        hc_o = paired(s["K4v"], s["K5"], "T_oracle_ms")
        hc_keep = hc_o["ci95"] is not None and hc_o["ci95"][0] > 0 and hc[cls]["outcome_unchanged"]
        cands = {a: s[a] for a in ("K2", "K3", "K4", "K5") if a in s and s[a]["valid_frac"] and s[a]["valid_frac"] >= 0.95}
        if not hc_keep:
            cands.pop("K5", None)
        best_o = min(cands, key=lambda a: cands[a]["T_oracle_ms"]["median"])
        sens[cls] = {
            "H_V_ratio": r, "H_V_verdict": "KEEP" if (r["ci95"] is not None and r["ci95"][0] >= 0.90) else "REVISE",
            "H_P_paired_prev_minus_K4": hp_o,
            "H_P_verdict": "KEEP" if ((s[prev]["sleeps_entered_frac"] or 0) >= 0.10 and hp_o["ci95"] is not None
                                      and hp_o["ci95"][0] > 0) else "no material component",
            "H_C_paired_K4_minus_K5": hc_o, "H_C_verdict": "KEEP" if hc_keep else "not material",
            "best_composed_arm": best_o, "best_composed_T_oracle_median_ms": cands[best_o]["T_oracle_ms"]["median"],
        }
    ht_o = paired(stats["fill"]["K2"], stats["fill"]["K3"], "T_oracle_ms")
    sens["fill"]["H_T_paired_K2_minus_K3"] = ht_o
    sens["fill"]["H_T_verdict"] = ("KILL/IRREDUCIBLE" if dk["drops"] else
                                   "OWNER_DECISION" if (ht_o["ci95"] and ht_o["ci95"][0] > 0) else "NOT_MATERIAL")
    out["sensitivity_T_oracle"] = sens

    # Controls and invariants.
    def ctrl_rows(kind: str) -> list[dict[str, Any]]:
        rows = []
        for t in ctrl + [x for x in prim + vblk + tblk if x["summary"]["kind"] == kind]:
            s = t["summary"]
            if s["kind"] != kind:
                continue
            row = {"trial": t["name"], "cls": s["cls"], "arm": s["arm"], "completion_mutations": s["completion_mutations"],
                   "oracle_satisfied": s["oracle_exact_match"], "runner_outcome": s["outcome"]}
            if kind == "stale_ref":
                env = s.get("stale_envelope") or {}
                row.update({"effect": env.get("effect"), "is_error": s.get("stale_is_error"),
                            "refusal_code": (env.get("error") or {}).get("code") if isinstance(env.get("error"), dict)
                            else env.get("code"),
                            "dispatch_marks": stale_dispatch_marks(t),
                            "pass": env.get("effect") == "refused" and s["completion_mutations"] == 0})
            elif kind == "first_only":
                row["pass"] = (not s["oracle_exact_match"]) and s["completion_mutations"] == 0
            elif kind == "guard_decline":
                g = (s.get("guard") or [None, None])[1] if len(s.get("guard") or []) > 1 else None
                row.update({"guard": g, "routes": s.get("routes"),
                            "pass": g == {"status": "declined", "reason": "submit_not_unique"}
                            and s.get("routes") == ["provider", "provider"] and s["oracle_exact_match"]
                            and s["completion_mutations"] == 1})
            rows.append(row)
        return rows

    def stale_dispatch_marks(t: dict[str, Any]) -> int:
        """Effectful-dispatch Driver marks inside the stale-ref call window (0 = refused before dispatch)."""
        sends = [e["t_mono_ns"] for e in t["events"] if e["event"] == "call_send" and e.get("label") == "stale_click"]
        rets = [e["t_mono_ns"] for e in t["events"] if e["event"] == "call_return" and e.get("label") == "stale_click"]
        if not sends or not rets:
            return -1
        return sum(1 for x in t["trace"] if sends[0] <= x["t_mono_ns"] <= rets[0]
                   and x["phase"] in ("click.ref_resolved", "click.cdp_send", "type.ref_resolved", "type.insert_send"))

    controls = {k: ctrl_rows(k) for k in ("stale_ref", "first_only", "guard_decline")}
    out["controls"] = {k: {"n": len(v), "pass": sum(1 for r in v if r["pass"]), "rows": v} for k, v in controls.items()}
    stale_cover = {}
    for r in controls["stale_ref"]:
        stale_cover.setdefault(f"{r['cls']}:{r['arm']}", 0)
        stale_cover[f"{r['cls']}:{r['arm']}"] += 1 if r["pass"] else 0
    out["controls"]["stale_ref_pass_per_arm_class"] = stale_cover
    measured_all = prim + vblk + tblk
    out["invariants"] = {
        "duplicate_completion_mutations": sum(1 for t in measured_all + ctrl if (t["summary"]["completion_mutations"] or 0) > 1),
        "unverified_successes": sum(1 for t in measured_all + ctrl if t["summary"]["outcome"] == "verified"
                                    and not t["summary"]["oracle_exact_match"]),
        "stale_ref_completion_mutations": sum(1 for r in controls["stale_ref"] if r["completion_mutations"] != 0),
        "stale_ref_trials_with_dispatch_marks": sum(1 for r in controls["stale_ref"] if r["dispatch_marks"] != 0),
        "stale_ref_refusal_codes": sorted({str(r["refusal_code"]) for r in controls["stale_ref"]}),
        "non_loopback_connect_attempts": sum(t["summary"].get("network", {}).get("non_loopback_connect_attempts", 0)
                                             for t in trials),
    }
    out["smoke"] = {"n": len(smoke), "verified": sum(1 for t in smoke if t["summary"]["outcome"] == "verified"
                                                     and t["summary"]["oracle_exact_match"]),
                    "trace_set": sum(1 for t in smoke if t["summary"].get("driver_env_trace_set")),
                    "knob_set": sum(1 for t in smoke if t["summary"].get("driver_env_knob") is not None)}
    return rnd(out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "b01-summary.json"))
    args = p.parse_args()
    out = build(Path(args.raw))
    Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"written": Path(args.out).name, "trials": out["counts"]["trials_total"]}))


if __name__ == "__main__":
    main()

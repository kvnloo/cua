"""R2-07e analysis: alpha-adjusted modal gate (block q), carry-over controls (block ctl), live Phase L
(block live) and the provider ledger.

Reads only the packet's raw/ (and, for the side-by-side and descriptive pooled view, the committed R2-07d
packet's raw/) and writes r2-07e-summary.json + headline-numbers.json. Reuses, by import and unchanged,
the R2-07d analysis (rows_of, controls, g1_g2, g3_of, pair_stats, e4_clean) and through it the R2-07c
analysis (load_block, manifests, row_of, g4_pass, decomposition, e4_total) and the R2-10 per-trial row.

paired_gate was committed with PREREG.json (097c71313): median paired difference with a seeded paired
percentile bootstrap CI at LEVEL (two-sided 97.5%, seed 20261003, 10 000 resamples). Same resampling
scheme as b01_analysis.boot_ci; only the seed and the level differ.

usage (under hostless): python analyze_r2_07e.py [--raw raw] [--out r2-07e-summary.json]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SEED = 20261003
BOOT = 10000
LEVEL = 0.975
GATE_MS = 2.0


def paired_gate(cr: list[float], comp: list[float], level: float = LEVEL, seed: int = SEED,
                boot: int = BOOT) -> dict[str, Any]:
    """Median of d = cr - comp with a two-sided ``level`` seeded paired bootstrap CI."""
    d = [x - y for x, y in zip(cr, comp)]
    n = len(d)
    out: dict[str, Any] = {"n": n, "median": statistics.median(d) if d else None, "ci": None, "level": level,
                           "seed": seed, "resamples": boot, "min": min(d) if d else None,
                           "max": max(d) if d else None, "positive": sum(1 for x in d if x > 0)}
    if n < 2:
        return out
    rng = random.Random(seed)
    vals = sorted(statistics.median([d[rng.randrange(n)] for _ in range(n)]) for _ in range(boot))
    a = (1.0 - level) / 2.0
    out["ci"] = [vals[int(math.floor(a * (len(vals) - 1)))], vals[int(math.ceil((1.0 - a) * (len(vals) - 1)))]]
    return out


HERE = Path(__file__).resolve().parent
R207D_PKT = HERE.parent / "r2-07d-quiet-timing-phase-l-2026-10-03"
sys.path.insert(0, str(R207D_PKT))
import analyze_r2_07d as AD  # noqa: E402  (puts the R2-07c analysis on sys.path)

AC = AD.AC
CLASSES = AD.CLASSES
Q_ROUNDS = 60
TOGGLE_ROUNDS = (5, 10, 17, 22, 29, 34, 41, 46, 53, 58)
LOAD_CEILING = 3.0
WARM_PLANNED = 29
LIVE_PLANNED = 30
LANE_CAP = {"reached": 18, "attempts": 22}
med, mean = AD.med, AD.mean


def default(o: Any) -> Any:
    return AD.default(o)


def latest_pairs(rows: list[dict[str, Any]], cls: str, rounds: list[int]) -> dict[str, Any]:
    latest: dict[tuple[int, str], dict[str, Any]] = {}
    for r in rows:
        if r["cls"] != cls or r["kind"] not in ("measured", "warm") or r.get("round") is None or r["round"] < 0:
            continue
        key = (r["round"], r["arm"])
        if key not in latest or r["attempt"] > latest[key]["attempt"]:
            latest[key] = r
    pairs, failed, loads, not_run, pairs_q = [], [], [], [], []
    for rnd in rounds:
        a, b = latest.get((rnd, "COMP")), latest.get((rnd, "COMP_CR"))
        if a is None and b is None:
            not_run.append(rnd)
            continue
        if not (a and b and a["valid"] and b["valid"] and a["T_oracle_ms"] is not None and b["T_oracle_ms"] is not None):
            failed.append({"round": rnd, "COMP": None if a is None else a["reasons"],
                           "COMP_CR": None if b is None else b["reasons"]})
            continue
        pairs.append((a["T_oracle_ms"], b["T_oracle_ms"]))
        loads += [a["loadavg_1m"], b["loadavg_1m"]]
        if max(a["loadavg_1m"], b["loadavg_1m"]) <= LOAD_CEILING:
            pairs_q.append((a["T_oracle_ms"], b["T_oracle_ms"]))
    return {"pairs": pairs, "failed": failed, "not_run": not_run, "loads": loads, "pairs_q": pairs_q}


def gate_view(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    st = AD.pair_stats(pairs) if pairs else {"n": 0}
    st["gate_975"] = paired_gate([p[1] for p in pairs], [p[0] for p in pairs])
    return st


def phase_q(raw: Path) -> dict[str, Any]:
    rows = AD.rows_of(raw, "q")
    gate_log = AD.jsonl(raw / "q-load-gate.jsonl")
    progress = json.loads((raw / "q-progress.json").read_text()) if (raw / "q-progress.json").exists() else {}
    Q: dict[str, Any] = {"cells": len(rows),
                         "interrupted_units": sorted(f"{x['unit']}#a{x['attempt']}" for x in progress.get("interrupted", []))}
    Q["load_gate"] = {"attempts": len(gate_log), "starts": sum(1 for g in gate_log if g["start"]),
                      "end_chunk": sum(1 for g in gate_log if not g["start"]),
                      "started_after_wait": sum(1 for g in gate_log if g["start"] and g["waited_s"] > 0),
                      "load_at_start_max": max((g["load_at_start"] for g in gate_log if g["start"]), default=None),
                      "load_at_start_median": med([g["load_at_start"] for g in gate_log if g["start"]]),
                      "chunks": sorted({g["chunk"] for g in gate_log}, key=lambda x: int(x))}
    for cls, rounds in (("modal", list(range(Q_ROUNDS))), ("toggle", list(TOGGLE_ROUNDS))):
        crows = [r for r in rows if r["cls"] == cls]
        lp = latest_pairs(crows, cls, rounds)
        st = gate_view(lp["pairs"])
        gg = AD.g1_g2(crows, cls)
        g3 = AD.g3_of(crows)
        e4 = AC.e4_total(crows)
        trows = [r for r in crows if r["kind"] in ("measured", "warm") and r["valid"]]
        wm = [r for r in crows if r["kind"] == "warm"]
        ci = st["gate_975"]["ci"]
        complete = not lp["failed"] and not lp["not_run"] and len(lp["pairs"]) == len(rounds)
        block = {"timing": {**st, "planned_pairs": len(rounds), "valid_pairs": len(lp["pairs"]),
                            "failed_pairs": lp["failed"], "not_run_rounds": lp["not_run"],
                            "loadavg_1m": {"min": min(lp["loads"]) if lp["loads"] else None, "median": med(lp["loads"]),
                                           "max": max(lp["loads"]) if lp["loads"] else None}},
                 "sensitivity_load_le_3": gate_view(lp["pairs_q"]),
                 "G1": gg["G1"], "G2": gg["G2"], "training": gg["training"], "admission": gg["admission"],
                 "G3": g3, "E4": e4, "E4_clean": AD.e4_clean(e4),
                 "warm": {"n": len(wm), "valid": sum(1 for r in wm if r["valid"]), "fallbacks": sum(1 for r in wm if r["fallback"]),
                          "decisions": sum(r["provider_decisions"] for r in wm)},
                 "decomposition": {arm: AC.decomposition([r for r in trows if r["arm"] == arm]) for arm in ("COMP", "COMP_CR")}}
        if cls == "modal":
            gate_ok = bool(ci and ci[1] <= GATE_MS and complete)
            block["timing"]["gate_ci975_upper_le_2ms"] = gate_ok
            block["phase_S_pass"] = bool(gate_ok and gg["G1"]["pass"] and gg["G2"]["pass"] and g3["pass"]
                                         and AD.e4_clean(e4))
        else:
            block["descriptive_only"] = True
        Q[cls] = block
    Q["first_trial_utc"] = min((r["utc_start"] for r in rows if r.get("utc_start")), default=None)
    return Q


def r2_07d_side_by_side(q_modal_pairs: list[tuple[float, float]]) -> dict[str, Any]:
    """R2-07d's failing modal block next to this one (never pooled into the gate)."""
    raw = R207D_PKT / "raw"
    out: dict[str, Any] = {"source": "r2-07d-quiet-timing-phase-l-2026-10-03 (79f6dd299), raw/q-trials.tar.gz"}
    if not (raw / "q-trials.tar.gz").exists():
        out["available"] = False
        return out
    rows = AD.rows_of(raw, "q")
    lp = latest_pairs(rows, "modal", list(range(AD.ROUNDS)))
    st = AD.pair_stats(lp["pairs"])
    out.update({"available": True, "n": len(lp["pairs"]), "median_T_COMP_ms": st["median_T_COMP_ms"],
                "median_T_COMP_CR_ms": st["median_T_COMP_CR_ms"], "diff_ci95_seed20261002": st["diff_COMP_CR_minus_COMP_ms"],
                "diff_ci975_seed20261003": paired_gate([p[1] for p in lp["pairs"]], [p[0] for p in lp["pairs"]])})
    pooled = lp["pairs"] + q_modal_pairs
    out["pooled_descriptive_only"] = {"n": len(pooled),
                                      "diff_ci975_seed20261003": paired_gate([p[1] for p in pooled], [p[0] for p in pooled]),
                                      "note": "descriptive only; different windows and session env; never a gate"}
    return out


def controls(raw: Path) -> dict[str, Any]:
    C = AD.controls(raw)
    rows = [AC.row_of(t) for t in AC.load_block(raw, "ctl") if t["summary"].get("kind") == "n4b"]
    C["G3_nonfresh_refused"] = {"n4b_cells": len(rows),
                                "nonfresh_attempts": sum(r["g3"]["nonfresh_attempts"] for r in rows),
                                "nonfresh_refused_effect_refused": sum(r["g3"]["nonfresh_refused"] for r in rows),
                                "cells_with_refused_nonfresh": sum(1 for r in rows if r["g3"]["nonfresh_attempts"] >= 1
                                                                   and r["g3"]["nonfresh_refused"] == r["g3"]["nonfresh_attempts"])}
    g = C["G3_nonfresh_refused"]
    g["pass"] = g["n4b_cells"] == 2 and g["cells_with_refused_nonfresh"] == 2
    C["all_pass"] = bool(C["pass"] and C["E4_clean"] and C["G3"]["pass"] and g["pass"]
                         and all(C["G1_G2"][c]["G1"]["pass"] and C["G1_G2"][c]["G2"]["pass"] for c in CLASSES))
    return C


def fb_row(r: dict[str, Any] | None, summ: dict[str, Any]) -> dict[str, Any] | None:
    if r is None:
        return None
    ok, note = AC.g4_pass(r)
    return {"trial": r["trial"], "kind": r["kind"], "outcome": r["outcome"], "routine_outcome": r["routine_outcome"],
            "verified": r["verified"], "completion_mutations": r["completion_mutations"],
            "accepted_mutations": r["accepted_mutations"], "fallback": r["fallback"], "decisions": r["provider_decisions"],
            "requests": r["provider_requests"], "T_oracle_ms": r["T_oracle_ms"], "t_to_end_ms": r.get("t_to_end_ms"),
            "decided": [x.get("choice") for x in (summ.get(r["trial"], {}).get("decisions") or [])], "E4": r["e4"], "row_pass": ok,
            "note": note, "loadavg_1m": r["loadavg_1m"]}


def phase_l(raw: Path, q_modal_pass: bool, controls_pass: bool) -> dict[str, Any]:
    rows = AD.rows_of(raw, "live")
    summ = {t["name"]: t["summary"] for t in AC.load_block(raw, "live")}
    man = AC.manifests(raw, "live")
    not_run = [x for m in man for x in m.get("not_run", [])]
    L: dict[str, Any] = {"run": bool(rows), "manifests": len(man), "not_run": not_run,
                         "stopped_for_budget": [m.get("stopped_for_budget") for m in man if m.get("stopped_for_budget")],
                         "kind_changes": [x for m in man for x in m.get("kind_changes", [])], "provider_models": {},
                         "classes_run": sorted({c for m in man for c in m.get("classes", [])})}
    for m in man:
        for k, v in (m.get("provider_models") or {}).items():
            L["provider_models"][k] = L["provider_models"].get(k, 0) + v
    pre = {"toggle": {"phase_S": True, "phase_S_source": "R2-07d toggle Phase S PASS (accepted)", "controls": controls_pass},
           "modal": {"phase_S": q_modal_pass, "phase_S_source": "R2-07e Part Q", "controls": controls_pass}}
    for cls in CLASSES:
        p = pre[cls]
        crow = [r for r in rows if r["cls"] == cls]
        inv = [r for r in crow if r["kind"] in ("train", "warm")]
        tr = [r for r in inv if r["kind"] == "train"]
        wm = [r for r in inv if r["kind"] == "warm"]
        ad = [r for r in crow if r["kind"] == "admission"]
        lf = next((r for r in crow if r["kind"] == "n7"), None)
        ln = next((r for r in crow if r["kind"] == "n1"), None)
        nr = [x for x in not_run if f"-{cls}-" in x["trial"]]
        entry: dict[str, Any] = {"precondition": {**p, "met": bool(p["phase_S"] and p["controls"])}}
        if not crow:
            entry["status"] = "NOT_RUN"
            entry["reason"] = ("precondition failed: " + ("Part Q modal gate FAIL" if not p["phase_S"] else "controls")
                               if not entry["precondition"]["met"] else
                               ("budget" if any(x["reason"] == "budget" for x in nr) else "not run"))
            entry["verdict"] = "NOT_RUN"
            L[cls] = entry
            continue
        valid = sum(1 for r in wm if r["valid"])
        t_all = [r["T_oracle_ms"] for r in inv if r["T_oracle_ms"] is not None]
        compile_ms = sum((r["training"] or {}).get("compile_ms") or 0 for r in tr)
        adm_T = sum(r["T_oracle_ms"] or 0 for r in ad)
        mean_warm = mean([r["T_oracle_ms"] for r in wm if r["T_oracle_ms"] is not None])
        base_sum = sum(t_all) + compile_ms + adm_T
        mean_all = base_sum / LIVE_PLANNED if inv else None
        lf_T = (lf or {}).get("T_oracle_ms")
        mean_all_fb = (base_sum + lf_T) / (LIVE_PLANNED + 1) if (inv and lf_T is not None) else None
        all_cells = crow
        e4 = AC.e4_total(all_cells)
        warm_req = sum((r["provider_requests"] or {}).get("attempts", 0) for r in wm)
        dec_inv = sum(r["provider_decisions"] for r in inv)
        req_tr = sum((r["provider_requests"] or {}).get("reached", 0) for r in tr)
        decomp_all = AC.decomposition([r for r in inv if r["verified"]])
        decomp_warm = AC.decomposition([r for r in wm if r["valid"]])
        decomp_tr = AC.decomposition([r for r in tr if r["verified"]])
        lf_v = fb_row(lf, summ)
        ln_v = fb_row(ln, summ)
        entry.update({
            "status": "RUN", "invocations_run": len(inv), "planned": LIVE_PLANNED, "not_run": nr,
            "training": [{"trial": r["trial"], "verified": r["verified"], "T_oracle_ms": r["T_oracle_ms"],
                          "decisions": r["provider_decisions"], "requests": r["provider_requests"],
                          "compile_ms": (r["training"] or {}).get("compile_ms"),
                          "admitted": (r["training"] or {}).get("admitted"), "models": r.get("provider_models")} for r in tr],
            "admission": [{"trial": r["trial"], "verified": r["verified"], "valid": r["valid"], "T_oracle_ms": r["T_oracle_ms"],
                           "decisions": r["provider_decisions"], "requests": r["provider_requests"]} for r in ad],
            "warm": {"n_run": len(wm), "planned": WARM_PLANNED, "valid": valid, "validity": valid / WARM_PLANNED,
                     "fallbacks": sum(1 for r in wm if r["fallback"]), "decisions": sum(r["provider_decisions"] for r in wm),
                     "provider_requests": warm_req,
                     "median_T_oracle_ms": med([r["T_oracle_ms"] for r in wm if r["T_oracle_ms"] is not None]),
                     "mean_T_oracle_ms": mean_warm,
                     "invalid": [{"trial": r["trial"], "reasons": r["reasons"]} for r in wm if not r["valid"]]},
            "T_training_ms": [r["T_oracle_ms"] for r in tr], "compile_ms": compile_ms, "T_admission_ms": [r["T_oracle_ms"] for r in ad],
            "mean_all_ms": mean_all, "mean_all_with_fallback_ms": mean_all_fb,
            "ratio_of_means": (mean_all / mean_warm) if (mean_all and mean_warm) else None,
            "ratio_of_means_with_fallback": (mean_all_fb / mean_warm) if (mean_all_fb and mean_warm) else None,
            "decisions_total_30": dec_inv, "decisions_per_invocation_30": dec_inv / LIVE_PLANNED,
            "decisions_per_invocation_31_incl_LF": (dec_inv + ((lf_v or {}).get("decisions") or 0)) / (LIVE_PLANNED + 1),
            "work_deleted_per_warm": {"decisions": (sum(r["provider_decisions"] for r in tr) / len(tr) if tr else None),
                                      "provider_requests_reached": (req_tr / len(tr) if tr else None),
                                      "note": "training (ordinary step loop) minus warm (0 expected); wall-clock reported separately"},
            "decomposition_warm": decomp_warm, "decomposition_all": decomp_all, "decomposition_training": decomp_tr,
            "provider_decision_share_all": (decomp_all.get("share") or {}).get("provider_decision"),
            "provider_decision_share_warm": (decomp_warm.get("share") or {}).get("provider_decision"),
            "provider_decision_share_training": (decomp_tr.get("share") or {}).get("provider_decision"),
            "LF": lf_v, "LN_descriptive": ln_v,
            "G3": AD.g3_of(all_cells), "E4": e4, "E4_clean": AD.e4_clean(e4),
            "loadavg_1m": {"min": min((r["loadavg_1m"] for r in inv), default=None), "median": med([r["loadavg_1m"] for r in inv]),
                           "max": max((r["loadavg_1m"] for r in inv), default=None)}})
        failing = []
        if valid != WARM_PLANNED:
            failing.append(f"warm_validity={valid}/{WARM_PLANNED}")
        if entry["warm"]["decisions"] != 0:
            failing.append(f"warm_decisions={entry['warm']['decisions']}")
        if warm_req != 0:
            failing.append(f"warm_provider_lines={warm_req}")
        if not entry["E4_clean"]:
            failing.append("E4")
        if not (lf_v and lf_v["row_pass"] and lf_v["verified"] and (lf_v["decisions"] or 0) >= 1):
            failing.append("LF_fallback_not_verified")
        if not p["phase_S"]:
            failing.append("phase_S")
        if ln_v is not None and (ln_v["verified"] or ln_v["E4"].get("unverified_success")):
            failing.append("LN_reported_success")
        entry["failing_gates"] = failing
        entry["verdict"] = "DELETED" if not failing else "REVISE"
        entry["e4_kill_candidate"] = not entry["E4_clean"]
        L[cls] = entry
    L["first_trial_utc"] = min((r["utc_start"] for r in rows if r.get("utc_start")), default=None)
    L["shakedown"] = [{"trial": r["trial"], "kind": r["kind"], "verified": r["verified"], "decisions": r["provider_decisions"],
                       "requests": r["provider_requests"], "models": r.get("provider_models")} for r in AD.rows_of(raw, "lshake")]
    return L


def provider(raw: Path) -> dict[str, Any]:
    led = AD.jsonl(raw / "provider-ledger.jsonl")
    att = [x for x in led if x.get("kind") == "attempt"]
    return {"attempts": len(att), "reached": sum(1 for x in att if x.get("reached")),
            "blocked_by_cap": sum(1 for x in led if x.get("kind") == "blocked_by_cap"),
            "by_layer": dict(Counter(x.get("layer") for x in att)),
            "reached_by_layer": dict(Counter(x.get("layer") for x in att if x.get("reached"))),
            "status": dict(Counter(str(x.get("status")) for x in att)),
            "request_id_present": sum(1 for x in att if x.get("request_id_present")),
            "hosts": sorted({str(x.get("host")) for x in att}), "paths": sorted({str(x.get("path")) for x in att}),
            "latency_ms_median": med([x["latency_ms"] for x in att if x.get("latency_ms") is not None]),
            "lane_cap": LANE_CAP,
            "within_cap": len(att) <= LANE_CAP["attempts"] and sum(1 for x in att if x.get("reached")) <= LANE_CAP["reached"]}


def analyze(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "r2-07e.summary.v1"}
    S["part_Q"] = phase_q(raw)
    rows = AD.rows_of(raw, "q")
    S["part_Q"]["r2_07d_modal_side_by_side"] = r2_07d_side_by_side(latest_pairs(rows, "modal", list(range(Q_ROUNDS)))["pairs"])
    S["part_C"] = controls(raw)
    q_pass = bool(S["part_Q"]["modal"].get("phase_S_pass"))
    S["part_L"] = phase_l(raw, q_pass, S["part_C"]["all_pass"])
    S["provider"] = provider(raw)
    arts = {}
    for p in sorted((raw / "artifacts").glob("*.json")) if (raw / "artifacts").exists() else []:
        art = json.loads(p.read_text())
        arts[p.name] = {"problems": AC.crt.check_artifact_authority_tm(art), "task_class": art.get("task_class"),
                        "steps": [s["logical_target"] for s in art.get("steps", [])]}
    S["artifacts"] = arts
    S["authority_clean"] = bool(arts) and all(not v["problems"] for v in arts.values())
    starts = [x for x in (S["part_Q"]["first_trial_utc"], S["part_C"]["first_trial_utc"], S["part_L"]["first_trial_utc"]) if x]
    S["first_measured_trial_utc"] = min(starts) if starts else None
    Q, C, L = S["part_Q"], S["part_C"], S["part_L"]
    per_class = {}
    for cls in CLASSES:
        v = L[cls]["verdict"]
        per_class[cls] = {"phase_L_verdict": v, "lineage": "KEEP" if v == "DELETED" else ("REVISE" if v == "REVISE" else "REVISE (L NOT_RUN)"),
                          "failing_gates": L[cls].get("failing_gates") or ([L[cls].get("reason")] if v == "NOT_RUN" else []),
                          "e4_kill_candidate": bool(L[cls].get("e4_kill_candidate"))}
    failing = []
    if not Q["modal"]["timing"]["gate_ci975_upper_le_2ms"]:
        failing.append("Q:modal_timing")
    for g in ("G1", "G2", "G3"):
        if not Q["modal"][g]["pass"]:
            failing.append(f"Q:modal_{g}")
    if not Q["modal"]["E4_clean"]:
        failing.append("Q:modal_E4")
    if not C["all_pass"]:
        failing.append("controls")
    if not S["authority_clean"]:
        failing.append("authority")
    S["disposition"] = {"part_Q_modal": "PASS" if Q["modal"]["phase_S_pass"] else "FAIL",
                        "controls": "PASS" if C["all_pass"] else "FAIL", "per_class": per_class,
                        "failing_gates": failing,
                        "lineage": ("KEEP" if all(per_class[c]["lineage"] == "KEEP" for c in CLASSES) else
                                    "KEEP (toggle) / REVISE (modal)" if per_class["toggle"]["lineage"] == "KEEP" else "REVISE"),
                        "e4_kill_candidate": (not Q["modal"]["E4_clean"]) or (not C["E4_clean"])
                        or any(per_class[c]["e4_kill_candidate"] for c in CLASSES)}
    return S


def f1(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def headlines(S: dict[str, Any]) -> dict[str, Any]:
    """Every number the README headline cites, with the exact text that must appear in README.md."""
    H: dict[str, Any] = {}
    Q = S["part_Q"]
    for cls in ("modal", "toggle"):
        t = Q[cls]["timing"]
        g = t["gate_975"]
        if g.get("ci"):
            H[f"Q_{cls}_diff975"] = {"value": [round(g["median"], 3), round(g["ci"][0], 3), round(g["ci"][1], 3)],
                                     "text": f"{g['median']:+.1f} ms [{g['ci'][0]:+.1f}, {g['ci'][1]:+.1f}]"}
            H[f"Q_{cls}_medians"] = {"value": [round(t["median_T_COMP_ms"], 3), round(t["median_T_COMP_CR_ms"], 3)],
                                     "text": f"{t['median_T_COMP_ms']:.1f} -> {t['median_T_COMP_CR_ms']:.1f} ms"}
        H[f"Q_{cls}_pairs"] = {"value": t["valid_pairs"], "text": f"{t['valid_pairs']}/{t['planned_pairs']} pairs valid"}
    H["Q_modal_gate"] = {"value": Q["modal"]["timing"]["gate_ci975_upper_le_2ms"],
                         "text": f"modal gate {'PASS' if Q['modal']['timing']['gate_ci975_upper_le_2ms'] else 'FAIL'}"}
    g = Q["load_gate"]
    H["Q_load_gate"] = {"value": [g["attempts"], g["starts"], g["end_chunk"]],
                        "text": f"{g['attempts']} gate attempts, {g['starts']} starts, {g['end_chunk']} chunk ends"}
    C = S["part_C"]
    H["controls"] = {"value": [C["pass_cells"], C["expected_cells"]], "text": f"controls {C['pass_cells']}/{C['expected_cells']} pass"}
    P = S["provider"]
    H["provider"] = {"value": [P["attempts"], P["reached"]], "text": f"{P['attempts']} attempts / {P['reached']} reached"}
    L = S["part_L"]
    for cls in CLASSES:
        e = L[cls]
        H[f"L_{cls}_verdict"] = {"value": e["verdict"], "text": f"{cls}: {e['verdict']}"}
        if e.get("status") == "RUN":
            w = e["warm"]
            H[f"L_{cls}_warm_valid"] = {"value": w["valid"], "text": f"warm valid {w['valid']}/29"}
            H[f"L_{cls}_warm_decisions"] = {"value": [w["decisions"], w["provider_requests"]],
                                            "text": f"warm decisions {w['decisions']}, warm provider lines {w['provider_requests']}"}
            if w["median_T_oracle_ms"] is not None:
                H[f"L_{cls}_warm_median"] = {"value": round(w["median_T_oracle_ms"], 3), "text": f"{w['median_T_oracle_ms']:.1f} ms"}
    H["lineage"] = {"value": S["disposition"]["lineage"], "text": f"Lineage disposition: {S['disposition']['lineage']}"}
    return H


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "r2-07e-summary.json"))
    p.add_argument("--headlines", default=str(HERE / "headline-numbers.json"))
    a = p.parse_args()
    S = json.loads(json.dumps(analyze(Path(a.raw)), sort_keys=True, default=default))
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    Path(a.headlines).write_text(json.dumps(headlines(S), indent=1, sort_keys=True) + "\n")
    print(json.dumps({"disposition": S["disposition"], "provider": S["provider"],
                      "Q_modal": {k: S["part_Q"]["modal"]["timing"].get(k) for k in ("valid_pairs", "gate_ci975_upper_le_2ms",
                                                                                     "median_T_COMP_ms", "median_T_COMP_CR_ms", "gate_975")},
                      "controls": {k: S["part_C"][k] for k in ("all_pass", "pass_cells", "expected_cells", "E4_clean")}},
                     indent=1, default=str))


if __name__ == "__main__":
    main()

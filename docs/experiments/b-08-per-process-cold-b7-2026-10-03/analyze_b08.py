#!/usr/bin/env python3
"""B-08 analysis: recompute every number from raw/ (standard library only; run it under bin/hostless).

Rules are PREREG.json's. Per-trial rows: b08_rows.py (B-04's b04_rows + T_j, E4, routes). Part E uses R2-10R's
own analysis code (harness/r2-10r/analyze_r2_10.py with the src/b-02 modules, blob-identical from the B-07
packet) and B-05's sub-span decomposition (harness/b05/b05_spans.py), with the verdict map in PREREG.json.

usage: analyze_b08.py [--raw raw] [--out b08-summary.json]
       analyze_b08.py --trials-dir <dir> --out <file>    (pilot / smoke check of the pipeline; no gate)
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
H = HERE / "harness"
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(H / "b05"), str(H / "r2-10r" / "src" / "b-02-browser-driver-sites-2026-10-02"),
                str(H / "r2-10r")]
import b08_rows as R  # noqa: E402
import b01_analysis as B  # noqa: E402
import analyze_browser as AB  # noqa: E402,F401  (installs the B-02 classify_mark extension on B)
import analyze_r2_10 as A  # noqa: E402
import b05_spans as SP  # noqa: E402

PREREG = json.loads((HERE / "PREREG.json").read_text())
SEED = 20261003
BOOT = 10000
CLASSES = ["fill", "toggle", "modal"]
ARMS = ["C", "Wa", "Wb", "P2"]
NC_BAND = (-2.0, 2.0)
PC2_WINDOW = (12.0, 18.0)
VALID_MIN = 0.95
AGREE_MIN = 0.95
OD_LO = 1.0
SHARE = 0.05
ABS_MS = 50.0
LOAD_MAX = 4.0
COVERAGE_MIN = 0.98
GATE_MS = 0.5
VM = PREREG["part_E"]["verdict_map"]
LANE_SCOPE = set(VM["lane_scope_components"])
UNIT_MEMBERS = {u: VM["unit_members"].get(u, [u]) for u in VM["units"] if u != "any other lane-scope label"}
SUB_TO_UNIT = {m: u for u, ms in UNIT_MEMBERS.items() for m in ms}


# ── statistics ────────────────────────────────────────────────────────────────
def median_ci(d: list[float]) -> dict[str, Any]:
    """Median of paired differences + percentile bootstrap CI (fresh Random(SEED) per call)."""
    n = len(d)
    if n == 0:
        return {"n_pairs": 0, "median": None, "ci": None}
    rng = random.Random(SEED)
    vals = sorted(statistics.median([d[rng.randrange(n)] for _ in range(n)]) for _ in range(BOOT))
    return {"n_pairs": n, "median": statistics.median(d), "ci": [vals[250], vals[9749]], "mean": sum(d) / n}


def med(xs: list[Any]) -> float | None:
    v = [x for x in xs if x is not None]
    return statistics.median(v) if v else None


def mean(xs: list[Any]) -> float | None:
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


def rnd(x: Any, nd: int = 4) -> Any:
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, list):
        return [rnd(y, nd) for y in x]
    if isinstance(x, dict):
        return {k: rnd(v, nd) for k, v in x.items()}
    return x


# ── loading ──────────────────────────────────────────────────────────────────
def load(raw: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trials: list[dict[str, Any]] = []
    tar = raw / "main-trials.tar.gz"
    if tar.exists():
        trials = R.load_tar(tar)
    mans = [json.loads(p.read_text()) for p in sorted((raw / "main").glob("run-manifest-*.json"))]
    return trials, mans


def name_of(t: dict[str, Any]) -> str:
    return t["summary"]["trial"]


def select_rounds(trials: list[dict[str, Any]], mans: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """PREREG round_attempts: for each round the first attempt listed as completed in a manifest."""
    done: dict[int, int] = {}
    for m in mans:
        for r in m.get("rounds_completed", []):
            a = int(m.get("attempt", 1))
            done[r] = min(done.get(r, a), a)
    used, cut = [], []
    for t in trials:
        s = t["summary"]
        r, a = s.get("round"), int(s.get("attempt") or 1)
        (used if done.get(r) == a else cut).append(t)
    info = {"rounds_used": sorted(done), "attempt_by_round": {str(k): v for k, v in sorted(done.items())},
            "trials_in_used_rounds": len(used), "trials_in_cut_or_unlisted_attempts": [name_of(t) for t in cut]}
    return used, info


# ── per class ─────────────────────────────────────────────────────────────────
def pairs(rows: list[dict[str, Any]], cls: str, a: str, b: str, key: str = "T_j_ms",
          rounds: set[int] | None = None) -> list[float]:
    by: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for x in rows:
        if x["cls"] == cls and x["b08_arm"] in ARMS:
            by[x["round"]][x["b08_arm"]] = x
    out = []
    for rd in sorted(by):
        if rounds is not None and rd not in rounds:
            continue
        xa, xb = by[rd].get(a), by[rd].get(b)
        if xa and xb and xa["valid"] and xb["valid"] and xa.get(key) is not None and xb.get(key) is not None:
            out.append(xa[key] - xb[key])
    return out


def e4_sum(rows: list[dict[str, Any]]) -> dict[str, int]:
    tot: Counter = Counter({k: 0 for k in PREREG["e4"]["counters"]})
    for x in rows:
        tot.update(x["e4"])
    return dict(tot)


def arm_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    v = [x for x in rows if x["valid"]]
    sub = defaultdict(list)
    for x in v:
        for k, val in (x.get("snapshot1_sub") or {}).items():
            sub[k].append(val)
    return {"n": len(rows), "valid": len(v), "valid_share": (len(v) / len(rows)) if rows else None,
            "invalid": [{"trial": x["trial"], "outcome": x.get("outcome"), "valid_b04": x.get("valid_b04"),
                         "pids_ok": x.get("pids_ok"), "T_j": x.get("T_j_ms"), "e4": {k: c for k, c in x["e4"].items() if c},
                         "telemetry_off": x.get("telemetry_off"), "driver_id_ok": x.get("driver_id_ok"),
                         "route_ok": x.get("route_ok"), "arm_ok": x.get("arm_ok")} for x in rows if not x["valid"]],
            "T_j_median": med([x["T_j_ms"] for x in v]), "T_j_mean": mean([x["T_j_ms"] for x in v]),
            "T_oracle_median": med([x["T_oracle_ms"] for x in v]),
            "T_j_from": dict(Counter(x.get("T_j_from") for x in v)),
            "snapshot1_span_median": med([x.get("snapshot1_span_ms") for x in v]),
            "snapshot1_call_median": med([x.get("snapshot1_call_ms") for x in v]),
            "snapshot1_sub_median": {k: med(vs) for k, vs in sorted(sub.items())},
            "E_snapshot1_minus_snapshot2_median": med([x.get("excess_b03_ms") for x in v]),
            "E_snapshot1_minus_snapshot2_mean": mean([x.get("excess_b03_ms") for x in v]),
            "warmup_median": med([x.get("warmup_span_ms") for x in v]),
            "pc_sleep_ms": {"median": med([x.get("pc_sleep_ms") for x in v]),
                            "max": max((x["pc_sleep_ms"] for x in v if x.get("pc_sleep_ms") is not None), default=None),
                            "min": min((x["pc_sleep_ms"] for x in v if x.get("pc_sleep_ms") is not None), default=None)},
            "loadavg_1m": {"median": med([x.get("loadavg_before_1m") for x in rows]),
                           "max": max((x["loadavg_before_1m"] for x in rows if x.get("loadavg_before_1m") is not None), default=None)},
            "e4": e4_sum(rows)}


def verdict(cls_doc: dict[str, Any]) -> tuple[str, list[str]]:
    failed = []
    nc = cls_doc["NC_Wa_minus_Wb"]
    if not (nc["ci"] and NC_BAND[0] <= nc["ci"][0] and nc["ci"][1] <= NC_BAND[1]):
        failed.append("NC")
    pc = cls_doc["PC2_P2_minus_Wa"]
    if not (pc["median"] is not None and PC2_WINDOW[0] <= pc["median"] <= PC2_WINDOW[1] and pc["ci"]
            and (pc["ci"][0] > 0 or pc["ci"][1] < 0)):
        failed.append("PC2")
    if any((cls_doc["arms"][a]["valid_share"] or 0) < VALID_MIN for a in ARMS):
        failed.append("validity")
    if any(any(cls_doc["arms"][a]["e4"].values()) for a in ARMS + ["SMOKE"] if a in cls_doc["arms"]):
        failed.append("E4")
    if failed:
        return "UNDECIDED", failed
    D, TC = cls_doc["D_C_minus_Wa"], cls_doc["T_C_median"]
    lo, hi = D["ci"]
    if lo > OD_LO and (D["median"] >= SHARE * TC or D["median"] >= ABS_MS):
        return "OWNER_DECISION", []
    if hi < SHARE * TC and hi < ABS_MS:
        return "NOT_MATERIAL", []
    return "UNDECIDED_WIDE", []


# ── Part E ───────────────────────────────────────────────────────────────────
def r210_trial(t: dict[str, Any]) -> dict[str, Any]:
    return {**t, "summary": dict(t["summary"]), "trace": SP.r210_view(t["trace"])}


def unit_of(lab: str) -> str | None:
    return SUB_TO_UNIT.get(lab)


def unit_verdict(unit: str | None, cls: str) -> tuple[str, str]:
    if unit is None:
        return "UNTESTED", "-"
    v, src = VM["units"][unit]
    return (v[cls] if isinstance(v, dict) else v), src


def comp_verdict(comp: str, cls: str) -> tuple[str, str]:
    """R2-10 component outside the lane scope -> PREREG verdict map (observation = its IRREDUCIBLE rest; the cold
    carve-out is applied in part_e_arm). A component the map does not name is UNTESTED."""
    key = "observation (rest)" if comp == "observation" else comp
    if key not in VM:
        return "UNTESTED", "-"
    v, src = VM[key]
    return (v[cls] if isinstance(v, dict) else v), src


def bucket(v: str, bg: str) -> str:
    if v == "BELOW_GATE":
        return bg
    for k in ("DELETED", "IRREDUCIBLE", "OWNER_DECISION", "UNTESTED"):
        if v.startswith(k):
            return k
    return "UNTESTED"


def pp_bucket(lane_verdict: str) -> str:
    return {"OWNER_DECISION": "OWNER_DECISION", "NOT_MATERIAL": "IRREDUCIBLE"}.get(lane_verdict, "UNTESTED")


def decompose_rows(trials: list[dict[str, Any]], rows: dict[str, dict[str, Any]], c_m: float) -> list[dict[str, Any]]:
    out = []
    for t in trials:
        x = rows[name_of(t)]
        d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, c_m)
        d210 = B.decompose(r210_trial(t))
        if d is None or d210 is None:
            out.append({"trial": x["trial"], "ok": False})
            continue
        e2c = A.e2_components(d210)
        mine = {k: sum(v.values()) for k, v in d["by_comp"].items()}
        other = sum(v for k, v in d["sub"].items() if k.startswith("other.") or k == "c_other")
        cov = 1 - other / d["T_runner_ms"] if d["T_runner_ms"] else None
        out.append({"trial": x["trial"], "ok": True, "T_runner_ms": d["T_runner_ms"], "T_runner_corr_ms": d["T_runner_corr_ms"],
                    "by_comp": d["by_comp"], "by_comp_corr": d["by_comp_corr"], "n_marks_in_T": d["n_marks_in_T"],
                    "consistency_max_abs_ms": max(abs(e2c.get(k, 0.0) - mine.get(k, 0.0)) for k in set(e2c) | set(mine)),
                    "coverage_b05": cov, "coverage_r210": d210["coverage"], "E_ms": x.get("excess_b03_ms"),
                    "T_j_ms": x.get("T_j_ms")})
    return out


def part_e_arm(dec: list[dict[str, Any]], cls: str, view: str, bg: str, carve: dict[str, float]) -> dict[str, Any]:
    v = [d for d in dec if d["ok"] and d["coverage_b05"] is not None and d["coverage_b05"] >= COVERAGE_MIN]
    T = mean([d["T_runner_ms"] if view == "raw" else d["T_runner_corr_ms"] for d in v])
    bc = "by_comp" if view == "raw" else "by_comp_corr"
    comps = sorted({c for d in v for c in d[bc]})
    acc: dict[str, float] = defaultdict(float)
    items: list[dict[str, Any]] = []
    comp_tot: dict[str, float] = {}
    units: dict[str, float] = defaultdict(float)
    for comp in comps:
        labs = sorted({lab for d in v for lab in d[bc].get(comp, {})})
        comp_tot[comp] = mean([sum(d[bc].get(comp, {}).values()) for d in v]) or 0.0
        for lab in labs:
            m = mean([d[bc].get(comp, {}).get(lab, 0.0) for d in v]) or 0.0
            if comp in LANE_SCOPE:
                unit = unit_of(lab)
                verd, src = unit_verdict(unit, cls)
                units[unit or f"other:{lab}"] += m
            else:
                verd, src = comp_verdict(comp, cls)
            b = bucket(verd, bg)
            acc[b] += m
            items.append({"component": comp, "label": lab, "unit": unit_of(lab) if comp in LANE_SCOPE else None,
                          "mean_ms": m, "verdict": verd, "source": src, "bucket": b})
    # cold carve-out inside observation (IRREDUCIBLE by the map): move the per-process part to the lane bucket
    pp, pdoc = carve.get("per_process_ms", 0.0), carve.get("per_document_ms", 0.0)
    acc["IRREDUCIBLE"] -= pp
    acc[carve["per_process_bucket"]] += pp
    untested = acc["UNTESTED"]
    listed = []
    rows_c = []
    for comp, tot in sorted(comp_tot.items(), key=lambda kv: -kv[1]):
        if comp == "observation":
            parts = [("observation (rest)", tot - pp - pdoc, "IRREDUCIBLE", "B-04"),
                     ("cold per-document", pdoc, "IRREDUCIBLE", "B-04 (SOURCE carry)"),
                     ("cold per-process", pp, carve["lane_verdict"], "B-08")]
            for name, val, verd, src in parts:
                rows_c.append({"component": name, "mean_ms": val, "verdict": verd, "source": src})
        elif comp in LANE_SCOPE:
            rows_c.append({"component": comp, "mean_ms": tot, "verdict": "per unit (see units)", "source": "B-05 / B-07"})
        else:
            verd, src = comp_verdict(comp, cls)
            rows_c.append({"component": comp, "mean_ms": tot, "verdict": verd, "source": src})
    for rc_ in rows_c:
        rc_["share"] = rc_["mean_ms"] / T if T else None
        if rc_["mean_ms"] >= ABS_MS or (T and rc_["mean_ms"] >= SHARE * T):
            listed.append(rc_)
    unit_rows = []
    for u, val in sorted(units.items(), key=lambda kv: -kv[1]):
        verd, src = unit_verdict(u if u in UNIT_MEMBERS else None, cls)
        r_ = {"unit": u, "mean_ms": val, "share": val / T if T else None, "verdict": verd, "source": src}
        unit_rows.append(r_)
        if val >= ABS_MS or (T and val >= SHARE * T):
            listed.append({"component": f"unit {u}", "mean_ms": val, "share": r_["share"], "verdict": verd, "source": src})
    flags = [r_["unit"] for r_ in unit_rows if r_["verdict"] == "BELOW_GATE" and r_["mean_ms"] >= GATE_MS and view == "corr"]
    return {"n": len(v), "excluded_coverage": len([d for d in dec if d["ok"]]) - len(v), "mean_T_ms": T,
            "by_bucket_ms": dict(acc), "untested_ms": untested, "untested_share": untested / T if T else None,
            "components": rows_c, "units": unit_rows, "listed_ge_5pct_or_50ms": listed,
            "untested_items": [i for i in items if i["bucket"] == "UNTESTED" and i["mean_ms"] > 0.01]
            + ([{"component": "observation", "label": "cold per-process", "mean_ms": pp, "verdict": carve["lane_verdict"],
                 "source": "B-08", "bucket": "UNTESTED"}] if carve["per_process_bucket"] == "UNTESTED" and pp > 0 else []),
            "below_gate_carried_with_corr_mean_ge_0_5ms": flags}


def part_e(trials_by: dict[tuple[str, str], list[dict[str, Any]]], rows: dict[str, dict[str, Any]],
           verdicts: dict[str, str], D: dict[str, dict[str, Any]]) -> dict[str, Any]:
    nulls: list[float] = []
    for (cls, arm), ts in trials_by.items():
        for t in ts:
            if t["trace"]:
                d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, 0.0)
                if d:
                    nulls += d["null_us"]
    c_m = (statistics.median(nulls) / 1000.0) if nulls else 0.0
    out: dict[str, Any] = {"c_m_us": c_m * 1000.0, "n_null_samples": len(nulls), "classes": {}}
    for cls in CLASSES:
        dec = {arm: decompose_rows(trials_by.get((cls, arm), []), rows, c_m) for arm in ("C", "Wa")}
        E = {arm: mean([d["E_ms"] for d in dec[arm] if d["ok"]]) for arm in dec}
        lane = verdicts[cls]
        pp = max(0.0, (E["C"] or 0.0) - (E["Wa"] or 0.0))
        carves = {"C": {"per_process_ms": pp, "per_document_ms": (E["C"] or 0.0) - pp, "lane_verdict": lane,
                        "per_process_bucket": pp_bucket(lane)},
                  "Wa": {"per_process_ms": 0.0, "per_document_ms": E["Wa"] or 0.0, "lane_verdict": lane,
                         "per_process_bucket": pp_bucket(lane)}}
        res: dict[str, Any] = {"E_mean_ms": E, "cold_per_process_ms_C": pp, "lane_verdict": lane}
        for arm in ("C", "Wa"):
            ok = [d for d in dec[arm] if d["ok"]]
            res[arm] = {"n_decomposed": len(ok), "n_failed": len(dec[arm]) - len(ok),
                        "consistency_max_abs_ms": max((d["consistency_max_abs_ms"] for d in ok), default=None),
                        "coverage_b05_min": min((d["coverage_b05"] for d in ok if d["coverage_b05"] is not None), default=None),
                        "coverage_r210_min": min((d["coverage_r210"] for d in ok if d["coverage_r210"] is not None), default=None),
                        "n_marks_in_T_mean": mean([d["n_marks_in_T"] for d in ok])}
            for view in ("corr", "raw"):
                for bg in ("IRREDUCIBLE", "UNTESTED"):
                    res[arm][f"{view}:below_gate_as_{bg.lower()}"] = part_e_arm(dec[arm], cls, view, bg, carves[arm])
        if pp_bucket(lane) == "UNTESTED":
            dmed = max(0.0, D[cls]["median"] or 0.0)
            res["sensitivity_D_sized"] = {
                k: {"untested_ms": res["C"][k]["untested_ms"] - pp + dmed,
                    "untested_share": (res["C"][k]["untested_ms"] - pp + dmed) / res["C"][k]["mean_T_ms"]}
                for k in res["C"] if ":" in k}
        out["classes"][cls] = res
    return out


# ── main ─────────────────────────────────────────────────────────────────────
def analyse_trials(trials: list[dict[str, Any]], mans: list[dict[str, Any]]) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "b-08.summary.v1", "prereg": "PREREG.json"}
    used, info = select_rounds(trials, mans) if mans else (trials, {"rounds_used": "all (no manifests)"})
    S["rounds"] = info
    S["chunks"] = [{"block": m.get("block"), "attempt": m.get("attempt"), "lock_label": m.get("lock_label"),
                    "rounds_requested": m.get("rounds_requested"), "rounds_completed": m.get("rounds_completed"),
                    "rounds_not_started": m.get("rounds_not_started"), "stop_reason": m.get("stop_reason"),
                    "started_utc": m.get("started_utc"), "ended_utc": m.get("ended_utc"),
                    "load_checks_over_max": [c for c in m.get("load_checks", []) if c["load1"] > LOAD_MAX],
                    "driver_sha256": m.get("driver_sha256"), "driver_version": m.get("driver_version")} for m in mans]
    main_t = [t for t in used if t["summary"].get("kind") in ("measured", "smoke")]
    nw2_t = [t for t in used if t["summary"].get("kind") == "nw2"]
    rows_l = [R.row(t) for t in main_t]
    rows = {x["trial"]: x for x in rows_l}
    meas = [x for x in rows_l if x["b08_arm"] in ARMS]
    S["n_trials"] = {"measured": len(meas), "smoke": sum(1 for x in rows_l if x["b08_arm"] == "SMOKE"), "nw2": len(nw2_t),
                     "valid_measured": sum(1 for x in meas if x["valid"])}
    # agreement check (pre-registered, all valid measured trials)
    ag = [x["agree_2_5"] for x in meas if x["valid"] and x.get("agree_2_5") is not None]
    S["agreement_T_j_vs_T_oracle"] = {"n": len(ag), "within_2_5ms": sum(ag), "share": (sum(ag) / len(ag)) if ag else None,
                                      "pass": bool(ag) and sum(ag) / len(ag) >= AGREE_MIN,
                                      "abs_diff_median_ms": med([x["agree_abs_ms"] for x in meas if x["valid"]]),
                                      "abs_diff_max_ms": max((x["agree_abs_ms"] for x in meas if x["valid"] and x.get("agree_abs_ms") is not None), default=None)}
    S["classes"] = {}
    verdicts: dict[str, str] = {}
    Dd: dict[str, dict[str, Any]] = {}
    load_ok_rounds: dict[str, set[int]] = {}
    for cls in CLASSES:
        cr = [x for x in rows_l if x["cls"] == cls]
        doc: dict[str, Any] = {"arms": {a: arm_block([x for x in cr if x["b08_arm"] == a]) for a in ARMS + ["SMOKE"]}}
        doc["NC_Wa_minus_Wb"] = median_ci(pairs(cr, cls, "Wa", "Wb"))
        doc["PC2_P2_minus_Wa"] = median_ci(pairs(cr, cls, "P2", "Wa"))
        doc["D_C_minus_Wa"] = median_ci(pairs(cr, cls, "C", "Wa"))
        doc["Dprime_C_minus_Wb"] = median_ci(pairs(cr, cls, "C", "Wb"))
        doc["T_C_median"] = doc["arms"]["C"]["T_j_median"]
        doc["thresholds"] = {"five_pct_of_T_C": SHARE * doc["T_C_median"] if doc["T_C_median"] is not None else None,
                             "abs_ms": ABS_MS, "OD_ci_lo_gt": OD_LO}
        doc["secondary_T_oracle"] = {"NC": median_ci(pairs(cr, cls, "Wa", "Wb", "T_oracle_ms")),
                                     "PC2": median_ci(pairs(cr, cls, "P2", "Wa", "T_oracle_ms")),
                                     "D": median_ci(pairs(cr, cls, "C", "Wa", "T_oracle_ms"))}
        v, failed = verdict(doc) if all(doc[k]["n_pairs"] for k in ("NC_Wa_minus_Wb", "PC2_P2_minus_Wa", "D_C_minus_Wa")) \
            else ("UNDECIDED", ["no pairs"])
        doc["verdict"], doc["failed_gates"] = v, failed
        doc["gates"] = {"NC": "NC" not in failed, "PC2": "PC2" not in failed, "validity": "validity" not in failed,
                        "E4": "E4" not in failed}
        sm = doc["arms"]["SMOKE"]
        doc["smoke"] = {"n": sm["n"], "valid": sm["valid"], "pass": sm["n"] == 5 and sm["valid"] == 5}
        # load sensitivity (descriptive)
        by_round = defaultdict(list)
        for x in cr:
            by_round[x["round"]].append(x)
        ok_r = {r for r, xs in by_round.items() if all((x.get("loadavg_before_1m") or 0) <= LOAD_MAX for x in xs)}
        load_ok_rounds[cls] = ok_r
        doc["load_sensitivity"] = {"rounds_kept": len(ok_r), "rounds_total": len(by_round),
                                   "NC": median_ci(pairs(cr, cls, "Wa", "Wb", rounds=ok_r)),
                                   "PC2": median_ci(pairs(cr, cls, "P2", "Wa", rounds=ok_r)),
                                   "D": median_ci(pairs(cr, cls, "C", "Wa", rounds=ok_r))}
        # routes / producers (valid measured trials)
        rp = Counter()
        for x in cr:
            if x["b08_arm"] in ARMS and x["valid"]:
                for a in x["actions"]:
                    rp[f"{a['tool']}|{a['receipt_route']}|{a['dispatch_mark']}|{a['producer']}|{a['input_route']}"] += 1
        doc["routes_producers"] = dict(sorted(rp.items()))
        doc["pids_unique_C"] = len({(x["driver_pid"], x["driver_starttime"], x["chrome_pid"], x["chrome_starttime"])
                                    for x in cr if x["b08_arm"] == "C"}) == sum(1 for x in cr if x["b08_arm"] == "C")
        verdicts[cls], Dd[cls] = v, doc["D_C_minus_Wa"]
        S["classes"][cls] = doc
    S["nw2"] = {"rows": [R.nw2_row(t) for t in nw2_t]}
    S["nw2"]["by_class"] = {c: {"n": sum(1 for r in S["nw2"]["rows"] if r["cls"] == c),
                                "pass": sum(1 for r in S["nw2"]["rows"] if r["cls"] == c and r["pass"])} for c in CLASSES}
    S["e4"] = {a: e4_sum([x for x in rows_l if x["b08_arm"] == a]) for a in ARMS + ["SMOKE"]}
    S["e4_total"] = sum(sum(v.values()) for v in S["e4"].values())
    # every (pid, start time) pair unique across all trials (C always new processes)
    allp = [(x["driver_pid"], x["driver_starttime"]) for x in rows_l if x["driver_pid"]]
    S["process_identity"] = {"driver_pairs": len(allp), "driver_pairs_unique": len(set(allp)) == len(allp),
                             "warm_same_at_warmup_and_task": sum(1 for x in rows_l if x.get("pids_same_warmup_task")),
                             "warm_trials": sum(1 for x in rows_l if x["b08_arm"] in R.WARM)}
    S["driver_identity"] = dict(Counter(f"{x.get('driver_name')}|{x.get('driver_sha256')}|{x.get('driver_version')}"
                                        for x in rows_l))
    trials_by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in main_t:
        x = rows[name_of(t)]
        if x["valid"] and x["b08_arm"] in ("C", "Wa"):
            trials_by[(x["cls"], x["b08_arm"])].append(t)
    S["part_E"] = part_e(trials_by, rows, verdicts, Dd)
    nw2_ok = all(S["nw2"]["by_class"][c]["n"] >= 1 and S["nw2"]["by_class"][c]["pass"] == S["nw2"]["by_class"][c]["n"]
                 for c in CLASSES)
    keep = (all(verdicts[c] in ("OWNER_DECISION", "NOT_MATERIAL") for c in CLASSES) and S["e4_total"] == 0
            and all(S["classes"][c]["smoke"]["pass"] for c in CLASSES) and nw2_ok)
    S["disposition"] = {"value": "KEEP" if keep else "REVISE",
                        "per_class": {c: {"verdict": verdicts[c], "failed_gates": S["classes"][c]["failed_gates"],
                                          "smoke_pass": S["classes"][c]["smoke"]["pass"],
                                          "nw2_pass": S["nw2"]["by_class"][c]["pass"] == S["nw2"]["by_class"][c]["n"] >= 1}
                                      for c in CLASSES}}
    return rnd(S)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "b08-summary.json"))
    p.add_argument("--trials-dir")
    a = p.parse_args()
    if a.trials_dir:
        trials, mans = R.load_dir(Path(a.trials_dir) / "trials"), []
        mans = [json.loads(q.read_text()) for q in sorted(Path(a.trials_dir).glob("run-manifest-*.json"))]
    else:
        trials, mans = load(Path(a.raw))
    S = analyse_trials(trials, mans)
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"n": S["n_trials"], "verdicts": {c: S["classes"][c]["verdict"] for c in CLASSES},
                      "disposition": S["disposition"]["value"]}))


if __name__ == "__main__":
    main()

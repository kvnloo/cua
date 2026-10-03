#!/usr/bin/env python3
"""B-09 analysis: recompute every number from raw/ (standard library only; run it under bin/hostless).
Derived from B-08's analyze_b08.py (blob-identical copy in this lane's first commit; git history shows every
change).

Rules are PREREG.json's. Per-trial rows: b09_rows.py. Part E' uses R2-10R's analysis code
(harness/r2-10r/analyze_r2_10.py with the src/b-02 modules) and B-05's sub-span decomposition
(harness/b05/b05_spans.py), all blob-identical copies, with the verdict map in PREREG.json.

usage: analyze_b09.py [--raw raw] [--out b09-summary.json]
       analyze_b09.py --trials-dir <dir> --out <file>    (pilot check of the pipeline; no gate)
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
import b09_rows as R  # noqa: E402
import b01_analysis as B  # noqa: E402
import analyze_browser as AB  # noqa: E402,F401  (installs the B-02 classify_mark extension on B)
import analyze_r2_10 as A  # noqa: E402
import b05_spans as SP  # noqa: E402

PREREG = json.loads((HERE / "PREREG.json").read_text())
SEED = 20261003
BOOT = 10000
ARMS = ["BASE", "P10a", "P10b", "P1", "P0", "PC"]
COMPILED = ["P10a", "P10b", "P1", "P0", "PC"]
VALID_MIN = 0.95
NC_ABS = 1.0
PC_WINDOW = (12.0, 18.0)
KEEP_MS = 3.0
SHARE = 0.05
ABS_MS = 50.0
LOAD_MAX = 4.0
COVERAGE_MIN = 0.98
GATE_MS = 0.5
TARGET = 0.05
VM = PREREG["part_E_prime"]["verdict_map"]
LANE_SCOPE = set(VM["lane_scope_components"])
UNIT_MEMBERS = {u: VM["unit_members"].get(u, [u]) for u in VM["units"] if u != "any other lane-scope label"}
SUB_TO_UNIT = {m: u for u, ms in UNIT_MEMBERS.items() for m in ms}
SPLIT_RENAME = {"poll_sleep_start": "sleep_start", "poll_sleep_end": "sleep_end",
                "routine_read_send": "decide_start", "routine_read_return": "decided"}
SPLIT_LABEL = {"sleeps_polls": "poll_sleep", "provider_decision": "read_hop", "runner": "runner_other"}


# ── statistics ────────────────────────────────────────────────────────────────
def median_ci(d: list[float]) -> dict[str, Any]:
    """Median of paired differences + percentile bootstrap CI (fresh Random(SEED) per call)."""
    n = len(d)
    if n == 0:
        return {"n_pairs": 0, "median": None, "ci": None}
    rng = random.Random(SEED)
    vals = sorted(statistics.median([d[rng.randrange(n)] for _ in range(n)]) for _ in range(BOOT))
    return {"n_pairs": n, "median": statistics.median(d), "ci": [vals[250], vals[9749]], "mean": sum(d) / n}


def ratio_ci(pairs_ab: list[tuple[float, float]]) -> dict[str, Any]:
    """S = median(a) / median(b) over paired rounds; percentile bootstrap over the pairs (fresh Random(SEED))."""
    n = len(pairs_ab)
    if n == 0:
        return {"n_pairs": 0, "S": None, "ci": None}
    rng = random.Random(SEED)
    vals = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(statistics.median([pairs_ab[i][0] for i in idx]) / statistics.median([pairs_ab[i][1] for i in idx]))
    vals.sort()
    ma = statistics.median([a for a, _ in pairs_ab])
    mb = statistics.median([b for _, b in pairs_ab])
    return {"n_pairs": n, "median_a": ma, "median_b": mb, "S": ma / mb, "ci": [vals[250], vals[9749]]}


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


# ── contrasts ─────────────────────────────────────────────────────────────────
def by_round(rows: list[dict[str, Any]]) -> dict[int, dict[str, dict[str, Any]]]:
    by: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for x in rows:
        if x["b09_arm"] in ARMS:
            by[x["round"]][x["b09_arm"]] = x
    return by


def paired(rows: list[dict[str, Any]], a: str, b: str, key: str = "T_runner_ms",
           rounds: set[int] | None = None) -> list[tuple[float, float]]:
    by = by_round(rows)
    out = []
    for rd in sorted(by):
        if rounds is not None and rd not in rounds:
            continue
        xa, xb = by[rd].get(a), by[rd].get(b)
        if xa and xb and xa["valid"] and xb["valid"] and xa.get(key) is not None and xb.get(key) is not None:
            out.append((xa[key], xb[key]))
    return out


def diff(rows: list[dict[str, Any]], a: str, b: str, key: str = "T_runner_ms", rounds: set[int] | None = None) -> dict[str, Any]:
    return median_ci([x - y for x, y in paired(rows, a, b, key, rounds)])


def e4_sum(rows: list[dict[str, Any]]) -> dict[str, int]:
    tot: Counter = Counter({k: 0 for k in PREREG["e4"]["counters"]})
    for x in rows:
        tot.update(x["e4"])
    return dict(tot)


def arm_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    v = [x for x in rows if x["valid"]]
    return {"n": len(rows), "valid": len(v), "valid_share": (len(v) / len(rows)) if rows else None,
            "invalid": [{"trial": x["trial"], "outcome": x.get("outcome"), "valid_b04": x.get("valid_b04"),
                         "pids_ok": x.get("pids_ok"), "T_runner": x.get("T_runner_ms"), "lane_ok": x.get("lane_ok"),
                         "e4": {k: c for k, c in x["e4"].items() if c}, "telemetry_off": x.get("telemetry_off"),
                         "driver_id_ok": x.get("driver_id_ok"), "route_ok": x.get("route_ok"), "arm_ok": x.get("arm_ok"),
                         "config_ok": x.get("config_ok")} for x in rows if not x["valid"]],
            "outcomes": dict(Counter(f"{x.get('outcome')}|{x.get('completion_mutations')}" for x in rows)),
            "T_runner_median": med([x["T_runner_ms"] for x in v]), "T_runner_mean": mean([x["T_runner_ms"] for x in v]),
            "T_j_median": med([x["T_j_ms"] for x in v]), "T_oracle_median": med([x["T_oracle_ms"] for x in v]),
            "n_reads": {"mean": mean([x["n_reads"] for x in v]), "median": med([x["n_reads"] for x in v]),
                        "dist": dict(sorted(Counter(x["n_reads"] for x in v).items()))},
            "n_sleeps": {"mean": mean([x["n_sleeps"] for x in v]), "dist": dict(sorted(Counter(x["n_sleeps"] for x in v).items()))},
            "poll_sleep_ms": {"mean": mean([x["poll_sleep_ms"] for x in v]), "median": med([x["poll_sleep_ms"] for x in v])},
            "effect_latency_ms": {"mean": mean([x["effect_latency_ms"] for x in v]), "median": med([x["effect_latency_ms"] for x in v]),
                                  "min": min((x["effect_latency_ms"] for x in v if x["effect_latency_ms"] is not None), default=None),
                                  "max": max((x["effect_latency_ms"] for x in v if x["effect_latency_ms"] is not None), default=None)},
            "pc_sleep_ms": {"median": med([x.get("pc_sleep_ms") for x in v]),
                            "max": max((x["pc_sleep_ms"] for x in v if x.get("pc_sleep_ms") is not None), default=None)},
            "loadavg_1m": {"median": med([x.get("loadavg_before_1m") for x in rows]),
                           "max": max((x["loadavg_before_1m"] for x in rows if x.get("loadavg_before_1m") is not None), default=None)},
            "e4": e4_sum(rows)}


def poll_verdict(doc: dict[str, Any]) -> tuple[str, list[str]]:
    failed = [g for g in ("G0", "G1", "G2", "G3") if not doc["gates"][g]["pass"]]
    if failed:
        return "UNDECIDED", failed
    c = doc["POLL_P10a_minus_P1"]
    lo, hi = c["ci"]
    if c["median"] >= KEEP_MS and lo > 0:
        return "DELETED", []
    if hi < KEEP_MS:
        return "IRREDUCIBLE", []
    return "UNDECIDED", ["CI straddles 3.0 ms"]


# ── Part E' ──────────────────────────────────────────────────────────────────
def r210_trial(t: dict[str, Any]) -> dict[str, Any]:
    return {**t, "summary": dict(t["summary"]), "trace": SP.r210_view(t["trace"])}


def split_view(t: dict[str, Any]) -> dict[str, Any]:
    return {**t, "events": [({**e, "event": SPLIT_RENAME[e["event"]]} if e["event"] in SPLIT_RENAME else e)
                            for e in t["events"]]}


def decompose_rows(trials: list[dict[str, Any]], rows: dict[str, dict[str, Any]], c_m: float) -> list[dict[str, Any]]:
    out = []
    for t in trials:
        x = rows[name_of(t)]
        d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, c_m)
        ds = SP.decompose_b05(split_view(t), B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, c_m)
        d210 = B.decompose(r210_trial(t))
        if d is None or ds is None or d210 is None:
            out.append({"trial": x["trial"], "ok": False})
            continue
        T0, T1 = d["T0_ns"], d["T1_ns"]
        real_decisions = sum(1 for e in t["events"] if e["event"] == "decide_start" and T0 <= e["t_mono_ns"] <= T1)
        e2c = A.e2_components(d210)
        mine = {k: sum(v.values()) for k, v in d["by_comp"].items()}
        other = sum(v for k, v in d["sub"].items() if k.startswith("other.") or k == "c_other")
        cov = 1 - other / d["T_runner_ms"] if d["T_runner_ms"] else None
        run_b08 = sum(d["by_comp"].get("runner", {}).values())
        run_split = sum(sum(ds["by_comp"].get(k, {}).values()) for k in ("sleeps_polls", "provider_decision", "runner"))
        out.append({"trial": x["trial"], "ok": True, "T_runner_ms": d["T_runner_ms"], "T_runner_corr_ms": d["T_runner_corr_ms"],
                    "by_comp": d["by_comp"], "by_comp_corr": d["by_comp_corr"],
                    "split_by_comp": ds["by_comp"], "split_by_comp_corr": ds["by_comp_corr"],
                    "n_marks_in_T": d["n_marks_in_T"], "real_decisions_in_T": real_decisions,
                    "consistency_max_abs_ms": max(abs(e2c.get(k, 0.0) - mine.get(k, 0.0)) for k in set(e2c) | set(mine)),
                    "split_consistency_abs_ms": abs(run_b08 - run_split),
                    "coverage_b05": cov, "coverage_r210": d210["coverage"], "E_ms": x.get("excess_b03_ms"),
                    "poll_sleep_total_ms": x.get("poll_sleep_ms"), "effect_latency_ms": x.get("effect_latency_ms")})
    return out


def unit_verdict(unit: str | None) -> tuple[str, str]:
    if unit is None:
        return "UNTESTED", "-"
    v, src = VM["units"][unit]
    return (v["fill"] if isinstance(v, dict) else v), src


def comp_verdict(comp: str, arm_role: str, lane: str) -> tuple[str, str]:
    """Verdict of a split-view component (PREREG part_E_prime.verdict_map)."""
    if comp == "poll_sleep":
        if arm_role == "P10a":
            return VM["poll_sleep"]["P10a"][lane], VM["poll_sleep"]["source"]
        return VM["poll_sleep"]["best_arm_residual"], VM["poll_sleep"]["source"]
    key = "observation (rest)" if comp == "observation" else comp
    if key not in VM:
        return "UNTESTED", "-"
    v, src = VM[key]
    return (v["fill"] if isinstance(v, dict) else v), src


def bucket(v: str, bg: str) -> str:
    if v == "BELOW_GATE":
        return bg
    for k in ("DELETED", "IRREDUCIBLE", "OWNER_DECISION", "UNTESTED"):
        if v.startswith(k):
            return k
    return "UNTESTED"


def part_e_arm(dec: list[dict[str, Any]], arm_role: str, lane: str, view: str, bg: str) -> dict[str, Any]:
    v = [d for d in dec if d["ok"] and d["coverage_b05"] is not None and d["coverage_b05"] >= COVERAGE_MIN]
    T = mean([d["T_runner_ms"] if view == "raw" else d["T_runner_corr_ms"] for d in v])
    bc = "split_by_comp" if view == "raw" else "split_by_comp_corr"
    comps = sorted({c for d in v for c in d[bc]})
    acc: dict[str, float] = defaultdict(float)
    items: list[dict[str, Any]] = []
    comp_tot: dict[str, float] = {}
    units: dict[str, float] = defaultdict(float)
    E = mean([d["E_ms"] for d in v]) or 0.0
    for comp in comps:
        name = SPLIT_LABEL.get(comp, comp)
        labs = sorted({lab for d in v for lab in d[bc].get(comp, {})})
        comp_tot[name] = mean([sum(d[bc].get(comp, {}).values()) for d in v]) or 0.0
        for lab in labs:
            m = mean([d[bc].get(comp, {}).get(lab, 0.0) for d in v]) or 0.0
            unit = SUB_TO_UNIT.get(lab) if comp in LANE_SCOPE else None
            if comp in LANE_SCOPE:
                verd, src = unit_verdict(unit)
                units[unit or f"other:{lab}"] += m
            else:
                verd, src = comp_verdict(name, arm_role, lane)
            b = bucket(verd, bg)
            acc[b] += m
            items.append({"component": name, "label": lab, "unit": unit, "mean_ms": m, "verdict": verd, "source": src,
                          "bucket": b})
    # cold excess inside observation (IRREDUCIBLE by the map): its per-process (OWNER_DECISION, B-08) / per-document
    # (IRREDUCIBLE, B-04) split is not measured here (no warm arm); both are terminal, so it is a separate bucket
    acc["IRREDUCIBLE"] -= E
    acc["COLD_EXCESS"] += E
    rows_c = []
    for comp, tot in sorted(comp_tot.items(), key=lambda kv: -kv[1]):
        if comp == "observation":
            rows_c.append({"component": "observation (rest)", "mean_ms": tot - E, "verdict": "IRREDUCIBLE", "source": "B-04"})
            rows_c.append({"component": "cold excess (span(snapshot1) - span(snapshot2))", "mean_ms": E,
                           "verdict": VM["cold excess"][0], "source": VM["cold excess"][1]})
        elif comp in LANE_SCOPE:
            rows_c.append({"component": comp, "mean_ms": tot, "verdict": "per unit (see units)", "source": "B-05 / B-07"})
        else:
            verd, src = comp_verdict(comp, arm_role, lane)
            rows_c.append({"component": comp, "mean_ms": tot, "verdict": verd, "source": src})
    listed = []
    for rc_ in rows_c:
        rc_["share"] = rc_["mean_ms"] / T if T else None
        if rc_["mean_ms"] >= ABS_MS or (T and rc_["mean_ms"] >= SHARE * T):
            listed.append(rc_)
    unit_rows = []
    for u, val in sorted(units.items(), key=lambda kv: -kv[1]):
        verd, src = unit_verdict(u if u in UNIT_MEMBERS else None)
        r_ = {"unit": u, "mean_ms": val, "share": val / T if T else None, "verdict": verd, "source": src}
        unit_rows.append(r_)
        if val >= ABS_MS or (T and val >= SHARE * T):
            listed.append({"component": f"unit {u}", "mean_ms": val, "share": r_["share"], "verdict": verd, "source": src})
    untested = acc["UNTESTED"]
    irr = acc["IRREDUCIBLE"]
    return {"n": len(v), "excluded_coverage": len([d for d in dec if d["ok"]]) - len(v), "mean_T_ms": T,
            "by_bucket_ms": dict(acc), "untested_ms": untested, "untested_share": untested / T if T else None,
            "target_lt_5pct": (untested / T < TARGET) if T else None,
            "T_irreducible_ms": {"excl_cold_excess": irr, "incl_cold_excess": irr + E},
            "floor_ratio": {"excl_cold_excess": T / irr if irr else None, "incl_cold_excess": T / (irr + E) if (irr + E) else None},
            "components": rows_c, "units": unit_rows, "listed_ge_5pct_or_50ms": listed,
            "untested_items": [i for i in items if i["bucket"] == "UNTESTED" and i["mean_ms"] > 0.01],
            "below_gate_carried_with_corr_mean_ge_0_5ms": [r_["unit"] for r_ in unit_rows if r_["verdict"] == "BELOW_GATE"
                                                           and r_["mean_ms"] >= GATE_MS and view == "corr"]}


def runner_split(dec: list[dict[str, Any]], view: str) -> dict[str, Any]:
    """'runner' as B-08 labels it (no stamps used) = poll_sleep + read_hop + runner_other (split view), plus the
    poll-sleep time that overlapped the target-effect tail (filed as target_effect_lag in both views)."""
    ok = [d for d in dec if d["ok"] and d["coverage_b05"] is not None and d["coverage_b05"] >= COVERAGE_MIN]
    bc, sc = ("by_comp", "split_by_comp") if view == "raw" else ("by_comp_corr", "split_by_comp_corr")
    g = lambda d, k, c: sum(d[k].get(c, {}).values())  # noqa: E731
    out = {"runner_b08_labels_ms": mean([g(d, bc, "runner") for d in ok]),
           "poll_sleep_ms": mean([g(d, sc, "sleeps_polls") for d in ok]),
           "read_hop_ms": mean([g(d, sc, "provider_decision") for d in ok]),
           "runner_other_ms": mean([g(d, sc, "runner") for d in ok]),
           "target_effect_lag_ms": mean([g(d, sc, "target_effect_lag") for d in ok]),
           "effect_wait_inside_poll_sleep_ms": mean([max(0.0, (d["poll_sleep_total_ms"] or 0.0) - g(d, "split_by_comp", "sleeps_polls"))
                                                     for d in ok]),
           "poll_sleep_total_ms": mean([d["poll_sleep_total_ms"] for d in ok]),
           "effect_latency_ms_mean": mean([d["effect_latency_ms"] for d in ok]),
           "split_consistency_max_abs_ms": max((d["split_consistency_abs_ms"] for d in ok), default=None),
           "real_decisions_in_T": sum(d["real_decisions_in_T"] for d in ok)}
    return out


def part_e_prime(trials_by: dict[str, list[dict[str, Any]]], rows: dict[str, dict[str, Any]], lane: str,
                 best: str) -> dict[str, Any]:
    arms = ["P10a"] + ([best] if best != "P10a" else [])
    nulls: list[float] = []
    for arm in arms:
        for t in trials_by.get(arm, []):
            if t["trace"]:
                d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, 0.0)
                if d:
                    nulls += d["null_us"]
    c_m = (statistics.median(nulls) / 1000.0) if nulls else 0.0
    out: dict[str, Any] = {"c_m_us": c_m * 1000.0, "n_null_samples": len(nulls), "lane_verdict": lane, "best_arm": best,
                           "arms": {}}
    for arm in arms:
        role = "P10a" if arm == "P10a" else "best"
        dec = decompose_rows(trials_by.get(arm, []), rows, c_m)
        ok = [d for d in dec if d["ok"]]
        res: dict[str, Any] = {"role": role, "n_decomposed": len(ok), "n_failed": len(dec) - len(ok),
                               "consistency_max_abs_ms": max((d["consistency_max_abs_ms"] for d in ok), default=None),
                               "coverage_b05_min": min((d["coverage_b05"] for d in ok if d["coverage_b05"] is not None), default=None),
                               "coverage_r210_min": min((d["coverage_r210"] for d in ok if d["coverage_r210"] is not None), default=None),
                               "n_marks_in_T_mean": mean([d["n_marks_in_T"] for d in ok]),
                               "E_mean_ms": mean([d["E_ms"] for d in ok])}
        for view in ("corr", "raw"):
            res[f"runner_split:{view}"] = runner_split(dec, view)
            for bg in ("IRREDUCIBLE", "UNTESTED"):
                res[f"{view}:below_gate_as_{bg.lower()}"] = part_e_arm(dec, role, lane, view, bg)
        out["arms"][arm] = res
    return out


# ── main ─────────────────────────────────────────────────────────────────────
def analyse_trials(trials: list[dict[str, Any]], mans: list[dict[str, Any]]) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "b-09.summary.v1", "prereg": "PREREG.json"}
    used, info = select_rounds(trials, mans) if mans else (trials, {"rounds_used": "all (no manifests)"})
    S["rounds"] = info
    S["chunks"] = [{"plan": m.get("plan_kind"), "block": m.get("block"), "attempt": m.get("attempt"),
                    "lock_label": m.get("lock_label"), "rounds_requested": m.get("rounds_requested"),
                    "rounds_completed": m.get("rounds_completed"), "rounds_not_started": m.get("rounds_not_started"),
                    "stop_reason": m.get("stop_reason"), "started_utc": m.get("started_utc"), "ended_utc": m.get("ended_utc"),
                    "load_checks_over_max": [c for c in m.get("load_checks", []) if c["load1"] > LOAD_MAX],
                    "driver_sha256": m.get("driver_sha256"), "driver_version": m.get("driver_version")} for m in mans]
    main_t = [t for t in used if t["summary"].get("kind") in ("measured", "smoke")]
    nw2_t = [t for t in used if t["summary"].get("kind") == "nw2"]
    rows_l = [R.row(t) for t in main_t]
    rows = {x["trial"]: x for x in rows_l}
    meas = [x for x in rows_l if x["b09_arm"] in ARMS]
    S["n_trials"] = {"measured": len(meas), "smoke": sum(1 for x in rows_l if x["b09_arm"] == "SMOKE"), "nw2": len(nw2_t),
                     "valid_measured": sum(1 for x in meas if x["valid"])}
    doc: dict[str, Any] = {"arms": {a: arm_block([x for x in rows_l if x["b09_arm"] == a]) for a in ARMS + ["SMOKE"]}}
    doc["NC_P10a_minus_P10b"] = diff(meas, "P10a", "P10b")
    doc["PC_PC_minus_P10a"] = diff(meas, "PC", "P10a")
    doc["POLL_P10a_minus_P1"] = diff(meas, "P10a", "P1")
    doc["P10a_minus_P0"] = diff(meas, "P10a", "P0")
    doc["P1_minus_P0"] = diff(meas, "P1", "P0")
    doc["BASE_minus_P10a"] = diff(meas, "BASE", "P10a")
    doc["secondary"] = {k: {"NC": diff(meas, "P10a", "P10b", k), "PC": diff(meas, "PC", "P10a", k),
                            "POLL": diff(meas, "P10a", "P1", k), "P10a_minus_P0": diff(meas, "P10a", "P0", k)}
                        for k in ("T_j_ms", "T_oracle_ms")}
    # gates
    vs = {a: doc["arms"][a]["valid_share"] or 0.0 for a in ARMS}
    # identical verified outcomes: every valid trial verified with exactly one completion mutation, and no measured
    # trial in any arm ended with a different target outcome (refuted, or more than one completion mutation)
    verified_identical = (all(x["outcome"] == "verified" and x["completion_mutations"] == 1 for x in meas if x["valid"])
                          and not any(x["outcome"] == "refuted" or (x["completion_mutations"] or 0) > 1 for x in meas))
    g0 = all(v >= VALID_MIN for v in vs.values()) and verified_identical
    nc = doc["NC_P10a_minus_P10b"]
    g1 = bool(nc["ci"] and nc["ci"][0] <= 0.0 <= nc["ci"][1] and abs(nc["median"]) <= NC_ABS)
    pc = doc["PC_PC_minus_P10a"]
    g2 = bool(pc["ci"] and PC_WINDOW[0] <= pc["ci"][0] and pc["ci"][1] <= PC_WINDOW[1])
    S["e4"] = {a: e4_sum([x for x in rows_l if x["b09_arm"] == a]) for a in ARMS + ["SMOKE"]}
    S["e4_total"] = sum(sum(v.values()) for v in S["e4"].values())
    S["nw2"] = {"rows": [R.nw2_row(t) for t in nw2_t]}
    S["nw2"]["n"] = len(S["nw2"]["rows"])
    S["nw2"]["pass"] = sum(1 for r in S["nw2"]["rows"] if r["pass"])
    nw2_ok = S["nw2"]["n"] == 3 and S["nw2"]["pass"] == 3
    g3 = S["e4_total"] == 0 and nw2_ok
    doc["gates"] = {"G0": {"pass": g0, "valid_share": vs, "verified_identical": verified_identical},
                    "G1": {"pass": g1, "rule": "CI(P10a - P10b) contains 0 and |median| <= 1.0 ms"},
                    "G2": {"pass": g2, "rule": "CI(PC - P10a) inside [12, 18] ms"},
                    "G3": {"pass": g3, "e4_total": S["e4_total"], "nw2_pass": f"{S['nw2']['pass']}/{S['nw2']['n']}"}}
    v, failed = poll_verdict(doc) if all(doc[k]["n_pairs"] for k in ("NC_P10a_minus_P10b", "PC_PC_minus_P10a", "POLL_P10a_minus_P1")) \
        else ("UNDECIDED", ["no pairs"])
    doc["poll_verdict"], doc["poll_failed"] = v, failed
    best = "P1" if v == "DELETED" else "P10a"
    doc["best_arm"] = best
    # E3: S = median T(BASE) / median T(best), 36 pairs
    doc["S"] = {**ratio_ci(paired(meas, "BASE", best)), "composed_arm": best,
                "gate_ci_lower_gt_1": None}
    doc["S"]["gate_ci_lower_gt_1"] = bool(doc["S"]["ci"] and doc["S"]["ci"][0] > 1.0)
    doc["S_secondary"] = {k: {**ratio_ci(paired(meas, "BASE", best, k)), "composed_arm": best} for k in ("T_j_ms", "T_oracle_ms")}
    # P0 descriptive: work added
    rd = {a: doc["arms"][a]["n_reads"]["mean"] for a in COMPILED}
    doc["P0_descriptive"] = {"reads_mean": rd,
                             "reads_added_P0_vs_P1": (rd["P0"] - rd["P1"]) if rd["P0"] is not None and rd["P1"] is not None else None,
                             "reads_added_P0_vs_P10a": (rd["P0"] - rd["P10a"]) if rd["P0"] is not None and rd["P10a"] is not None else None,
                             "reads_added_P1_vs_P10a": (rd["P1"] - rd["P10a"]) if rd["P1"] is not None and rd["P10a"] is not None else None}
    sm = doc["arms"]["SMOKE"]
    smoke_rows = [x for x in rows_l if x["b09_arm"] == "SMOKE"]
    doc["smoke"] = {"n": sm["n"], "valid": sm["valid"],
                    "no_exp_no_skip_marks": all(not x.get("driver_env_exp") and x.get("v_marks") == 0 for x in smoke_rows),
                    "lane_unset": all(x.get("lane_env") == R.ARM_SPEC["SMOKE"][1] for x in smoke_rows)}
    doc["smoke"]["pass"] = sm["n"] == 5 and sm["valid"] == 5 and doc["smoke"]["no_exp_no_skip_marks"] and doc["smoke"]["lane_unset"]
    # load sensitivity (descriptive)
    br = defaultdict(list)
    for x in meas:
        br[x["round"]].append(x)
    ok_r = {r for r, xs in br.items() if all((x.get("loadavg_before_1m") or 0) <= LOAD_MAX for x in xs)}
    doc["load_sensitivity"] = {"rounds_kept": len(ok_r), "rounds_total": len(br),
                               "NC": diff(meas, "P10a", "P10b", rounds=ok_r), "PC": diff(meas, "PC", "P10a", rounds=ok_r),
                               "POLL": diff(meas, "P10a", "P1", rounds=ok_r)}
    rp = Counter()
    for x in meas:
        if x["valid"]:
            for a in x["actions"]:
                rp[f"{x['b09_arm']}|{a['tool']}|{a['receipt_route']}|{a['dispatch_mark']}|{a['producer']}|{a['input_route']}"] += 1
    doc["routes_producers"] = dict(sorted(rp.items()))
    allp = [(x["driver_pid"], x["driver_starttime"]) for x in rows_l if x["driver_pid"]]
    doc["process_identity"] = {"driver_pairs": len(allp), "driver_pairs_unique": len(set(allp)) == len(allp)}
    S["driver_identity"] = dict(Counter(f"{x.get('driver_name')}|{x.get('driver_sha256')}|{x.get('driver_version')}"
                                        for x in rows_l))
    S["driver_identity_nw2"] = dict(Counter(f"{r.get('driver_name')}|{r.get('driver_sha256')}|{r.get('driver_version')}"
                                            for r in S["nw2"]["rows"]))
    S["fill"] = doc
    trials_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in main_t:
        x = rows[name_of(t)]
        if x["valid"] and x["b09_arm"] in ("P10a", best):
            trials_by[x["b09_arm"]].append(t)
    S["part_E_prime"] = part_e_prime(trials_by, rows, v, best)
    pe = S["part_E_prime"]["arms"]
    keep = (v in ("DELETED", "IRREDUCIBLE") and doc["S"]["gate_ci_lower_gt_1"] and doc["smoke"]["pass"] and nw2_ok
            and S["e4_total"] == 0)
    S["disposition"] = {"value": "KEEP" if keep else "REVISE", "poll_verdict": v, "failed": failed,
                        "S_gate": doc["S"]["gate_ci_lower_gt_1"], "smoke_pass": doc["smoke"]["pass"], "nw2_pass": nw2_ok,
                        "untested_share_target_lt_5pct": {arm: {k: pe[arm][k]["target_lt_5pct"] for k in pe[arm] if k.count(":") == 1
                                                                and k.split(":")[0] in ("corr", "raw")} for arm in pe}}
    return rnd(S)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "b09-summary.json"))
    p.add_argument("--trials-dir")
    a = p.parse_args()
    if a.trials_dir:
        trials = R.load_dir(Path(a.trials_dir) / "trials")
        mans = [json.loads(q.read_text()) for q in sorted(Path(a.trials_dir).glob("run-manifest-*.json"))]
    else:
        trials, mans = load(Path(a.raw))
    S = analyse_trials(trials, mans)
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    f = S["fill"]
    print(json.dumps({"n": S["n_trials"], "poll_verdict": f["poll_verdict"], "failed": f["poll_failed"],
                      "POLL": f["POLL_P10a_minus_P1"], "S": {k: f["S"].get(k) for k in ("S", "ci")},
                      "disposition": S["disposition"]["value"]}))


if __name__ == "__main__":
    main()

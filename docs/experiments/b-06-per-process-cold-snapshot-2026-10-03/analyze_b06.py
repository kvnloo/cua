"""B-06 analyzer (standard library only): pre-registered statistics, gates and verdicts (PREREG.json).

    python3 analyze_b06.py [--main raw/main-trials.tar.gz --wn raw/wn-trials.tar.gz | --main-dir D --wn-dir D]
        [--out b06-summary.json]

Inputs: trial records (runner event log + summary line + Driver phase trace per trial), the chunk
manifests (raw/main/, raw/wn/), raw/r10r-comp-rows.json (R2-10R COMP decomposition rows, copied from
r2-10r-summary.json @ c183b95e3) and raw/r10r-observation-rows.json (R2-10R's own cold excess E_R' per
trial, r10r_observation.py). Output is deterministic: every bootstrap uses a fresh random.Random(20261003).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import b06_rows as R

HERE = Path(__file__).resolve().parent
SEED = 20261003
NBOOT = 10000
GATED = ("fill", "toggle")
CLASSES = ("fill", "toggle", "modal")
SQUARE = ("C", "Wa", "Wb", "P")
SQUARE_X = ("C", "Wa", "Wb", "P2")  # PREREG-AMENDMENT-1 block x
MAIN_ROUNDS = {"fill": 32, "toggle": 32, "modal": 16}
LOAD_MAX = 4.0
NC_BAND = 1.0
PC_RANGE = (12.0, 18.0)
VALIDITY_MIN = 0.95
MATERIAL = 1.0
E4_KEYS = ("stale_dispatch", "duplicate_mutation", "unverified_success", "refusal_as_success", "non_loopback")


# ── statistics ───────────────────────────────────────────────────────────────────────────────

def boot_ci(xs: list[float], stat: Any = statistics.median) -> list[float] | None:
    if len(xs) < 2:
        return None
    rng = random.Random(SEED)
    n = len(xs)
    vals = sorted(stat([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(NBOOT))
    return [vals[int(0.025 * NBOOT)], vals[int(0.975 * NBOOT) - 1]]


def med(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def mean(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def r4(x: Any) -> Any:
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, list):
        return [r4(v) for v in x]
    if isinstance(x, dict):
        return {k: r4(v) for k, v in x.items()}
    return x


def contrast(diffs: list[float]) -> dict[str, Any]:
    return {"n": len(diffs), "median": med(diffs), "ci": boot_ci(diffs), "mean": mean(diffs),
            "n_positive": sum(1 for d in diffs if d > 0)}


def sign(x: float | None) -> int:
    return 0 if not x else (1 if x > 0 else -1)


# ── loading and attempt selection ────────────────────────────────────────────────────────────

def expected_count(plan: str, r: int) -> int:
    if plan == "main":
        return sum(4 for c in CLASSES if r < MAIN_ROUNDS[c]) + (3 if r < 5 else 0)
    if plan == "wn":
        return 6
    if plan == "x":
        return 8
    raise ValueError(plan)


def load(path: Path) -> list[dict[str, Any]]:
    trials = R.load_dir(path) if path.is_dir() else R.load_tar(path)
    out = []
    for t in trials:
        r = R.row(t)
        r["t_start_ns"] = t["events"][0]["t_mono_ns"] if t["events"] else None
        out.append(r)
    return out


def select(rows: list[dict[str, Any]], plan: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Per (block, round): the first attempt in which every trial of the round ran (PREREG round_attempts)."""
    by: dict[tuple[str, int], dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[(r["block"], r["round"])][r["attempt"]].append(r)
    used, cut = [], []
    info: dict[str, Any] = {"rounds": 0, "cut_attempts": []}
    for (block, rnd), atts in sorted(by.items()):
        chosen = None
        for a in sorted(atts):
            if chosen is None and len(atts[a]) == expected_count(plan, rnd):
                chosen = a
        for a in sorted(atts):
            if a == chosen:
                used += atts[a]
            else:
                cut += atts[a]
                info["cut_attempts"].append({"block": block, "round": rnd, "attempt": a, "trials": len(atts[a])})
        if chosen is not None:
            info["rounds"] += 1
    return used, cut, info


# ── per-class pieces ─────────────────────────────────────────────────────────────────────────

def cells(rows: list[dict[str, Any]], arms: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cls in CLASSES:
        for arm in arms:
            xs = [r for r in rows if r["cls"] == cls and r["b06_arm"] == arm]
            if xs:
                v = sum(1 for r in xs if r["valid"])
                out[f"{cls}/{arm}"] = {"n": len(xs), "valid": v, "validity": v / len(xs)}
    return out


def paired(rows: list[dict[str, Any]], cls: str, a: str, b: str, key: str = "T_oracle_ms",
           round_ok: Any = None) -> list[float]:
    by: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        if r["cls"] == cls and r["b06_arm"] in (a, b):
            by[(r["block"], r["round"])][r["b06_arm"]] = r
    out = []
    for k in sorted(by):
        d = by[k]
        if a in d and b in d and d[a]["valid"] and d[b]["valid"] and d[a][key] is not None and d[b][key] is not None:
            if round_ok is None or round_ok(k):
                out.append(d[a][key] - d[b][key])
    return out


def arm_stats(rows: list[dict[str, Any]], cls: str, arm: str) -> dict[str, Any]:
    xs = [r for r in rows if r["cls"] == cls and r["b06_arm"] == arm and r["valid"]]

    def col(k: str) -> list[float]:
        return [r[k] for r in xs if r.get(k) is not None]

    sub = defaultdict(list)
    for r in xs:
        for k, v in (r.get("snapshot1_sub") or {}).items():
            sub[k].append(v)
    eform = [r["snapshot1_span_ms"] - r["snapshot2_span_ms"] for r in xs
             if r.get("snapshot1_span_ms") is not None and r.get("snapshot2_span_ms") is not None]
    return {"n_valid": len(xs), "T_oracle_median": med(col("T_oracle_ms")), "T_oracle_mean": mean(col("T_oracle_ms")),
            "T_land_median": med(col("T_land_ms")), "warmup_median": med(col("warmup_span_ms")),
            "warmup_mean": mean(col("warmup_span_ms")), "navigate_median": med(col("navigate_ms")),
            "snapshot1_span_median": med(col("snapshot1_span_ms")), "snapshot1_call_median": med(col("snapshot1_call_ms")),
            "snapshot1_split_median": {k: med(sub[k]) for k in ("attach", "dom_get_document", "ax_tree")},
            "snapshot1_split_mean": {k: mean(sub[k]) for k in ("attach", "dom_get_document", "ax_tree")},
            "E_R_form_snapshot1_minus_snapshot2": {"n": len(eform), "median": med(eform), "mean": mean(eform)},
            "pc_sleep_ms": ({"median": med(col("pc_sleep_ms")), "min": min(col("pc_sleep_ms")), "max": max(col("pc_sleep_ms"))}
                            if col("pc_sleep_ms") else None),
            "loadavg_before_median": med(col("loadavg_before_1m"))}


def low_load_rounds(rows: list[dict[str, Any]], cls: str) -> set[tuple[str, int]]:
    high = {(r["block"], r["round"]) for r in rows if r["cls"] == cls and (r["loadavg_before_1m"] or 0) > LOAD_MAX}
    return {(r["block"], r["round"]) for r in rows if r["cls"] == cls} - high


def class_block(rows: list[dict[str, Any]], cls: str, smoke: dict[str, Any], cellv: dict[str, Any],
                round_ok: Any = None, pc_arm: str = "P", square: tuple[str, ...] = SQUARE) -> dict[str, Any]:
    nc = contrast(paired(rows, cls, "Wa", "Wb", round_ok=round_ok))
    pc = contrast(paired(rows, cls, pc_arm, "Wa", round_ok=round_ok))
    d = contrast(paired(rows, cls, "C", "Wa", round_ok=round_ok))
    d2 = contrast(paired(rows, cls, "C", "Wb", round_ok=round_ok))
    land = {"C-Wa": contrast(paired(rows, cls, "C", "Wa", key="T_land_ms", round_ok=round_ok)),
            "Wa-Wb": contrast(paired(rows, cls, "Wa", "Wb", key="T_land_ms", round_ok=round_ok)),
            f"{pc_arm}-Wa": contrast(paired(rows, cls, pc_arm, "Wa", key="T_land_ms", round_ok=round_ok))}
    gates = {
        "NC": bool(nc["median"] is not None and nc["ci"] and abs(nc["median"]) <= NC_BAND and nc["ci"][0] <= 0 <= nc["ci"][1]),
        "PC": bool(pc["median"] is not None and pc["ci"] and (pc["ci"][0] > 0 or pc["ci"][1] < 0)
                   and PC_RANGE[0] <= pc["median"] <= PC_RANGE[1]),
        "validity": all(cellv.get(f"{cls}/{a}", {}).get("validity", 0) >= VALIDITY_MIN for a in square),
        "smoke": smoke.get(cls, {}).get("valid") == 5 and smoke.get(cls, {}).get("n") == 5,
    }
    out = {"NC_Wa_minus_Wb": nc, f"PC_{pc_arm}_minus_Wa": pc, "D_C_minus_Wa": d, "Dprime_C_minus_Wb": d2, "T_land": land,
           "gates": gates}
    if cls not in GATED:
        out["verdict"] = "DESCRIPTIVE (modal: consistency only)"
        return out
    failed = [g for g, ok in gates.items() if not ok]
    if failed:
        out["verdict"] = "UNDECIDED"
        out["verdict_reason"] = "failed control(s): " + ", ".join(failed)
        return out
    agree = sign(d["median"]) == sign(d2["median"]) or sign(d["median"]) == 0 or sign(d2["median"]) == 0
    ci = d["ci"]
    if not agree:
        out["verdict"], out["verdict_reason"] = "UNDECIDED", "replicate D' disagrees in sign with D"
    elif d["median"] >= MATERIAL and ci and (ci[0] > 0 or ci[1] < 0):
        out["verdict"] = "OWNER_DECISION"
        out["verdict_reason"] = ("per-process part deletable only by process reuse kept outside T; owner "
                                 "session/process-reuse policy; sized D")
        out["sized_D_ms"] = d["median"]
    elif ci and -MATERIAL < ci[0] and ci[1] < MATERIAL:
        out["verdict"] = "NOT_MATERIAL"
        out["verdict_reason"] = "per-process part IRREDUCIBLE; whole cold excess IRREDUCIBLE (per-document by B-04 + SOURCE carry)"
    else:
        out["verdict"], out["verdict_reason"] = "UNDECIDED", "D neither >= 1.0 ms with CI excluding 0 nor CI inside (-1, +1)"
    return out


# ── E2 mapping (R2-10R rows on R'; nothing from B-04 or B-05 is combined) ──────────────────────

def e2(verdicts: dict[str, str], d_sizes: dict[str, float | None]) -> dict[str, Any]:
    comp = json.loads((HERE / "raw" / "r10r-comp-rows.json").read_text())
    obs = json.loads((HERE / "raw" / "r10r-observation-rows.json").read_text())
    out: dict[str, Any] = {"source": comp["source"], "observation_source": obs["source_packet"], "classes": {}}
    for cls in CLASSES:
        row = comp["rows"][f"{cls}/COMP"]
        ers = [x["E_R_ms"] for x in obs["rows"] if x["cls"] == cls and x["valid"] and x["E_R_ms"] is not None]
        n_all = len([x for x in obs["rows"] if x["cls"] == cls])
        er = mean(ers)
        mt, un = row["mean_T_ms"], row["untested_ms"]
        pre = (un + er) / mt if er is not None else None
        if cls == "modal":
            post, label, lower = un / mt, "unchanged (B-04 row: modal cold excess not remapped; D descriptive here)", False
        elif verdicts.get(cls) in ("OWNER_DECISION", "NOT_MATERIAL"):
            post, lower = un / mt, False
            label = ("cold excess terminal: per-document IRREDUCIBLE (B-04, SOURCE carry) + per-process "
                     + ("OWNER_DECISION (sized D in this lane)" if verdicts[cls] == "OWNER_DECISION" else "IRREDUCIBLE"))
        else:
            post, lower = pre, True
            label = "per-process UNDECIDED: cold excess counted UNTESTED; share is a lower bound"
        out["classes"][cls] = {
            "mean_T_ms": mt, "untested_ms_r10r": un, "untested_share_r10r": row["untested_share"],
            "observation_ms_r10r": row["observation_ms"], "E_R_prime_mean_ms": er, "E_R_prime_ci_mean": boot_ci(ers, statistics.fmean),
            "E_R_prime_n": f"{len(ers)}/{n_all}", "share_pre_B06_B04_mapping": pre, "share_post_B06": post,
            "post_label": label, "lower_bound": lower, "verdict": verdicts.get(cls, "DESCRIPTIVE"),
            "per_process_size_D_ms_this_lane": d_sizes.get(cls),
            "views": {"BELOW_GATE_counted_IRREDUCIBLE": post, "BELOW_GATE_counted_UNTESTED": post},
            "views_note": ("R2-10R carries no BELOW_GATE label measured on R'; both views coincide on R'. "
                           "B-05's BELOW_GATE rows are on binary B5 and are cited, not combined.")}
    return out


# ── main ─────────────────────────────────────────────────────────────────────────────────────

def analyse(main_src: Path, wn_src: Path | None, x_src: Path | None = None) -> dict[str, Any]:
    main_rows_all = load(main_src)
    main_rows, main_cut, main_info = select(main_rows_all, "main")
    wn_rows, wn_cut, wn_info = (select(load(wn_src), "wn") if wn_src is not None and wn_src.exists()
                                else ([], [], {"rounds": 0, "cut_attempts": []}))
    sq = [r for r in main_rows if r["b06_arm"] in SQUARE]
    smoke_rows = [r for r in main_rows if r["b06_arm"] == "SMOKE"]
    smoke = {cls: {"n": len([r for r in smoke_rows if r["cls"] == cls]),
                   "valid": len([r for r in smoke_rows if r["cls"] == cls and r["valid"]]),
                   "v_marks_total": sum(r["v_marks"] for r in smoke_rows if r["cls"] == cls),
                   "exp_env_any": any(r["driver_env_exp"] for r in smoke_rows if r["cls"] == cls)} for cls in CLASSES}
    cellv = cells(sq, SQUARE)
    classes: dict[str, Any] = {}
    sens: dict[str, Any] = {}
    for cls in CLASSES:
        classes[cls] = class_block(sq, cls, smoke, cellv)
        classes[cls]["arms"] = {a: arm_stats(sq, cls, a) for a in SQUARE}
        lo = low_load_rounds(sq, cls)
        s = class_block(sq, cls, smoke, cellv, round_ok=lambda k, lo=lo: k in lo)
        sens[cls] = {"rounds_kept": len(lo), "NC": s["NC_Wa_minus_Wb"], "PC": s["PC_P_minus_Wa"],
                     "D": s["D_C_minus_Wa"], "Dprime": s["Dprime_C_minus_Wb"], "gates": s["gates"],
                     "verdict": s["verdict"]}
        a = classes[cls]["arms"]
        wu = a["Wa"]["warmup_median"]
        classes[cls]["amortized"] = {
            "T_C_median": a["C"]["T_oracle_median"], "T_Wa_median": a["Wa"]["T_oracle_median"], "warmup_Wa_median": wu,
            "k1_T_Wa_plus_warmup": None if wu is None else a["Wa"]["T_oracle_median"] + wu,
            "k5_T_Wa_plus_warmup_over_5": None if wu is None else a["Wa"]["T_oracle_median"] + wu / 5}
    # Wn block (descriptive)
    wn = {}
    for cls in CLASSES:
        wn[cls] = {"Wn_minus_Wa": contrast(paired(wn_rows, cls, "Wn", "Wa")),
                   "Wn": arm_stats(wn_rows, cls, "Wn"), "Wa": arm_stats(wn_rows, cls, "Wa"),
                   "main_block_C_median_for_reference": classes[cls]["arms"]["C"]["T_oracle_median"]}
    # E4 and process receipts
    e4 = {}
    for arm in (*SQUARE, "SMOKE", "Wn", "Wa(wn)"):
        rs = ([r for r in wn_rows if r["b06_arm"] == "Wa"] if arm == "Wa(wn)" else
              [r for r in (wn_rows if arm == "Wn" else main_rows) if r["b06_arm"] == arm])
        e4[arm] = {"n": len(rs), **{k: sum(1 for r in rs if r.get(k)) for k in E4_KEYS},
                   "fallbacks": sum(1 for r in rs if r.get("fallback")),
                   "oracle_reverted_after_ok": sum(1 for r in rs if r.get("oracle_reverted_after_ok"))}
    all_rows = main_rows_all + (load(wn_src) if wn_src is not None and wn_src.exists() else [])
    ids = [(r["driver_pid"], r["driver_starttime"]) for r in all_rows if r["driver_pid"]]
    cids = [(r["chrome_pid"], r["chrome_starttime"]) for r in all_rows if r["chrome_pid"]]
    c_rows = [r for r in main_rows if r["b06_arm"] == "C"]
    warm_rows = [r for r in main_rows + wn_rows if r["b06_arm"] in ("Wa", "Wb", "P", "Wn")]
    pids = {"driver_ids_unique_across_all_trials": len(ids) == len(set(ids)), "driver_ids": len(ids),
            "chrome_ids_unique_across_all_trials": len(cids) == len(set(cids)), "chrome_ids": len(cids),
            "C_trials_with_pids": sum(1 for r in c_rows if r["pids_ok"]), "C_trials": len(c_rows),
            "warm_trials_same_pids_warmup_and_task": sum(1 for r in warm_rows if r["pids_same_warmup_task"]),
            "warm_trials": len(warm_rows),
            "driver_exe": sorted({r["driver_exe"] for r in all_rows if r["driver_exe"]}),
            "chrome_exe": sorted({r["chrome_exe"] for r in all_rows if r["chrome_exe"]})}
    receipts = {"fill_route_compiled": sum(1 for r in sq if r["cls"] == "fill" and (r["routes"] or [None])[0] == "compiled"),
                "fill_trials": sum(1 for r in sq if r["cls"] == "fill"),
                "route_ok": sum(1 for r in sq if r["route_ok"]), "trials": len(sq),
                "comp_receipts_ok": sum(1 for r in sq if r["arm_receipts_ok"]),
                "skip_marks_min": min((r["v_marks"] for r in sq), default=None),
                "driver_sha256": sorted({r["driver_sha256"] for r in all_rows}),
                "loadavg_before_1m": {"min": min(r["loadavg_before_1m"] for r in all_rows),
                                      "median": med([r["loadavg_before_1m"] for r in all_rows]),
                                      "max": max(r["loadavg_before_1m"] for r in all_rows),
                                      "trials_above_4": sum(1 for r in all_rows if r["loadavg_before_1m"] > LOAD_MAX)}}
    # PREREG-AMENDMENT-1 block x (secondary, amended verdict; never pooled with the main block)
    xb: dict[str, Any] = {"present": False}
    if x_src is not None and x_src.exists():
        x_all = load(x_src)
        x_rows, x_cut, x_info = select(x_all, "x")
        xcell = cells(x_rows, SQUARE_X)
        xb = {"present": True, "counts": {"trials_all": len(x_all), "trials_used": len(x_rows), "cut": len(x_cut),
                                          "rounds": x_info["rounds"], "cut_attempts": x_info["cut_attempts"],
                                          "valid_used": sum(1 for r in x_rows if r["valid"])},
              "validity": xcell, "classes": {}, "load_sensitivity": {}, "e4": {}}
        for cls in GATED:
            k = class_block(x_rows, cls, smoke, xcell, pc_arm="P2", square=SQUARE_X)
            k["arms"] = {a: arm_stats(x_rows, cls, a) for a in SQUARE_X}
            xb["classes"][cls] = k
            lo = low_load_rounds(x_rows, cls)
            sx = class_block(x_rows, cls, smoke, xcell, round_ok=lambda kk, lo=lo: kk in lo, pc_arm="P2", square=SQUARE_X)
            xb["load_sensitivity"][cls] = {"rounds_kept": len(lo), "NC": sx["NC_Wa_minus_Wb"], "PC2": sx["PC_P2_minus_Wa"],
                                           "D": sx["D_C_minus_Wa"], "gates": sx["gates"], "verdict": sx["verdict"]}
        for arm in SQUARE_X:
            rs = [r for r in x_rows if r["b06_arm"] == arm]
            xb["e4"][arm] = {"n": len(rs), **{k: sum(1 for r in rs if r.get(k)) for k in E4_KEYS}}
        xb["process_receipts"] = {
            "warm_trials_same_pids": sum(1 for r in x_rows if r["b06_arm"] != "C" and r["pids_same_warmup_task"]),
            "warm_trials": sum(1 for r in x_rows if r["b06_arm"] != "C"),
            "C_trials_with_pids": sum(1 for r in x_rows if r["b06_arm"] == "C" and r["pids_ok"]),
            "C_trials": sum(1 for r in x_rows if r["b06_arm"] == "C")}
        all_rows = all_rows + x_all
        xb["verdicts_amended"] = {c: xb["classes"][c]["verdict"] for c in GATED}
    ids = [(r["driver_pid"], r["driver_starttime"]) for r in all_rows if r["driver_pid"]]
    cids = [(r["chrome_pid"], r["chrome_starttime"]) for r in all_rows if r["chrome_pid"]]
    pids["driver_ids_unique_across_all_trials"] = len(ids) == len(set(ids))
    pids["chrome_ids_unique_across_all_trials"] = len(cids) == len(set(cids))
    pids["driver_ids"], pids["chrome_ids"] = len(ids), len(cids)
    verdicts = {c: classes[c]["verdict"] for c in GATED}
    sizes = {c: classes[c].get("sized_D_ms") for c in GATED}
    doc = {"schema": "b-06.summary.v1",
           "counts": {"main_trials_all": len(main_rows_all), "main_trials_used": len(main_rows),
                      "main_trials_cut_attempts": len(main_cut), "main_rounds": main_info["rounds"],
                      "wn_trials_used": len(wn_rows), "wn_trials_cut_attempts": len(wn_cut), "wn_rounds": wn_info["rounds"],
                      "cut_attempts": main_info["cut_attempts"] + wn_info["cut_attempts"],
                      "valid_used": sum(1 for r in main_rows + wn_rows if r["valid"])},
           "validity": cellv, "smoke": smoke, "classes": classes, "load_sensitivity": sens, "wn_block": wn,
           "e4": e4, "process_receipts": pids, "forced_path_receipts": receipts, "verdicts": verdicts,
           "e2": e2(verdicts, sizes), "block_x_amendment_1": xb}
    if xb.get("present"):
        av = xb["verdicts_amended"]
        doc["e2_amended"] = e2(av, {c: xb["classes"][c].get("sized_D_ms") for c in GATED})
    return r4(doc)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--main", default=str(HERE / "raw" / "main-trials.tar.gz"))
    p.add_argument("--wn", default=str(HERE / "raw" / "wn-trials.tar.gz"))
    p.add_argument("--x", default=str(HERE / "raw" / "x-trials.tar.gz"))
    p.add_argument("--out", default=str(HERE / "b06-summary.json"))
    a = p.parse_args()
    doc = analyse(Path(a.main), Path(a.wn) if a.wn else None, Path(a.x) if a.x else None)
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    for c in CLASSES:
        k = doc["classes"][c]
        print(c, k["verdict"], "gates", k["gates"], "D", k["D_C_minus_Wa"]["median"], k["D_C_minus_Wa"]["ci"],
              "NC", k["NC_Wa_minus_Wb"]["median"], k["NC_Wa_minus_Wb"]["ci"], "PC", k["PC_P_minus_Wa"]["median"],
              k["PC_P_minus_Wa"]["ci"])
    if doc["block_x_amendment_1"].get("present"):
        for c in GATED:
            k = doc["block_x_amendment_1"]["classes"][c]
            print("x", c, k["verdict"], "gates", k["gates"], "D", k["D_C_minus_Wa"]["median"], k["D_C_minus_Wa"]["ci"],
                  "Dp", k["Dprime_C_minus_Wb"]["median"], "NC", k["NC_Wa_minus_Wb"]["median"], k["NC_Wa_minus_Wb"]["ci"],
                  "PC2", k["PC_P2_minus_Wa"]["median"], k["PC_P2_minus_Wa"]["ci"])


if __name__ == "__main__":
    main()

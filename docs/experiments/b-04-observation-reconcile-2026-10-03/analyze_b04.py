"""B-04 analyzer (standard library only): pre-registered statistics, gates and verdicts (PREREG.json).

    python3 analyze_b04.py [--trials raw/measured-trials.tar.gz | --trials-dir <dir>/trials] \
        [--out b04-summary.json]

Inputs: the measured trial records (runner event log + summary line + Driver phase trace per trial),
raw/r210-observation-rows.json (R2-10's own cold excess, r210_observation.py) and
raw/r210-comp-rows.json (R2-10 COMP E2 rows copied from r2-10-summary.json @ 030f6bdbf).
Output: b04-summary.json (deterministic: bootstrap seeded with random.Random(20261003)).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import b04_rows as R

HERE = Path(__file__).resolve().parent
SEED = 20261003
NBOOT = 10000
CLASSES = ("fill", "toggle")
EST = {"E_span": "excess_ms", "E_walk": "excess_walk_ms"}


def boot_ci(xs: list[float], stat: Any, rng: random.Random) -> list[float] | None:
    if len(xs) < 2:
        return None
    n = len(xs)
    vals = sorted(stat([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(NBOOT))
    return [vals[int(0.025 * NBOOT)], vals[int(0.975 * NBOOT) - 1]]


def mean(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def r4(x: Any) -> Any:
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, list):
        return [r4(v) for v in x]
    if isinstance(x, dict):
        return {k: r4(v) for k, v in x.items()}
    return x


def describe(xs: list[float], rng: random.Random) -> dict[str, Any]:
    return {"n": len(xs), "mean": mean(xs), "mean_ci": boot_ci(xs, statistics.fmean, rng),
            "median": median(xs), "median_ci": boot_ci(xs, statistics.median, rng),
            "min": min(xs) if xs else None, "max": max(xs) if xs else None}


def rows_of(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for t in trials:
        r = R.row(t)
        # run order inside a round (runner monotonic clock at trial_start; one runner process per chunk)
        r["t_start_ns"] = t["events"][0]["t_mono_ns"] if t["events"] else None
        out.append(r)
    return out


def load(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.trials_dir:
        trials = R.load_dir(Path(args.trials_dir))
    else:
        trials = R.load_tar(Path(args.trials))
    return rows_of(trials)


# ── P4 order (added after the data; see README "P4 order defect and Williams extension") ────────────
P4_ARMS = ("W0", "W80", "PREWARM")
WILLIAMS3 = [[0, 1, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0], [0, 2, 1], [1, 0, 2]]  # run_b02.williams_any(3)


def p4_rule(d: dict[str, Any]) -> bool:
    """PREREG verdict rule for one deletion: median T_oracle increase with a CI excluding 0 (and cell validity)."""
    return d["median_ci"] is not None and d["median_ci"][0] > 0 and d["cells_ok"]


def p4_block(rows: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    """P4 statistics of one block with the analyze() definitions (T_oracle_P4_ms, paired by round, W0
    as reference), plus the run order of the arms in every round and the contrasts split by order."""
    cells: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["probe"] == "P4":
            cells[(r["cls"], r["cell"])].append(r)
    order: dict[tuple, tuple] = {}
    for (cls, _cell), rs in cells.items():
        for r in rs:
            order.setdefault((cls, r["round"]), ())
    for key in order:
        rs = [r for a in P4_ARMS for r in cells.get((key[0], a), []) if r["round"] == key[1]]
        order[key] = tuple(r["cell"] for r in sorted(rs, key=lambda r: r["t_start_ns"]))
    rows_named = ["-".join(P4_ARMS[j] for j in w) for w in WILLIAMS3]
    out: dict[str, Any] = {}
    for cls in CLASSES:
        val = {a: (sum(r["valid"] for r in cells.get((cls, a), [])), len(cells.get((cls, a), []))) for a in P4_ARMS}
        ok = {a: val[a][1] > 0 and val[a][0] / val[a][1] >= 0.95 for a in P4_ARMS}
        by = {a: {r["round"]: r for r in cells.get((cls, a), [])} for a in P4_ARMS}
        rounds = sorted(k[1] for k in order if k[0] == cls)
        used = {n: sum(1 for k in rounds if "-".join(order[(cls, k)]) == n) for n in rows_named}
        out[f"{cls}/order"] = {
            "rounds": len(rounds), "williams_rows_used": used,
            "all_6_rows_equally": len(set(used.values())) == 1 and sum(used.values()) == len(rounds),
            "W0_before_W80": sum(1 for k in rounds if order[(cls, k)].index("W0") < order[(cls, k)].index("W80")),
            "W0_before_PREWARM": sum(1 for k in rounds if order[(cls, k)].index("W0") < order[(cls, k)].index("PREWARM")),
            "W80_before_PREWARM": sum(1 for k in rounds if order[(cls, k)].index("W80") < order[(cls, k)].index("PREWARM")),
            "position_counts": {a: [sum(1 for k in rounds if order[(cls, k)].index(a) == i) for i in range(3)]
                                for a in P4_ARMS}}
        for a in P4_ARMS:
            xs = [r["T_oracle_P4_ms"] for r in cells.get((cls, a), []) if r["valid"] and r["T_oracle_P4_ms"] is not None]
            out[f"{cls}/{a}"] = describe(xs, rng)
            out[f"{cls}/{a}"]["valid"], out[f"{cls}/{a}"]["total"] = val[a]
        for a in ("W80", "PREWARM"):
            pairs = [(k, by[a][k]["T_oracle_P4_ms"] - by["W0"][k]["T_oracle_P4_ms"]) for k in sorted(by[a])
                     if k in by["W0"] and by[a][k]["valid"] and by["W0"][k]["valid"]
                     and by[a][k]["T_oracle_P4_ms"] is not None and by["W0"][k]["T_oracle_P4_ms"] is not None]
            d = describe([x for _k, x in pairs], rng)
            d["cells_ok"] = ok[a] and ok["W0"]
            d["rule_pass"] = p4_rule(d)
            first = {k: order[(cls, k)].index(a) < order[(cls, k)].index("W0") for k, _x in pairs}
            d["by_order"] = {f"{a}_first": describe([x for k, x in pairs if first[k]], rng),
                             "W0_first": describe([x for k, x in pairs if not first[k]], rng)}
            out[f"{cls}/{a}-W0"] = d
    e4 = {"stale_dispatch": sum(r["stale_dispatch"] for r in rows),
          "duplicate_mutation": sum(r["duplicate_mutation"] for r in rows),
          "unverified_success": sum(r["unverified_success"] for r in rows),
          "refusals": sum(r["refusals"] for r in rows),
          "non_loopback": sum(r["non_loopback"] for r in rows),
          "fallbacks": sum(1 for r in rows if r["fallback"]),
          "oracle_reverted_after_ok": sum(1 for r in rows if r.get("oracle_reverted_after_ok"))}
    la = [r["loadavg_before_1m"] for r in rows if r["loadavg_before_1m"] is not None]
    out["trials_total"] = len(rows)
    out["trials_valid"] = sum(r["valid"] for r in rows)
    out["E4"] = e4
    out["driver_sha256_set"] = sorted({r["driver_sha256"] for r in rows if r["driver_sha256"]})
    out["browser_exe_set"] = sorted({r["browser_exe"] for r in rows if r["browser_exe"]})
    out["loadavg_1m_before_all"] = {"min": min(la), "median": statistics.median(la), "max": max(la)} if la else None
    return out


def analyze(rows: list[dict[str, Any]], rows_x: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rng = random.Random(SEED)
    out: dict[str, Any] = {"schema": "b-04.summary.v1", "seed": SEED, "n_boot": NBOOT}
    cells: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        cells[(r["probe"], r["cls"], r["cell"])].append(r)

    # validity and loadavg per cell
    val: dict[str, Any] = {}
    for (probe, cls, cell), rs in sorted(cells.items()):
        la = [r["loadavg_before_1m"] for r in rs if r["loadavg_before_1m"] is not None]
        val[f"{probe}/{cls}/{cell}"] = {
            "valid": sum(r["valid"] for r in rs), "total": len(rs),
            "validity": sum(r["valid"] for r in rs) / len(rs),
            "invalid_trials": [r["trial"] for r in rs if not r["valid"]],
            "loadavg_1m_before": {"min": min(la), "median": statistics.median(la), "max": max(la)} if la else None}
    out["validity"] = val
    out["trials_total"] = len(rows)
    out["trials_valid"] = sum(r["valid"] for r in rows)

    def cell_ok(probe: str, cls: str, *names: str) -> bool:
        return all(val.get(f"{probe}/{cls}/{n}", {}).get("validity", 0) >= 0.95 for n in names)

    def by_round(probe: str, cls: str, cell: str) -> dict[int, dict[str, Any]]:
        return {r["round"]: r for r in cells.get((probe, cls, cell), [])}

    def paired(probe: str, cls: str, a: str, b: str, key: str) -> list[float]:
        A, B = by_round(probe, cls, a), by_round(probe, cls, b)
        return [A[k][key] - B[k][key] for k in sorted(A) if k in B and A[k]["valid"] and B[k]["valid"]
                and A[k][key] is not None and B[k][key] is not None]

    # P1 negative control
    p1: dict[str, Any] = {}
    p1_valid: dict[str, dict[str, bool]] = {e: {} for e in EST}
    for est, key in EST.items():
        for cls in CLASSES:
            ok_all = True
            for D in ("D80", "D160"):
                xs = [r[key] for r in cells.get(("P1", cls, D), []) if r["valid"] and r[key] is not None]
                d = describe(xs, rng)
                ci = d["mean_ci"]
                passed = (d["mean"] is not None and abs(d["mean"]) < 1.0 and ci is not None and ci[0] <= 0 <= ci[1]
                          and cell_ok("P1", cls, D))
                d["gate_pass"] = passed
                d["cell_validity_ok"] = cell_ok("P1", cls, D)
                p1[f"{est}/{cls}/{D}"] = d
                ok_all = ok_all and passed
            p1_valid[est][cls] = ok_all
    out["P1"] = p1
    out["P1_estimator_valid"] = p1_valid

    # positive control
    pos: dict[str, Any] = {}
    for est, key in EST.items():
        for cls in CLASSES:
            deltas = paired("POS", cls, "inject20", "inject0", key)
            d = describe(deltas, rng)
            n_pos = sum(1 for x in deltas if x > 0)
            d["n_delta_positive"] = n_pos
            ci = d["median_ci"]
            d["gate_pass"] = (len(deltas) == 10 and n_pos == 10 and ci is not None and ci[0] > 0)
            inj = [r[key] for r in cells.get(("POS", cls, "inject20"), []) if r["valid"] and r[key] is not None]
            lit = describe(inj, rng)
            d["literal_inject20_excess"] = {"n": lit["n"], "n_positive": sum(1 for x in inj if x > 0),
                                            "mean": lit["mean"], "mean_ci": lit["mean_ci"]}
            iv = [r["inject_vs_nav"] for r in cells.get(("POS", cls, "inject20"), []) if r["inject_vs_nav"]]
            d["inject_end_minus_nav_return_ms"] = describe([x["end_minus_nav_return_ms"] for x in iv], rng)
            d["inject_fired"] = sum(1 for r in cells.get(("POS", cls, "inject20"), []) if r["inject_fired"])
            pos[f"{est}/{cls}"] = d
    out["POS"] = pos

    # smoke
    out["SMOKE"] = {cls: {"valid": sum(r["valid"] for r in cells.get(("SMOKE", cls, "default"), [])),
                          "total": len(cells.get(("SMOKE", cls, "default"), [])),
                          "pass": (len(cells.get(("SMOKE", cls, "default"), [])) == 5
                                   and all(r["valid"] for r in cells.get(("SMOKE", cls, "default"), [])))}
                    for cls in ("fill", "toggle", "modal")}

    # P2, P3 contrasts (both estimators, descriptive for the unselected one)
    p2: dict[str, Any] = {}
    p3: dict[str, Any] = {}
    for est, key in EST.items():
        for cls in ("fill", "toggle", "modal"):
            p2[f"{est}/{cls}"] = describe(paired("P2", cls, "cold", "warm", key), rng)
            p2[f"{est}/{cls}"]["cold_excess"] = describe(
                [r[key] for r in cells.get(("P2", cls, "cold"), []) if r["valid"] and r[key] is not None], rng)
            p2[f"{est}/{cls}"]["warm_excess"] = describe(
                [r[key] for r in cells.get(("P2", cls, "warm"), []) if r["valid"] and r[key] is not None], rng)
            p2[f"{est}/{cls}"]["cells_ok"] = cell_ok("P2", cls, "cold", "warm")
        for cls in CLASSES:
            p3[f"{est}/{cls}"] = describe(paired("P3", cls, "newdoc", "samedoc", key), rng)
            p3[f"{est}/{cls}"]["newdoc_excess"] = describe(
                [r[key] for r in cells.get(("P3", cls, "newdoc"), []) if r["valid"] and r[key] is not None], rng)
            p3[f"{est}/{cls}"]["samedoc_excess"] = describe(
                [r[key] for r in cells.get(("P3", cls, "samedoc"), []) if r["valid"] and r[key] is not None], rng)
            p3[f"{est}/{cls}"]["cells_ok"] = cell_ok("P3", cls, "newdoc", "samedoc")
    out["P2"] = p2
    out["P3"] = p3

    # P4 T_oracle rule
    p4: dict[str, Any] = {}
    for cls in CLASSES:
        for arm in ("W80", "PREWARM"):
            d = describe(paired("P4", cls, arm, "W0", "T_oracle_P4_ms"), rng)
            d["land_rule"] = describe(paired("P4", cls, arm, "W0", "T_land_P4_ms"), rng)
            d["T_oracle_excl_warmup"] = describe(paired("P4", cls, arm, "W0", "T_oracle_ms"), rng)
            d["incl_navigate"] = describe(paired("P4", cls, arm, "W0", "T_oracle_P4_incl_nav_ms"), rng)
            d["r210_T0_rule"] = describe(paired("P4", cls, arm, "W0", "T_oracle_r210_ms"), rng)
            d["cells_ok"] = cell_ok("P4", cls, arm, "W0")
            p4[f"{cls}/{arm}-W0"] = d
        for arm in ("W0", "W80", "PREWARM"):
            xs = [r["T_oracle_P4_ms"] for r in cells.get(("P4", cls, arm), []) if r["valid"] and r["T_oracle_P4_ms"] is not None]
            p4[f"{cls}/{arm}"] = describe(xs, rng)
            p4[f"{cls}/{arm}"]["snapshot1_span"] = describe(
                [r["snapshot1_span_ms"] for r in cells.get(("P4", cls, arm), []) if r["valid"] and r["snapshot1_span_ms"] is not None], rng)
            p4[f"{cls}/{arm}"]["warmup"] = describe(
                [r["warmup_ms"] for r in cells.get(("P4", cls, arm), []) if r["valid"] and r["warmup_ms"] is not None], rng)
        p4[f"{cls}/cell_median_differences"] = {
            arm: (p4[f"{cls}/{arm}"]["median"] - p4[f"{cls}/W0"]["median"])
            if p4[f"{cls}/{arm}"]["median"] is not None and p4[f"{cls}/W0"]["median"] is not None else None
            for arm in ("W80", "PREWARM")}
    out["P4"] = p4

    # component split (descriptive): per-CDP-step sub-spans, snapshot1 - resnap1, P2 cold and warm
    comp: dict[str, Any] = {}
    for cls in ("fill", "toggle", "modal"):
        for cell in ("cold", "warm"):
            rs = [r for r in cells.get(("P2", cls, cell), []) if r["valid"]]
            keys = [k for k, _a, _b in R.SUB]
            comp[f"{cls}/{cell}"] = {k: mean([r["snapshot1_sub"].get(k, 0.0) - r["resnap1_sub"].get(k, 0.0) for r in rs])
                                     for k in keys}
    for cls in CLASSES:
        for cell in ("D80", "D160"):
            rs = [r for r in cells.get(("P1", cls, cell), []) if r["valid"]]
            comp[f"P1/{cls}/{cell}"] = {k: mean([r["snapshot1_sub"].get(k, 0.0) - r["resnap1_sub"].get(k, 0.0) for r in rs])
                                        for k, _a, _b in R.SUB}
    out["component_split_snapshot1_minus_resnap1_mean_ms"] = comp

    # P4 order: block m (fixed arm order per class, the defect) and the Williams extension block x.
    # Separate seeded RNGs so every pre-existing number above and below is unchanged.
    p4m = p4_block(rows, random.Random(SEED + 41))
    p4x = p4_block(rows_x, random.Random(SEED + 42)) if rows_x else None
    out["P4_block_m_order"] = {k: v for k, v in p4m.items() if "/" in k}
    if p4x is not None:
        out["P4X"] = r4(p4x)

    # estimator selection and verdicts
    verdicts: dict[str, Any] = {}
    for cls in CLASSES:
        sel = "E_span" if p1_valid["E_span"][cls] else ("E_walk" if p1_valid["E_walk"][cls] else None)
        v: dict[str, Any] = {"estimator": sel}
        # per-document part (T_oracle only)
        w80, pw = p4[f"{cls}/W80-W0"], p4[f"{cls}/PREWARM-W0"]
        inc = all(d["median_ci"] is not None and d["median_ci"][0] > 0 and d["cells_ok"] for d in (w80, pw))
        v["per_document_block_m"] = "IRREDUCIBLE" if inc else "UNDECIDED"
        if p4x is not None:
            # The PREREG rule needs Williams order; block m had a fixed order per class (disclosed), so the
            # verdict is IRREDUCIBLE only if the rule holds in block m AND in the Williams block x.
            inc_x = all(p4x[f"{cls}/{a}-W0"]["rule_pass"] for a in ("W80", "PREWARM"))
            v["per_document_block_x_williams"] = "IRREDUCIBLE" if inc_x else "UNDECIDED"
            inc = inc and inc_x
            v["per_document_rule"] = "IRREDUCIBLE iff the PREREG rule holds in block m and in Williams block x"
            v["per_document_numbers_x"] = {
                "W80_minus_W0_median": p4x[f"{cls}/W80-W0"]["median"], "W80_ci": p4x[f"{cls}/W80-W0"]["median_ci"],
                "PREWARM_minus_W0_median": p4x[f"{cls}/PREWARM-W0"]["median"], "PREWARM_ci": p4x[f"{cls}/PREWARM-W0"]["median_ci"]}
        v["per_document"] = "IRREDUCIBLE" if inc else "UNDECIDED"
        v["per_document_numbers"] = {"W80_minus_W0_median": w80["median"], "W80_ci": w80["median_ci"],
                                     "PREWARM_minus_W0_median": pw["median"], "PREWARM_ci": pw["median_ci"]}
        # per-process part (P2 contrast with the selected estimator)
        if sel is None:
            v["per_process"] = "UNDECIDED"
            v["per_process_reason"] = "no estimator passed the P1 negative control (no carry-over)"
        else:
            c = p2[f"{sel}/{cls}"]
            ci = c["median_ci"]
            pos_ok = pos[f"{sel}/{cls}"]["gate_pass"]
            v["positive_control_selected"] = pos_ok
            if not c["cells_ok"] or ci is None:
                v["per_process"], v["per_process_reason"] = "UNDECIDED", "cell validity < 95% or no CI"
            elif c["median"] >= 1.0 and ci[0] > 0:
                v["per_process"], v["per_process_reason"] = "OWNER_DECISION", "contrast >= 1 ms, CI excludes 0"
            elif ci[0] <= 0 <= ci[1] and ci[1] < 1.0:
                if pos_ok:
                    v["per_process"], v["per_process_reason"] = "NOT_MATERIAL", "CI includes 0, upper < 1 ms, positive control passed"
                else:
                    v["per_process"], v["per_process_reason"] = "UNDECIDED", "NOT_MATERIAL conditions but the positive control failed"
            else:
                v["per_process"], v["per_process_reason"] = "UNDECIDED", "contrast neither >= 1 ms with CI > 0 nor CI within (.., 1 ms)"
        verdicts[cls] = v
    out["verdicts"] = verdicts
    out["modal_consistency"] = {est: {"P2_contrast_median": p2[f"{est}/modal"]["median"],
                                      "P2_contrast_ci": p2[f"{est}/modal"]["median_ci"],
                                      "P2_contrast_mean": p2[f"{est}/modal"]["mean"]} for est in EST}

    # accounting
    acc: dict[str, Any] = {}
    for cls in CLASSES:
        v = verdicts[cls]
        est = v["estimator"] or "E_span"
        e_cold = p2[f"{est}/{cls}"]["cold_excess"]["mean"]
        pp = p2[f"{est}/{cls}"]["mean"]
        pd = p3[f"{est}/{cls}"]["mean"]
        a: dict[str, Any] = {"estimator_used": est, "estimator_gate_failed": v["estimator"] is None,
                             "E_cold": e_cold, "per_process": pp, "per_document": pd}
        if None in (e_cold, pp, pd) or e_cold <= 0:
            a["u"] = 1.0
            a["u_conservative"] = 1.0
        else:
            rest = max(0.0, e_cold - max(0.0, pp) - max(0.0, pd))
            a["rest"] = rest
            un = rest + (max(0.0, pp) if v["per_process"] == "UNDECIDED" else 0.0) \
                + (max(0.0, pd) if v["per_document"] == "UNDECIDED" else 0.0)
            u = min(1.0, max(0.0, un / e_cold))
            uc = un
            if v["per_process"] == "NOT_MATERIAL":
                uc += max(0.0, p2[f"{est}/{cls}"]["median_ci"][1])
            a["u_split"] = u
            a["u_conservative_split"] = min(1.0, max(0.0, uc / e_cold))
            if v["estimator"] is None:
                a["u"] = 1.0
                a["u_conservative"] = 1.0
                a["note"] = "no valid estimator: headline u = 1; u_split is descriptive (gate-failed estimator)"
            else:
                a["u"] = a["u_split"]
                a["u_conservative"] = a["u_conservative_split"]
        acc[cls] = a
    out["accounting"] = acc

    # R2-10 rows
    obs = json.loads((HERE / "raw" / "r210-observation-rows.json").read_text())
    comp_rows = json.loads((HERE / "raw" / "r210-comp-rows.json").read_text())["rows"]
    r210: dict[str, Any] = {}
    for layer in ("scripted", "live"):
        for cls in ("fill", "toggle", "modal"):
            er = [x["E_R_ms"] for x in obs["rows"] if x["layer"] == layer and x["cls"] == cls and x["valid"]
                  and x["E_R_ms"] is not None]
            e_r = mean(er)
            row = comp_rows[f"{layer}/{cls}"]
            d: dict[str, Any] = {"E_R_mean": e_r, "E_R_n": len(er), "E_R_ci": boot_ci(er, statistics.fmean, rng),
                                 "R2_10_mean_T_ms": row["mean_T_ms"], "R2_10_untested_ms": row["untested_ms"],
                                 "R2_10_untested_share": row["untested_share"], "R2_10_observation_ms": row["observation_ms"]}
            d["observation_base_ms"] = row["observation_ms"] - max(0.0, e_r)
            if cls == "modal":
                d["verdict"] = "unchanged (B-02 H_W IRREDUCIBLE; this lane's P2 modal contrast is a consistency check)"
                d["updated_untested_share"] = row["untested_share"]
                d["updated_untested_share_conservative"] = row["untested_share"]
            else:
                a, v = acc[cls], verdicts[cls]
                add = a["u"] * max(0.0, e_r)
                addc = a["u_conservative"] * max(0.0, e_r)
                d["E_R_untested_ms"] = add
                d["updated_untested_ms"] = row["untested_ms"] + add
                d["updated_untested_share"] = (row["untested_ms"] + add) / row["mean_T_ms"]
                d["updated_untested_share_conservative"] = (row["untested_ms"] + addc) / row["mean_T_ms"]
                if "u_split" in a:  # descriptive: the split of a gate-failed estimator, labelled as such
                    d["updated_untested_share_descriptive_split"] = (row["untested_ms"] + a["u_split"] * max(0.0, e_r)) / row["mean_T_ms"]
                if a.get("E_cold") and a["E_cold"] > 0 and not a["estimator_gate_failed"]:
                    frac_pp = max(0.0, a["per_process"]) / a["E_cold"]
                    frac_pd = max(0.0, a["per_document"]) / a["E_cold"]
                    d["E_R_split_ms"] = {"per_process": frac_pp * max(0.0, e_r), "per_document": frac_pd * max(0.0, e_r),
                                         "rest_untested": a.get("rest", 0.0) / a["E_cold"] * max(0.0, e_r)}
                d["verdicts"] = {"per_process": v["per_process"], "per_document": v["per_document"]}
                d["R2_10_share_is_lower_bound"] = add > 0
            r210[f"{layer}/{cls}"] = d
    out["r2_10_rows"] = r210

    # E4
    e4 = {"stale_dispatch": sum(r["stale_dispatch"] for r in rows),
          "duplicate_mutation": sum(r["duplicate_mutation"] for r in rows),
          "unverified_success": sum(r["unverified_success"] for r in rows),
          "refusals": sum(r["refusals"] for r in rows),
          "non_loopback": sum(r["non_loopback"] for r in rows),
          "fallbacks": sum(1 for r in rows if r["fallback"]),
          "oracle_reverted_after_ok": sum(1 for r in rows if r.get("oracle_reverted_after_ok"))}
    out["E4"] = e4
    out["driver_sha256_set"] = sorted({r["driver_sha256"] for r in rows if r["driver_sha256"]})
    out["browser_exe_set"] = sorted({r["browser_exe"] for r in rows if r["browser_exe"]})
    la = [r["loadavg_before_1m"] for r in rows if r["loadavg_before_1m"] is not None]
    out["loadavg_1m_before_all"] = {"min": min(la), "median": statistics.median(la), "max": max(la)} if la else None
    return r4(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trials", default=str(HERE / "raw" / "measured-trials.tar.gz"))
    p.add_argument("--trials-dir")
    p.add_argument("--p4x", default=str(HERE / "raw" / "p4x-trials.tar.gz"),
                   help="P4 Williams extension block x (tarball); skipped if missing")
    p.add_argument("--p4x-dir", help="P4 extension trials directory instead of the tarball")
    p.add_argument("--out", default=str(HERE / "b04-summary.json"))
    a = p.parse_args()
    if a.p4x_dir:
        rows_x = rows_of(R.load_dir(Path(a.p4x_dir)))
    elif Path(a.p4x).exists():
        rows_x = rows_of(R.load_tar(Path(a.p4x)))
    else:
        rows_x = None
    s = analyze(load(a), rows_x)
    Path(a.out).write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
    for cls, v in s["verdicts"].items():
        print(cls, json.dumps(v))
    print("accounting", json.dumps(s["accounting"]))


if __name__ == "__main__":
    main()

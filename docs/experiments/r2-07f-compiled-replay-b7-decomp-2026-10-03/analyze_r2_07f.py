#!/usr/bin/env python3
"""R2-07f analysis: recompute every gate, S_E3, the amortized cost and the one-binary decomposition from raw/.

Standard library only; run it under bin/hostless. Rules are PREREG.json's.

Per-trial rows reuse, by import and unchanged:
* R2-10's ``browser_row`` (B-08's R2-10R copy ``b08/harness/r2-10r/analyze_r2_10.py``, a reporting-only superset
  of R2-10's) for BASE and COMP, and R2-07c's ``row_of`` / ``g4_pass`` / ``nw2_row``
  (``../r2-07c-toggle-modal-compiled-2026-10-03/analyze_r2_07c.py``) for every COMP+CR invocation; both run on the
  R2-10 mark view of the B7 trace (``b05_spans.r210_view``: B7's extra B-05 marks dropped), exactly as B-08 did;
* B-05's sub-span decomposition (``b08/harness/b05/b05_spans.decompose_b05``) on the full B7 trace with the
  B-07 stamped caller events, and B-04's snapshot span readers (``b08/harness/b04/b04_rows``) for the cold
  first-snapshot excess E.

usage: analyze_r2_07f.py [--raw raw] [--out r2-07f-summary.json]
       analyze_r2_07f.py --trials-dir <run dir> --out <file>   (pilot / pipeline check; no gate)
"""

from __future__ import annotations

import argparse
import io
import json
import random
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
H = HERE / "b08" / "harness"
R207C_PKT = HERE.parent / "r2-07c-toggle-modal-compiled-2026-10-03"
sys.dont_write_bytecode = True
sys.path[:0] = [str(H / "b05"), str(H / "b04"), str(H / "r2-10r" / "src" / "b-02-browser-driver-sites-2026-10-02"),
                str(H / "r2-10r")]
import b01_analysis as B  # noqa: E402
import analyze_browser as AB  # noqa: E402,F401  (installs the B-02 classify_mark extension on B)
import analyze_r2_10 as A  # noqa: E402  (B-08's R2-10R copy; analyze_r2_07c below reuses this module)
import b05_spans as SP  # noqa: E402
import b04_rows as B4  # noqa: E402

sys.path.insert(0, str(R207C_PKT))
import analyze_r2_07c as C7  # noqa: E402

PREREG = json.loads((HERE / "PREREG.json").read_text()) if (HERE / "PREREG.json").exists() else {}
SEED = 20261003
BOOT = 10000
CLASSES = ["toggle", "modal"]
ARMS = ["BASE", "COMP", "CRa", "CRb", "PC"]
ROUNDS = 40
VALID_MIN = 0.95
NC_MEDIAN_MAX = 1.5
PC_WINDOW = (12.0, 18.0)
HCR_MARGIN_MS = 2.0
SHARE = 0.05
ABS_MS = 50.0
COVERAGE_MIN = 0.98
GATE_MS = 0.5
B7 = {"driver_name": "cua-driver-b07-231f6e8bb",
      "driver_sha256": "6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa",
      "driver_version": "cua-driver 0.32.0"}
E4_KEYS = ["caller_stale_dispatch", "duplicate_mutation", "unverified_success", "refusal_returned_as_success",
           "blind_replay", "dispatches_after_unknown", "ambiguous_dispatch", "non_loopback_connects"]


# ── statistics (paired percentile bootstrap, fresh Random(SEED) per contrast) ──────────────────────────
def median_ci(d: list[float]) -> dict[str, Any]:
    n = len(d)
    if n == 0:
        return {"n_pairs": 0, "median": None, "ci95": None, "mean": None}
    rng = random.Random(SEED)
    vals = sorted(statistics.median([d[rng.randrange(n)] for _ in range(n)]) for _ in range(BOOT))
    return {"n_pairs": n, "median": statistics.median(d), "ci95": [vals[249], vals[9749]], "mean": sum(d) / n,
            "n_positive": sum(1 for x in d if x > 0)}


def ratio_ci(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    """S = median(a) / median(b) over paired rounds; paired bootstrap over rounds (fresh Random(SEED))."""
    n = len(pairs)
    if n == 0:
        return {"n_pairs": 0, "S": None, "ci95": None}
    a, b = [p[0] for p in pairs], [p[1] for p in pairs]
    rng = random.Random(SEED)
    vals = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(statistics.median([a[i] for i in idx]) / statistics.median([b[i] for i in idx]))
    vals.sort()
    return {"n_pairs": n, "S": statistics.median(a) / statistics.median(b), "ci95": [vals[249], vals[9749]],
            "median_num_ms": statistics.median(a), "median_den_ms": statistics.median(b)}


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
    if isinstance(x, tuple):
        return [rnd(y, nd) for y in x]
    if isinstance(x, dict):
        return {k: rnd(v, nd) for k, v in x.items()}
    if isinstance(x, Counter):
        return dict(x)
    return x


# ── loading ───────────────────────────────────────────────────────────────────────────────────────
def load_block(raw: Path, block: str) -> list[dict[str, Any]]:
    return C7.load_block(raw, block)


def load_dir(run: Path, block: str) -> list[dict[str, Any]]:
    out = []
    for p in sorted((run / "trials").glob("*.jsonl")):
        if p.name.endswith(".driver-trace.jsonl"):
            continue
        lines = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        s = lines[-1]
        if s.get("event") != "summary":
            continue
        tp = run / s["driver_trace"] if s.get("driver_trace") else None
        trace = [json.loads(x) for x in tp.read_text().splitlines() if x.strip()] if tp and tp.exists() else []
        out.append({"name": s["trial"], "summary": s, "events": lines[:-1], "trace": trace, "bundle": block,
                    "block": block})
    return out


def manifests(raw: Path, block: str) -> list[dict[str, Any]]:
    d = raw / f"{block}-manifests"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.exists() else []


# ── per-trial row ─────────────────────────────────────────────────────────────────────────────────
def view210(t: dict[str, Any]) -> dict[str, Any]:
    return {**t, "summary": dict(t["summary"]), "trace": SP.r210_view(t["trace"])}


def t_j_ms(t: dict[str, Any]) -> float | None:
    """T_j = max(journal completion ts, caller return of the last accepted mutation) - snapshot1 send."""
    s = t["summary"]
    snap1 = A.first_window(t["events"], "snapshot1")
    eff = B.completion_effect_ns(s.get("page_cls") or s["cls"], s.get("journal") or [])
    rets = [m["t_return_ns"] for m in (s.get("mutations") or []) if m.get("result") == "accepted" and m.get("t_return_ns")]
    if snap1 is None or eff is None or not rets:
        return None
    return (max(eff, max(rets)) - snap1["t0"]) / 1e6


def pc_sleep_ms(t: dict[str, Any]) -> float | None:
    e = next((x for x in t["events"] if x["event"] == "pc_sleep_end"), None)
    return None if e is None else e["slept_ns"] / 1e6


def pc_after_snapshot1(t: dict[str, Any]) -> bool:
    """The PC sleep starts after snapshot1 returns and ends before the next Driver call is sent."""
    ev = t["events"]
    i = next((k for k, x in enumerate(ev) if x["event"] == "pc_sleep_start"), None)
    if i is None:
        return False
    ret1 = next((k for k, x in enumerate(ev) if x["event"] == "call_return" and x.get("label") == "snapshot1"), None)
    nxt = next((k for k, x in enumerate(ev) if k > i and x["event"] == "call_send"), None)
    end = next((k for k, x in enumerate(ev) if k > i and x["event"] == "pc_sleep_end"), None)
    return ret1 is not None and ret1 < i and end is not None and (nxt is None or end < nxt)


def snapshot_excess(t: dict[str, Any]) -> dict[str, Any]:
    w = B4.windows(t)
    m1, m2 = B4.snap_measures(t["trace"], w.get("snapshot1")), B4.snap_measures(t["trace"], w.get("snapshot2"))
    e = None if (m1["span_ms"] is None or m2["span_ms"] is None) else m1["span_ms"] - m2["span_ms"]
    return {"snapshot1_span_ms": m1["span_ms"], "snapshot2_span_ms": m2["span_ms"], "E_ms": e}


def driver_ok(s: dict[str, Any]) -> bool:
    return all(s.get(k) == v for k, v in B7.items())


def row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    v = view210(t)
    if s.get("arm") == "BASE":
        r = A.browser_row(v, None)
        r["block"] = t["block"]
    else:
        r = C7.row_of(v)
    r["f_arm"] = s.get("f_arm")
    r["round"] = s.get("f_round", s.get("round"))
    r["attempt"] = s.get("attempt")
    r["williams_seq"], r["pos_in_round"] = s.get("williams_seq"), s.get("pos_in_round")
    r["driver"] = {k: s.get(k) for k in B7}
    r["driver_ok"] = driver_ok(s)
    r["T_j_ms"] = t_j_ms(t)
    r["final_state"] = s.get("final_state")
    r["loadavg_after_1m"] = float(str(s.get("loadavg_after", "nan")).split()[0])
    r["utc_start"] = s.get("utc_start")
    r["network_non_loopback"] = (s.get("network") or {}).get("non_loopback_connects", 0)
    r["e4"] = {**{k: 0 for k in E4_KEYS}, **(r.get("e4") or {}), "non_loopback_connects": r["network_non_loopback"]}
    r["caller_variant_stamps"] = sum(1 for e in t["events"] if e["event"] == "c.req_written")
    r.update(snapshot_excess(t))
    reasons = list(r.get("reasons") or [])
    if not r["driver_ok"]:
        reasons.append("driver_identity")
    if r["f_arm"] == "PC":
        r["pc_sleep_ms"] = pc_sleep_ms(t)
        if r["pc_sleep_ms"] is None or not pc_after_snapshot1(t):
            reasons.append("pc_sleep_not_after_snapshot1")
    if any(r["e4"].values()):
        reasons.append("e4")
    if r["f_arm"] in ARMS and r["caller_variant_stamps"] == 0:
        reasons.append("no_caller_stamps")
    r["reasons"] = reasons
    r["valid"] = not reasons
    return r


# ── design bookkeeping ────────────────────────────────────────────────────────────────────────────
def completed_attempts(mans: list[dict[str, Any]]) -> dict[str, int]:
    """PREREG: for each unit (round / training / fallback / control) the first attempt listed as run in a manifest."""
    done: dict[str, int] = {}
    for m in mans:
        for u in m.get("units_run", []):
            done[u["unit"]] = min(done.get(u["unit"], u["attempt"]), u["attempt"])
    return done


def select(trials: list[dict[str, Any]], mans: list[dict[str, Any]], unit_of) -> tuple[list[dict[str, Any]], list[str]]:  # noqa: ANN001
    done = completed_attempts(mans)
    used, cut = [], []
    for t in trials:
        s = t["summary"]
        key = unit_of(s)
        if mans and done.get(key) != int(s.get("attempt") or 1):
            cut.append(t["name"])
        else:
            used.append(t)
    return used, cut


def round_unit(s: dict[str, Any]) -> str:
    return f"round-{int(s.get('f_round', s.get('round'))):02d}"


# ── gates ─────────────────────────────────────────────────────────────────────────────────────────
def by_round(rows: list[dict[str, Any]], cls: str) -> dict[int, dict[str, dict[str, Any]]]:
    out: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        if r["cls"] == cls and r["f_arm"] in ARMS:
            out[r["round"]][r["f_arm"]] = r
    return out


def pairs(rows: list[dict[str, Any]], cls: str, a: str, b: str, key: str = "T_runner_ms") -> dict[str, Any]:
    br = by_round(rows, cls)
    diffs, both, ran, failed = [], [], 0, []
    for rd in sorted(br):
        xa, xb = br[rd].get(a), br[rd].get(b)
        if xa and xb:
            ran += 1
        if xa and xb and xa["valid"] and xb["valid"] and xa.get(key) is not None and xb.get(key) is not None:
            diffs.append(xa[key] - xb[key])
            both.append((xa[key], xb[key]))
        else:
            failed.append({"round": rd, a: None if xa is None else xa["reasons"], b: None if xb is None else xb["reasons"]})
    return {"diffs": diffs, "pairs": both, "ran": ran, "failed": failed}


def arm_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    v = [x for x in rows if x["valid"]]
    return {"n": len(rows), "valid": len(v), "valid_share": len(v) / len(rows) if rows else None,
            "invalid": [{"trial": x["trial"], "reasons": x["reasons"]} for x in rows if not x["valid"]],
            "T_runner_median": med([x["T_runner_ms"] for x in v]), "T_runner_mean": mean([x["T_runner_ms"] for x in v]),
            "T_oracle_median": med([x["T_oracle_ms"] for x in v]), "T_j_median": med([x["T_j_ms"] for x in v]),
            "decisions_per_invocation": mean([x["provider_decisions"] for x in v]),
            "fallbacks": sum(1 for x in rows if x.get("fallback")),
            "provider_attempts": sum(int((x.get("provider_requests") or {}).get("attempts", 0) or 0) for x in rows),
            "final_states": dict(Counter(json.dumps(x.get("final_state"), sort_keys=True) for x in v)),
            "actual_routes": dict(Counter("|".join(x.get("actual_routes") or []) for x in v)),
            "decision_routes": dict(Counter("|".join(x.get("decision_routes") or []) for x in v)),
            "pc_sleep_ms": {"median": med([x.get("pc_sleep_ms") for x in v]),
                            "min": min((x["pc_sleep_ms"] for x in v if x.get("pc_sleep_ms") is not None), default=None),
                            "max": max((x["pc_sleep_ms"] for x in v if x.get("pc_sleep_ms") is not None), default=None)},
            "loadavg_1m": {"median": med([x["loadavg_1m"] for x in rows]),
                           "max": max((x["loadavg_1m"] for x in rows), default=None)},
            "e4": {k: sum(int(x["e4"].get(k, 0)) for x in rows) for k in E4_KEYS}}


# ── decomposition (B-08 Part E method) ────────────────────────────────────────────────────────────
def vm() -> dict[str, Any]:
    return PREREG.get("decomposition", {}).get("verdict_map", {})


def unit_members() -> dict[str, list[str]]:
    m = vm()
    return {u: m.get("unit_members", {}).get(u, [u]) for u in m.get("units", {}) if u != "any other lane-scope label"}


def unit_of_label(lab: str) -> str | None:
    return {x: u for u, xs in unit_members().items() for x in xs}.get(lab)


def pick(v: Any, cls: str) -> str:
    return v[cls] if isinstance(v, dict) else v


def comp_verdict(comp: str, cls: str) -> tuple[str, str]:
    key = "observation (rest)" if comp == "observation" else comp
    m = vm()
    if key not in m:
        return "UNTESTED", "-"
    v, src = m[key]
    return pick(v, cls), src


def unit_verdict(unit: str | None, cls: str) -> tuple[str, str]:
    if unit is None:
        return "UNTESTED", "-"
    v, src = vm()["units"][unit]
    return pick(v, cls), src


def bucket(v: str, bg: str) -> str:
    if v == "BELOW_GATE":
        return bg
    for k in ("DELETED", "IRREDUCIBLE", "OWNER_DECISION", "UNTESTED"):
        if v.startswith(k):
            return k
    return "UNTESTED"


def decompose_trial(t: dict[str, Any], r: dict[str, Any], c_m: float) -> dict[str, Any]:
    d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, c_m)
    d210 = B.decompose(view210(t))
    if d is None or d210 is None:
        return {"trial": r["trial"], "ok": False}
    e2c = A.e2_components(d210)
    mine = {k: sum(x.values()) for k, x in d["by_comp"].items()}
    other = sum(x for k, x in d["sub"].items() if k.startswith("other.") or k == "c_other")
    return {"trial": r["trial"], "ok": True, "T_runner_ms": d["T_runner_ms"], "T_runner_corr_ms": d["T_runner_corr_ms"],
            "by_comp": d["by_comp"], "by_comp_corr": d["by_comp_corr"], "n_marks_in_T": d["n_marks_in_T"],
            "consistency_max_abs_ms": max(abs(e2c.get(k, 0.0) - mine.get(k, 0.0)) for k in set(e2c) | set(mine)),
            "coverage_b05": 1 - other / d["T_runner_ms"] if d["T_runner_ms"] else None,
            "coverage_r210": d210["coverage"], "E_ms": r.get("E_ms"), "T_runner_row_ms": r.get("T_runner_ms")}


def part_e_view(dec: list[dict[str, Any]], cls: str, view: str, bg: str, carve: dict[str, Any]) -> dict[str, Any]:
    lane_scope = set(vm().get("lane_scope_components", []))
    v = [d for d in dec if d["ok"] and d["coverage_b05"] is not None and d["coverage_b05"] >= COVERAGE_MIN]
    T = mean([d["T_runner_ms"] if view == "raw" else d["T_runner_corr_ms"] for d in v])
    bc = "by_comp" if view == "raw" else "by_comp_corr"
    comps = sorted({c for d in v for c in d[bc]})
    acc: dict[str, float] = defaultdict(float)
    items, comp_tot, units = [], {}, defaultdict(float)
    for comp in comps:
        comp_tot[comp] = mean([sum(d[bc].get(comp, {}).values()) for d in v]) or 0.0
        for lab in sorted({lab for d in v for lab in d[bc].get(comp, {})}):
            m = mean([d[bc].get(comp, {}).get(lab, 0.0) for d in v]) or 0.0
            if comp in lane_scope:
                unit = unit_of_label(lab)
                verd, src = unit_verdict(unit, cls)
                units[unit or f"other:{lab}"] += m
            else:
                unit = None
                verd, src = comp_verdict(comp, cls)
            b = bucket(verd, bg)
            acc[b] += m
            items.append({"component": comp, "label": lab, "unit": unit, "mean_ms": m, "verdict": verd, "source": src,
                          "bucket": b})
    pp, pdoc = carve["per_process_ms"], carve["per_document_ms"]
    acc["IRREDUCIBLE"] -= pp
    acc[bucket(carve["per_process_verdict"], bg)] += pp
    rows_c, listed = [], []
    for comp, tot in sorted(comp_tot.items(), key=lambda kv: -kv[1]):
        if comp == "observation":
            for name, val, (verd, src) in (("observation (rest)", tot - pp - pdoc, comp_verdict("observation", cls)),
                                           ("cold per-document", pdoc, tuple(vm()["cold per-document"])),
                                           ("cold per-process", pp, (carve["per_process_verdict"], vm()["cold per-process"][1]))):
                rows_c.append({"component": name, "mean_ms": val, "verdict": verd, "source": src})
        elif comp in lane_scope:
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
        verd, src = unit_verdict(u if u in unit_members() else None, cls)
        ur = {"unit": u, "mean_ms": val, "share": val / T if T else None, "verdict": verd, "source": src}
        unit_rows.append(ur)
        if val >= ABS_MS or (T and val >= SHARE * T):
            listed.append({"component": f"unit {u}", "mean_ms": val, "share": ur["share"], "verdict": verd, "source": src})
    untested = acc["UNTESTED"]
    listed_untested = [x["component"] for x in listed if bucket(str(x["verdict"]), bg) == "UNTESTED"
                       and not str(x["verdict"]).startswith("per unit")]
    return {"n": len(v), "excluded_coverage": len([d for d in dec if d["ok"]]) - len(v), "mean_T_ms": T,
            "by_bucket_ms": dict(acc), "untested_ms": untested, "untested_share": untested / T if T else None,
            "components": rows_c, "units": unit_rows, "listed_ge_5pct_or_50ms": listed,
            "listed_without_terminal_verdict": listed_untested,
            "untested_items": [i for i in items if i["bucket"] == "UNTESTED" and i["mean_ms"] > 0.01],
            "below_gate_carried_with_corr_mean_ge_0_5ms": [u["unit"] for u in unit_rows if u["verdict"] == "BELOW_GATE"
                                                          and u["mean_ms"] >= GATE_MS and view == "corr"]}


def decomposition(trials_by: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]]) -> dict[str, Any]:
    nulls: list[float] = []
    for pairs_ in trials_by.values():
        for t, _r in pairs_:
            d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, 0.0)
            if d:
                nulls += d["null_us"]
    c_m = (statistics.median(nulls) / 1000.0) if nulls else 0.0
    carry = PREREG.get("decomposition", {}).get("cold_split", {}).get("carried_per_document_ms", {})
    out: dict[str, Any] = {"c_m_us": c_m * 1000.0, "n_null_samples": len(nulls), "classes": {}}
    for cls in CLASSES:
        res: dict[str, Any] = {}
        for arm in ("CRa", "COMP"):
            dec = [decompose_trial(t, r, c_m) for t, r in trials_by.get((cls, arm), [])]
            ok = [d for d in dec if d["ok"]]
            e_mean = mean([d["E_ms"] for d in ok]) or 0.0
            pdoc = min(float(carry.get(cls, 0.0)), max(e_mean, 0.0))
            carve = {"E_mean_ms": e_mean, "per_document_ms": pdoc, "per_process_ms": max(0.0, e_mean - pdoc),
                     "per_process_verdict": pick(vm().get("cold per-process", ["UNTESTED", "-"])[0], cls),
                     "carried_per_document_ms": carry.get(cls)}
            a: dict[str, Any] = {"n_decomposed": len(ok), "n_failed": len(dec) - len(ok), "cold_split": carve,
                                 "consistency_max_abs_ms": max((d["consistency_max_abs_ms"] for d in ok), default=None),
                                 "coverage_b05_min": min((d["coverage_b05"] for d in ok if d["coverage_b05"] is not None), default=None),
                                 "coverage_r210_min": min((d["coverage_r210"] for d in ok if d["coverage_r210"] is not None), default=None),
                                 "n_marks_in_T_mean": mean([d["n_marks_in_T"] for d in ok]),
                                 "T_row_vs_decomp_max_abs_ms": max((abs(d["T_runner_ms"] - d["T_runner_row_ms"]) for d in ok
                                                                    if d["T_runner_row_ms"] is not None), default=None)}
            for view in ("corr", "raw"):
                for bg in ("IRREDUCIBLE", "UNTESTED"):
                    a[f"{view}:below_gate_as_{bg.lower()}"] = part_e_view(dec, cls, view, bg, carve)
            res[arm] = a
        prim = [res["CRa"][f"corr:below_gate_as_{b}"] for b in ("irreducible", "untested")]
        res["H_D"] = {"untested_share_bg_irreducible": prim[0]["untested_share"],
                      "untested_share_bg_untested": prim[1]["untested_share"],
                      "listed_without_terminal_verdict": sorted(set(prim[0]["listed_without_terminal_verdict"])
                                                                | set(prim[1]["listed_without_terminal_verdict"])),
                      "pass": all(p["untested_share"] is not None and p["untested_share"] < SHARE
                                  and not p["listed_without_terminal_verdict"] for p in prim)}
        out["classes"][cls] = res
    return out


# ── controls ──────────────────────────────────────────────────────────────────────────────────────
def controls(trials: list[dict[str, Any]]) -> dict[str, Any]:
    rows, out = [], defaultdict(lambda: {"n": 0, "pass": 0})
    for t in trials:
        s = t["summary"]
        k = s.get("kind")
        drv = driver_ok(s)
        if k == "nw2":
            r = C7.nw2_row(t)
            ok, detail = r["pass"] and drv, f"{r['stale_effect']}:{r['stale_code']} m={r['stale_mutations']}"
            key = f"nw2:{s.get('cls')}"
        elif k == "smoke":
            ok = (s.get("outcome") == "verified" and s.get("oracle_exact_match") is True and s.get("completion_mutations") == 1
                  and s.get("driver_env_exp") == {} and s.get("driver_env_trace_set") is False and s.get("arm") == "BASE"
                  and drv)
            detail, key = f"{s.get('outcome')} cm={s.get('completion_mutations')}", f"default_smoke:{s.get('cls')}"
        else:
            r = row(t)
            ok, detail = C7.g4_pass(r)
            ok = ok and drv and not any(r["e4"].values())
            page = f"-on-{s['page_cls']}" if s.get("page_cls") and s.get("page_cls") != s.get("cls") else ""
            key = f"{k}:{s.get('cls')}{page}"
        rows.append({"trial": t["name"], "key": key, "pass": bool(ok), "detail": detail, "driver_ok": drv})
        out[key]["n"] += 1
        out[key]["pass"] += int(bool(ok))
    return {"rows": rows, "by_key": dict(out), "all_pass": bool(rows) and all(r["pass"] for r in rows),
            "n": len(rows), "passed": sum(1 for r in rows if r["pass"])}


# ── main analysis ─────────────────────────────────────────────────────────────────────────────────
def analyze(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "r2-07f.summary.v1", "prereg": "PREREG.json"}
    blocks = {b: load_block(raw, b) for b in ("t", "m", "f", "c")}
    mans = {b: manifests(raw, b) for b in blocks}
    if not blocks["m"]:
        return rnd(blocked_summary(raw, S))
    S["blocks"] = {b: len(v) for b, v in blocks.items()}
    m_used, m_cut = select(blocks["m"], mans["m"], round_unit)
    S["main_cut_or_unlisted_trials"] = m_cut
    S["chunks"] = {b: [{k: m.get(k) for k in ("plan", "chunk", "started_utc", "ended_utc", "exit", "lock_mode",
                                             "remaining_units", "driver_name", "driver_sha256", "driver_version",
                                             "loadavg_start", "loadavg_end", "provider_mode", "caller_variant")}
                       for m in v] for b, v in mans.items()}
    S["load_gate"] = {b: {"units_started": sum(len(m.get("units_run", [])) for m in v),
                          "max_load_at_start": max((u["load_at_start"] for m in v for u in m.get("units_run", [])), default=None),
                          "chunk_ends_on_load": sum(1 for m in v if m.get("exit") == 75)} for b, v in mans.items()}
    rows_m = [row(t) for t in m_used]
    S["first_measured_trial_utc"] = min((r["utc_start"] for b in ("t", "m", "f") for r in
                                         [{"utc_start": t["summary"].get("utc_start")} for t in blocks[b]]
                                         if r["utc_start"]), default=None)
    S["driver_identity"] = dict(Counter(f"{t['summary'].get('driver_name')}|{t['summary'].get('driver_sha256')}|"
                                        f"{t['summary'].get('driver_version')}" for b in blocks for t in blocks[b]))
    # training + admission (block t)
    tr_rows = {t["name"]: row(t) for t in blocks["t"]}
    training = {}
    for cls in CLASSES:
        tr = next((r for n, r in tr_rows.items() if r["cls"] == cls and r["kind"] == "train"), None)
        adm = next((r for n, r in tr_rows.items() if r["cls"] == cls and r["kind"] == "admission"), None)
        training[cls] = {"training_trial": tr and tr["trial"], "training_valid": bool(tr and tr["valid"]),
                         "training_T_runner_ms": tr and tr["T_runner_ms"],
                         "compile_ms": (tr or {}).get("training", {}).get("compile_ms") if tr else None,
                         "authority_problems": (tr or {}).get("training", {}).get("authority_problems") if tr else None,
                         "admitted": (tr or {}).get("training", {}).get("admitted") if tr else None,
                         "admission_trial": adm and adm["trial"], "admission_valid": bool(adm and adm["valid"]),
                         "admission_T_runner_ms": adm and adm["T_runner_ms"],
                         "training_decisions": tr and tr["provider_decisions"],
                         "admission_decisions": adm and adm["provider_decisions"]}
    S["training"] = training
    # fallbacks (block f)
    fb_rows = [row(t) for t in blocks["f"]]
    S["fallback"] = {cls: [{"trial": r["trial"], "g4_n7_pass": C7.g4_pass(r)[0], "detail": C7.g4_pass(r)[1],
                            "T_runner_ms": r["T_runner_ms"], "decisions": r["provider_decisions"],
                            "fallback": r.get("fallback"), "e4": sum(r["e4"].values())}
                           for r in fb_rows if r["cls"] == cls] for cls in CLASSES}
    # per class gates
    S["classes"] = {}
    e4_all = 0
    for cls in CLASSES:
        cr = [r for r in rows_m if r["cls"] == cls]
        doc: dict[str, Any] = {"arms": {a: arm_block([r for r in cr if r["f_arm"] == a]) for a in ARMS}}
        doc["rounds_complete"] = len({r["round"] for r in cr if r["f_arm"] in ARMS
                                      and all(any(x["round"] == r["round"] and x["f_arm"] == a for x in cr) for a in ARMS)})
        cont: dict[str, Any] = {}
        for name, (a, b) in {"NC_CRa_minus_CRb": ("CRa", "CRb"), "PC_PC_minus_CRa": ("PC", "CRa"),
                             "HCR_CRa_minus_COMP": ("CRa", "COMP"), "CRa_minus_BASE": ("CRa", "BASE"),
                             "COMP_minus_BASE": ("COMP", "BASE")}.items():
            p = pairs(cr, cls, a, b)
            cont[name] = {**median_ci(p["diffs"]), "pairs_ran": p["ran"], "failed_pairs": p["failed"]}
            cont[name]["secondary_T_oracle"] = median_ci(pairs(cr, cls, a, b, "T_oracle_ms")["diffs"])
            cont[name]["secondary_T_j"] = median_ci(pairs(cr, cls, a, b, "T_j_ms")["diffs"])
        doc["contrasts"] = cont
        pb = pairs(cr, cls, "BASE", "CRa")
        doc["S_E3_BASE_over_CRa"] = {**ratio_ci(pb["pairs"]), "pairs_ran": pb["ran"]}
        pbc = pairs(cr, cls, "BASE", "COMP")
        doc["S_BASE_over_COMP"] = {**ratio_ci(pbc["pairs"]), "pairs_ran": pbc["ran"]}
        doc["S_E3_secondary_T_oracle"] = ratio_ci(pairs(cr, cls, "BASE", "CRa", "T_oracle_ms")["pairs"])
        # gates
        A_ = doc["arms"]
        states = {s for a in ARMS for s in A_[a]["final_states"]}
        g0 = all((A_[a]["valid_share"] or 0) >= VALID_MIN for a in ARMS) and len(states) == 1
        nc = cont["NC_CRa_minus_CRb"]
        g1 = bool(nc["ci95"] and nc["ci95"][0] <= 0 <= nc["ci95"][1] and abs(nc["median"]) <= NC_MEDIAN_MAX)
        pc = cont["PC_PC_minus_CRa"]
        g2 = bool(pc["ci95"] and PC_WINDOW[0] <= pc["ci95"][0] and pc["ci95"][1] <= PC_WINDOW[1])
        warm = [r for r in cr if r["f_arm"] in ("CRa", "CRb", "PC")]
        g3 = {"warm_invocations": len(warm), "decisions": sum(r["provider_decisions"] for r in warm),
              "fallbacks": sum(1 for r in warm if r.get("fallback")),
              "provider_attempts": sum(int((r.get("provider_requests") or {}).get("attempts", 0) or 0) for r in warm),
              "provider_mode_mock_all_chunks": all(m.get("provider_mode") == "mock" for m in mans["m"])}
        g3["pass"] = (g3["decisions"] == 0 and g3["fallbacks"] == 0 and g3["provider_attempts"] == 0
                      and g3["provider_mode_mock_all_chunks"])
        e4 = {a: A_[a]["e4"] for a in ARMS}
        e4_cls = sum(sum(v.values()) for v in e4.values())
        e4_all += e4_cls
        hcr = cont["HCR_CRa_minus_COMP"]
        hcr_pass = bool(hcr["ci95"] and hcr["ci95"][1] <= HCR_MARGIN_MS and hcr["pairs_ran"] == ROUNDS)
        s3 = doc["S_E3_BASE_over_CRa"]
        doc["gates"] = {"G0_validity_identical_outcomes": g0, "final_states_valid": sorted(states),
                        "G1_NC": g1, "G2_PC": g2, "G3": g3, "G4_E4_zero_class_measured": e4_cls == 0,
                        "H_CR_non_regression": hcr_pass, "S_E3_ci_lower_gt_1": bool(s3["ci95"] and s3["ci95"][0] > 1.0)}
        S["classes"][cls] = doc
    # amortized cost over ALL invocations (training + compile + admission + 40 warm CRa + forced fallbacks)
    S["amortized"] = {}
    for cls in CLASSES:
        tr = S["training"][cls]
        warm = [r["T_runner_ms"] for r in rows_m if r["cls"] == cls and r["f_arm"] == "CRa"]
        fb = [x["T_runner_ms"] for x in S["fallback"][cls]]
        parts = [tr["training_T_runner_ms"], tr["admission_T_runner_ms"]] + warm + fb
        defined = [x for x in parts if x is not None]
        total = sum(defined) + (tr["compile_ms"] or 0.0)
        n = len(parts)
        base = [r["T_runner_ms"] for r in rows_m if r["cls"] == cls and r["f_arm"] == "BASE" and r["valid"]]
        S["amortized"][cls] = {"invocations": n, "T_undefined": n - len(defined), "training_ms": tr["training_T_runner_ms"],
                               "compile_ms": tr["compile_ms"], "admission_ms": tr["admission_T_runner_ms"],
                               "warm_n": len(warm), "warm_mean_ms": mean(warm), "fallback_n": len(fb),
                               "fallback_mean_ms": mean(fb), "amortized_mean_ms": total / n if n else None,
                               "warm_median_ms": S["classes"][cls]["arms"]["CRa"]["T_runner_median"],
                               "BASE_mean_ms": mean(base),
                               "S_mean_BASE_over_amortized_descriptive": (mean(base) / (total / n)) if (base and n) else None}
    S["controls"] = controls(blocks["c"])
    for cls in CLASSES:
        S["classes"][cls]["gates"]["G4_E4_zero_all"] = (
            sum(sum(v.values()) for v in [S["classes"][cls]["arms"][a]["e4"] for a in ARMS]) == 0
            and all(x["e4"] == 0 for x in S["fallback"][cls]))
    # decomposition (CRa primary, COMP reference): valid trials only
    trials_by: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for t, r in zip(m_used, rows_m):
        if r["valid"] and r["f_arm"] in ("CRa", "COMP"):
            trials_by[(r["cls"], r["f_arm"])].append((t, r))
    S["decomposition"] = decomposition(trials_by)
    # work deleted vs wall-clock saved (descriptive)
    S["work_vs_wallclock"] = {cls: {
        "decisions_per_invocation": {a: S["classes"][cls]["arms"][a]["decisions_per_invocation"] for a in ARMS},
        "wall_clock_saved_COMP_minus_CRa_median_ms": -(S["classes"][cls]["contrasts"]["HCR_CRa_minus_COMP"]["median"] or 0.0),
        "wall_clock_saved_BASE_minus_CRa_median_ms": -(S["classes"][cls]["contrasts"]["CRa_minus_BASE"]["median"] or 0.0)}
        for cls in CLASSES}
    S["e4_total_measured"] = e4_all
    S["e4_total_all"] = e4_all + sum(x["e4"] for c in CLASSES for x in S["fallback"][c]) + sum(
        sum(r["e4"].values()) for r in [row(t) for t in blocks["c"] if t["summary"].get("kind") not in ("nw2", "smoke")])
    # disposition
    g = {cls: S["classes"][cls]["gates"] for cls in CLASSES}
    all_g = all(g[c]["G0_validity_identical_outcomes"] and g[c]["G1_NC"] and g[c]["G2_PC"] and g[c]["G3"]["pass"]
                and g[c]["G4_E4_zero_all"] for c in CLASSES) and S["controls"]["all_pass"]
    hcr = all(g[c]["H_CR_non_regression"] for c in CLASSES)
    if S["e4_total_all"] > 0:
        disp = "KILL"
    elif hcr and all_g:
        disp = "KEEP"
    else:
        disp = "REVISE"
    S["disposition"] = {"value": disp, "H_CR": {c: g[c]["H_CR_non_regression"] for c in CLASSES},
                        "gates_G0_G4_controls": all_g,
                        "H_D": {c: S["decomposition"]["classes"][c]["H_D"]["pass"] for c in CLASSES},
                        "S_E3_ci_lower_gt_1": {c: g[c]["S_E3_ci_lower_gt_1"] for c in CLASSES}}
    return rnd(S)


def fmt(x: float | None, nd: int = 1, sign: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def ci_txt(c: dict[str, Any], nd: int = 1) -> str:
    return f"{fmt(c['median'], nd, True)} ms [{fmt(c['ci95'][0], nd, True)}, {fmt(c['ci95'][1], nd, True)}]" \
        if c.get("ci95") else "n/a"


def headlines(S: dict[str, Any]) -> dict[str, Any]:
    """Headline numbers with the exact README text (recomputed by verify_artifacts.py)."""
    if S["disposition"]["value"] == "BLOCKED":
        return rnd(headlines_blocked(S))
    H: dict[str, Any] = {}
    for cls in CLASSES:
        d = S["classes"][cls]
        g = d["gates"]
        c = d["contrasts"]
        arms = d["arms"]
        H[f"{cls}.validity"] = {"value": [arms[a]["valid"] for a in ARMS],
                                "text": f"{cls} valid " + ", ".join(f"{a} {arms[a]['valid']}/{arms[a]['n']}" for a in ARMS)}
        H[f"{cls}.medians"] = {"value": [arms[a]["T_runner_median"] for a in ARMS],
                               "text": f"{cls} median T_runner " + ", ".join(f"{a} {fmt(arms[a]['T_runner_median'])}" for a in ARMS)
                               + " ms"}
        H[f"{cls}.H_CR"] = {"value": [c["HCR_CRa_minus_COMP"]["median"], c["HCR_CRa_minus_COMP"]["ci95"], g["H_CR_non_regression"]],
                            "text": f"{cls} CRa - COMP {ci_txt(c['HCR_CRa_minus_COMP'])} ({c['HCR_CRa_minus_COMP']['n_pairs']} pairs), "
                                    f"H_CR {'PASS' if g['H_CR_non_regression'] else 'FAIL'}"}
        H[f"{cls}.G1"] = {"value": [c["NC_CRa_minus_CRb"]["median"], c["NC_CRa_minus_CRb"]["ci95"], g["G1_NC"]],
                          "text": f"{cls} NC CRa - CRb {ci_txt(c['NC_CRa_minus_CRb'])}, G1 {'PASS' if g['G1_NC'] else 'FAIL'}"}
        H[f"{cls}.G2"] = {"value": [c["PC_PC_minus_CRa"]["median"], c["PC_PC_minus_CRa"]["ci95"], g["G2_PC"]],
                          "text": f"{cls} PC - CRa {ci_txt(c['PC_PC_minus_CRa'])}, G2 {'PASS' if g['G2_PC'] else 'FAIL'}"}
        s3 = d["S_E3_BASE_over_CRa"]
        H[f"{cls}.S_E3"] = {"value": [s3["S"], s3["ci95"], g["S_E3_ci_lower_gt_1"]],
                            "text": f"{cls} S_E3 = {fmt(s3['S'], 2)} [{fmt(s3['ci95'][0], 2)}, {fmt(s3['ci95'][1], 2)}]"
                            if s3.get("ci95") else f"{cls} S_E3 n/a"}
        am = S["amortized"][cls]
        H[f"{cls}.amortized"] = {"value": [am["amortized_mean_ms"], am["warm_median_ms"], am["invocations"]],
                                 "text": f"{cls} amortized mean {fmt(am['amortized_mean_ms'])} ms over {am['invocations']} invocations "
                                         f"(warm median {fmt(am['warm_median_ms'])} ms)"}
        hd = S["decomposition"]["classes"][cls]["H_D"]
        H[f"{cls}.H_D"] = {"value": [hd["untested_share_bg_irreducible"], hd["untested_share_bg_untested"], hd["pass"]],
                           "text": f"{cls} untested share {fmt(100 * hd['untested_share_bg_irreducible'])}% / "
                                   f"{fmt(100 * hd['untested_share_bg_untested'])}%, H_D {'PASS' if hd['pass'] else 'FAIL'}"}
    H["disposition"] = {"value": S["disposition"]["value"], "text": f"Disposition: {S['disposition']['value']}"}
    H["controls"] = {"value": [S["controls"]["passed"], S["controls"]["n"]],
                     "text": f"controls {S['controls']['passed']}/{S['controls']['n']} pass"}
    H["e4"] = {"value": S["e4_total_all"], "text": f"E4 total {S['e4_total_all']}"}
    return rnd(H)


def blocked_summary(raw: Path, S: dict[str, Any]) -> dict[str, Any]:
    """No measured trial ran (no EXCLUSIVE quiet-lane acquisition was possible): the summary is the pilot
    pipeline check (SHARED, excluded from every result), the lock-wedge evidence and the BLOCKED disposition."""
    pilot = [row(t) for t in load_block(raw, "pilot")]
    wedge = [json.loads(x) for x in (raw / "lock-wedge.jsonl").read_text().splitlines() if x.strip()] \
        if (raw / "lock-wedge.jsonl").exists() else []
    gl = [json.loads(x) for x in (raw / "lock-receipts-global.jsonl").read_text().splitlines() if x.strip()] \
        if (raw / "lock-receipts-global.jsonl").exists() else []
    S["blocks"] = {b: 0 for b in ("t", "m", "f", "c")}
    S["first_measured_trial_utc"] = None
    S["pilot"] = {"n": len(pilot), "valid": sum(1 for r in pilot if r["valid"]),
                  "rows": [{"trial": r["trial"], "f_arm": r["f_arm"], "kind": r.get("kind"), "valid": r["valid"],
                            "reasons": r["reasons"], "decisions": r.get("provider_decisions"),
                            "decision_routes": r.get("decision_routes"), "driver_ok": r["driver_ok"],
                            "caller_stamps": r["caller_variant_stamps"], "pc_sleep_ms": r.get("pc_sleep_ms"),
                            "e4": sum(r["e4"].values())} for r in pilot],
                  "note": "SHARED lock, store 'pilot', excluded from every result; timing not reported"}
    S["driver_identity"] = dict(Counter(f"{r['driver']['driver_name']}|{r['driver']['driver_sha256']}|"
                                        f"{r['driver']['driver_version']}" for r in pilot))
    S["lock_wedge"] = wedge
    S["lane_receipts"] = {"shared": sum(1 for x in gl if x.get("mode") == "shared"),
                          "exclusive": sum(1 for x in gl if "mode" not in x)}
    S["gates"] = {g: "NOT_RUN" for g in ("G0", "G1_NC", "G2_PC", "G3", "G4", "H_CR", "S_E3", "H_D", "amortized",
                                         "controls")}
    S["e4_total_all"] = sum(sum(r["e4"].values()) for r in pilot)
    S["disposition"] = {"value": "BLOCKED",
                        "blocker": "no EXCLUSIVE quiet-lane acquisition was possible: the quiet-lane lock was held SHARED "
                                   "continuously by long-lived processes of another track (lock_wedge), so the lane's "
                                   "quiet-timed waiter (and every other exclusive waiter) starved; measuring outside the "
                                   "exclusive lock is not allowed"}
    return S


def headlines_blocked(S: dict[str, Any]) -> dict[str, Any]:
    w = S["lock_wedge"][-1] if S["lock_wedge"] else {}
    return {"disposition": {"value": "BLOCKED", "text": "Disposition: BLOCKED"},
            "pilot": {"value": [S["pilot"]["valid"], S["pilot"]["n"]],
                      "text": f"pilot {S['pilot']['valid']}/{S['pilot']['n']} trial records valid"},
            "wedge": {"value": [w.get("exclusive_waiters"), w.get("quiet_lane_lock_read_locks"), w.get("last_exclusive_receipt")],
                      "text": f"{w.get('exclusive_waiters')} exclusive waiters, {w.get('quiet_lane_lock_read_locks')} shared "
                              f"locks held, last exclusive receipt {w.get('last_exclusive_receipt')}"},
            "e4": {"value": S["e4_total_all"], "text": f"E4 total {S['e4_total_all']}"}}


def default(o: Any) -> Any:
    if isinstance(o, Counter):
        return dict(o)
    raise TypeError(type(o))


def pipeline_check(run: Path) -> dict[str, Any]:
    """Pilot: every trial row, validity reasons and whether the decomposition runs (no gate)."""
    ts = load_dir(run, "pilot")
    out = []
    for t in ts:
        s = t["summary"]
        r = row(t)
        d = decompose_trial(t, r, 0.0) if r.get("T_runner_ms") else {"ok": False}
        out.append({"trial": t["name"], "f_arm": s.get("f_arm"), "kind": s.get("kind"), "valid": r["valid"],
                    "reasons": r["reasons"], "T_runner_ms": r.get("T_runner_ms"), "T_oracle_ms": r.get("T_oracle_ms"),
                    "T_j_ms": r.get("T_j_ms"), "E_ms": r.get("E_ms"), "pc_sleep_ms": r.get("pc_sleep_ms"),
                    "decisions": r.get("provider_decisions"), "routes": r.get("decision_routes"),
                    "stamps": r.get("caller_variant_stamps"), "driver_ok": r["driver_ok"],
                    "decomp_ok": d.get("ok"), "consistency": d.get("consistency_max_abs_ms"),
                    "coverage_b05": d.get("coverage_b05"), "coverage_r210": d.get("coverage_r210"),
                    "training": (s.get("training") or {}) and {k: s["training"].get(k) for k in
                                                                ("learning_verified", "admitted", "compile_ms",
                                                                 "authority_problems")}})
    return rnd({"n": len(out), "rows": out})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "r2-07f-summary.json"))
    p.add_argument("--trials-dir")
    a = p.parse_args()
    S = pipeline_check(Path(a.trials_dir)) if a.trials_dir else analyze(Path(a.raw))
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True, default=default) + "\n")
    if not a.trials_dir:
        print(json.dumps(S["disposition"], indent=1))


if __name__ == "__main__":
    main()

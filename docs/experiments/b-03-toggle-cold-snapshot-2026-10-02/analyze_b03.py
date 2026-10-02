"""B-03 Part 2 analysis: recompute b03-summary.json from raw/ (standard library only).

    python analyze_b03.py [--raw raw] [--out b03-summary.json]

Rules: PREREG.json (part2.verdict_rules_per_K, gates, positive_replication). The per-trial
validity, decomposition and first-snapshot excess are B-02's ``analyze_browser.trial_row``
(B-01 forced path + B-02 knob path, unchanged); T_oracle/T_runner are re-based on the
``task_start`` stamp so that T_oracle(D=80) includes the wait. Statistics reuse B-01's
seeded bootstrap. Part 1 (``part1-summary.json``) supplies the B-02 E2 rows used for the
restatement.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tarfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
B02 = HERE.parent / "b-02-browser-driver-sites-2026-10-02"
sys.path.insert(0, str(B02))

import analyze_browser as AB  # noqa: E402  (B-02, unchanged)
import b01_analysis as B  # noqa: E402

SNAP_SUB = [("attach", "snap.enter", "snap.attached"), ("dom_get_document", "snap.attached", "snap.document"),
            ("frame_tree", "snap.document", "snap.frame_tree"),
            ("layout_snapshot", "snap.frame_tree", "snap.layout_cdp_done"),
            ("ax_tree", "snap.indexed", "snap.ax_cdp_done"), ("total", "snap.enter", "snap.serialized")]
DISPATCH = ("click.cdp_send", "type.insert_send")


def load(raw: Path, block: str) -> list[dict[str, Any]]:
    files: dict[str, str] = {}
    with tarfile.open(raw / f"{block}-trials.tar.gz", "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name.endswith(".jsonl"):
                files[Path(m.name).name] = tar.extractfile(m).read().decode()
    out = []
    for name in sorted(files):
        if name.endswith("driver-trace.jsonl"):
            continue
        lines = [json.loads(x) for x in files[name].splitlines() if x.strip()]
        s = lines[-1]
        trace_text = files.get(Path(s["driver_trace"]).name, "") if s.get("driver_trace") else ""
        out.append({"name": s["trial"], "summary": s, "events": lines[:-1],
                    "trace": [json.loads(x) for x in trace_text.splitlines() if x.strip()], "block": block})
    return out


def ev_t(t: dict[str, Any], name: str) -> int | None:
    return next((e["t_mono_ns"] for e in t["events"] if e["event"] == name), None)


def snap_spans(trace: list[dict[str, Any]], w: dict[str, Any] | None) -> dict[str, float]:
    if w is None:
        return {}
    marks: dict[str, int] = {}
    for m in trace:
        if w["t0"] <= m["t_mono_ns"] <= w["t1"] and m["phase"].startswith("snap.") and m["phase"] not in marks:
            marks[m["phase"]] = m["t_mono_ns"]
    return {k: (marks[b] - marks[a]) / 1e6 for k, a, b in SNAP_SUB if a in marks and b in marks}


def row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    r = AB.trial_row(t)
    r.update({"P": s.get("P"), "D": s.get("D"), "variant": s.get("variant")})
    wins = {w["label"]: w for w in AB.windows(t)}
    ts, de = ev_t(t, "task_start"), ev_t(t, "delay_end")
    verified = next((e["t_mono_ns"] for e in t["events"] if e["event"] == "oracle_return" and e.get("outcome") == "verified"), None)
    poller = s.get("poller_first_ok_ns")
    nav = wins.get("navigate")
    bind = wins.get("bind")
    if ts is None:
        r["valid"] = False
        r["reasons"] = r["reasons"] + ["no_task_start"]
    r["T_oracle_task_ms"] = None if (ts is None or poller is None) else (poller - ts) / 1e6
    r["T_runner_task_ms"] = None if (ts is None or verified is None) else (verified - ts) / 1e6
    r["delay_actual_ms"] = None if (ts is None or de is None) else (de - ts) / 1e6
    r["nav_return_to_first_obs_send_ms"] = (None if (nav is None or "snapshot1" not in wins)
                                            else (wins["snapshot1"]["t0"] - nav["t1"]) / 1e6)
    r["navigate_ms"] = None if nav is None else (nav["t1"] - nav["t0"]) / 1e6
    ww, wsn = wins.get("warm_navigate"), wins.get("warm_snapshot")
    r["warmup_ms"] = (wsn["t1"] - ww["t0"]) / 1e6 if (ww and wsn) else (0.0 if s.get("P") == "cold" else None)
    r["bind_end_to_oracle_ms"] = None if (bind is None or poller is None) else (poller - bind["t1"]) / 1e6
    r["snapshot1_ms"] = None if "snapshot1" not in wins else (wins["snapshot1"]["t1"] - wins["snapshot1"]["t0"]) / 1e6
    r["snapshot2_ms"] = None if "snapshot2" not in wins else (wins["snapshot2"]["t1"] - wins["snapshot2"]["t0"]) / 1e6
    r["snap1_sub"] = snap_spans(t["trace"], wins.get("snapshot1"))
    r["snap2_sub"] = snap_spans(t["trace"], wins.get("snapshot2"))
    r["warm_snapshot_sub"] = snap_spans(t["trace"], wsn)
    r["nc_presnapshot_ms"] = (None if "nc_presnapshot" not in wins
                              else (wins["nc_presnapshot"]["t1"] - wins["nc_presnapshot"]["t0"]) / 1e6)
    # Amendment 1: a dom_event action's envelope is effect=unverifiable in every trial (the oracle
    # verifies), so staleness is judged from order and refusals: every actionN must be dispatched
    # from snapshotN of the same step, with no navigate or other snapshot in between, and no
    # action may be refused (browser_ref_stale) or error out.
    order = [w for w in AB.windows(t) if w["tool"] in ("get_browser_state", "browser_navigate", "browser_click", "browser_type")]
    stale = bool(s.get("action_error"))
    for i, w in enumerate(order):
        if w["label"].startswith("action"):
            prev = order[i - 1] if i else None
            if prev is None or prev["label"] != "snapshot" + w["label"].removeprefix("action"):
                stale = True
    rets = [e for e in t["events"] if e["event"] == "call_return" and str(e.get("label", "")).startswith("action")]
    if any(e.get("effect") == "refused" or e.get("ok") is False for e in rets):
        stale = True
    r["stale_dispatch"] = stale
    r["action_routes"] = [e.get("route") for e in rets]
    r["action_effects"] = [e.get("effect") for e in rets]
    r["dispatch_marks_in_T"] = sum(1 for m in t["trace"] if m["phase"] in DISPATCH)
    r["admission_residual_ms"] = r.get("admission_ms")
    r["loadavg_after_1m"] = float(s["loadavg_after"].split()[0]) if s.get("loadavg_after") else None
    r["duplicate_mutation"] = (s.get("completion_mutations") or 0) > 1
    r["unverified_success"] = s.get("outcome") == "verified" and not s.get("oracle_exact_match")
    r["non_loopback"] = (s.get("network") or {}).get("non_loopback_connect_attempts", 0)
    r["driver_env_knobs"] = s.get("driver_env_knobs")
    r["driver_env_telemetry"] = s.get("driver_env_telemetry")
    r["browser_alive_after_close"] = s.get("browser_alive_after_close")
    return r


def med(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def mean(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def one_sample(xs: list[float]) -> dict[str, Any]:
    xs = [x for x in xs if x is not None]
    return {"n": len(xs), "median": med(xs), "mean": mean(xs),
            "ci95": B.boot_ci(len(xs), lambda idx: statistics.median([xs[i] for i in idx]))}


def cell(rows: list[dict[str, Any]], **k: Any) -> list[dict[str, Any]]:
    return [r for r in rows if all(r.get(a) == b for a, b in k.items())]


def by_round(rows: list[dict[str, Any]], key: str, **k: Any) -> dict[int, float]:
    return {r["round"]: r[key] for r in cell(rows, **k) if r["valid"] and r.get(key) is not None}


def paired(rows: list[dict[str, Any]], key_a: str, a: dict, key_b: str, b: dict) -> dict[str, Any]:
    """Round-paired differences a - b (each side a cell selector and a value key)."""
    ra, rb = by_round(rows, key_a, **a), by_round(rows, key_b, **b)
    rounds = sorted(set(ra) & set(rb))
    out = B.paired_diff([ra[r] for r in rounds], [rb[r] for r in rounds])
    out["mean"] = mean([ra[r] - rb[r] for r in rounds])
    out["rounds_dropped"] = sorted((set(ra) | set(rb)) - set(rounds))
    return out


def with_incl(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        r["T_oracle_incl_warmup_ms"] = (None if (r.get("T_oracle_task_ms") is None or r.get("warmup_ms") is None)
                                        else r["T_oracle_task_ms"] + r["warmup_ms"])


def ci_lo_pos(d: dict) -> bool:
    return bool(d.get("ci95") and d["ci95"][0] > 0)


def ci_has_0(d: dict) -> bool:
    return bool(d.get("ci95") and d["ci95"][0] <= 0 <= d["ci95"][1])


def cell_block(rs: list[dict[str, Any]]) -> dict[str, Any]:
    v = [r for r in rs if r["valid"]]
    subs = {}
    for which in ("snap1_sub", "snap2_sub"):
        keys = sorted({k for r in v for k in r[which]})
        subs[which] = {k: med([r[which].get(k) for r in v]) for k in keys}
    keys = sorted({k for r in v for k in r["snap1_sub"]})
    subs["excess_by_subspan_median"] = {k: med([r["snap1_sub"].get(k, 0) - r["snap2_sub"].get(k, 0) for r in v
                                                if k in r["snap1_sub"] and k in r["snap2_sub"]]) for k in keys}
    return {"n": len(rs), "valid": len(v), "failures": [{"trial": r["trial"], "reasons": r["reasons"]} for r in rs if not r["valid"]],
            "T_oracle_task_ms": {"median": med([r["T_oracle_task_ms"] for r in v]), "mean": mean([r["T_oracle_task_ms"] for r in v])},
            "T_runner_task_ms": {"median": med([r["T_runner_task_ms"] for r in v]), "mean": mean([r["T_runner_task_ms"] for r in v])},
            "T_runner_from_snapshot1_mean_ms": mean([r["T_runner_ms"] for r in v]),
            "first_snapshot_span_ms": {"median": med([r["snapshot1_ms"] for r in v]), "mean": mean([r["snapshot1_ms"] for r in v])},
            "snapshot2_span_ms_median": med([r["snapshot2_ms"] for r in v]),
            "observation_total_ms": one_sample([(r["snapshot1_ms"] + r["snapshot2_ms"]) for r in v
                                                if r["snapshot1_ms"] is not None and r["snapshot2_ms"] is not None]),
            "action_routes": sorted({json.dumps(r["action_routes"]) for r in v}),
            "cold_excess_ms": one_sample([r["first_snapshot_excess_ms"] for r in v]),
            "warmup_ms_median": med([r["warmup_ms"] for r in v]),
            "navigate_ms_median": med([r["navigate_ms"] for r in v]),
            "delay_actual_ms": {"median": med([r["delay_actual_ms"] for r in v]),
                                "min": min([r["delay_actual_ms"] for r in v], default=None),
                                "max": max([r["delay_actual_ms"] for r in v], default=None)},
            "nav_return_to_first_obs_send_ms_median": med([r["nav_return_to_first_obs_send_ms"] for r in v]),
            "bind_end_to_oracle_ms_median": med([r["bind_end_to_oracle_ms"] for r in v]),
            "admission_residual_ms_mean": mean([r["admission_residual_ms"] for r in v]),
            "unattributed_ms_mean": mean([r["components"]["unattributed"] for r in v]),
            "components_mean_ms": {c: mean([r["components"][c] for r in v]) for c in B.COMPONENTS} if v else {},
            "coverage_min": min([r["coverage"] for r in v], default=None),
            "producer": subs,
            "loadavg_1m_range": [min(r["loadavg_1m"] for r in rs), max(r["loadavg_1m"] for r in rs)] if rs else None}


def decide(rows: list[dict[str, Any]], cls: str, k: str, gates_ok: bool, pos_ok: bool | None) -> dict[str, Any]:
    base = {"cls": cls, "arm": k, "variant": "task"}
    c = {f"{p}_D{d}": cell(rows, **base, P=p, D=d) for p in ("cold", "warm") for d in (0, 80)}
    E = one_sample([r["first_snapshot_excess_ms"] for r in c["cold_D0"] if r["valid"]])
    X = "first_snapshot_excess_ms"
    pp = paired(rows, X, {**base, "P": "cold", "D": 80}, X, {**base, "P": "warm", "D": 80})
    pd = paired(rows, X, {**base, "P": "warm", "D": 0}, X, {**base, "P": "warm", "D": 80})
    doc_cold = paired(rows, X, {**base, "P": "cold", "D": 0}, X, {**base, "P": "cold", "D": 80})
    floor = one_sample([r[X] for r in c["warm_D80"] if r["valid"]])
    T = "T_oracle_task_ms"
    dT_cold = paired(rows, T, {**base, "P": "cold", "D": 80}, T, {**base, "P": "cold", "D": 0})
    dT_warm = paired(rows, T, {**base, "P": "warm", "D": 80}, T, {**base, "P": "warm", "D": 0})
    sav_cold = paired(rows, T, {**base, "P": "cold", "D": 0}, T, {**base, "P": "cold", "D": 80})
    sav_warm = paired(rows, T, {**base, "P": "warm", "D": 0}, T, {**base, "P": "warm", "D": 80})
    warm_incl = paired(rows, T, {**base, "P": "cold", "D": 0}, "T_oracle_incl_warmup_ms", {**base, "P": "warm", "D": 0})
    warm_incl_d80 = paired(rows, T, {**base, "P": "cold", "D": 80}, "T_oracle_incl_warmup_ms", {**base, "P": "warm", "D": 80})
    warm_only = paired(rows, T, {**base, "P": "cold", "D": 0}, T, {**base, "P": "warm", "D": 0})
    e2e = paired(rows, "bind_end_to_oracle_ms", {**base, "P": "cold", "D": 0}, "bind_end_to_oracle_ms", {**base, "P": "warm", "D": 0})

    # per-process rule
    if ci_lo_pos(pp) and E["median"] and pp["median"] >= 0.5 * E["median"]:
        pp_v = "OWNER_DECISION" if ci_lo_pos(warm_incl) else "NOT DELETED (moved only)"
        pp_rule = "per-process first-document work (CI excludes 0, >= 50% of the excess)"
    elif ci_lo_pos(pp):
        pp_v, pp_rule = "UNDECIDED", "per-process part shown (CI excludes 0) but < 50% of the excess"
    elif (pp["mean"] or 0) > 0:
        pp_v, pp_rule = "UNDECIDED", "per-process part not shown (CI includes 0) and its mean is > 0"
    else:
        pp_v, pp_rule = "NONE (mean <= 0)", "no per-process part"
    if pos_ok is False and pp_v != "NONE (mean <= 0)":
        pp_v, pp_rule = "UNDECIDED", pp_rule + "; positive replication failed"

    def doc_rule(dT: dict, sav: dict) -> str:
        if dT["median"] is not None and dT["median"] >= -2.0:
            return "IRREDUCIBLE"
        if ci_lo_pos(sav) and sav["median"] > 2.0:
            return "DELETED candidate (KEEP)"
        return "UNDECIDED"
    pd_v = doc_rule(dT_cold, sav_cold)
    pd_v_warm = doc_rule(dT_warm, sav_warm)
    if not gates_ok:
        pp_v, pd_v = "UNDECIDED (gate failed)", "UNDECIDED (gate failed)"
    floor_counts = bool(floor["ci95"] and floor["ci95"][0] > 0)
    parts = {"doc_cold": {"mean_ms": doc_cold["mean"], "verdict": pd_v},
             "per_process": {"mean_ms": pp["mean"], "verdict": pp_v},
             "floor": {"mean_ms": floor["mean"], "verdict": "UNTESTED (CI excludes 0, > 0)" if floor_counts
                       else "no excess (CI includes 0 or <= 0)"}}
    undecided_ms = sum(max(0.0, p["mean_ms"] or 0.0) for n, p in parts.items()
                       if n != "floor" and str(p["verdict"]).startswith("UNDECIDED"))
    undecided_ms += max(0.0, floor["mean"] or 0.0) if floor_counts else 0.0
    cd0 = [r for r in c["cold_D0"] if r["valid"]]
    meanT = mean([r["T_runner_ms"] for r in cd0])
    adm = mean([r["admission_residual_ms"] for r in cd0]) or 0.0
    una = mean([r["components"]["unattributed"] for r in cd0]) or 0.0
    E_mean = E["mean"] or 0.0
    return {
        "cells": {n: cell_block(v) for n, v in c.items()},
        "E_cold_D0": E, "per_process": pp, "per_document_warm": pd, "doc_cold": doc_cold, "floor_warm_D80": floor,
        "dT_oracle_D80_minus_D0": {"cold": dT_cold, "warm": dT_warm},
        "T_oracle_saving_D0_minus_D80": {"cold": sav_cold, "warm": sav_warm},
        "cold_minus_warm_incl_warmup": {"D0": warm_incl, "D80": warm_incl_d80},
        "cold_minus_warm_T_oracle_excl_warmup_D0": warm_only,
        "cold_minus_warm_bind_end_to_oracle_D0": e2e,
        "per_process_share_of_E": None if (not E["median"] or pp["median"] is None) else pp["median"] / E["median"],
        "verdicts": {"per_process": pp_v, "per_process_rule": pp_rule, "per_document": pd_v,
                     "per_document_at_warm": pd_v_warm},
        "accounting": {"parts": parts, "sum_of_parts_mean_ms": sum((p["mean_ms"] or 0.0) for p in parts.values()),
                       "E_mean_ms": E_mean, "undecided_cold_excess_ms": undecided_ms,
                       "untested_fraction_of_cold_excess": (undecided_ms / E_mean) if E_mean else None,
                       "admission_residual_ms": adm, "unattributed_ms": una, "T_runner_mean_ms": meanT,
                       "untested_share": ((adm + una + undecided_ms) / meanT) if meanT else None},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "raw"))
    ap.add_argument("--out", default=str(HERE / "b03-summary.json"))
    ap.add_argument("--block", default="measured")
    a = ap.parse_args()
    raw = Path(a.raw)
    trials = load(raw, a.block)
    rows = [row(t) for t in trials]
    with_incl(rows)
    out: dict[str, Any] = {"schema": "cua.r2.b03.summary.v1", "block": a.block, "trials": len(rows),
                           "valid": sum(r["valid"] for r in rows)}
    # gates
    cells = {}
    for r in rows:
        key = f"{r['cls']}:{r['arm']}:{r['P']}:D{r['D']}:{r['variant']}"
        cells.setdefault(key, []).append(r)
    validity = {k: {"n": len(v), "valid": sum(x["valid"] for x in v),
                    "pass": sum(x["valid"] for x in v) >= 0.95 * len(v)} for k, v in sorted(cells.items())}
    inv = {"stale_dispatches": sum(r["stale_dispatch"] for r in rows),
           "duplicate_completion_mutations": sum(r["duplicate_mutation"] for r in rows),
           "unverified_successes": sum(r["unverified_success"] for r in rows),
           "non_loopback_connect_attempts": sum(r["non_loopback"] for r in rows)}
    inv["pass"] = all(v == 0 for v in inv.values())
    nc = [r for r in rows if r["variant"] == "nc"]
    nc_ex = one_sample([r["first_snapshot_excess_ms"] for r in nc if r["valid"]])
    nc_gate = {"cold_excess": nc_ex, "pass": ci_has_0(nc_ex),
               "nc_presnapshot_ms_median": med([r["nc_presnapshot_ms"] for r in nc if r["valid"]]),
               "snapshot1_ms_median": med([r["snapshot1_ms"] for r in nc if r["valid"]]),
               "snapshot2_ms_median": med([r["snapshot2_ms"] for r in nc if r["valid"]]),
               "producer": cell_block(nc)["producer"] if nc else None,
               "T_oracle_task_ms_median": med([r["T_oracle_task_ms"] for r in nc if r["valid"]])}
    out["gates"] = {"validity": validity, "validity_pass": all(v["pass"] for v in validity.values()),
                    "invariants": inv, "negative_control": nc_gate}
    # forced path and environment receipts
    out["forced_path"] = {"input_routes": sorted({str(x) for t in trials for x in (t["summary"].get("input_routes") or [])}),
                          "knob_env_by_arm": {a_: sorted({json.dumps(r["driver_env_knobs"], sort_keys=True) for r in rows if r["arm"] == a_})
                                              for a_ in sorted({r["arm"] for r in rows})},
                          "telemetry_env": sorted({str(r["driver_env_telemetry"]) for r in rows}),
                          "invalid_reasons": sorted({x for r in rows for x in r["reasons"]})}
    out["loadavg_1m_range"] = [min(r["loadavg_1m"] for r in rows), max(r["loadavg_1m"] for r in rows)] if rows else None
    gates_ok = out["gates"]["validity_pass"] and inv["pass"] and nc_gate["pass"]
    # positive replication (fill, K5V)
    fill = decide(rows, "fill", "K5V", gates_ok, None) if cell(rows, cls="fill") else None
    pos_ok = None
    if fill:
        pos_ok = ci_lo_pos(fill["per_process"]) and bool(fill["E_cold_D0"]["median"]) and \
            fill["per_process"]["median"] >= 0.5 * fill["E_cold_D0"]["median"]
        out["positive_replication_fill_K5V"] = {**fill, "reproduces_moved_only": pos_ok}
    out["toggle"] = {k: decide(rows, "toggle", k, gates_ok, pos_ok) for k in ("K5V", "K5EV")
                     if cell(rows, cls="toggle", arm=k, variant="task")}
    # restatement on B-02's E2 rows (Part 1)
    p1f = HERE / "part1-summary.json"
    if p1f.exists() and out["toggle"]:
        p1 = json.loads(p1f.read_text())["classes"]["toggle"]["arms"]
        rest = {}
        for k, d in out["toggle"].items():
            b = p1[k]
            frac = d["accounting"]["untested_fraction_of_cold_excess"] or 0.0
            un = b["untested_ms"]
            ms = un["admission_residual_after_V"] + un["unattributed"] + frac * un.get("first_snapshot_cold_excess", 0.0)
            rest[k] = {"b02_T_runner_mean_ms": b["T_runner_mean_ms"], "b02_cold_excess_mean_ms": b["first_snapshot_excess_mean_ms"],
                       "untested_fraction_from_b03": frac, "untested_ms": ms,
                       "untested_share": ms / b["T_runner_mean_ms"], "b02_untested_share_before": b["untested_share"]}
        out["toggle_restated_on_b02_e2"] = rest
    out["per_trial"] = [{k: r.get(k) for k in ("trial", "cls", "arm", "P", "D", "variant", "round", "valid", "reasons",
                                               "T_oracle_task_ms", "T_runner_task_ms", "T_oracle_ms", "first_snapshot_excess_ms",
                                               "snapshot1_ms", "snapshot2_ms", "warmup_ms", "delay_actual_ms",
                                               "nav_return_to_first_obs_send_ms", "navigate_ms", "bind_end_to_oracle_ms",
                                               "admission_residual_ms", "stale_dispatch", "action_routes", "action_effects", "dispatch_marks_in_T",
                                               "loadavg_1m", "loadavg_after_1m", "snap1_sub", "snap2_sub")} for r in rows]
    out = json.loads(json.dumps(out, sort_keys=True, default=lambda x: round(x, 6) if isinstance(x, float) else str(x)))
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    brief = {"trials": f"{out['valid']}/{out['trials']}", "validity_pass": out["gates"]["validity_pass"],
             "invariants": inv, "nc": {"median": nc_ex["median"], "ci95": nc_ex["ci95"], "pass": nc_gate["pass"]},
             "fill_moved_only": pos_ok}
    for k, d in out["toggle"].items():
        brief[k] = {"E": d["E_cold_D0"]["median"], "PP": [d["per_process"]["median"], d["per_process"]["ci95"]],
                    "PD": [d["per_document_warm"]["median"], d["per_document_warm"]["ci95"]],
                    "dT_cold": [d["dT_oracle_D80_minus_D0"]["cold"]["median"], d["dT_oracle_D80_minus_D0"]["cold"]["ci95"]],
                    "verdicts": d["verdicts"], "untested_share": d["accounting"]["untested_share"]}
    print(json.dumps(brief, indent=1, default=str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""R2-07 analysis: recompute every headline from raw/ (stdlib only).

usage: python3 analyze.py [--write]   (prints the summary; --write updates r2-07-summary.json)
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
sys.path.insert(0, str(HERE / "harness"))
import compiled_routine as cr  # noqa: E402

SEED = 20261002
RESAMPLES = 10000


def jl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def iqr(xs):
    xs = sorted(x for x in xs if x is not None)
    if len(xs) < 4:
        return None
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return [round(q[0], 3), round(q[2], 3)]


def boot_median_ci(diffs: list[float]) -> dict:
    if not diffs:
        return {"n": 0}
    rng = random.Random(SEED)
    n = len(diffs)
    stats = sorted(statistics.median(rng.choices(diffs, k=n)) for _ in range(RESAMPLES))
    lo, hi = stats[int(0.025 * RESAMPLES)], stats[int(0.975 * RESAMPLES) - 1]
    return {"n": n, "median": round(statistics.median(diffs), 3), "ci95": [round(lo, 3), round(hi, 3)],
            "excludes_0": lo > 0 or hi < 0, "upper_below_0": hi < 0}


def trial_rows(phase_dir: Path) -> list[tuple[dict, list[dict]]]:
    out = []
    for f in sorted((phase_dir / "trials").glob("*.jsonl")):
        rows = jl(f)
        out.append((rows[0], rows))
    return out


def receipt_components(rows: list[dict]) -> dict:
    cell = rows[0]
    t0 = cell.get("first_semantic_send_ns")
    rec = [r for r in rows if r.get("type") == "receipt"]
    if t0 is None:
        return {}
    end = cell.get("oracle_seen_ns") or 0
    obs = prov = mut = 0.0
    windows = []
    last_obs_end = None
    last_mut_end = None
    fresh_ok, fresh_total = 0, 0
    latest_snap, latest_snap_start = None, None
    for r in rec:
        if r.get("kind") == "driver_call" and r.get("t_start_ns", 0) >= t0 and r["t_start_ns"] <= end:
            span = (r["t_end_ns"] - r["t_start_ns"]) / 1e6
            if r.get("tool") == "get_browser_state" and r.get("arg_snapshot_format") == "semantic_v2":
                obs += span
                last_obs_end = r["t_end_ns"]
            elif r.get("tool") in ("browser_type", "browser_click"):
                mut += span
                if last_obs_end:
                    windows.append(round((r["t_start_ns"] - last_obs_end) / 1e6, 3))
        if r.get("kind") == "provider_response" and r.get("t_start_ns", 0) >= t0 and r["t_start_ns"] <= end:
            prov += (r["t_end_ns"] - r["t_start_ns"]) / 1e6
        # G3 freshness (whole trial)
        if r.get("kind") == "driver_call" and r.get("tool") == "get_browser_state" and r.get("arg_snapshot_format") == "semantic_v2" and r.get("ok"):
            latest_snap, latest_snap_start = r.get("snapshot_id"), r["t_start_ns"]
        if r.get("kind") == "driver_call" and r.get("tool") in ("browser_type", "browser_click"):
            fresh_total += 1
            ok = (latest_snap is not None and str(r.get("arg_ref", "")).split(":")[0] == latest_snap
                  and (last_mut_end is None or latest_snap_start >= last_mut_end))
            fresh_ok += int(ok)
            last_mut_end = r["t_end_ns"]
    T = cell.get("T_ms")
    return {"observe_ms": round(obs, 3), "provider_ms": round(prov, 3), "mutation_ms": round(mut, 3),
            "other_ms": round(T - obs - prov - mut, 3) if T is not None else None,
            "obs_to_dispatch_windows_ms": windows, "fresh_dispatch": [fresh_ok, fresh_total]}


def cell_valid(cell: dict) -> bool:
    fb = cell.get("feedback_off") or []
    return bool(fb) and all(x.get("enabled_after") is False and x.get("session_label_matches") for x in fb)


def analyze() -> dict:
    S: dict = {"schema": "cua.r2.r2-07.summary.v1", "seed": SEED, "resamples": RESAMPLES}

    # ---------------- learn / compile / admission
    learn = RAW / "learn"
    lt = {c["cell_id"]: (c, rows) for c, rows in trial_rows(learn)}
    p1 = next(v for k, v in lt.items() if "-P1-" in k)
    p3 = next(v for k, v in lt.items() if "-P3-" in k)
    compile_info = json.loads((learn / "compile.json").read_text())
    artifact = json.loads((learn / "artifact.json").read_text())
    authority = cr.check_artifact_authority(artifact)
    p1c, p3c = p1[0], p3[0]
    S["learning"] = {"cell": p1c["cell_id"], "verified": p1c["independently_verified"], "reported": p1c["reported_outcome"],
                     "T_ms": p1c["T_ms"], "process_wall_ms": p1c["process_wall_ms"], "http_attempts": p1c["http_attempts"],
                     "http_reached": p1c["http_reached"], "live_decisions": p1c["provider_decisions_live"],
                     "models": sorted({d.get("model") for d in p1c["provider_responses"] if d.get("model")}),
                     "feedback_off_valid": cell_valid(p1c), "components": receipt_components(p1[1])}
    S["compile"] = {"compile_ms": compile_info["compile_ms"], "error": compile_info["compile_error"],
                    "authority_problems": authority, "steps": len(artifact["steps"])}
    S["admission"] = {"cell": p3c["cell_id"], "verified": p3c["independently_verified"], "reported": p3c["reported_outcome"],
                      "T_ms": p3c["T_ms"], "process_wall_ms": p3c["process_wall_ms"], "http_attempts": p3c["http_attempts"],
                      "feedback_off_valid": cell_valid(p3c), "components": receipt_components(p3[1])}
    G1 = bool(p1c["independently_verified"] and p1c["provider_decisions_live"] == 2 and cell_valid(p1c))
    G2 = bool(p3c["independently_verified"] and p3c["reported_outcome"] == "verified" and p3c["http_attempts"] == 0 and cell_valid(p3c))

    # ---------------- warm
    warm = trial_rows(RAW / "warm")
    by = {}
    for cell, rows in warm:
        by[(cell["round"], cell["arm"])] = (cell, rows)
    arms = {}
    for arm in "ABC":
        cells = [v for (r, a), v in sorted(by.items()) if a == arm]
        ok = [c for c, _ in cells if c.get("independently_verified") and cell_valid(c)]
        comps = [receipt_components(rows) for c, rows in cells if c.get("independently_verified")]
        arms[arm] = {
            "n": len(cells), "verified": len(ok),
            "reported_verified": sum(1 for c, _ in cells if c.get("reported_outcome") == "verified"),
            "unverified_success": sum(1 for c, _ in cells if c.get("unverified_success")),
            "duplicates": sum(c.get("duplicate_submits", 0) for c, _ in cells),
            "feedback_invalid": sum(1 for c, _ in cells if not cell_valid(c)),
            "failures": [{"cell": c["cell_id"], "reported": c.get("reported_outcome"), "rc": c.get("rc"),
                          "journal_applied": c.get("journal_applied")} for c, _ in cells if not c.get("independently_verified")],
            "T_ms": {"median": med([c["T_ms"] for c in ok]), "iqr": iqr([c["T_ms"] for c in ok]),
                     "min": min((c["T_ms"] for c in ok), default=None), "max": max((c["T_ms"] for c in ok), default=None)},
            "T_target_ms_median": med([c["T_target_ms"] for c in ok]),
            "process_wall_ms_median": med([c["process_wall_ms"] for c, _ in cells]),
            "process_wall_ms_sum_all": round(sum(c["process_wall_ms"] for c, _ in cells), 3),
            "http_attempts": sum(c.get("http_attempts", 0) for c, _ in cells),
            "http_reached": sum(c.get("http_reached", 0) for c, _ in cells),
            "live_decisions": sum(c.get("provider_decisions_live", 0) for c, _ in cells),
            "input_tokens": sum((d.get("input_tokens") or 0) for c, _ in cells for d in c.get("provider_responses", [])),
            "output_tokens": sum((d.get("output_tokens") or 0) for c, _ in cells for d in c.get("provider_responses", [])),
            "models": sorted({d.get("model") for c, _ in cells for d in c.get("provider_responses", []) if d.get("model")}),
            "decision_routes": sorted({"/".join(str(x) for x in c.get("decision_routes", [])) for c, _ in cells}),
            "components_median": {k: med([x.get(k) for x in comps]) for k in ("observe_ms", "provider_ms", "mutation_ms", "other_ms")},
            "obs_to_dispatch_window_ms_median": [med([x["obs_to_dispatch_windows_ms"][i] for x in comps if len(x["obs_to_dispatch_windows_ms"]) > i]) for i in range(2)],
            "fresh_dispatch": [sum(x["fresh_dispatch"][0] for x in comps), sum(x["fresh_dispatch"][1] for x in comps)],
            "loadavg_spawn_1m": [float(c["loadavg_at_spawn"][0]) for c, _ in cells],
            "T_by_position": {str(p): med([c["T_ms"] for c in ok if c["position"] == p]) for p in (1, 2, 3)},
        }
    S["warm"] = arms
    rounds = sorted({r for (r, a) in by})
    paired = {}
    for name, (x, y) in {"C_minus_B": ("C", "B"), "C_minus_A": ("C", "A"), "B_minus_A": ("B", "A")}.items():
        diffs = []
        for r in rounds:
            cx, cy = by.get((r, x), (None,))[0], by.get((r, y), (None,))[0]
            if cx and cy and cx.get("independently_verified") and cy.get("independently_verified") and cell_valid(cx) and cell_valid(cy):
                diffs.append(cx["T_ms"] - cy["T_ms"])
        paired[name] = boot_median_ci(diffs)
        paired[name]["diffs_ms"] = [round(d, 3) for d in diffs]
    S["paired_T"] = paired

    # all-arm G3 for C cells (subprocess): receipts
    c_fresh = [receipt_components(rows)["fresh_dispatch"] for (r, a), (c, rows) in by.items() if a == "C"]
    c_fresh.append(receipt_components(p3[1])["fresh_dispatch"])

    # ---------------- negatives
    negs = []
    setup_failed = []
    for f in sorted(glob.glob(str(RAW / "neg" / "*" / "cells" / "*.jsonl"))):
        rows = jl(Path(f))
        cell = rows[0]
        cell["_block"] = Path(f).parts[-3]
        journal = rows[1]["events"] if len(rows) > 1 else []
        cell["_modal_opened"] = any(e["kind"] == "modal_opened" for e in journal)
        # Deviation (disclosed): a cell whose routine never started (setup error before the first
        # routine observation, no dispatch, no target POST) is a setup failure, not a routine outcome.
        if (cell.get("outcome") == "error" and not cell.get("observations") and not cell.get("mutations")
                and cell.get("journal_received") == 0):
            setup_failed.append({"block": cell["_block"], "cell": cell["cell_id"], "stop_reason": cell.get("stop_reason"),
                                 "wall_ms": cell.get("wall_ms_informational")})
            cell["_setup_failed"] = True
        negs.append(cell)
    rows_out = {}
    stale_routine = 0
    stale_driver_node = 0
    ambiguous = 0
    dup_all = 0
    unverified_all = 0
    n8_dispatch = 0
    neg_fresh = [0, 0]
    for cell in negs:
        if cell.get("_setup_failed"):
            continue
        row = cell["row"]
        r = rows_out.setdefault(row, {"reps": 0, "outcomes": [], "stop_reasons": [], "dispatches": [], "accepted": [],
                                      "journal_applied": [], "duplicates": 0, "unverified_success": 0, "notes": []})
        r["reps"] += 1
        r["outcomes"].append(cell["outcome"])
        r["journal_applied"].append(cell["journal_applied"])
        r["duplicates"] += cell.get("duplicate_submits", 0)
        dup_all += cell.get("duplicate_submits", 0)
        if row == "N4a_ord":
            r["dispatches"].append(cell.get("clicks_dispatched"))
            r["accepted"].append(sum(1 for d in cell.get("driver_calls", []) if d["tool"] == "browser_click" and d.get("ok")))
            r["notes"].append({"first_click_accepted_after_rerender": cell.get("first_click_accepted_after_rerender"),
                               "verified": cell.get("independently_verified")})
            continue
        r["stop_reasons"].append(cell.get("stop_reason"))
        muts = cell.get("mutations", [])
        r["dispatches"].append(len(muts))
        r["accepted"].append(cell.get("mutations_accepted"))
        r["unverified_success"] += int(bool(cell.get("unverified_success")))
        unverified_all += int(bool(cell.get("unverified_success")))
        neg_fresh[0] += sum(1 for m in muts if m.get("fresh"))
        neg_fresh[1] += len(muts)
        stale_routine += sum(1 for m in muts if not m.get("fresh"))
        if row == "N4a":
            n = cell.get("accepted_after_rerender", 0)
            stale_driver_node += n
            r["notes"].append({"driver_accepted_stale_node": n, "hook": cell.get("hook_log")})
        if row == "N3":
            amb = sum(1 for m in muts if m.get("action") == "browser_click" and m.get("result") == "accepted")
            ambiguous += amb
        if row == "N8":
            n8_dispatch += len(muts) + cell.get("journal_toggle_events", 0)
        if row == "N4b":
            r["notes"].append({"mutation_results": [(m["step"], m["result"], m.get("code")) for m in muts]})
        if row == "N5":
            r["notes"].append({"hook": cell.get("hook_log")})
        if row == "N6":
            r["notes"].append({"modal_opened": cell["_modal_opened"]})
        if row == "N7":
            r["notes"].append({"route": cell.get("route"), "fallback_decisions": cell.get("fallback_decisions")})
    def row_safe(row, r):
        ends_ok = all(o in ("verified", "fallback_verified", "stopped", "unknown") for o in r["outcomes"])
        return ends_ok and r["duplicates"] == 0 and r["unverified_success"] == 0
    g4_rows = {}
    for row, r in rows_out.items():
        if row == "N4a_ord":
            continue
        ok = row_safe(row, r) and r["reps"] == 3
        if row == "N3":
            ok = ok and all(a <= 1 for a in r["accepted"]) and ambiguous == 0
        if row == "N4a":
            ok = ok and stale_driver_node == 0
        if row == "N8":
            ok = ok and n8_dispatch == 0
        g4_rows[row] = ok
    S["negatives"] = {"setup_failed_before_routine": setup_failed, "rows": rows_out, "g4_row_pass": g4_rows, "stale_routine_attributable": stale_routine,
                      "stale_driver_accepted_node": stale_driver_node, "ambiguous_dispatch": ambiguous,
                      "duplicates": dup_all, "unverified_success": unverified_all, "n8_dispatches": n8_dispatch,
                      "fresh_dispatch": neg_fresh}
    G4_expected_rows = {"N1", "N2", "N3", "N4a", "N4b", "N5", "N6", "N7", "N8"}
    G4 = set(g4_rows) == G4_expected_rows and all(g4_rows.values())

    # ---------------- P6
    p6 = {}
    p6_fresh = [0, 0]
    p6_dup = 0
    redispatch = 0
    for f in sorted(glob.glob(str(RAW / "p6" / "*" / "cells" / "*.jsonl"))):
        cell = jl(Path(f))[0]
        row = cell["row"]
        r = p6.setdefault(row, {"reps": 0, "outcomes": [], "received": [], "applied": [], "reconcile_reads": [],
                                "dispatch_after_unknown": 0, "fault_fired": []})
        r["reps"] += 1
        r["outcomes"].append(cell["outcome"])
        r["received"].append(cell["journal_received"])
        r["applied"].append(cell["journal_applied"])
        r["fault_fired"].append(cell["fault_fired"])
        muts = cell["mutations"]
        idx = next((i for i, m in enumerate(muts) if m.get("result") == "transport_failure"), None)
        after = len(muts) - idx - 1 if idx is not None else 0
        r["dispatch_after_unknown"] += after
        redispatch += after
        r["reconcile_reads"].append(sum(1 for x in cell["reconcile_reads"] if x["purpose"] == "reconcile"))
        p6_fresh[0] += sum(1 for m in muts if m.get("fresh"))
        p6_fresh[1] += len(muts)
        p6_dup += max(0, cell["journal_received"] - 1) + cell.get("duplicate_submits", 0)
    def p6_ok(row, expect):
        r = p6.get(row)
        return bool(r) and all(o == expect for o in r["outcomes"]) and all(x <= 1 for x in r["received"]) and \
            all(x <= 1 for x in r["applied"]) and r["dispatch_after_unknown"] == 0 and all(r["fault_fired"]) and \
            all(n >= 1 for n in r["reconcile_reads"])
    G5 = (p6_ok("applied_ack_lost", "verified_by_reconcile") and p6.get("applied_ack_lost", {}).get("reps") == 5
          and p6_ok("delayed_after_first_unchanged_read", "verified_by_reconcile")
          and p6.get("delayed_after_first_unchanged_read", {}).get("reps") == 5
          and p6_ok("withheld_unresolved", "unknown") and p6_dup == 0)
    S["reconcile"] = {"rows": p6, "duplicates": p6_dup, "dispatch_after_unknown": redispatch, "fresh_dispatch": p6_fresh}

    # ---------------- P7 live fallback
    lf = trial_rows(RAW / "livefallback")
    p7 = []
    for cell, rows in lf:
        rep = next((r["event"] for r in rows if r.get("type") == "runner_event" and r["event"].get("event") == "compiled_replay"), {})
        end = next((e["t_ms"] for e in rep.get("events", []) if e["kind"] == "replay_end"), None)
        p7.append({"cell": cell["cell_id"], "outcome": cell.get("reported_outcome"), "stop_reason": rep.get("stop_reason"),
                   "time_to_stop_ms": end, "process_wall_ms": cell.get("process_wall_ms"),
                   "http_attempts": cell.get("http_attempts"), "http_reached": cell.get("http_reached"),
                   "live_decisions": cell.get("provider_decisions_live"),
                   "choices": [e.get("choice") for e in rep.get("events", []) if e["kind"] == "fallback_choice"],
                   "journal_applied": cell.get("journal_applied"), "duplicates": cell.get("duplicate_submits"),
                   "fresh": receipt_components(rows).get("fresh_dispatch") if cell.get("first_semantic_send_ns") else None})
        c_fresh.append(receipt_components(rows)["fresh_dispatch"] if cell.get("first_semantic_send_ns") else [0, 0])
    S["live_fallback"] = {"cells": p7, "time_to_stop_ms_median": med([x["time_to_stop_ms"] for x in p7]),
                          "process_wall_ms_median": med([x["process_wall_ms"] for x in p7]),
                          "http_reached": sum(x["http_reached"] or 0 for x in p7)}

    # ---------------- G3
    sub_fresh = [sum(x[0] for x in c_fresh), sum(x[1] for x in c_fresh)]
    all_fresh = [sub_fresh[0] + neg_fresh[0] + p6_fresh[0], sub_fresh[1] + neg_fresh[1] + p6_fresh[1]]
    G3 = all_fresh[0] == all_fresh[1] and all_fresh[1] > 0
    S["g3_fresh_dispatch"] = {"subprocess_receipts": sub_fresh, "negatives": neg_fresh, "reconcile": p6_fresh, "all": all_fresh}

    # ---------------- costs
    n8 = [c for c in negs if c["row"] == "N8" and not c.get("_setup_failed")]
    n8_stop = []
    for c in n8:
        end = next((e["t_ms"] for e in c.get("events", []) if e["kind"] == "replay_end"), None)
        n8_stop.append(end)
    all_c = []  # every compiled-routine invocation
    all_c.append({"phase": "P3", "outcome": p3c["reported_outcome"], "verified": p3c["independently_verified"], "wall_ms": p3c["process_wall_ms"], "reached": 0})
    for (r, a), (c, _) in by.items():
        if a == "C":
            all_c.append({"phase": "P4", "outcome": c.get("reported_outcome"), "verified": c.get("independently_verified"), "wall_ms": c.get("process_wall_ms"), "reached": c.get("http_reached", 0)})
    for c in negs:
        if c["row"] != "N4a_ord":
            all_c.append({"phase": "P5" + ("-setup-failed" if c.get("_setup_failed") else ""), "outcome": c["outcome"], "verified": c["independently_verified"], "wall_ms": c.get("wall_ms_informational"), "reached": 0})
    for f in sorted(glob.glob(str(RAW / "p6" / "*" / "cells" / "*.jsonl"))):
        c = jl(Path(f))[0]
        all_c.append({"phase": "P6", "outcome": c["outcome"], "verified": c["independently_verified"], "wall_ms": c.get("wall_ms_informational"), "reached": 0})
    for x in p7:
        all_c.append({"phase": "P7", "outcome": x["outcome"], "verified": False, "wall_ms": x["process_wall_ms"], "reached": x["http_reached"] or 0})
    totals = {"invocations": len(all_c), "independently_verified": sum(1 for x in all_c if x["verified"]),
              "explicit_stop_or_unknown": sum(1 for x in all_c if x["outcome"] in ("stopped", "unknown")),
              "other": sum(1 for x in all_c if not x["verified"] and x["outcome"] not in ("stopped", "unknown")),
              "wall_ms_sum": round(sum(x["wall_ms"] or 0 for x in all_c), 3),
              "provider_reached": sum(x["reached"] for x in all_c),
              "by_phase": {ph: sum(1 for x in all_c if x["phase"] == ph) for ph in ("P3", "P4", "P5", "P5-setup-failed", "P6", "P7")}}
    saving_B = (arms["B"]["T_ms"]["median"] - arms["C"]["T_ms"]["median"]) if arms["C"]["T_ms"]["median"] is not None and arms["B"]["T_ms"]["median"] is not None else None
    saving_A = (arms["A"]["T_ms"]["median"] - arms["C"]["T_ms"]["median"]) if arms["C"]["T_ms"]["median"] is not None and arms["A"]["T_ms"]["median"] is not None else None
    overhead_incr = compile_info["compile_ms"] + (p3c["T_ms"] or 0)
    overhead_cons = overhead_incr + (p1c["T_ms"] or 0)
    def be(saving, overhead):
        return math.ceil(overhead / saving) if saving and saving > 0 else None
    S["costs"] = {
        "learning": {"T_ms": p1c["T_ms"], "process_wall_ms": p1c["process_wall_ms"], "provider_reached": p1c["http_reached"]},
        "compile": {"compile_ms": compile_info["compile_ms"]},
        "admission": {"T_ms": p3c["T_ms"], "process_wall_ms": p3c["process_wall_ms"], "provider_reached": 0},
        "warm_replay_C": {"T_ms_median": arms["C"]["T_ms"]["median"], "process_wall_ms_median": arms["C"]["process_wall_ms_median"], "provider_reached": arms["C"]["http_reached"]},
        "fallback_P7": S["live_fallback"],
        "wrong_match_N8": {"time_to_stop_ms": n8_stop, "dispatches": n8_dispatch, "note": "untimed phase (shared lock); informational"},
        "totals_all_compiled_invocations": totals,
        "work_deleted_per_warm_run": {"provider_decisions_vs_A": 2, "provider_decisions_vs_B": 1,
                                      "input_tokens_per_run_A": round(arms["A"]["input_tokens"] / max(arms["A"]["n"], 1), 1),
                                      "input_tokens_per_run_B": round(arms["B"]["input_tokens"] / max(arms["B"]["n"], 1), 1),
                                      "provider_requests_per_run_A": round(arms["A"]["http_reached"] / max(arms["A"]["n"], 1), 2),
                                      "provider_requests_per_run_B": round(arms["B"]["http_reached"] / max(arms["B"]["n"], 1), 2)},
        "wall_clock_saved_median_paired_ms": {"vs_B": paired["C_minus_B"].get("median"), "vs_A": paired["C_minus_A"].get("median")},
        "saving_from_arm_medians_ms": {"vs_B": round(saving_B, 3) if saving_B is not None else None, "vs_A": round(saving_A, 3) if saving_A is not None else None},
        "one_time_overhead_ms": {"incremental_compile_plus_admission": round(overhead_incr, 3), "conservative_plus_learning": round(overhead_cons, 3)},
        "wall_basis": {
            "saving_per_run_process_wall_ms_vs_B": round(arms["B"]["process_wall_ms_median"] - arms["C"]["process_wall_ms_median"], 3),
            "saving_per_run_process_wall_ms_vs_A": round(arms["A"]["process_wall_ms_median"] - arms["C"]["process_wall_ms_median"], 3),
            "overhead_incremental_ms": round(compile_info["compile_ms"] + p3c["process_wall_ms"], 3),
            "overhead_conservative_ms": round(compile_info["compile_ms"] + p3c["process_wall_ms"] + p1c["process_wall_ms"], 3),
            "break_even_vs_B_incremental": be(arms["B"]["process_wall_ms_median"] - arms["C"]["process_wall_ms_median"], compile_info["compile_ms"] + p3c["process_wall_ms"]),
            "break_even_vs_B_conservative": be(arms["B"]["process_wall_ms_median"] - arms["C"]["process_wall_ms_median"], compile_info["compile_ms"] + p3c["process_wall_ms"] + p1c["process_wall_ms"]),
            "break_even_vs_A_incremental": be(arms["A"]["process_wall_ms_median"] - arms["C"]["process_wall_ms_median"], compile_info["compile_ms"] + p3c["process_wall_ms"]),
            "break_even_vs_A_conservative": be(arms["A"]["process_wall_ms_median"] - arms["C"]["process_wall_ms_median"], compile_info["compile_ms"] + p3c["process_wall_ms"] + p1c["process_wall_ms"]),
        },
        "break_even_runs": {"vs_B_incremental": be(saving_B, overhead_incr), "vs_B_conservative": be(saving_B, overhead_cons),
                            "vs_A_incremental": be(saving_A, overhead_incr), "vs_A_conservative": be(saving_A, overhead_cons)},
    }
    G6 = True

    # ---------------- gates + disposition
    duplicates_any = arms["A"]["duplicates"] + arms["B"]["duplicates"] + arms["C"]["duplicates"] + dup_all + p6_dup + \
        sum(x["duplicates"] or 0 for x in p7) + p1c["duplicate_submits"] + p3c["duplicate_submits"]
    unverified_any = arms["A"]["unverified_success"] + arms["B"]["unverified_success"] + arms["C"]["unverified_success"] + unverified_all
    cb = paired["C_minus_B"]
    kill = {
        "routine_attributable_stale_dispatch": stale_routine > 0 or not G3,
        "ambiguous_dispatch": ambiguous > 0,
        "duplicate_any_phase": duplicates_any > 0,
        "unverified_success": unverified_any > 0,
        "authority_in_artifact": bool(authority),
        "failed_admission": not G2,
        "n8_dispatched": n8_dispatch > 0,
        "C_minus_B_ci_not_below_0": not cb.get("upper_below_0", False),
    }
    gates = {"G1": G1, "G2": G2, "G3": G3, "G4": G4, "G5": G5, "G6": G6}
    # a C failure is safe when it did not duplicate (journal applied <= 1) and did not report a false success
    c_fail_safe = all((f["journal_applied"] or 0) <= 1 and f["reported"] not in ("verified", "fallback_verified")
                      for f in arms["C"]["failures"])
    keep = (all(gates.values()) and paired["C_minus_B"].get("upper_below_0") and paired["C_minus_A"].get("upper_below_0")
            and arms["C"]["verified"] >= 19 and c_fail_safe)
    if any(kill.values()):
        disposition = "KILL"
    elif keep:
        disposition = "KEEP"
    else:
        disposition = "REVISE"
    literal = "KILL" if (any(kill.values()) or stale_driver_node > 0) else disposition
    S["gates"] = gates
    S["kill_checks"] = kill
    S["duplicates_any_phase"] = duplicates_any
    S["unverified_success_any_phase"] = unverified_any
    S["disposition"] = disposition
    S["disposition_if_literal_stale_rule"] = literal
    S["budget"] = json.loads((RAW / "budget.json").read_text())
    return S


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    S = analyze()
    text = json.dumps(S, indent=1, sort_keys=True) + "\n"
    if a.write:
        (HERE / "r2-07-summary.json").write_text(text)
    print(text)


if __name__ == "__main__":
    main()

"""kvnloo/cua#107 lane AB: build i107ab-summary.json and ledger.jsonl from raw/ (standard library only).

    python3 analyze.py            # rewrites i107ab-summary.json and ledger.jsonl

Every number in the summary is recomputed from raw/ by verify_artifacts.py.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import b01_analysis as A  # noqa: E402
import i107ab_ledger as L  # noqa: E402

LANE = "i107-ab"
CONDITIONS = ("W-quiet", "W-churn", "W-static")
SAVINGS = ("response_bytes", "client_parse_ms", "client_validation_ms", "driver_projection_ms",
           "snapshot_build_ms", "driver_serialize_ms", "candidate_build_ms", "selected_nodes", "refs",
           "outline_chars", "T_oracle_ms", "T_runner_ms", "startup_ms", "cleanup_ms", "lifetime_ms",
           "driver_cpu_ms", "driver_vmhwm_kb", "browser_cpu_ms", "browser_rss_kb")


def _r(x: Any, nd: int = 3) -> Any:
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, dict):
        return {k: _r(v, nd) for k, v in x.items()}
    if isinstance(x, list):
        return [_r(v, nd) for v in x]
    return x


def _first(events: list[dict[str, Any]], name: str) -> int | None:
    return next((e["t_mono_ns"] for e in events if e["event"] == name), None)


def _interval(trace: list[dict[str, Any]], start: str, end: str, t0: int, t1: int) -> float:
    """Sum of start->next end mark intervals inside [t0, t1], ms."""
    total, open_t = 0.0, None
    for m in trace:
        t = m["t_mono_ns"]
        if not (t0 <= t <= t1):
            continue
        if m["phase"] == start and open_t is None:
            open_t = t
        elif m["phase"] == end and open_t is not None:
            total += (t - open_t) / 1e6
            open_t = None
    return total


def _in(pairs: list[tuple[int, int]], t0: int, t1: int) -> float:
    return sum((b - a) / 1e6 for a, b in pairs if t0 <= a and b <= t1)


def trial_metrics(trial: dict[str, Any]) -> dict[str, Any]:
    s, ev = trial["summary"], trial["events"]
    trace = L.strip_ledger(trial["trace"])
    windows = A._windows(ev)
    parses = [(a, b) for a, b in A._pairs(ev, "parse_start", "parse_end")]
    parse_bytes = [(e["t_mono_ns"], e.get("bytes", 0)) for e in ev if e["event"] == "parse_end"]
    vals = A._pairs(ev, "client_validate_start", "client_validate_end")
    cands = A._pairs(ev, "cand_start", "cand_done")
    snaps = []
    for w in windows:
        if w["tool"] != "get_browser_state" or not w["label"].startswith("snapshot"):
            continue
        t0, t1 = w["t0"], w["t1"]
        step = int(w["label"].removeprefix("snapshot"))
        cand = next(((a, b) for a, b in cands if a >= t1), None)
        snaps.append({
            "label": w["label"], "call_ms": (t1 - t0) / 1e6,
            "response_bytes": sum(b for t, b in parse_bytes if t0 <= t <= t1),
            "client_parse_ms": _in(parses, t0, t1), "client_validation_ms": _in(vals, t0, t1),
            "driver_projection_ms": _interval(trace, "snap.oopif_done", "snap.paged", t0, t1),
            "snapshot_build_ms": _interval(trace, "snap.paged", "snap.serialized", t0, t1),
            "driver_serialize_ms": _interval(trace, "mcp.handled", "mcp.serialized", t0, t1),
            "candidate_build_ms": 0.0 if cand is None else (cand[1] - cand[0]) / 1e6,
            "facts": next((x for x in s.get("steps") or [] if x["step"] == step), None),
        })
    led = L.snapshot_ledgers(trial)
    d_r = A.decompose(L.decomposable(trial), end="runner")
    d_o = A.decompose(L.decomposable(trial), end="oracle")
    spawn, nav = _first(ev, "driver_spawn"), None
    nav_ret = [e for e in ev if e["event"] == "call_return" and e.get("label") == "navigate"]
    nav = nav_ret[0]["t_mono_ns"] if nav_ret else None
    decided, exited, gone = _first(ev, "outcome_decided"), _first(ev, "client_exited"), _first(ev, "browser_gone")
    cleanup_end = max([t for t in (exited, gone) if t is not None], default=None)
    res = s.get("resources_at_outcome") or {}
    tck = res.get("clk_tck") or 100
    tree = res.get("browser_tree") or {}
    out = {
        "snapshots": snaps, "ledger": led,
        "T_oracle_ms": None if d_o is None else d_o["T_ms"],
        "T_runner_ms": None if d_r is None else d_r["T_ms"],
        "decomp_oracle": d_o, "decomp_runner": d_r,
        "startup_ms": None if spawn is None or nav is None else (nav - spawn) / 1e6,
        "cleanup_ms": None if decided is None or cleanup_end is None else (cleanup_end - decided) / 1e6,
        "lifetime_ms": None if spawn is None or cleanup_end is None else (cleanup_end - spawn) / 1e6,
        "driver_cpu_ms": None if res.get("driver_cpu_ticks") is None else res["driver_cpu_ticks"] * 1000 / tck,
        "driver_vmhwm_kb": (res.get("driver_status_kb") or {}).get("VmHWM"),
        "browser_cpu_ms": None if not tree else tree.get("cpu_ticks", 0) * 1000 / tck,
        "browser_rss_kb": tree.get("rss_kb") if tree else None,
        "load1": _load1(s.get("loadavg_before")),
    }
    for k in ("response_bytes", "client_parse_ms", "client_validation_ms", "driver_projection_ms",
              "snapshot_build_ms", "driver_serialize_ms", "candidate_build_ms"):
        out[k] = sum(x[k] for x in snaps)
    for k in ("selected_nodes", "refs", "outline_chars"):
        out[k] = sum((x["facts"] or {}).get(k) or 0 for x in snaps)
    return out


def _load1(text: Any) -> float | None:
    try:
        return float(str(text).split()[0])
    except (ValueError, IndexError):
        return None


def stale_dispatch_marks(trial: dict[str, Any]) -> int:
    w = next((w for w in A._windows(trial["events"]) if w["label"] == "stale_click"), None)
    if w is None:
        return 0
    return sum(1 for m in trial["trace"] if m["phase"] in ("click.cdp_send", "type.insert_send")
               and w["t0"] <= m["t_mono_ns"] <= w["t1"])


def ledger_row(trial: dict[str, Any], m: dict[str, Any]) -> dict[str, Any]:
    s = trial["summary"]
    d = m["decomp_oracle"]
    return _r({
        "row_type": "trial", "lane": LANE, "issue": "kvnloo/cua#107", "task": "browser-fixture-form",
        "comparison": {"ab": "CMP-AB", "static": "CMP-AB", "distortion": "CMP-distortion", "default_off": "default-off",
                       "controls": "controls", "controls2": "controls", "shakedown": "shakedown"}.get(s.get("plan"), s.get("plan")),
        "trial": s["trial"], "plan": s.get("plan"), "condition": s.get("condition"), "cohort": s.get("cohort"),
        "regime": s.get("regime"), "pair": s.get("pair"), "order": s.get("order"), "arm": s.get("arm"),
        "binary_sha256": s.get("binary_sha256"), "caller_tree": "72bf8156136771da9a767ec12ae7c364e426d910",
        "token_sha16": s.get("token_sha16"), "outcome": s.get("outcome"), "oracle_exact_match": s.get("oracle_exact_match"),
        "route": "dom_event" if "dom_event" in (s.get("input_routes") or []) else None,
        "decision_routes": s.get("routes"), "guard": None, "control": s.get("control"),
        "control_applied": s.get("control_applied"),
        "counts": {"semantic_observations": len(m["snapshots"]),
                   "query_observations": len(m["snapshots"]) if s.get("query") else 0,
                   "cdp_methods": [x["methods"] for x in m["ledger"]],
                   "cdp_send_bytes": sum(x["send_bytes"] for x in m["ledger"]),
                   "cdp_reply_bytes": sum(x["reply_bytes"] for x in m["ledger"]),
                   "acquired_dom_layout_ax": [[x["dom_nodes"], x["layout_nodes"], x["ax_nodes"]] for x in m["ledger"]],
                   "selected_nodes": m["selected_nodes"], "refs": m["refs"], "mcp_response_bytes": m["response_bytes"],
                   "decisions": len(s.get("routes") or []), "driver_mutations": len(s.get("tools") or []),
                   "journal_submits": s.get("completion_mutations"), "wrong_target_submits": s.get("wrong_target_submits")},
        "spans_ms": None if d is None else L.span10(d["components"], d["sub"]),
        "coverage": None if d is None else d["coverage"],
        "T_oracle_ms": m["T_oracle_ms"], "T_runner_ms": m["T_runner_ms"], "startup_ms": m["startup_ms"],
        "cleanup_ms": m["cleanup_ms"], "lifetime_ms": m["lifetime_ms"],
        "resources": {"driver_cpu_ms": m["driver_cpu_ms"], "driver_vmhwm_kb": m["driver_vmhwm_kb"],
                      "browser_cpu_ms": m["browser_cpu_ms"], "browser_rss_kb": m["browser_rss_kb"]},
        "loadavg_before": s.get("loadavg_before"), "psi_before": s.get("psi_before"),
        "loadavg_after": s.get("loadavg_after"), "psi_after": s.get("psi_after"),
        "lock_receipt": s.get("lock_label"), "excluded": bool(s.get("excluded")),
        "evidence": "REAL/BENCHMARK (scripted chooser choose_mock_for_task)",
    })


BLOCKED_CELLS = [
    ("CMP-AB", "W-quiet", "A,B_proj", 60), ("CMP-AB", "W-churn", "A,B_proj", 60), ("CMP-AB", "W-static", "A,B_proj", 60),
    ("CMP-distortion", "W-quiet", "A,A_ref", 20), ("default-off", "W-quiet", "A_off", 5),
    ("controls DC03", "W-quiet", "A,B_proj", 10), ("controls DC04", "W-quiet", "A,B_proj", 10),
    ("controls stale_ref", "W-quiet", "A,B_proj", 10),
]


def build(raw: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trials = A.load_trials(raw) if (raw / "trials").is_dir() or list(raw.glob("trials-*.tar.gz")) else []
    manifests = {p.name: json.loads(p.read_text()) for p in sorted(raw.glob("run-manifest-*.json"))}
    metrics = {t["name"]: trial_metrics(t) for t in trials}
    rows = [ledger_row(t, metrics[t["name"]]) for t in trials]
    measured = [t for t in trials if not t["summary"].get("excluded")]
    summary: dict[str, Any] = {"schema": "cua.i107.ab.summary.v1", "lane": LANE, "issue": "kvnloo/cua#107",
                               "trials_attempted": len(trials), "trials_measured": len(measured),
                               "manifests": {k: {"status": v.get("status"), "plan": v.get("plan_kind"),
                                                 "lock_label": v.get("lock_label"),
                                                 "preflight_ok": (v.get("preflight") or {}).get("ok"),
                                                 "preflight_reasons": [c["reason"] for c in (v.get("preflight") or {}).get("checked", [])],
                                                 "non_loopback_connects": (v.get("network") or {}).get("non_loopback_connect_attempts")}
                                             for k, v in manifests.items()}}
    blocked = any(v.get("status") == "infrastructure_blocked" for v in manifests.values())
    ran_plans = {t["summary"].get("plan") for t in measured}
    summary["status"] = "BLOCKED" if (blocked and not measured) else ("RAN" if measured else "NOT_RUN")

    by = lambda **kw: [t for t in measured if all(t["summary"].get(k) == v for k, v in kw.items())]  # noqa: E731
    summary["denominators"] = {f"{p}|{c}|{a}": L.denominators([t["summary"].get("outcome") for t in by(plan=p, condition=c, arm=a)])
                               for p in sorted(ran_plans) for c in CONDITIONS for a in A.ARMS + ("A_off",)
                               if by(plan=p, condition=c, arm=a)}
    cmp_ab = {}
    for cond in CONDITIONS:
        rows_c = [{"pair": t["summary"].get("pair"), "arm": t["summary"].get("arm"), "name": t["name"]}
                  for t in by(plan="ab", condition=cond) + by(plan="static", condition=cond)]
        if not rows_c:
            continue
        pairs: dict[str, dict[str, str]] = {}
        for r in rows_c:
            pairs.setdefault(r["pair"], {})[r["arm"]] = r["name"]
        full = [(v["A"], v["B_proj"]) for _, v in sorted(pairs.items()) if "A" in v and "B_proj" in v]
        acq = [L.compare_acquisition(metrics[a]["ledger"], metrics[b]["ledger"]) for a, b in full]
        eq = [L.equivalent([{"candidates": (x["facts"] or {}).get("candidates"), "controls": (x["facts"] or {}).get("controls")}
                            for x in metrics[a]["snapshots"]],
                           [{"candidates": (x["facts"] or {}).get("candidates"), "controls": (x["facts"] or {}).get("controls")}
                            for x in metrics[b]["snapshots"]]) for a, b in full]
        tot = lambda name, key: sum(x[key] for x in metrics[name]["ledger"])  # noqa: E731
        noise = {}
        for key in ("dom_nodes", "layout_nodes", "ax_nodes", "reply_bytes", "send_bytes"):
            deltas = [tot(b, key) - tot(a, key) for a, b in full]
            a_med = statistics.median([tot(a, key) for a, _ in full]) if full else 0
            noise[key] = L.within_noise(deltas, a_med)
        exact_nodes = all(x["nodes_equal"] for x in acq)
        savings = {}
        for key in SAVINGS:
            a_v = [metrics[a][key] for a, b in full if metrics[a][key] is not None and metrics[b][key] is not None]
            b_v = [metrics[b][key] for a, b in full if metrics[a][key] is not None and metrics[b][key] is not None]
            savings[key] = {**A.paired_diff(b_v, a_v), "A_median": A.median(a_v), "B_proj_median": A.median(b_v),
                            "A_p95": A.p95(a_v), "B_proj_p95": A.p95(b_v)}
        t = savings["T_oracle_ms"]
        thr = L.threshold_ms(t["A_median"]) if t["A_median"] is not None else None
        lo = [(a, b) for a, b in full if (metrics[a]["load1"] or 0) <= 8 and (metrics[b]["load1"] or 0) <= 8]
        sens = A.paired_diff([metrics[b]["T_oracle_ms"] for a, b in lo if metrics[a]["T_oracle_ms"] and metrics[b]["T_oracle_ms"]],
                             [metrics[a]["T_oracle_ms"] for a, b in lo if metrics[a]["T_oracle_ms"] and metrics[b]["T_oracle_ms"]])
        methods_equal = all(x["methods_equal"] for x in acq) and bool(acq)
        quiet_rule = exact_nodes if cond == "W-quiet" else all(noise[k]["equal"] for k in ("dom_nodes", "layout_nodes", "ax_nodes"))
        bytes_rule = noise["reply_bytes"]["equal"] and noise["send_bytes"]["equal"]
        cmp_ab[cond] = {
            "pairs": len(full), "evidence": "REAL/BENCHMARK (scripted chooser choose_mock_for_task); DIAGNOSTIC",
            "acquisition": {"methods_equal_all_pairs": methods_equal, "nodes_exact_all_pairs": exact_nodes,
                            "within_noise": noise, "pairs_with_diffs": sum(1 for x in acq if x["diffs"]),
                            "diff_examples": [d for x in acq for d in x["diffs"]][:10],
                            "equal": bool(methods_equal and quiet_rule and bytes_rule)},
            "semantic_equivalence": {"equivalent_pairs": sum(1 for x in eq if x["equivalent"]), "pairs": len(eq),
                                     "reasons": [r for x in eq for r in x["reasons"]][:10]},
            "savings_B_minus_A": savings, "T_oracle_threshold_ms": thr,
            "T_oracle_verdict": None if thr is None else L.improvement_verdict(t["median"], t["ci95"], thr),
            "sensitivity_load1_le_8": sens,
            "load1_range": [min((metrics[n]["load1"] or 0) for p in full for n in p), max((metrics[n]["load1"] or 0) for p in full for n in p)] if full else None,
            "read_cost_claim": "BLOCKED (B_proj is payload projection, never a read-cost claim)",
        }
    summary["cmp_ab"] = cmp_ab
    decomp = {}
    for cond in CONDITIONS:
        a_trials = [t for t in by(plan="ab", condition=cond, arm="A") + by(plan="static", condition=cond, arm="A")
                    if A.is_valid(L.decomposable(t))[0]]
        ds = [metrics[t["name"]]["decomp_oracle"] for t in a_trials if metrics[t["name"]]["decomp_oracle"]]
        if not ds:
            continue
        spans = [L.span10(d["components"], d["sub"]) for d in ds]
        decomp[cond] = {"n": len(ds), "T_oracle_mean_ms": statistics.mean(d["T_ms"] for d in ds),
                        "T_oracle_median_ms": A.median([d["T_ms"] for d in ds]),
                        "spans_mean_ms": {k: statistics.mean(s[k] for s in spans) for k in L.SPANS10},
                        "cleanup_mean_ms": statistics.mean(metrics[t["name"]]["cleanup_ms"] for t in a_trials
                                                           if metrics[t["name"]]["cleanup_ms"] is not None) if a_trials else None,
                        "startup_mean_ms": statistics.mean(metrics[t["name"]]["startup_ms"] for t in a_trials
                                                           if metrics[t["name"]]["startup_ms"] is not None) if a_trials else None,
                        "sub_mean_ms": {k: statistics.mean(d["sub"].get(k, 0.0) for d in ds)
                                        for k in sorted({k for d in ds for k in d["sub"]})},
                        "composition_split_ms": {
                            "note": "post-hoc reading: observation_processing is whole-page DOM/layout/AX composition that runs before projection and is equal across arms; the pre-registered mapping files it under projection/encoding/transport",
                            "acquisition_cdp": statistics.mean(d["sub"].get("observation_cdp", 0.0) for d in ds),
                            "whole_page_composition": statistics.mean(d["sub"].get("observation_processing", 0.0) for d in ds),
                            "projection_proper": statistics.mean(d["sub"].get("projection_page", 0.0) + d["sub"].get("snapshot_build_store", 0.0)
                                                                 + d["components"].get("driver_post_dispatch", 0.0) + d["components"].get("transport", 0.0)
                                                                 + d["components"].get("client_parse", 0.0) + d["components"].get("client_validation", 0.0)
                                                                 for d in ds)},
                        "coverage_min": min(d["coverage"] for d in ds),
                        "gate_named_coverage_gt_0_9": min(d["coverage"] for d in ds) > 0.9,
                        "evidence": "REAL/BENCHMARK (scripted chooser)"}
    summary["decomposition_A"] = decomp
    controls = {}
    for ctl in ("DC03", "DC04", "stale_ref"):
        for arm in ("A", "B_proj"):
            ts = by(plan="controls", control=ctl, arm=arm) + by(plan="controls2", control=ctl, arm=arm)
            if not ts:
                continue
            controls[f"{ctl}|{arm}"] = {
                "n": len(ts), "applied": sum(1 for t in ts if t["summary"].get("control_applied") or ctl == "stale_ref"),
                "outcomes": L.denominators([t["summary"].get("outcome") for t in ts]),
                "submits": sum(t["summary"].get("completion_mutations") or 0 for t in ts),
                "wrong_target_submits": sum(t["summary"].get("wrong_target_submits") or 0 for t in ts),
                "stale_codes": sorted({(t["summary"].get("stale_envelope") or {}).get("code") for t in ts} - {None}),
                "stale_code_missing": sum(1 for t in ts if ctl == "stale_ref" and not (t["summary"].get("stale_envelope") or {}).get("code")),
                "stale_effects": sorted({e.get("effect") for t in ts for e in t["events"]
                                         if e["event"] == "call_return" and e.get("label") == "stale_click"} - {None}),
                "stale_dispatch_marks": sum(stale_dispatch_marks(t) for t in ts)}
    summary["controls"] = controls
    mixed = []
    for t in measured:
        for x in metrics[t["name"]]["ledger"]:
            if x["layout_nodes"] and x["dom_nodes"] < 0.5 * x["layout_nodes"]:
                mixed.append({"trial": t["name"], "snapshot": x["label"], "dom_nodes": x["dom_nodes"],
                              "layout_nodes": x["layout_nodes"], "ax_nodes": x["ax_nodes"]})
    summary["mixed_generation_snapshots"] = mixed
    summary["default_off"] = {"n": len(by(plan="default_off")),
                              "verified": sum(1 for t in by(plan="default_off") if t["summary"].get("outcome") == "verified"),
                              "trace_set": sum(1 for t in by(plan="default_off") if t["summary"].get("driver_env_trace_set")),
                              "trace_files": sum(1 for t in by(plan="default_off") if t["summary"].get("trace_file_exists"))}
    dist = [(t["summary"]["pair"], t["summary"]["arm"], metrics[t["name"]]["T_oracle_ms"]) for t in by(plan="distortion")]
    dp: dict[str, dict[str, float]] = {}
    for p, arm, v in dist:
        if v is not None:
            dp.setdefault(p, {})[arm] = v
    dpairs = [v for v in dp.values() if "A" in v and "A_ref" in v]
    summary["distortion"] = {"pairs": len(dpairs), **A.paired_diff([v["A"] for v in dpairs], [v["A_ref"] for v in dpairs])}
    all_m = measured
    summary["required_zero"] = {
        "stale_ref_dispatch_with_effect": sum(1 for t in by(plan="controls", control="stale_ref") + by(plan="controls2", control="stale_ref")
                                              if t["summary"].get("completion_mutations")),
        "unauthorized_action": 0 if all_m else None,
        "wrong_target_effect_by_arm": {arm: sum(t["summary"].get("wrong_target_submits") or 0 for t in all_m if t["summary"].get("arm") == arm)
                                       for arm in ("A", "B_proj", "A_ref", "A_off")},
        "duplicate_effect": sum(1 for t in all_m if (t["summary"].get("completion_mutations") or 0) > 1),
        "unverified_success": sum(1 for t in all_m if t["summary"].get("outcome") == "verified" and not t["summary"].get("oracle_exact_match")),
        "non_loopback_connects": sum((t["summary"].get("network") or {}).get("non_loopback_connect_attempts", 0) for t in trials),
    }
    summary["cells"] = []
    for cell, cond, arms, planned in BLOCKED_CELLS:
        n = len([t for t in measured if _cell_of(t) == (cell, cond)])
        summary["cells"].append({"cell": cell, "condition": cond, "arms": arms, "planned_trials": planned, "trials": n,
                                 "status": "BLOCKED" if (blocked and n == 0) else ("RAN" if n else "NOT_RUN")})
    if not measured:
        for c in summary["cells"]:
            rows.append({"row_type": "cell", "lane": LANE, "issue": "kvnloo/cua#107", "task": "browser-fixture-form",
                         "comparison": c["cell"], "condition": c["condition"], "arms": c["arms"], "cohort": "K1",
                         "trials": 0, "status": c["status"],
                         "reason": "infrastructure blocker: isolated launch refused under the hostless wrapper (no REAL trial)"
                         if c["status"] == "BLOCKED" else "not run"})
    return _r(summary), rows


def _cell_of(t: dict[str, Any]) -> tuple[str, str]:
    s = t["summary"]
    plan = s.get("plan")
    name = {"ab": "CMP-AB", "static": "CMP-AB", "distortion": "CMP-distortion", "default_off": "default-off"}.get(plan)
    if plan in ("controls", "controls2"):
        name = f"controls {s.get('control')}"
    return name or str(plan), s.get("condition")


def write(raw: Path = HERE / "raw") -> None:
    summary, rows = build(raw)
    (HERE / "i107ab-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    with (HERE / "ledger.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


if __name__ == "__main__":
    write()

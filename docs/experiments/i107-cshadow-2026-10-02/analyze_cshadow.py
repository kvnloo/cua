"""Analysis for kvnloo/cua#107 lane CSHADOW. Pure standard library.

Usage: python3 analyze_cshadow.py <packet-dir>

Reads the measured trials from <packet>/raw/trials-measured.tar.gz (or, if
absent, <packet>/raw/trials/), each a caller-event file *.jsonl (summary line
last) plus the matching Driver phase trace *.driver-trace.jsonl, together with
raw/admissibility.json, and writes <packet>/raw/ledger.jsonl (#10 task x arm x
trial format) and <packet>/cshadow-summary.json.

Statistics follow the map PREREG (lane PREREG + PREREG_AMENDMENT_1 add only
the refinements they list): paired delta = C_shadow_M - A, median, seeded
percentile bootstrap (10000 resamples, seed 20261002), threshold max(5 ms, 5% of
A's median T_oracle), resource budget, continuation rule, sensitivity excluding
pairs with 1-min loadavg > 8. A cell with no trials is BLOCKED, never zero-filled.
"""

from __future__ import annotations

import io
import json
import random
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SEED = 20261002
RESAMPLES = 10000
BUDGET = {
    "idle_driver_cpu_s": {"W-idle-quiet": 0.2, "W-idle-churn": 1.0},
    "idle_browser_cpu_s": {"W-idle-quiet": 1.0, "W-idle-churn": 2.0},
    "driver_vmhwm_mib": 32.0,
    "browser_rss_mib": 64.0,
}
PRIMARY = {"CMP-C-overhead": ["W-quiet", "W-churn"], "CMP-C-idle": ["W-idle-quiet", "W-idle-churn"]}
FIDELITY_CONDITIONS = ["W-quiet", "W-churn"]
CONTROL_IDS = ["DC01", "DC02", "DC03", "DC04", "DC05a", "DC07", "DC10", "DC11", "DC12", "DC13", "DC14a",
               "DC14b", "DC15", "DC16a", "DC16b", "DC17a", "DC17b", "DC18", "DC19a", "DC19b"]
# PREREG_AMENDMENT_1: controls whose safe outcome is "no submit" (the target is gone, hidden,
# covered, disabled or renamed); every other control may verify or refuse, never mis-submit.
NO_SUBMIT_EXPECTED = {"DC04", "DC12", "DC14a", "DC16a", "DC16b", "DC17b"}
MIRROR_ONLY_METHODS = ("Page.enable", "Inspector.enable", "DOM.requestChildNodes", "Target.detachFromTarget")
REF_SHA = "f3a5c01a2c1b5bce75ccb611d0bacd491a7c3b1a8c3fac65889a1fc9d6977aed"  # map binary cua-driver-i107-092b065d5


# ── loading ─────────────────────────────────────────────────────────────────────

def parse_jsonl(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def read_trial_files(raw: Path) -> dict[str, str]:
    archive = raw / "trials-measured.tar.gz"
    files: dict[str, str] = {}
    if archive.exists():
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith(".jsonl"):
                    files[Path(member.name).name] = tar.extractfile(member).read().decode()
    elif (raw / "trials").is_dir():
        for path in (raw / "trials").glob("*.jsonl"):
            files[path.name] = path.read_text()
    return files


def load_trials(raw: Path) -> list[dict[str, Any]]:
    files = read_trial_files(raw)
    trials = []
    for name in sorted(files):
        if name.endswith(".driver-trace.jsonl"):
            continue
        rows = parse_jsonl(files[name])
        if not rows or rows[-1].get("event") != "summary":
            continue
        summary = rows[-1]
        summary["_events"] = rows[:-1]
        summary["_trace"] = parse_jsonl(files.get(name.replace(".jsonl", ".driver-trace.jsonl"), ""))
        trials.append(summary)
    return trials


# ── statistics ──────────────────────────────────────────────────────────────────

def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def p95(xs: list[float]) -> float | None:
    if not xs:
        return None
    ordered = sorted(xs)
    return ordered[max(0, -(-95 * len(ordered) // 100) - 1)]


def bootstrap_ci(xs: list[float]) -> list[float] | None:
    if len(xs) < 2:
        return None
    rng = random.Random(SEED)
    meds = sorted(statistics.median(rng.choices(xs, k=len(xs))) for _ in range(RESAMPLES))
    return [meds[int(0.025 * RESAMPLES)], meds[int(0.975 * RESAMPLES) - 1]]


def r3(x: float | None) -> float | None:
    return None if x is None else round(x, 3)


# ── per-trial measures ──────────────────────────────────────────────────────────

def first_event(trial: dict[str, Any], **match: Any) -> dict[str, Any] | None:
    return next((e for e in trial["_events"] if all(e.get(k) == v for k, v in match.items())), None)


def t_oracle_ms(trial: dict[str, Any]) -> float | None:
    send = first_event(trial, event="call_send", label="snapshot1")
    ok = trial.get("poller_first_ok_ns")
    return None if send is None or ok is None else (ok - send["t_mono_ns"]) / 1e6


def t_runner_ms(trial: dict[str, Any]) -> float | None:
    send = first_event(trial, event="call_send", label="snapshot1")
    done = first_event(trial, event="oracle_return", outcome="verified")
    return None if send is None or done is None else (done["t_mono_ns"] - send["t_mono_ns"]) / 1e6


def cold_startup_ms(trial: dict[str, Any]) -> float | None:
    start, nav = first_event(trial, event="trial_start"), first_event(trial, event="navigate_done")
    return None if start is None or nav is None else (nav["t_mono_ns"] - start["t_mono_ns"]) / 1e6


def caller_spans(trial: dict[str, Any]) -> dict[str, Any] | None:
    """Sequential caller spans inside [snapshot1 send, poller first ok]; no nesting, no overlap."""
    t0e = first_event(trial, event="call_send", label="snapshot1")
    t1 = trial.get("poller_first_ok_ns")
    if t0e is None or t1 is None:
        return None
    t0 = t0e["t_mono_ns"]
    spans: Counter = Counter()
    open_: dict[str, tuple[str, int]] = {}
    pairs = {"call_send": "call_return", "oracle_send": "oracle_return", "cand_start": "cand_done",
             "decide_start": "decided", "sleep_start": "sleep_end", "op_send": "op_ack"}
    for e in trial["_events"]:
        ev, t = e.get("event"), e["t_mono_ns"]
        if ev in pairs:
            name = {"call_send": f"call:{e.get('tool')}", "oracle_send": "oracle_read", "cand_start": "candidates",
                    "decide_start": "decide", "sleep_start": "poll_sleep", "op_send": "control_op"}[ev]
            open_[pairs[ev]] = (name, t)
        elif ev in open_:
            name, ts = open_.pop(ev)
            lo, hi = max(ts, t0), min(t, t1)
            if hi > lo:
                spans[name] += hi - lo
    total = t1 - t0
    named = sum(spans.values())
    return {"named_share": named / total if total > 0 else None,
            "ms": {k: round(v / 1e6, 3) for k, v in sorted(spans.items())}}


def ledger_counts(trial: dict[str, Any]) -> dict[str, Any]:
    trace = trial["_trace"]
    sends = Counter(m["detail"]["method"] for m in trace if m.get("phase") == "cdp.send" and isinstance(m.get("detail"), dict))
    events = Counter(m["detail"]["method"] for m in trace if m.get("phase") == "cdp.event" and isinstance(m.get("detail"), dict))
    mirror_marks = Counter(m["phase"] for m in trace if str(m.get("phase", "")).startswith("i107.mirror."))
    return {
        "cdp_sends_by_method": dict(sorted(sends.items())), "cdp_events_total": sum(events.values()),
        "cdp_events_by_method": dict(sorted(events.items())),
        "cdp_send_bytes": sum(m["detail"].get("bytes", 0) for m in trace if m.get("phase") == "cdp.send"),
        "cdp_reply_bytes": sum(m["detail"].get("bytes", 0) for m in trace if m.get("phase") == "cdp.reply"),
        "attach_calls": sends.get("Target.attachToTarget", 0), "detach_calls": sends.get("Target.detachFromTarget", 0),
        "mirror_only_sends": sum(sends.get(m, 0) for m in MIRROR_ONLY_METHODS),
        "mirror_marks": dict(sorted(mirror_marks.items())),
        "semantic_snapshots": sum(1 for e in trial["_events"] if e.get("event") == "call_send"
                                  and str(e.get("label", "")).startswith(("snapshot", "idle_snapshot"))),
        "decisions": sum(1 for e in trial["_events"] if e.get("event") == "decided"),
        "driver_mutations": sum(1 for e in trial["_events"] if e.get("event") == "call_send"
                                and e.get("tool") in ("browser_type", "browser_click")),
        "polls": sum(1 for e in trial["_events"] if e.get("event") == "sleep_start"),
        "screenshots": sum(1 for e in trial["_events"] if e.get("event") == "call_send" and e.get("tool") == "screenshot"),
    }


def mirror_stats(trial: dict[str, Any]) -> dict[str, Any] | None:
    marks = [m for m in trial["_trace"] if m.get("phase") == "i107.mirror.stats"]
    return marks[-1]["detail"] if marks else None


def mirror_bootstraps(trial: dict[str, Any]) -> list[dict[str, Any]]:
    return [m["detail"] for m in trial["_trace"] if m.get("phase") == "i107.mirror.bootstrap"]


def audits(trial: dict[str, Any]) -> list[dict[str, Any]]:
    return [m["detail"] for m in trial["_trace"] if m.get("phase") == "i107.mirror.audit"]


def lags_ms(trial: dict[str, Any]) -> list[dict[str, float]]:
    applied = {m["detail"]["op"]: m["t_mono_ns"] for m in trial["_trace"]
               if m.get("phase") == "i107.mirror.op_applied" and isinstance(m.get("detail"), dict)}
    out = []
    for e in trial.get("journal", []):
        if e.get("event") == "ack" and e.get("id") in applied:
            row = {"vs_ack_receipt_ms": round((applied[e["id"]] - e["t_mono_ns"]) / 1e6, 3)}
            if e.get("applied_mono_ns_mapped"):
                row["vs_page_mutation_ms"] = round((applied[e["id"]] - e["applied_mono_ns_mapped"]) / 1e6, 3)
            out.append(row)
    return out


def idle_events_per_s(trial: dict[str, Any]) -> float | None:
    s, e = first_event(trial, event="idle_start"), first_event(trial, event="idle_end")
    if s is None or e is None:
        return None
    lo, hi = s["t_mono_ns"], e["t_mono_ns"]
    n = sum(1 for m in trial["_trace"] if m.get("phase") == "cdp.event" and lo <= m.get("t_mono_ns", 0) <= hi)
    return n / ((hi - lo) / 1e9)


def resident_tasks(trial: dict[str, Any]) -> list[dict[str, Any]]:
    """Per resident task: runner-read latency (task start -> verified oracle read), runner-read based."""
    out, start = [], None
    k = None
    for e in trial["_events"]:
        if e.get("event") == "resident_task_start":
            start, k = e["t_mono_ns"], e.get("k")
        elif e.get("event") == "oracle_return" and e.get("outcome") == "verified" and start is not None:
            out.append({"k": k, "t_runner_ms": round((e["t_mono_ns"] - start) / 1e6, 3)})
            start = None
    return out


def required_zero(trial: dict[str, Any]) -> dict[str, int]:
    outcome = trial.get("outcome")
    faulted = bool(trial.get("fault"))
    fc_ar = sum(a.get("false_current_action_relevant", 0) for a in audits(trial))
    submits_main = trial.get("submits_main", 0)
    limit = len(trial.get("resident") or []) if trial.get("plan") == "resident" else 1
    return {
        "duplicate_effect": int(submits_main > max(1, limit)),
        "wrong_target_effect": int(trial.get("submits_decoy", 0) > 0),
        "unverified_success": int(outcome == "verified" and not trial.get("oracle_verified")),
        "unexpected_submit": int(trial.get("control") in NO_SUBMIT_EXPECTED and submits_main > 0),
        "mirror_false_current_action_relevant": 0 if faulted else fc_ar,
        "injected_fault_false_current_action_relevant": fc_ar if faulted else 0,
    }


def ledger_row(trial: dict[str, Any], binary_sha: str | None) -> dict[str, Any]:
    plan = trial.get("plan")
    ref = trial.get("driver_kind") == "ref"
    return {
        "lane": "CSHADOW", "issue": "kvnloo/cua#107", "trial": trial.get("trial"), "plan": plan,
        "comparison": trial.get("comparison"), "condition": trial.get("condition"), "cohort": "K1",
        "regime": "resident" if plan == "resident" else "fresh", "block": trial.get("block"),
        "pair_id": trial.get("pair"), "order": trial.get("order"), "arm": trial.get("arm"),
        "driver_kind": trial.get("driver_kind"),
        "binary_sha256": REF_SHA if ref else binary_sha,
        "caller_tree": "635a4f588c6817ccb6cb6f5b7baacddbfc42f786 (jev-use at upstream main; runner mirrors run.py)",
        "token_sha16": trial.get("token_sha16"), "outcome": trial.get("outcome"),
        "oracle_verified": trial.get("oracle_verified"), "route": "dom_event",
        "decision_routes": ["chooser:choose_mock_for_task"] * len(trial.get("candidates", [])), "guard": None,
        "candidates": trial.get("candidates"),
        "action_effects": [f"{e.get('tool')}:{e.get('effect')}" for e in trial["_events"]
                           if e.get("event") == "call_return" and str(e.get("label", "")).startswith("action")],
        "counts": ledger_counts(trial),
        "t_oracle_ms": r3(t_oracle_ms(trial)), "t_runner_ms": r3(t_runner_ms(trial)),
        "cold_startup_ms": r3(cold_startup_ms(trial)), "lifetime_ms": r3((trial.get("lifetime_ns") or 0) / 1e6),
        "caller_spans": caller_spans(trial),
        "resources": {"start": trial.get("resources_start"), "end": trial.get("resources_end"),
                      "idle_start": trial.get("idle_start"), "idle_end": trial.get("idle_end")},
        "idle_events_per_s": r3(idle_events_per_s(trial)),
        "resident_tasks": resident_tasks(trial) if plan == "resident" else None,
        "resident_oracle": trial.get("resident"),
        "mirror": mirror_stats(trial), "mirror_bootstraps": mirror_bootstraps(trial), "audits": audits(trial),
        "lags": lags_ms(trial), "required_zero": required_zero(trial),
        "submits_main": trial.get("submits_main"), "submits_decoy": trial.get("submits_decoy"),
        "pressure_before": trial.get("pressure_before"), "pressure_after": trial.get("pressure_after"),
        "lock_receipt_label": f"i107-cshadow-{trial.get('block')}", "control_id": trial.get("control"),
        "fault": trial.get("fault"), "snapshot_error": trial.get("snapshot_error"),
        "action_error": trial.get("action_error"), "dc10": trial.get("dc10"),
        "dc11": {k: v for k, v in (trial.get("dc11") or {}).items() if k != "proofs"} or None,
        "network": trial.get("network"), "browser_alive_after_close": trial.get("browser_alive_after_close"),
        "excluded": plan == "smoke", "error": trial.get("error"),
        "evidence": "REAL" if plan != "smoke" else "REAL (smoke, excluded)",
        "chooser": "choose_mock_for_task (FIXTURE/BENCHMARK, never LIVE_PROVIDER)",
    }


def loadavg1(row: dict[str, Any]) -> float:
    try:
        return float(((row.get("pressure_before") or {}).get("loadavg") or "99").split()[0])
    except ValueError:
        return 99.0


# ── comparisons ─────────────────────────────────────────────────────────────────

def metric_value(r: dict[str, Any], metric: str) -> float | None:
    res = r["resources"]
    end = res.get("end") or {}
    a, b = res.get("idle_start") or {}, res.get("idle_end") or {}
    if metric == "t_oracle_ms":
        return r["t_oracle_ms"]
    if metric == "driver_cpu_ms":
        return None if "driver_cpu_s" not in end else end["driver_cpu_s"] * 1000
    if metric == "idle_driver_cpu_s":
        return None if "driver_cpu_s" not in b or "driver_cpu_s" not in a else b["driver_cpu_s"] - a["driver_cpu_s"]
    if metric == "idle_browser_cpu_s":
        return None if "browser_tree_cpu_s" not in b or "browser_tree_cpu_s" not in a else \
            b["browser_tree_cpu_s"] - a["browser_tree_cpu_s"]
    if metric == "idle_events_per_s":
        return r["idle_events_per_s"]
    if metric == "driver_vmhwm_mib":
        src = b if r["plan"] == "idle" else end
        return None if "driver_vmhwm_kib" not in src else src["driver_vmhwm_kib"] / 1024
    if metric == "browser_rss_mib":
        src = b if r["plan"] == "idle" else end
        return None if "browser_tree_rss_kib" not in src else src["browser_tree_rss_kib"] / 1024
    if metric == "driver_rss_plus_swap_mib":
        src = b if r["plan"] == "idle" else end
        return None if "driver_vmrss_kib" not in src else (src["driver_vmrss_kib"] + src.get("driver_vmswap_kib", 0)) / 1024
    if metric == "resident_task_median_ms":
        ts = [t["t_runner_ms"] for t in (r["resident_tasks"] or [])]
        return median(ts)
    if metric == "attach_calls":
        return r["counts"]["attach_calls"]
    if metric == "cdp_sends_total":
        return sum(r["counts"]["cdp_sends_by_method"].values())
    if metric == "cdp_events_total":
        return r["counts"]["cdp_events_total"]
    if metric == "cdp_reply_kib":
        return r["counts"]["cdp_reply_bytes"] / 1024
    raise ValueError(metric)


def compare(rows: list[dict[str, Any]], comparison: str, condition: str, metric: str,
            need_verified: bool = True) -> dict[str, Any]:
    cell = [r for r in rows if r["comparison"] == comparison and r["condition"] == condition and not r["excluded"]]
    by_pair: dict[Any, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in cell:
        by_pair[r["pair_id"]][r["arm"]] = r
    pairs, invalid = [], 0
    for _pid, arms in sorted(by_pair.items(), key=lambda kv: int(kv[0])):
        a, c = arms.get("A"), arms.get("C_shadow_M")
        ok = a is not None and c is not None
        if ok and need_verified:
            ok = bool(a["oracle_verified"]) and bool(c["oracle_verified"])
        va = metric_value(a, metric) if ok else None
        vc = metric_value(c, metric) if ok else None
        if va is None or vc is None:
            invalid += 1
            continue
        pairs.append((vc - va, va, vc, max(loadavg1(a), loadavg1(c))))
    if not pairs:
        return {"status": "BLOCKED" if not cell else "NO_VALID_PAIRS", "pairs": 0, "trials": len(cell),
                "invalid_pairs": invalid}
    deltas = [p[0] for p in pairs]
    sens = [p[0] for p in pairs if p[3] <= 8]
    return {"status": "MEASURED", "pairs": len(pairs), "trials": len(cell), "invalid_pairs": invalid,
            "median_delta": r3(median(deltas)), "ci95": [r3(x) for x in bootstrap_ci(deltas) or []] or None,
            "a_median": r3(median([p[1] for p in pairs])), "a_p95": r3(p95([p[1] for p in pairs])),
            "c_median": r3(median([p[2] for p in pairs])), "c_p95": r3(p95([p[2] for p in pairs])),
            "sign_counts": {"neg": sum(d < 0 for d in deltas), "zero": sum(d == 0 for d in deltas),
                            "pos": sum(d > 0 for d in deltas)},
            "loadavg1_median": r3(median([p[3] for p in pairs])),
            "sensitivity_loadavg_le_8": {"pairs": len(sens), "median_delta": r3(median(sens)),
                                         "ci95": [r3(x) for x in bootstrap_ci(sens) or []] or None}}


def t_budget(cmp: dict[str, Any]) -> dict[str, Any]:
    if cmp.get("status") != "MEASURED":
        return {"status": cmp.get("status")}
    threshold = max(5.0, 0.05 * cmp["a_median"])
    ci = cmp["ci95"] or [None, None]
    within = cmp["median_delta"] <= threshold and ci[1] is not None and ci[1] <= 2 * threshold
    straddled = not within and ci[0] is not None and ci[0] <= threshold
    return {"threshold_ms": r3(threshold), "within_budget": within, "straddled": straddled,
            "exceeds": not within and not straddled,
            "continuation_block_required": straddled and cmp["pairs"] < 60}


def cpu_budget(cmp: dict[str, Any]) -> dict[str, Any]:
    if cmp.get("status") != "MEASURED":
        return {"status": cmp.get("status")}
    limit = max(5.0, 0.10 * cmp["a_median"])
    return {"limit_ms": r3(limit), "within_budget": cmp["median_delta"] <= limit}


def mem_budget(cmp: dict[str, Any], limit: float) -> dict[str, Any]:
    if cmp.get("status") != "MEASURED":
        return {"status": cmp.get("status")}
    return {"limit_mib": limit, "within_budget": cmp["median_delta"] <= limit}


def mirror_costs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stats = [r["mirror"]["stats"] for r in rows if r["mirror"] and r["mirror"].get("stats")]
    boots = [b for r in rows for b in r["mirror_bootstraps"] if b.get("ok")]
    if not stats:
        return {"trials": 0}

    def med(key: str, scale: float = 1e6) -> float | None:
        vals = [s.get(key, 0) / scale for s in stats]
        return r3(median(vals))

    inval: Counter = Counter()
    for s in stats:
        inval.update(s.get("invalidations") or {})
    return {
        "trials": len(stats),
        "median_ms": {"construct": med("construct_ns"), "bootstrap_total": med("bootstrap_ns"),
                      "event_handling": med("handle_ns"), "cut": med("cut_ns"), "audit_compare": med("audit_ns")},
        "bootstrap_parts_median_ms": {k[:-3]: r3(median([b.get(k, 0) / 1e3 for b in boots]))
                                      for k in ("attach_us", "enable_us", "frame_tree_us", "get_document_us")},
        "bootstrap_nodes_median": median([b.get("nodes", 0) for b in boots]) if boots else None,
        "median_events_total": median([s.get("events_total", 0) for s in stats]),
        "median_events_applied": median([s.get("applied", 0) for s in stats]),
        "median_unrelated_events": median([s.get("unrelated", 0) for s in stats]),
        "nodes_hwm_max": max(s.get("nodes_hwm", 0) for s in stats),
        "queue_hwm_max": max(s.get("queue_hwm", 0) for s in stats),
        "bootstraps_total": sum(s.get("bootstraps", 0) for s in stats),
        "bootstrap_failures_total": sum(s.get("bootstrap_failures", 0) for s in stats),
        "resyncs_total": sum(s.get("resyncs", 0) for s in stats),
        "overflows_total": sum(s.get("overflows", 0) for s in stats),
        "node_cap_trips_total": sum(s.get("node_cap_trips", 0) for s in stats),
        "discarded_overflow_total": sum(s.get("discarded_overflow", 0) for s in stats),
        "invalidation_reasons": dict(sorted(inval.items())),
        "final_coverage": dict(Counter(r["mirror"].get("coverage") for r in rows if r["mirror"])),
    }


def fidelity_block(cell: list[dict[str, Any]]) -> dict[str, Any]:
    reports = [a for r in cell for a in r["audits"]]
    compared = [a for a in reports if a.get("field_checks", 0) > 0]
    boot_coincident = [a for a in reports if a.get("field_checks", 0) == 0 and a.get("coverage") == "current"]
    lags = [l for r in cell for l in r["lags"]]
    fc_fields: Counter = Counter()
    for a in reports:
        fc_fields.update(a.get("false_current_fields") or {})
    ms = Counter(str(a.get("match_set", {}).get("estimate_agrees")) for a in reports)
    fresh_counts = Counter(a.get("match_set", {}).get("fresh_count") for a in reports)
    return {
        "status": "BLOCKED" if not cell else "MEASURED", "trials": len(cell), "audits": len(reports),
        "audits_compared": len(compared), "audits_bootstrap_coincident": len(boot_coincident),
        "audits_coverage_unknown": dict(Counter(a.get("coverage") for a in reports if a.get("coverage") != "current")),
        "field_checks": sum(a.get("field_checks", 0) for a in reports),
        "agree": sum(a.get("agree", 0) for a in reports),
        "false_current_total": sum(a.get("false_current", 0) for a in reports),
        "false_current_action_relevant": sum(a.get("false_current_action_relevant", 0) for a in reports),
        "false_current_fields": dict(fc_fields),
        "ambiguous_in_flight": sum(a.get("ambiguous_in_flight", 0) for a in reports),
        "raw_differences_including_window": sum(a.get("raw_differences_including_window", 0) for a in reports),
        "action_relevant_field_checks": sum(a.get("action_relevant_field_checks", 0) for a in reports),
        "unknown_action_relevant": sum(a.get("unknown_action_relevant", 0) for a in reports),
        "unknown_share_action_relevant": r3(sum(a.get("unknown_action_relevant", 0) for a in reports)
                                            / max(1, sum(a.get("action_relevant_field_checks", 0) for a in reports))),
        "match_set": {"mirror_status": dict(Counter(a.get("match_set", {}).get("mirror_status") for a in reports)),
                      "fresh_count": {str(k): v for k, v in fresh_counts.items()},
                      "dom_estimate_agrees_diagnostic": dict(ms)},
        "event_lag_ms": {"n": len(lags),
                         "vs_page_mutation_median": r3(median([l["vs_page_mutation_ms"] for l in lags if "vs_page_mutation_ms" in l])),
                         "vs_page_mutation_p95": r3(p95([l["vs_page_mutation_ms"] for l in lags if "vs_page_mutation_ms" in l])),
                         "vs_ack_receipt_median": r3(median([l["vs_ack_receipt_ms"] for l in lags]))},
        "mirror_costs": mirror_costs(cell),
    }


def control_summary(rows: list[dict[str, Any]], cid: str) -> dict[str, Any]:
    cell = [r for r in rows if r["control_id"] == cid and not r["excluded"]]
    by_arm: dict[str, Any] = {}
    for arm in sorted({r["arm"] for r in cell}):
        arm_rows = [r for r in cell if r["arm"] == arm]
        entry: dict[str, Any] = {
            "trials": len(arm_rows), "outcomes": dict(Counter(r["outcome"] for r in arm_rows)),
            "oracle_verified": sum(1 for r in arm_rows if r.get("oracle_verified")),
            "submits_main_total": sum(r.get("submits_main") or 0 for r in arm_rows),
            "submits_decoy_total": sum(r.get("submits_decoy") or 0 for r in arm_rows),
            "required_zero": {k: sum(r["required_zero"][k] for r in arm_rows) for k in arm_rows[0]["required_zero"]},
            "snapshot_errors": dict(Counter((r["snapshot_error"] or {}).get("code") for r in arm_rows if r["snapshot_error"])),
            "action_errors": dict(Counter((r["action_error"] or {}).get("code") for r in arm_rows if r["action_error"])),
            "candidates": dict(Counter(" > ".join(r["candidates"] or []) for r in arm_rows)),
            "action_effects": dict(Counter(" > ".join(r["action_effects"]) for r in arm_rows)),
        }
        if arm != "A":
            fid = fidelity_block(arm_rows)
            entry["audit"] = {k: fid[k] for k in ("audits", "audits_compared", "audits_coverage_unknown",
                                                  "false_current_total", "false_current_action_relevant",
                                                  "false_current_fields", "unknown_share_action_relevant",
                                                  "event_lag_ms")}
            entry["mirror_invalidations"] = fid["mirror_costs"].get("invalidation_reasons")
            entry["mirror_final_coverage"] = fid["mirror_costs"].get("final_coverage")
        if cid == "DC10":
            entry["dc10_refusals"] = dict(Counter(json.dumps(r["dc10"], sort_keys=True) for r in arm_rows if r["dc10"]))
        if cid == "DC11":
            entry["dc11_descent_proven"] = sum(1 for r in arm_rows if (r["dc11"] or {}).get("proven_all"))
            entry["dc11_killed_total"] = sum((r["dc11"] or {}).get("killed", 0) for r in arm_rows)
        by_arm[arm] = entry
    if cid == "DC18":
        faults: dict[str, Any] = {}
        for fault in sorted({r["fault"] for r in cell if r["fault"]}):
            fr = [r for r in cell if r["fault"] == fault]
            fid = fidelity_block(fr)
            faults[fault] = {"trials": len(fr), "outcomes": dict(Counter(r["outcome"] for r in fr)),
                             "false_current_total_detected_by_audit": fid["false_current_total"],
                             "false_current_action_relevant_detected_by_audit": fid["false_current_action_relevant"],
                             "false_current_fields": fid["false_current_fields"],
                             "self_detected_invalidations": fid["mirror_costs"].get("invalidation_reasons"),
                             "faults_injected": sum((r["mirror"] or {}).get("stats", {}).get("faults_injected", 0) for r in fr),
                             "final_coverage": fid["mirror_costs"].get("final_coverage")}
        by_arm["by_fault"] = faults
    n_arm_min = min((v["trials"] for k, v in by_arm.items() if k != "by_fault"), default=0)
    if cid == "DC11":
        proven = min((v.get("dc11_descent_proven", 0) for k, v in by_arm.items() if k != "by_fault"), default=0)
        status = "NOT_RUN" if cell and proven == 0 else ("BLOCKED" if not cell else
                                                         ("MEASURED" if proven >= 5 else "PARTIAL"))
    elif cid == "DC18":
        per_fault = [v["trials"] for v in by_arm.get("by_fault", {}).values()]
        status = "BLOCKED" if not cell else ("MEASURED" if per_fault and min(per_fault) >= 5 else "PARTIAL")
    else:
        status = "BLOCKED" if not cell else ("MEASURED" if n_arm_min >= 5 else "PARTIAL")
    expectation = "no submit (target gone/hidden/covered/disabled/renamed)" if cid in NO_SUBMIT_EXPECTED else \
        "verified or refusal; zero wrong-target/duplicate effects"
    met = all(v["required_zero"][k] == 0 for a, v in by_arm.items() if a != "by_fault"
              for k in ("duplicate_effect", "wrong_target_effect", "unverified_success", "unexpected_submit"))
    if cid == "DC10":
        met = met and all("accepted" not in key for a, v in by_arm.items() if a != "by_fault"
                          for key in v.get("dc10_refusals", {}))
    return {"status": status, "expectation": expectation, "expectation_met": met if cell else None, "by_arm": by_arm}


def default_off(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cell = [r for r in rows if r["plan"] == "defaultoff"]
    if not cell:
        return {"status": "BLOCKED"}
    rounds: dict[Any, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in cell:
        key = "lane_A" if r["arm"] == "A" and r["driver_kind"] == "lane" else ("ref_A" if r["arm"] == "A" else "lane_C")
        rounds[r["pair_id"]][key] = r
    equal_multiset, equal_set, compared = 0, 0, 0
    diffs = []
    for pid, k in sorted(rounds.items(), key=lambda kv: int(kv[0])):
        if "lane_A" in k and "ref_A" in k:
            compared += 1
            ma, mr = k["lane_A"]["counts"]["cdp_sends_by_method"], k["ref_A"]["counts"]["cdp_sends_by_method"]
            equal_multiset += ma == mr
            equal_set += set(ma) == set(mr)
            if ma != mr:
                diffs.append({"round": pid, "lane_minus_ref": {m: ma.get(m, 0) - mr.get(m, 0)
                                                               for m in set(ma) | set(mr) if ma.get(m, 0) != mr.get(m, 0)}})
    lane_a = [r for r in rows if r["arm"] == "A" and r["driver_kind"] != "ref" and not r["excluded"]]
    lane_c = [r for r in cell if r["arm"] == "C_shadow_M"]
    return {
        "status": "MEASURED", "rounds": len(rounds), "rounds_compared": compared,
        "lane_A_vs_map_binary_A_equal_method_multiset": equal_multiset,
        "lane_A_vs_map_binary_A_equal_method_set": equal_set, "multiset_differences": diffs[:20],
        "all_lane_A_trials": len(lane_a),
        "all_lane_A_trials_with_mirror_marks": sum(1 for r in lane_a if r["counts"]["mirror_marks"]),
        "all_lane_A_trials_with_mirror_only_sends": sum(1 for r in lane_a if r["counts"]["mirror_only_sends"]),
        "lane_C_trials_with_mirror_create": sum(1 for r in lane_c if r["counts"]["mirror_marks"].get("i107.mirror.create")),
        "outcomes": dict(Counter(f"{r['arm']}/{r['driver_kind']}:{r['outcome']}" for r in cell)),
    }


def accounting(rows: list[dict[str, Any]], comparison: str, condition: str) -> dict[str, Any]:
    out = {}
    for arm in ("A", "C_shadow_M", "C_shadow_audit"):
        shares = [r["caller_spans"]["named_share"] for r in rows if r["comparison"] == comparison
                  and r["condition"] == condition and r["arm"] == arm and r["caller_spans"]
                  and r["caller_spans"]["named_share"] is not None]
        if shares:
            out[arm] = {"trials": len(shares), "median_named_share": r3(median(shares)),
                        "min_named_share": r3(min(shares)), "gate_gt_0_90": min(shares) > 0.90}
    return out


def lane_read_sequence(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Active-C cross-check on this lane's own REAL A trials: every get_browser_state call is the
    bind (b) or a fresh semantic_v2 read whose refs the next mutation uses (a); none follows the
    last mutation (verification is the fixture oracle, c)."""
    checked, ok, reads, after_last, other = 0, 0, Counter(), 0, Counter()
    for t in trials:
        if t.get("arm") != "A" or t.get("driver_kind") == "ref" or t.get("plan") not in ("overhead", "defaultoff", "controls"):
            continue
        calls = [e for e in t["_events"] if e.get("event") == "call_send"]
        labels = [e.get("label") for e in calls]
        mut_idx = [i for i, e in enumerate(calls) if e.get("tool") in ("browser_type", "browser_click")]
        state_idx = [i for i, e in enumerate(calls) if e.get("tool") == "get_browser_state"]
        checked += 1
        good = True
        for i in state_idx:
            label = labels[i] or ""
            if label == "bind":
                reads["b_binding"] += 1
            elif label.startswith("snapshot"):
                nxt = calls[i + 1] if i + 1 < len(calls) else None
                if nxt is not None and nxt.get("tool") in ("browser_type", "browser_click"):
                    reads["a_ref_minting_before_mutation"] += 1
                elif nxt is None and t.get("outcome") in ("budget_exhausted", "abstained", "unknown"):
                    reads["a_ref_minting_no_admissible_candidate"] += 1  # read, then the chooser declined
                else:
                    reads["a_ref_minting_then_reobserve"] += 1
            else:
                other[label] += 1
                good = False
            if mut_idx and i > mut_idx[-1] and label.startswith("snapshot") and t.get("outcome") == "verified":
                after_last += 1
                good = False
        ok += good
    return {"lane_A_trials_checked": checked, "trials_all_reads_in_a_d": ok, "reads": dict(reads),
            "reads_outside_a_d": dict(other), "driver_reads_after_last_mutation_in_verified_trials": after_last}


def denominators(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r["excluded"]:
            continue
        key = f"{r['plan']}/{r['control_id'] or r['condition']}/{r['arm']}" + ("/ref" if r["driver_kind"] == "ref" else "")
        out[key][r["outcome"]] += 1
    return {k: dict(v) for k, v in sorted(out.items())}


# ── main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    packet = Path(sys.argv[1])
    raw = packet / "raw"
    trials = load_trials(raw)
    provenance = json.loads((packet / "provenance.json").read_text()) if (packet / "provenance.json").exists() else {}
    binary_sha = (provenance.get("binary") or {}).get("sha256")
    rows = [ledger_row(t, binary_sha) for t in trials]
    (raw / "ledger.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    measured = [r for r in rows if not r["excluded"]]

    admissibility = json.loads((raw / "admissibility.json").read_text())
    summary: dict[str, Any] = {
        "schema": "cua.i107.cshadow.summary.v2",
        "trials_total": len(rows), "trials_measured": len(measured),
        "trials_smoke_excluded": len(rows) - len(measured),
        "trials_with_harness_error": sum(1 for r in measured if r["error"]),
        "non_loopback_connect_attempts": sum((r["network"] or {}).get("non_loopback_connect_attempts", 0) for r in rows),
        "active_c": {"verdict": admissibility["verdict"], "calls": admissibility["get_browser_state_calls"],
                     "by_category": admissibility["by_category"], "trials": admissibility["trials"],
                     "driver_reads_after_last_mutation": admissibility["driver_reads_after_last_mutation"],
                     "lane_real_cross_check": lane_read_sequence([t for t in trials if t.get("plan") != "smoke"])},
        "comparisons": {}, "accounting_gate": {}, "fidelity": {}, "controls": {}, "denominators": denominators(rows),
    }
    for comparison, conditions in PRIMARY.items():
        for condition in conditions:
            if comparison == "CMP-C-overhead":
                cell = {m: compare(measured, comparison, condition, m) for m in
                        ("t_oracle_ms", "driver_cpu_ms", "driver_vmhwm_mib", "browser_rss_mib", "driver_rss_plus_swap_mib",
                         "attach_calls", "cdp_sends_total", "cdp_events_total", "cdp_reply_kib")}
                cell["t_budget"] = t_budget(cell["t_oracle_ms"])
                cell["driver_cpu_budget"] = cpu_budget(cell["driver_cpu_ms"])
                summary["accounting_gate"][f"{comparison}/{condition}"] = accounting(measured, comparison, condition)
                cell["mirror_costs_C_shadow_M"] = mirror_costs([r for r in measured if r["comparison"] == comparison
                                                                and r["condition"] == condition
                                                                and r["arm"] == "C_shadow_M"])
            else:
                cell = {m: compare(measured, comparison, condition, m, need_verified=False) for m in
                        ("idle_driver_cpu_s", "idle_browser_cpu_s", "idle_events_per_s", "driver_vmhwm_mib",
                         "browser_rss_mib", "driver_rss_plus_swap_mib")}
                for m in ("idle_driver_cpu_s", "idle_browser_cpu_s"):
                    c = cell[m]
                    if c.get("status") == "MEASURED":
                        c["budget"] = BUDGET[m][condition]
                        c["within_budget"] = c["median_delta"] <= c["budget"]
            for m, limit in (("driver_vmhwm_mib", BUDGET["driver_vmhwm_mib"]), ("browser_rss_mib", BUDGET["browser_rss_mib"])):
                cell[m]["budget"] = mem_budget(cell[m], limit)
            summary["comparisons"][f"{comparison}/{condition}"] = cell
    res = {m: compare(measured, "CMP-C-resident", "W-churn", m, need_verified=False)
           for m in ("resident_task_median_ms", "driver_cpu_ms", "driver_vmhwm_mib", "browser_rss_mib", "attach_calls",
                     "cdp_sends_total", "cdp_events_total")}
    res_rows = [r for r in measured if r["comparison"] == "CMP-C-resident"]
    res["sessions"] = len(res_rows)
    res["tasks_verified"] = sum(sum(1 for t in (r["resident_oracle"] or []) if t.get("oracle")) for r in res_rows)
    res["tasks_total"] = sum(len(r["resident_oracle"] or []) for r in res_rows)
    res["session_age_ms_median"] = r3(median([r["lifetime_ms"] for r in res_rows]))
    res["mirror_costs_C_shadow_M"] = mirror_costs([r for r in res_rows if r["arm"] == "C_shadow_M"])
    res["evidence_note"] = "secondary; per-task latency is the runner's verified read (no independent poller in resident sessions)"
    summary["comparisons"]["CMP-C-resident/W-churn"] = res
    for condition in FIDELITY_CONDITIONS:
        summary["fidelity"][condition] = fidelity_block(
            [r for r in measured if r["comparison"] == "CMP-C-fidelity" and r["condition"] == condition])
    unfaulted_audit = [r for r in measured if r["arm"] == "C_shadow_audit" and not r["fault"]]
    summary["fidelity"]["all_unfaulted_C_shadow_audit_trials"] = {
        k: v for k, v in fidelity_block(unfaulted_audit).items() if k != "mirror_costs"}
    for cid in CONTROL_IDS:
        summary["controls"][cid] = control_summary(rows, cid)
    summary["default_off"] = default_off(measured)
    summary["required_zero"] = {k: sum(r["required_zero"][k] for r in measured)
                                for k in ("duplicate_effect", "wrong_target_effect", "unverified_success",
                                          "unexpected_submit", "mirror_false_current_action_relevant")}
    summary["injected_fault_false_current_action_relevant"] = sum(
        r["required_zero"]["injected_fault_false_current_action_relevant"] for r in measured)
    summary["disposition"] = disposition(summary)
    (packet / "cshadow-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"trials": len(rows), "measured": len(measured), "active_c": admissibility["verdict"],
                      "disposition": summary["disposition"]["verdict"]}))
    return 0


def disposition(s: dict[str, Any]) -> dict[str, Any]:
    """Map PREREG decision table, applied mechanically."""
    if s["trials_measured"] == 0:
        return {"verdict": "BLOCKED", "rows": ["evidence incomplete"]}
    rows, reasons = [], []
    fc = s["required_zero"]["mirror_false_current_action_relevant"]
    other_zero = {k: v for k, v in s["required_zero"].items() if k != "mirror_false_current_action_relevant" and v}
    fid_status = [s["fidelity"][c]["status"] for c in FIDELITY_CONDITIONS]
    budget_flags = []
    for key, cell in s["comparisons"].items():
        if key.startswith("CMP-C-overhead"):
            tb = cell["t_budget"]
            if tb.get("exceeds"):
                budget_flags.append(f"{key}: per-task T exceeds budget")
            if tb.get("continuation_block_required"):
                reasons.append(f"{key}: continuation block required (budget straddled)")
            if cell["driver_cpu_budget"].get("within_budget") is False:
                budget_flags.append(f"{key}: per-task Driver CPU over budget")
        if key.startswith("CMP-C-idle"):
            for m in ("idle_driver_cpu_s", "idle_browser_cpu_s"):
                if cell[m].get("within_budget") is False:
                    budget_flags.append(f"{key}: {m} over budget")
        if not key.startswith("CMP-C-resident"):
            for m in ("driver_vmhwm_mib", "browser_rss_mib"):
                if cell[m].get("budget", {}).get("within_budget") is False:
                    budget_flags.append(f"{key}: {m} over budget")
    if fc > 0:
        verdict = "KILL"
        rows.append("C shadow false-current > 0 on an action-relevant field -> KILL the mirror mechanism as built")
    elif any(st != "MEASURED" for st in fid_status):
        verdict = "BLOCKED"
        rows.append("evidence incomplete -> BLOCKED")
    else:
        verdict = "park"
        rows.append("C shadow fidelity holds (false-current 0) and C_active NOT_ADMISSIBLE -> park the persistent "
                    "mirror (no deletable read on this fixture); keep the shadow evidence as qualification data")
    if budget_flags:
        rows.append("C_shadow_M exceeds resource_budget_C -> narrow or KILL the affected mechanism: " + "; ".join(budget_flags))
        if verdict == "park":
            verdict = "park + narrow"
    if other_zero:
        rows.append(f"required-zero counts non-zero: {other_zero} -> no promotion")
    return {"verdict": verdict, "rows": rows, "open_items": reasons}


if __name__ == "__main__":
    raise SystemExit(main())

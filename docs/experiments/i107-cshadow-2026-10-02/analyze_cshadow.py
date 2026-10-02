"""Analysis for kvnloo/cua#107 lane CSHADOW. Pure standard library.

Usage: python3 analyze_cshadow.py <packet-dir>

Reads <packet>/raw/trials/*.jsonl (caller events + summary line) and the
matching *.driver-trace.jsonl, plus raw/admissibility.json and
raw/protocol_events.json, and writes <packet>/raw/ledger.jsonl (#10 task x arm
x trial format) and <packet>/cshadow-summary.json. Every statistic follows the
lane PREREG (which defers to the map PREREG): paired deltas = treatment - A,
median, seeded percentile bootstrap (10000 resamples, seed 20261002), threshold
max(5 ms, 5% of A's median T_oracle), resource budget, continuation rule.
A cell with no trials is reported BLOCKED (never zero-filled).
"""

from __future__ import annotations

import json
import random
import statistics
import sys
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
PRIMARY = {
    "CMP-C-overhead": ["W-quiet", "W-churn"],
    "CMP-C-idle": ["W-idle-quiet", "W-idle-churn"],
}
FIDELITY_CONDITIONS = ["W-quiet", "W-churn"]
CONTROL_IDS = ["DC01", "DC02", "DC03", "DC04", "DC05a", "DC07", "DC10", "DC11", "DC12", "DC13", "DC14a",
               "DC14b", "DC15", "DC16a", "DC16b", "DC17a", "DC17b", "DC18", "DC19a", "DC19b"]


def jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


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


def load_trials(raw: Path) -> list[dict[str, Any]]:
    trials = []
    for path in sorted((raw / "trials").glob("*.jsonl")):
        if path.name.endswith(".driver-trace.jsonl"):
            continue
        rows = jsonl(path)
        if not rows or rows[-1].get("event") != "summary":
            continue
        summary = rows[-1]
        summary["_events"] = rows[:-1]
        summary["_trace"] = jsonl(path.with_name(path.name.replace(".jsonl", ".driver-trace.jsonl")))
        trials.append(summary)
    return trials


def t_oracle_ms(trial: dict[str, Any]) -> float | None:
    send = next((e["t_mono_ns"] for e in trial["_events"]
                 if e.get("event") == "call_send" and e.get("label") == "snapshot1"), None)
    ok = trial.get("poller_first_ok_ns")
    return None if send is None or ok is None else (ok - send) / 1e6


def t_runner_ms(trial: dict[str, Any]) -> float | None:
    send = next((e["t_mono_ns"] for e in trial["_events"]
                 if e.get("event") == "call_send" and e.get("label") == "snapshot1"), None)
    done = next((e["t_mono_ns"] for e in trial["_events"]
                 if e.get("event") == "oracle_return" and e.get("outcome") == "verified"), None)
    return None if send is None or done is None else (done - send) / 1e6


def ledger_counts(trial: dict[str, Any]) -> dict[str, Any]:
    sends = Counter(m["detail"]["method"] for m in trial["_trace"]
                    if m.get("phase") == "cdp.send" and isinstance(m.get("detail"), dict))
    events = Counter(m["detail"]["method"] for m in trial["_trace"]
                     if m.get("phase") == "cdp.event" and isinstance(m.get("detail"), dict))
    send_bytes = sum(m["detail"].get("bytes", 0) for m in trial["_trace"] if m.get("phase") == "cdp.send")
    reply_bytes = sum(m["detail"].get("bytes", 0) for m in trial["_trace"] if m.get("phase") == "cdp.reply")
    mirror_marks = Counter(m["phase"] for m in trial["_trace"] if str(m.get("phase", "")).startswith("i107.mirror."))
    return {
        "cdp_sends_by_method": dict(sends), "cdp_events_total": sum(events.values()),
        "cdp_events_by_method": dict(events), "cdp_send_bytes": send_bytes, "cdp_reply_bytes": reply_bytes,
        "attach_calls": sends.get("Target.attachToTarget", 0), "detach_calls": sends.get("Target.detachFromTarget", 0),
        "mirror_only_sends": sum(sends.get(m, 0) for m in ("Page.enable", "Inspector.enable", "DOM.requestChildNodes")),
        "mirror_marks": dict(mirror_marks),
        "semantic_snapshots": sum(1 for e in trial["_events"] if e.get("event") == "call_send"
                                  and str(e.get("label", "")).startswith("snapshot")),
        "decisions": sum(1 for e in trial["_events"] if e.get("event") == "decided"),
        "driver_mutations": sum(1 for e in trial["_events"] if e.get("event") == "call_send"
                                and e.get("tool") in ("browser_type", "browser_click")),
        "polls": sum(1 for e in trial["_events"] if e.get("event") == "sleep_start"),
    }


def mirror_stats(trial: dict[str, Any]) -> dict[str, Any] | None:
    marks = [m for m in trial["_trace"] if m.get("phase") == "i107.mirror.stats"]
    return marks[-1]["detail"] if marks else None


def audits(trial: dict[str, Any]) -> list[dict[str, Any]]:
    return [m["detail"] for m in trial["_trace"] if m.get("phase") == "i107.mirror.audit"]


def lags_ms(trial: dict[str, Any]) -> list[dict[str, float]]:
    applied = {m["detail"]["op"]: m["t_mono_ns"] for m in trial["_trace"]
               if m.get("phase") == "i107.mirror.op_applied" and isinstance(m.get("detail"), dict)}
    out = []
    for e in trial.get("journal", []):
        if e.get("event") == "ack" and e.get("id") in applied:
            row = {"vs_ack_receipt_ms": (applied[e["id"]] - e["t_mono_ns"]) / 1e6}
            if e.get("applied_mono_ns_mapped"):
                row["vs_page_mutation_ms"] = (applied[e["id"]] - e["applied_mono_ns_mapped"]) / 1e6
            out.append(row)
    return out


def required_zero(trial: dict[str, Any]) -> dict[str, int]:
    outcome = trial.get("outcome")
    return {
        "duplicate_effect": int(trial.get("submits_main", 0) > 1),
        "wrong_target_effect": int(trial.get("submits_decoy", 0) > 0),
        "unverified_success": int(outcome == "verified" and not trial.get("oracle_verified")),
        "mirror_false_current_action_relevant": sum(a.get("false_current_action_relevant", 0) for a in audits(trial)),
    }


def ledger_row(trial: dict[str, Any], binary_sha: str | None) -> dict[str, Any]:
    res_start, res_end = trial.get("resources_start") or {}, trial.get("resources_end") or {}
    return {
        "lane": "CSHADOW", "issue": "kvnloo/cua#107", "comparison": trial.get("comparison"),
        "condition": trial.get("condition"), "cohort": "K1", "regime": "resident" if trial.get("plan") == "resident" else "fresh",
        "pair_id": trial.get("pair"), "order": trial.get("order"), "arm": trial.get("arm"),
        "binary_sha256": binary_sha, "caller_tree": "635a4f588c6817ccb6cb6f5b7baacddbfc42f786",
        "token_sha16": trial.get("token_sha16"), "outcome": trial.get("outcome"),
        "oracle_verified": trial.get("oracle_verified"), "route": "dom_event",
        "decision_routes": ["provider"] * len(trial.get("candidates", [])), "guard": None,
        "counts": ledger_counts(trial), "t_oracle_ms": t_oracle_ms(trial), "t_runner_ms": t_runner_ms(trial),
        "lifetime_ms": (trial.get("lifetime_ns") or 0) / 1e6,
        "resources": {"start": res_start, "end": res_end, "idle_start": trial.get("idle_start"),
                      "idle_end": trial.get("idle_end")},
        "mirror": mirror_stats(trial), "audits": audits(trial), "lags": lags_ms(trial),
        "required_zero": required_zero(trial), "pressure_before": trial.get("pressure_before"),
        "pressure_after": trial.get("pressure_after"), "lock_receipt": trial.get("block"),
        "control_id": trial.get("control"), "fault": trial.get("fault"),
        "excluded": trial.get("plan") == "smoke", "error": trial.get("error"),
        "evidence": "REAL" if trial.get("plan") != "smoke" else "REAL (smoke, excluded)",
        "chooser": "choose_mock_for_task (FIXTURE/BENCHMARK, never LIVE_PROVIDER)",
    }


def loadavg1(row: dict[str, Any]) -> float:
    try:
        return float(((row.get("pressure_before") or {}).get("loadavg") or "99").split()[0])
    except ValueError:
        return 99.0


def compare(rows: list[dict[str, Any]], comparison: str, condition: str, metric: str) -> dict[str, Any]:
    cell = [r for r in rows if r["comparison"] == comparison and r["condition"] == condition and not r["excluded"]]
    by_pair: dict[Any, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in cell:
        by_pair[r["pair_id"]][r["arm"]] = r

    def value(r: dict[str, Any]) -> float | None:
        if metric == "t_oracle_ms":
            return r["t_oracle_ms"]
        if metric == "driver_cpu_ms":
            v = (r["resources"]["end"] or {}).get("driver_cpu_s")
            return None if v is None else v * 1000
        if metric == "idle_driver_cpu_s":
            a, b = r["resources"].get("idle_start") or {}, r["resources"].get("idle_end") or {}
            return None if "driver_cpu_s" not in b else b["driver_cpu_s"] - a.get("driver_cpu_s", 0)
        if metric == "idle_browser_cpu_s":
            a, b = r["resources"].get("idle_start") or {}, r["resources"].get("idle_end") or {}
            return None if "browser_tree_cpu_s" not in b else b["browser_tree_cpu_s"] - a.get("browser_tree_cpu_s", 0)
        if metric == "driver_vmhwm_mib":
            v = (r["resources"]["end"] or {}).get("driver_vmhwm_kib")
            return None if v is None else v / 1024
        if metric == "browser_rss_mib":
            v = (r["resources"]["end"] or {}).get("browser_tree_rss_kib")
            return None if v is None else v / 1024
        raise ValueError(metric)

    pairs = []
    for pid, arms in sorted(by_pair.items(), key=lambda kv: str(kv[0])):
        a, c = arms.get("A"), arms.get("C_shadow_M")
        if a and c and a["oracle_verified"] in (True, None) and value(a) is not None and value(c) is not None:
            pairs.append((value(c) - value(a), value(a), value(c), max(loadavg1(a), loadavg1(c))))
    deltas = [p[0] for p in pairs]
    if not pairs:
        return {"status": "BLOCKED" if not cell else "NO_VALID_PAIRS", "pairs": 0, "trials": len(cell)}
    a_vals = [p[1] for p in pairs]
    sens = [p[0] for p in pairs if p[3] <= 8]
    return {"status": "MEASURED", "pairs": len(pairs), "trials": len(cell), "median_delta": median(deltas),
            "ci95": bootstrap_ci(deltas), "a_median": median(a_vals), "a_p95": p95(a_vals),
            "c_median": median([p[2] for p in pairs]), "c_p95": p95([p[2] for p in pairs]),
            "sign_counts": {"neg": sum(d < 0 for d in deltas), "zero": sum(d == 0 for d in deltas),
                            "pos": sum(d > 0 for d in deltas)},
            "sensitivity_loadavg_le_8": {"pairs": len(sens), "median_delta": median(sens), "ci95": bootstrap_ci(sens)}}


def t_budget(cmp: dict[str, Any]) -> dict[str, Any]:
    if cmp.get("status") != "MEASURED":
        return {"status": cmp.get("status")}
    threshold = max(5.0, 0.05 * cmp["a_median"])
    ci = cmp["ci95"] or [None, None]
    within = cmp["median_delta"] <= threshold and ci[1] is not None and ci[1] <= 2 * threshold
    straddled = not within and ci[0] is not None and ci[0] <= threshold
    return {"threshold_ms": threshold, "within_budget": within, "straddled": straddled,
            "continuation_block_required": straddled and cmp["pairs"] < 60}


def main() -> int:
    packet = Path(sys.argv[1])
    raw = packet / "raw"
    trials = load_trials(raw)
    provenance = json.loads((packet / "provenance.json").read_text()) if (packet / "provenance.json").exists() else {}
    binary_sha = (provenance.get("binary") or {}).get("sha256")
    rows = [ledger_row(t, binary_sha) for t in trials]
    (raw / "ledger.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))

    admissibility = json.loads((raw / "admissibility.json").read_text())
    summary: dict[str, Any] = {
        "schema": "cua.i107.cshadow.summary.v1",
        "trials_total": len(rows), "trials_measured": sum(1 for r in rows if not r["excluded"]),
        "trials_smoke_excluded": sum(1 for r in rows if r["excluded"]),
        "active_c": {"verdict": admissibility["verdict"], "calls": admissibility["get_browser_state_calls"],
                     "by_category": admissibility["by_category"], "trials": admissibility["trials"],
                     "driver_reads_after_last_mutation": admissibility["driver_reads_after_last_mutation"]},
        "comparisons": {}, "fidelity": {}, "controls": {}, "default_off": {}, "required_zero": {},
    }
    for comparison, conditions in PRIMARY.items():
        for condition in conditions:
            metrics = ["t_oracle_ms", "driver_cpu_ms", "driver_vmhwm_mib", "browser_rss_mib"] \
                if comparison == "CMP-C-overhead" else ["idle_driver_cpu_s", "idle_browser_cpu_s",
                                                        "driver_vmhwm_mib", "browser_rss_mib"]
            cell = {m: compare(rows, comparison, condition, m) for m in metrics}
            if comparison == "CMP-C-overhead":
                cell["t_budget"] = t_budget(cell["t_oracle_ms"])
            else:
                for m in ("idle_driver_cpu_s", "idle_browser_cpu_s"):
                    c = cell[m]
                    if c.get("status") == "MEASURED":
                        c["budget"] = BUDGET[m][condition]
                        c["within_budget"] = c["median_delta"] <= c["budget"]
            summary["comparisons"][f"{comparison}/{condition}"] = cell
    for condition in FIDELITY_CONDITIONS:
        cell = [r for r in rows if r["comparison"] == "CMP-C-fidelity" and r["condition"] == condition]
        reports = [a for r in cell for a in r["audits"]]
        current = [a for a in reports if a.get("coverage") == "current"]
        fc_ar = sum(a.get("false_current_action_relevant", 0) for a in reports)
        summary["fidelity"][condition] = {
            "status": "BLOCKED" if not cell else "MEASURED", "trials": len(cell), "audits": len(reports),
            "audits_current": len(current),
            "coverage_unknown_reasons": dict(Counter(a.get("coverage") for a in reports if a.get("coverage") != "current")),
            "false_current_total": sum(a.get("false_current", 0) for a in reports),
            "false_current_action_relevant": fc_ar,
            "field_checks": sum(a.get("field_checks", 0) for a in reports),
            "agree": sum(a.get("agree", 0) for a in reports),
            "ambiguous_in_flight": sum(a.get("ambiguous_in_flight", 0) for a in reports),
            "unknown_share_action_relevant": (sum(a.get("unknown_action_relevant", 0) for a in reports)
                                              / max(1, sum(a.get("action_relevant_field_checks", 0) for a in reports))),
            "match_set_estimate_agreement": dict(Counter(str(a.get("match_set", {}).get("estimate_agrees")) for a in reports)),
        }
    for cid in CONTROL_IDS:
        cell = [r for r in rows if r["control_id"] == cid]
        by_arm: dict[str, Any] = {}
        for arm in sorted({r["arm"] for r in cell}):
            arm_rows = [r for r in cell if r["arm"] == arm]
            by_arm[arm] = {
                "trials": len(arm_rows), "outcomes": dict(Counter(r["outcome"] for r in arm_rows)),
                "oracle_verified": sum(1 for r in arm_rows if r.get("oracle_verified")),
                "required_zero": {k: sum(r["required_zero"][k] for r in arm_rows) for k in arm_rows[0]["required_zero"]},
                "audit_coverage": dict(Counter(a.get("coverage") for r in arm_rows for a in r["audits"])),
                "faults": dict(Counter(r["fault"] for r in arm_rows if r["fault"])),
                "lags_ms": [l for r in arm_rows for l in r["lags"]][:200],
            }
        summary["controls"][cid] = {"status": "BLOCKED" if not cell else ("MEASURED" if len(cell) >= 5 else "PARTIAL"),
                                    "by_arm": by_arm}
    a_rows = [r for r in rows if r["arm"] == "A" and not r["excluded"]]
    summary["default_off"] = {
        "status": "BLOCKED" if not a_rows else "MEASURED", "a_trials": len(a_rows),
        "a_trials_with_mirror_marks": sum(1 for r in a_rows if r["counts"]["mirror_marks"]),
        "a_trials_with_mirror_only_sends": sum(1 for r in a_rows if r["counts"]["mirror_only_sends"]),
    }
    summary["required_zero"] = {k: sum(r["required_zero"][k] for r in rows if not r["excluded"])
                                for k in ("duplicate_effect", "wrong_target_effect", "unverified_success",
                                          "mirror_false_current_action_relevant")}
    measured_any = summary["trials_measured"] > 0
    fc = summary["required_zero"]["mirror_false_current_action_relevant"]
    if not measured_any:
        disposition = ("BLOCKED: no REAL measured trial (C shadow qualification cells empty). "
                       "Pre-registered expectation stands untested; active C NOT_ADMISSIBLE from SOURCE+REAL(B-01) "
                       "classification: park the persistent mirror for this fixture regardless of shadow results.")
    elif fc > 0:
        disposition = "KILL the mirror mechanism as built (false-current on an action-relevant field)"
    else:
        disposition = "park the persistent mirror (no deletable read on this fixture); keep shadow evidence"
    summary["disposition"] = disposition
    (packet / "cshadow-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"trials": len(rows), "measured": summary["trials_measured"], "active_c": admissibility["verdict"],
                      "disposition": disposition}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

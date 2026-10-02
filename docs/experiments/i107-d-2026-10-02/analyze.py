"""Build the lane-D summary and #10 ledger from raw/ (standard library only).

    python3 analyze.py            # writes d-summary.json, ledger/i107-d-ledger.jsonl, ledger/cells.json
    python3 analyze.py --check    # exit 1 if the committed files differ from a fresh build

Inputs: raw/real/<block>/{trials/,manifests/} (REAL runs, if any), raw/unit/*.json (UNIT),
raw/pr4316-head-*.json (live PR head reads), PREREG.json.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

import d_analysis as D  # noqa: E402
import d_plan  # noqa: E402

LANE = "i107-d"
CONDITIONS = {"CMP-D": ["W-quiet", "W-churn"], "CMP-D-K2": ["W-quiet"]}
OUTCOMES = ["verified", "refuted", "abstained", "unknown", "timeout", "budget_exhausted", "error"]
BLOCKER = ("hostless (bubblewrap, unprivileged user namespace) shows host root-owned files as uid 65534, so the "
           "Driver's isolated-launch trust check refuses browser_prepare with browser_route_unavailable; an approved "
           "isolation wrapper is required (map PREREG infrastructure_blocker_at_freeze)")


def load_real(raw: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trials, manifests = [], []
    real = raw / "real"
    if real.is_dir():
        for block in sorted(p for p in real.iterdir() if p.is_dir()):
            trials += D.load_trials(block / "trials")
            manifests += [json.loads(m.read_text()) for m in sorted((block / "manifests").glob("*.json"))]
    return trials, manifests


def med(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def arm_profile(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Median per-task counts and spans over valid trials of one arm/condition."""
    valid = [t for t in trials if not D.validity(t)]
    out: dict[str, Any] = {"n_trials": len(trials), "n_valid": len(valid),
                           "outcomes": {o: sum(1 for t in trials if t["summary"].get("outcome") == o) for o in OUTCOMES},
                           "oracle_verified": sum(1 for t in trials if D.oracle_satisfied(t["summary"]))}
    if not valid:
        return out
    cs = [D.counts(t) for t in valid]
    decs = [D.decompose_d(t) for t in valid]
    keys = ["decisions", "decision_ms", "plan_calls", "plan_ms", "resolve_calls", "resolve_ms", "snapshots_full",
            "cdp_sends", "cdp_send_bytes", "cdp_reply_bytes", "cdp_events", "acquired_dom_nodes",
            "acquired_layout_nodes", "acquired_ax_nodes", "mcp_snapshot_bytes", "mcp_bytes_total",
            "driver_mutations", "sleeps", "runner_oracle_reads"]
    out["median_counts"] = {k: med([c[k] for c in cs]) for k in keys}
    out["cdp_methods"] = dict(sorted(Counter(m for c in cs for m, n in c["cdp_sends_by_method"].items()
                                             for _ in range(n)).items()))
    out["median_spans10_ms"] = {k: med([d["spans10"][k] for d in decs]) for k in D.SPANS10}
    out["median_T_oracle_ms"] = med([d["T_ms"] for d in decs])
    cov = [d["coverage"] for d in decs]
    out["coverage"] = {"median": med(cov), "min": min(cov), "gate_gt_0_90": med(cov) > 0.90}
    clean = [D.cleanup_spans(t) for t in valid]
    out["median_cleanup_ms"] = {k: med([c[k] for c in clean]) for k in clean[0]}
    res = [t["summary"].get("resources") or {} for t in valid]
    out["median_resources"] = {k: med([r.get(k) for r in res]) for k in
                               ("driver_cpu_s", "driver_vmhwm_kib", "browser_cpu_s", "browser_rss_kib")}
    return out


def real_status(comparisons: dict[str, Any], measured: list[dict[str, Any]]) -> str:
    if not measured:
        return "BLOCKED"
    pairs_ok = all(c.get("paired", {}).get("pairs_valid", 0) >= 30 for conds in comparisons.values() for c in conds.values())
    per = Counter((t["summary"].get("control"), t["summary"]["arm"]) for t in measured if t["summary"].get("kind") == "control")
    ctl_ok = all(per[(cid, arm)] >= 5 for cid in d_plan.CONTROLS for arm in ("A", "D"))
    return "COMPLETE" if pairs_ok and ctl_ok else "PARTIAL"


def build(raw: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    prereg = json.loads((HERE / "PREREG.json").read_text())
    trials, manifests = load_real(raw)
    measured = [t for t in trials if not t["summary"].get("excluded")]
    excluded = [t for t in trials if t["summary"].get("excluded")]
    heads = {p.stem.removeprefix("pr4316-head-"): json.loads(p.read_text()) for p in sorted(raw.glob("pr4316-head-*.json"))}
    guard = json.loads((raw / "unit" / "guard-matrix.json").read_text())
    structural = json.loads((raw / "unit" / "structural-work.json").read_text())

    comparisons: dict[str, Any] = {}
    verdicts: dict[str, Any] = {}
    for comp, conds in CONDITIONS.items():
        comparisons[comp] = {}
        for cond in conds:
            sel = [t for t in measured if t["summary"].get("comparison") == comp and t["summary"].get("condition") == cond]
            if not sel:
                comparisons[comp][cond] = {"status": "BLOCKED", "reason": BLOCKER}
                continue
            p = D.paired(measured, comp, cond)
            s8 = D.paired(measured, comp, cond, max_load1=8.0)
            comparisons[comp][cond] = {
                "status": "BENCHMARK (REAL, scripted chooser)", "paired": p,
                "continuation_needed": D.continuation_needed(p["verdict"]),
                "sensitivity_load1_le_8": s8["verdict"],
                "arms": {arm: arm_profile([t for t in sel if t["summary"]["arm"] == arm]) for arm in ("A", "D")}}
            if comp == "CMP-D":
                verdicts[cond] = p["verdict"]
    zero = D.required_zero(measured)
    a_dec = [D.counts(t)["decisions"] for t in measured if t["summary"]["arm"] == "A" and t["summary"]["kind"] == "measured"
             and not D.validity(t)]
    d_dec = [D.counts(t)["decisions"] for t in measured if t["summary"]["arm"] == "D" and t["summary"]["kind"] == "measured"
             and not D.validity(t)]
    deleted_real = (med(a_dec) - med(d_dec)) if a_dec and d_dec else None
    disp = D.disposition(verdicts or None, zero, deleted_real)

    sa, sd = structural["arms"]["A"]["per_task"], structural["arms"]["D"]["per_task"]
    guard_rows = {f"{r['control']}/{r['branch']}": {"A_target": r["A"]["target"], "A_choice": r["A"]["choice"],
                                                    "D_guard": r["D"]["guard"], "D_target": r["D"]["target"],
                                                    "evidence": r["evidence"]} for r in guard}
    excluded_rows = []
    for t in excluded:
        c = D.counts(t)
        d = D.decompose_d(t)
        excluded_rows.append({
            "trial": t["name"], "excluded": t["summary"].get("excluded"), "arm": t["summary"]["arm"],
            "control": t["summary"].get("control"), "condition": t["summary"].get("condition"),
            "outcome": t["summary"]["outcome"], "oracle_verified": D.oracle_satisfied(t["summary"]),
            "decision_routes": c["decision_routes"], "guard": c["guard"], "journal_submits": c["journal_submits"],
            "wrong_target_submits": c["wrong_target_submits"], "mutation_refusals": c["mutation_refusals"],
            "T_oracle_ms": None if d is None else round(d["T_ms"], 3),
            "coverage": None if d is None else round(d["coverage"], 4),
            "cursor_ack": t["summary"].get("cursor_ack"),
            "fault": None if not t["summary"].get("fault") else {
                k: t["summary"]["fault"].get(k) for k in ("mode", "fired", "clicks_after_fault")}})

    summary = {
        "schema": "cua.i107.lane-d.summary.v1", "issue": "kvnloo/cua#107", "lane": LANE,
        "prereg": {"lane": "PREREG.json", "map_sha256": prereg["map_prereg"]["sha256"]},
        "identities": prereg["identities"], "live_pr_head_reads": heads,
        "chooser": "choose_mock_for_task (scripted mock) in every row: FIXTURE/BENCHMARK, never LIVE_PROVIDER",
        "real": {
            "status": real_status(comparisons, measured),
            "blocker": BLOCKER if not measured else None,
            "trials_measured": len(measured), "trials_excluded": len(excluded),
            "manifests": [{k: m.get(k) for k in ("block", "lock_label", "started_utc", "ended_utc", "isolation",
                                                 "fixture_pid_separate", "provider", "trials")} for m in manifests],
            "excluded_runs": excluded_rows,
            "comparisons": comparisons,
            "required_zero": zero,
            "controls": D.controls_table(measured) or "BLOCKED",
        },
        "unit": {
            "structural_work_per_task": {
                "evidence": structural["evidence"], "n_per_arm": structural["n_per_arm"],
                "decisions": {"A": sa["decisions"], "D": sd["decisions"]},
                "plan_calls": {"A": sa["plan_calls"], "D": sd["plan_calls"]},
                "resolve_calls": {"A": sa["resolve_calls"], "D": sd["resolve_calls"]},
                "snapshots_full": {"A": sa["snapshots_full"], "D": sd["snapshots_full"]},
                "driver_mutations": {"A": sa["driver_mutations"], "D": sd["driver_mutations"]},
                "decision_routes": {"A": structural["arms"]["A"]["decision_routes"],
                                    "D": structural["arms"]["D"]["decision_routes"]}},
            "guard_matrix": guard_rows,
            "dc06_missing_scope_fact": guard_rows["DC06/only"],
        },
        "work_deleted_vs_wallclock": {
            "work_deleted_UNIT": "chooser decisions per task A 2 -> D 1; PR 4316 program creation 0 -> 1 and verification "
                                 "0 -> 1 call per task; snapshots, mutations and tool sequence unchanged",
            "work_deleted_REAL": deleted_real,
            "wallclock_REAL": verdicts or "BLOCKED",
            "deleted_decision_cost_with_mock": "about 0 ms expected (B-01 K0n vs K0: -2.1 [-9.3, 3.5] ms); not measured here",
            "live_provider_value": "BLOCKED pending owner budget (R2-03's live -212 ms on 0.31.0 is not borrowed or summed)",
        },
        "disposition": disp,
        "provisional_from_unit": ("REVISE D expected: given a fresh snapshot with one role=button name=Submit action ref, "
                                  "PR 4316's guard accepts a Submit relocated into a different form (DC06), because it "
                                  "binds role + name + uniqueness only; this is UNIT evidence on the caller logic and "
                                  "still needs the REAL DC06 run"),
    }
    rows = [D.ledger_row(t, LANE) for t in trials]
    cells: dict[str, Any] = {"lane": LANE, "task": "jev-use FixtureFormTask fill->submit", "cells": []}
    for comp, conds in CONDITIONS.items():
        for cond in conds:
            for arm in ("A", "D"):
                n = sum(1 for t in measured if t["summary"].get("comparison") == comp
                        and t["summary"].get("condition") == cond and t["summary"]["arm"] == arm)
                cells["cells"].append({"comparison": comp, "condition": cond, "arm": arm, "trials": n,
                                       "label": "BENCHMARK" if n else "BLOCKED", "reason": None if n else BLOCKER})
    for cid in d_plan.CONTROLS:
        for arm in ("A", "D"):
            n = sum(1 for t in measured if t["summary"].get("control") == cid and t["summary"]["arm"] == arm)
            cells["cells"].append({"comparison": "controls", "condition": cid, "arm": arm, "trials": n,
                                   "label": "FIXTURE (REAL)" if n else "BLOCKED", "reason": None if n else BLOCKER,
                                   "unit_expectation": [k for k in guard_rows if k.startswith(cid + "/")]})
    cells["cells"].append({"comparison": "CMP-D live provider", "label": "BLOCKED", "reason": "owner budget (TypeSafe reserved for R2-10)"})
    return summary, rows, cells


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, default=str) + "\n"


def main() -> None:
    raw = HERE / "raw"
    summary, rows, cells = build(raw)
    texts = {HERE / "d-summary.json": dump(summary),
             HERE / "ledger" / "i107-d-ledger.jsonl": "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows),
             HERE / "ledger" / "cells.json": dump(cells)}
    if "--check" in sys.argv:
        bad = [p.name for p, t in texts.items() if not p.exists() or p.read_text() != t]
        print("analyze --check:", "OK" if not bad else f"DIFFERS {bad}")
        sys.exit(1 if bad else 0)
    (HERE / "ledger").mkdir(exist_ok=True)
    for p, t in texts.items():
        p.write_text(t)
    print(json.dumps({"real": summary["real"]["status"], "disposition": summary["disposition"]}, indent=1))


if __name__ == "__main__":
    main()

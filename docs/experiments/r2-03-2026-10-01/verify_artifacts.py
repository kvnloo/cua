#!/usr/bin/env python3
"""Recompute every R2-03 headline number from raw/ and check it against r2-03-summary.json.

usage: python3 verify_artifacts.py           # verify (exit 1 on any mismatch or failed check)
       python3 verify_artifacts.py --write   # (re)write r2-03-summary.json from raw/

Standard library only. All timestamps in raw/ are CLOCK_MONOTONIC nanoseconds from the same host,
shared by the harness process (oracle, spawn, exit, submit instants) and the runner process
(receipts), so cross-process differences are valid without clock alignment.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
RAW = R / "raw"
SEED = 20261001
RESAMPLES = 10000
REQUEST_CAP = 300
SPAN_KEYS = ("semantic_observe_ms", "visual_observe_ms", "candidate_build_ms", "provider_decision_ms", "action_ms")


def load_trial(path: Path) -> dict:
    cell, events, receipts = None, [], []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        kind = row.pop("type")
        if kind == "cell":
            cell = row
        elif kind == "runner_event":
            events.append(row)
        elif kind == "receipt":
            receipts.append(row)
    assert cell is not None, path
    return {"cell": cell, "events": events, "receipts": sorted(receipts, key=lambda r: r["seq"])}


def ms(a: int | None, b: int | None) -> float | None:
    return None if a is None or b is None else round((b - a) / 1e6, 3)


def derive(trial: dict) -> dict:
    cell, receipts = trial["cell"], trial["receipts"]
    events = [row["event"] for row in trial["events"]]
    steps = [e for e in events if e.get("event") == "step"]
    outcomes = [e for e in events if e.get("event") == "outcome"]
    driver = [r for r in receipts if r.get("kind") == "driver_call"]
    http = [r for r in receipts if r.get("kind") == "http_attempt"]
    provider = [r for r in receipts if r.get("kind") == "provider_response"]
    live_ok = [r for r in provider if r.get("ok") and r.get("backend") == "typesafe"]
    http_ok = [r for r in http if r.get("status") == 200 and r.get("host") == "api.typesafe.ai" and r.get("request_id_present")]
    snapshots = [r for r in driver if r["tool"] == "get_browser_state" and r.get("arg_snapshot_format")]
    first_semantic = snapshots[0]["t_start_ns"] if snapshots else None
    types = [r for r in driver if r["tool"] == "browser_type"]
    clicks = [r for r in driver if r["tool"] == "browser_click"]

    def latest_snapshot_before(seq: int) -> dict | None:
        prior = [s for s in snapshots if s["seq"] < seq]
        return prior[-1] if prior else None

    ref_checks = []
    for click in clicks:
        post = latest_snapshot_before(click["seq"])
        pre_type = [t for t in types if t["seq"] < click["seq"]]
        pre = latest_snapshot_before(pre_type[0]["seq"]) if pre_type else None
        ref_checks.append(
            {
                "dispatched_ref": click.get("arg_ref"),
                "post_mutation_submit_refs": post.get("submit_refs") if post else None,
                "pre_mutation_submit_refs": pre.get("submit_refs") if pre else None,
                "uses_latest_snapshot_ref": bool(post) and click.get("arg_ref") in (post.get("submit_refs") or []),
                "reuses_pre_mutation_ref": bool(pre) and click.get("arg_ref") in (pre.get("submit_refs") or []),
                "route": click.get("result", {}).get("route"),
                "effect": click.get("result", {}).get("effect"),
                "ok": click.get("ok"),
            }
        )
    guarded_steps = [s for s in steps if s.get("decision_route") == "guarded-completion"]
    guarded_proofs = []
    for step in guarded_steps:
        proof = step.get("guarded_completion") or {}
        dispatched = ref_checks[-1]["dispatched_ref"] if ref_checks else None
        guarded_proofs.append(
            {
                "status": proof.get("status"),
                "prior_ref": proof.get("prior_ref"),
                "fresh_ref": proof.get("fresh_ref"),
                "fresh_equals_dispatched": proof.get("fresh_ref") == dispatched,
                "prior_differs_from_fresh": proof.get("prior_ref") != proof.get("fresh_ref"),
                "provider_decision_ms": step.get("provider_decision_ms"),
            }
        )
    declines = [s.get("guarded_completion") for s in steps if isinstance(s.get("guarded_completion"), dict) and s["guarded_completion"].get("status") == "declined"]
    stale_dispatch = sum(1 for c in ref_checks if c["reuses_pre_mutation_ref"] or not c["uses_latest_snapshot_ref"])

    if cell.get("harness_error"):
        outcome = "harness_error"
    elif cell.get("independently_verified"):
        outcome = "verified"
    elif cell.get("timed_out"):
        outcome = "timed_out"
    elif outcomes:
        outcome = outcomes[-1].get("outcome") or "unknown"
        outcome = "unknown" if outcome == "verified" else outcome  # runner claim without oracle support
    else:
        outcome = "runner_error"

    named = sum(float(s.get(k) or 0) for s in steps for k in SPAN_KEYS)
    task_verified = ms(first_semantic, cell.get("oracle_seen_ns")) if cell.get("independently_verified") else None
    return {
        "cell_id": cell["cell_id"], "phase": cell["phase"], "pair": cell["pair"], "order": cell["order"], "arm": cell["arm"],
        "provider_configured": cell.get("provider_configured"),
        "outcome": outcome, "verified": bool(cell.get("independently_verified")), "rc": cell.get("rc"),
        "submit_count": cell.get("submit_count"), "final_state_matches": cell.get("final_state") == {"submitted": cell.get("token")},
        "decision_routes": [s.get("decision_route") for s in steps],
        "candidates": [s.get("candidate") for s in steps],
        "runner_provider_decisions": sum(1 for s in steps if s.get("decision_route") == "provider") + sum(1 for o in outcomes if o.get("outcome") == "abstained" and "confidence" in o),
        "guarded_decisions": len(guarded_steps),
        "provider_responses_receipt": len(live_ok),
        "provider_http_200_receipt": len(http_ok),
        "provider_http_attempts": len(http),
        "provider_errors": [r.get("error") for r in provider if not r.get("ok")],
        "mock_responses": sum(1 for r in provider if r.get("backend") == "mock"),
        "provider_models": sorted({r.get("model") for r in live_ok if r.get("model")}),
        "provider_hosts": sorted({r.get("host") for r in http if r.get("host")}),
        "input_tokens": sum(int(r.get("input_tokens") or 0) for r in live_ok),
        "output_tokens": sum(int(r.get("output_tokens") or 0) for r in live_ok),
        "provider_decision_ms": [s.get("provider_decision_ms") for s in steps if s.get("decision_route") == "provider"],
        "provider_http_ms": [ms(r["t_start_ns"], r["t_end_ns"]) for r in http],
        "driver_actions": len(types) + len(clicks),
        "driver_action_routes": [t.get("result", {}).get("route") for t in types] + [c["route"] for c in ref_checks],
        "semantic_observations": len(snapshots),
        "visual_statuses": [(s.get("visual") or {}).get("status") for s in steps],
        "ref_checks": ref_checks, "guarded_proofs": guarded_proofs, "guard_declines": declines,
        "stale_dispatch": stale_dispatch,
        "task_verified_ms": task_verified,
        "spawn_verified_ms": ms(cell.get("spawn_ns"), cell.get("oracle_seen_ns")) if cell.get("independently_verified") else None,
        "task_mutation_ms": ms(first_semantic, (cell.get("submit_ns") or [None])[0]),
        "cold_setup_ms": ms(cell.get("spawn_ns"), first_semantic),
        "runner_lifetime_ms": ms(cell.get("spawn_ns"), cell.get("exit_ns")),
        "cleanup_after_outcome_ms": ms(cell.get("oracle_seen_ns"), cell.get("exit_ns")),
        "named_step_span_ms": round(named, 2),
        "named_span_coverage": round(named / task_verified, 4) if task_verified else None,
        "loadavg_at_spawn": cell.get("loadavg_at_spawn"), "loadavg_at_exit": cell.get("loadavg_at_exit"),
        "leftover_processes_killed": cell.get("leftover_processes_killed"),
    }


def q(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo), 3)


def describe(values: list[float]) -> dict | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"n": len(values), "median": round(statistics.median(values), 3), "mean": round(statistics.fmean(values), 3),
            "p05": q(values, 0.05), "p95": q(values, 0.95), "min": round(min(values), 3), "max": round(max(values), 3)}


def bootstrap(diffs: list[float], fn) -> list[float]:
    rng = random.Random(SEED)
    stats = sorted(fn([rng.choice(diffs) for _ in diffs]) for _ in range(RESAMPLES))
    return [round(stats[int(0.025 * RESAMPLES)], 3), round(stats[int(0.975 * RESAMPLES) - 1], 3)]


def paired(rows: list[dict], field: str) -> dict:
    by_pair: dict[int, dict] = {}
    for row in rows:
        by_pair.setdefault(row["pair"], {})[row["arm"]] = row
    diffs, excluded = [], []
    for pair in sorted(by_pair):
        cells = by_pair[pair]
        base, treat = cells.get("baseline"), cells.get("guarded")
        if not base or not treat or base.get(field) is None or treat.get(field) is None:
            excluded.append({"pair": pair, "baseline": base and base["outcome"], "guarded": treat and treat["outcome"]})
            continue
        diffs.append(round(treat[field] - base[field], 3))
    if not diffs:
        return {"n_pairs": 0, "excluded": excluded}
    return {
        "n_pairs": len(diffs), "excluded": excluded,
        "median_diff_ms": round(statistics.median(diffs), 3), "mean_diff_ms": round(statistics.fmean(diffs), 3),
        "bootstrap95_median": bootstrap(diffs, statistics.median), "bootstrap95_mean": bootstrap(diffs, statistics.fmean),
        "guarded_faster": sum(d < 0 for d in diffs), "guarded_slower": sum(d > 0 for d in diffs),
        "diffs_ms": diffs,
    }


def load_phase(name: str) -> list[dict]:
    directory = RAW / name
    return [derive(load_trial(p)) for p in sorted(directory.glob("*.jsonl"))] if directory.exists() else []


def arm_summary(rows: list[dict]) -> dict:
    outcomes: dict[str, int] = {}
    for row in rows:
        outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
    verified = [r for r in rows if r["verified"]]
    return {
        "attempted": len(rows), "verified": len(verified), "outcomes": dict(sorted(outcomes.items())),
        "route_patterns": dict(sorted({str(r["decision_routes"]): sum(1 for x in rows if x["decision_routes"] == r["decision_routes"]) for r in rows}.items())),
        "provider_responses_total": sum(r["provider_responses_receipt"] for r in rows),
        "provider_http_attempts_total": sum(r["provider_http_attempts"] for r in rows),
        "provider_responses_per_verified_trial": describe([r["provider_responses_receipt"] for r in verified]),
        "runner_provider_decisions_per_verified_trial": describe([r["runner_provider_decisions"] for r in verified]),
        "receipt_matches_runner_decisions": all(r["provider_responses_receipt"] == r["runner_provider_decisions"] == r["provider_http_200_receipt"] for r in rows),
        "input_tokens_total": sum(r["input_tokens"] for r in rows), "output_tokens_total": sum(r["output_tokens"] for r in rows),
        "input_tokens_per_verified_trial": describe([r["input_tokens"] for r in verified]),
        "output_tokens_per_verified_trial": describe([r["output_tokens"] for r in verified]),
        "provider_decision_ms": describe([v for r in rows for v in r["provider_decision_ms"]]),
        "provider_http_ms": describe([v for r in rows for v in r["provider_http_ms"]]),
        "provider_decision_ms_per_verified_trial": describe([sum(r["provider_decision_ms"]) for r in verified]),
        "models": sorted({m for r in rows for m in r["provider_models"]}),
        "hosts": sorted({h for r in rows for h in r["provider_hosts"]}),
        "driver_actions_per_verified_trial": describe([r["driver_actions"] for r in verified]),
        "semantic_observations_per_verified_trial": describe([r["semantic_observations"] for r in verified]),
        "driver_action_routes": sorted({str(r["driver_action_routes"]) for r in rows}),
        "visual_statuses": sorted({str(r["visual_statuses"]) for r in rows}),
        "stale_dispatch_total": sum(r["stale_dispatch"] for r in rows),
        "clicks_using_latest_snapshot_ref": sum(c["uses_latest_snapshot_ref"] for r in rows for c in r["ref_checks"]),
        "clicks_total": sum(len(r["ref_checks"]) for r in rows),
        "duplicate_submits": sum(1 for r in rows if (r["submit_count"] or 0) > 1),
        "timing": {k: describe([r[k] for r in verified]) for k in ("task_verified_ms", "spawn_verified_ms", "task_mutation_ms", "cold_setup_ms", "runner_lifetime_ms", "cleanup_after_outcome_ms")},
        "named_span_coverage": describe([r["named_span_coverage"] for r in verified]),
        "leftover_processes_killed": sum(len(r["leftover_processes_killed"] or []) for r in rows),
    }


def summarize() -> dict:
    main = load_phase("main")
    smoke, decline, unreachable = load_phase("smoke"), load_phase("controls-c1-decline"), load_phase("controls-c2-unreachable")
    validity = {p.stem: json.loads(p.read_text()) for p in sorted((RAW / "validity").glob("*.json"))}
    budget = json.loads((RAW / "budget.json").read_text())
    base = [r for r in main if r["arm"] == "baseline"]
    guard = [r for r in main if r["arm"] == "guarded"]
    pairs_complete = sorted({r["pair"] for r in base} & {r["pair"] for r in guard}
                            - {r["pair"] for r in main if r["outcome"] == "harness_error"})
    accepted = [p for r in guard for p in r["guarded_proofs"]]
    guarded_route_verified = [r for r in guard if r["verified"] and r["decision_routes"] == ["provider", "guarded-completion"]]
    baseline_route_verified = [r for r in base if r["verified"] and r["decision_routes"] == ["provider", "provider"]]
    orders = {}
    for r in main:
        orders.setdefault(r["pair"], []).append((r["order"], r["arm"]))
    interleave_ok = all(
        [a for _, a in sorted(v)] == (["baseline", "guarded"] if pair % 2 else ["guarded", "baseline"]) for pair, v in orders.items()
    )
    loads = [float(r["loadavg_at_spawn"][0]) for r in main if r.get("loadavg_at_spawn")]

    timing = {k: paired(main, k) for k in ("task_verified_ms", "spawn_verified_ms", "task_mutation_ms", "cold_setup_ms", "runner_lifetime_ms")}
    deleted_requests = paired(main, "provider_responses_receipt")
    deleted_tokens_in = paired(main, "input_tokens")
    deleted_tokens_out = paired(main, "output_tokens")
    provider_ms_rows = [dict(r, provider_ms_sum=sum(r["provider_decision_ms"]) if r["verified"] else None) for r in main]
    deleted_provider_ms = paired(provider_ms_rows, "provider_ms_sum")

    validity_ok = all(v.get("ok") for k, v in validity.items() if not k.startswith("smoke")) and len(pairs_complete) >= 30
    kill = []
    if any(r["stale_dispatch"] for r in main + decline):
        kill.append("stale_ref_dispatch")
    if any(r["outcome"] != "verified" for r in guard if r["guarded_decisions"]):
        kill.append("guarded_completion_not_verified")
    if any((r["submit_count"] or 0) > 1 for r in main + decline):
        kill.append("duplicate_submission")
    if any(p["status"] == "accepted" for r in decline for p in r["guarded_proofs"]):
        kill.append("guard_accepted_in_decline_control")
    structural = (
        bool(guarded_route_verified)
        and all(r["provider_responses_receipt"] == 1 for r in guarded_route_verified)
        and all(r["provider_responses_receipt"] == 2 for r in baseline_route_verified)
        and statistics.median([r["provider_responses_receipt"] for r in guard if r["verified"]] or [99])
        < statistics.median([r["provider_responses_receipt"] for r in base if r["verified"]] or [0])
    )
    if not structural:
        kill.append("structural_deletion_absent")
    primary = timing["task_verified_ms"]
    if not validity_ok:
        disposition = "BLOCKED"
    elif kill:
        disposition = "KILL"
    elif primary.get("n_pairs") and primary["median_diff_ms"] < 0 and primary["bootstrap95_median"][1] < 0:
        disposition = "KEEP"
    else:
        disposition = "REVISE"
    reliability_gap = len([r for r in base if r["verified"]]) - len([r for r in guard if r["verified"]])

    return {
        "schema": "cua.r2.r2-03.summary.v1",
        "seed": SEED, "resamples": RESAMPLES,
        "validity": {
            "phases": {k: {key: v.get(key) for key in ("ok", "examples_identical_to_tested_sha", "driver_sha256", "forbidden_env_present", "harness_sha256", "launcher_sha256", "run_py_sha256", "fixture_server_sha256", "tested_sha", "head")} for k, v in validity.items()},
            "pairs_planned": 40, "pairs_complete": len(pairs_complete), "ab_ba_alternation_ok": interleave_ok,
            "loadavg1_at_spawn": describe(loads),
            "request_budget": {"cap": REQUEST_CAP, "http_attempts_used": budget["http_attempts"], "includes_loopback_refused_attempts_of_C2": sum(r["provider_http_attempts"] for r in unreachable)},
        },
        "main": {"baseline": arm_summary(base), "guarded": arm_summary(guard)},
        "fresh_ref_proof": {
            "guarded_accepted": sum(1 for p in accepted if p["status"] == "accepted"),
            "guarded_fresh_equals_dispatched": sum(1 for p in accepted if p["fresh_equals_dispatched"]),
            "guarded_prior_differs_from_fresh": sum(1 for p in accepted if p["prior_differs_from_fresh"]),
            "guarded_provider_decision_ms_zero": sum(1 for p in accepted if p["provider_decision_ms"] == 0),
            "guard_declines_main": [d for r in guard for d in r["guard_declines"]],
            "stale_dispatch_main": sum(r["stale_dispatch"] for r in main),
        },
        "paired_guarded_minus_baseline": {**timing, "provider_responses": deleted_requests, "input_tokens": deleted_tokens_in,
                                          "output_tokens": deleted_tokens_out, "provider_decision_ms_sum": deleted_provider_ms},
        "controls": {
            "C0_mock_smoke": {"cells": len(smoke), "verified": sum(r["verified"] for r in smoke), "mock_responses": sum(r["mock_responses"] for r in smoke),
                              "provider_http_attempts": sum(r["provider_http_attempts"] for r in smoke), "routes": [r["decision_routes"] for r in smoke]},
            "C1_guard_decline": {"cells": len(decline), "verified": sum(r["verified"] for r in decline), "routes": [r["decision_routes"] for r in decline],
                                 "declines": [d for r in decline for d in r["guard_declines"]], "provider_responses": [r["provider_responses_receipt"] for r in decline],
                                 "stale_dispatch": sum(r["stale_dispatch"] for r in decline), "submit_counts": [r["submit_count"] for r in decline]},
            "C2_provider_unreachable": {"cells": len(unreachable), "verified": sum(r["verified"] for r in unreachable), "outcomes": [r["outcome"] for r in unreachable],
                                        "successful_provider_responses": sum(r["provider_responses_receipt"] for r in unreachable),
                                        "provider_errors": [r["provider_errors"] for r in unreachable], "http_hosts": sorted({h for r in unreachable for h in r["provider_hosts"]}),
                                        "driver_actions": sum(r["driver_actions"] for r in unreachable), "submit_counts": [r["submit_count"] for r in unreachable]},
        },
        "gates": {"validity_ok": validity_ok, "kill_conditions": kill, "structural_deletion": structural,
                  "verified_gap_baseline_minus_guarded": reliability_gap, "disposition": disposition},
        "trials": main + decline + unreachable + smoke,
    }


PRIVACY = [re.compile(p) for p in (r"/home/\w", r"/mnt/\w", r"/tmp/\w", r"(?i)bearer \w", r"x11-session\.[A-Za-z0-9]{6}")]


def privacy_scan() -> list[str]:
    hits = []
    for path in sorted(R.rglob("*")):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".txt", ".py", ".sh"}:
            text = path.read_text(errors="replace")
            for pattern in PRIVACY:
                if pattern.search(text) and path.name != "verify_artifacts.py":
                    hits.append(f"{path.relative_to(R)}: {pattern.pattern}")
    return hits


def main() -> int:
    summary = summarize()
    target = R / "r2-03-summary.json"
    if "--write" in sys.argv:
        target.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        print(f"wrote {target.name}: disposition {summary['gates']['disposition']}")
        return 0
    stored = json.loads(target.read_text())
    problems = []
    if stored != json.loads(json.dumps(summary, sort_keys=True)):
        problems.append("r2-03-summary.json differs from recomputation")
    problems += [f"privacy: {h}" for h in privacy_scan()]
    prereg = json.loads((R / "PREREG.json").read_text())
    if prereg["design"]["n_pairs_planned"] != 40:
        problems.append("prereg mismatch")
    main_rows = summary["main"]
    readme = (R / "README.md").read_text()
    for needle in (
        f"{main_rows['baseline']['verified']}/{main_rows['baseline']['attempted']}",
        f"{main_rows['guarded']['verified']}/{main_rows['guarded']['attempted']}",
        str(summary["paired_guarded_minus_baseline"]["task_verified_ms"]["median_diff_ms"]),
        summary["gates"]["disposition"],
    ):
        if needle not in readme:
            problems.append(f"README missing headline value {needle!r}")
    for problem in problems:
        print("FAIL", problem)
    if problems:
        return 1
    p = summary["paired_guarded_minus_baseline"]["task_verified_ms"]
    print(
        "OK: baseline verified {}/{}, guarded verified {}/{}; provider responses per verified trial {} -> {}; "
        "paired task_verified_ms median {} ms, 95% CI {} over {} pairs; disposition {}".format(
            main_rows["baseline"]["verified"], main_rows["baseline"]["attempted"],
            main_rows["guarded"]["verified"], main_rows["guarded"]["attempted"],
            main_rows["baseline"]["provider_responses_per_verified_trial"]["median"],
            main_rows["guarded"]["provider_responses_per_verified_trial"]["median"],
            p["median_diff_ms"], p["bootstrap95_median"], p["n_pairs"], summary["gates"]["disposition"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Analyze an ab_harness.py run: work counts, hard invariants, timing tables, MCP-trace proofs.

usage: analyze.py RUN_DIR [--md OUT.md] [--json OUT.json]

Nothing here re-times anything: every number comes from cells.jsonl (runner JSONL + independent
fixture-oracle timeline) or from mcp-trace.jsonl (the recorded MCP conversation).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

STEP_FIELDS = (
    "semantic_observe_ms", "visual_observe_ms", "candidate_build_ms", "provider_decision_ms",
    "decision_ms", "action_ms", "total_step_ms",
)
BASELINE = "main-default"
DEFAULT_PR = "pr4316-default"
GUARDED = "pr4316-guarded"


def q(values, p) -> float:
    values = sorted(v for v in values if v is not None)
    if not values:
        return float("nan")
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def stat(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {
        "n": len(values), "min": round(min(values), 2), "p25": round(q(values, 0.25), 2),
        "median": round(statistics.median(values), 2), "mean": round(statistics.fmean(values), 2),
        "p75": round(q(values, 0.75), 2), "max": round(max(values), 2),
    }


def load(run: Path):
    manifest = json.loads((run / "manifest.json").read_text())
    cells = [json.loads(line) for line in (run / "cells.jsonl").read_text().splitlines() if line.strip()]
    return manifest, cells


def step(cell, index):
    steps = cell.get("steps") or []
    return steps[index] if len(steps) > index else {}


def invariants(cell):
    """Return a list of violated hard invariants for one cell (empty == all hold)."""
    bad = []
    arm = cell["arm"]
    if not cell.get("independently_verified"):
        bad.append("independent fixture /state did not verify the outcome")
    counts = cell.get("counts") or {}
    routes = cell.get("decision_routes")
    if arm == GUARDED:
        if routes != ["provider", "guarded-completion"]:
            bad.append(f"decision_routes={routes}")
        if counts.get("provider_decisions") != 1:
            bad.append(f"provider_decisions={counts.get('provider_decisions')} (want 1)")
        if step(cell, 1).get("provider_decision_ms") != 0.0:
            bad.append(f"guarded step provider_decision_ms={step(cell, 1).get('provider_decision_ms')} (want exactly 0.0)")
        if counts.get("semantic_observations") != 2:
            bad.append(f"semantic_observations={counts.get('semantic_observations')} (guarded must still observe fresh)")
        if counts.get("driver_actions") != 2:
            bad.append(f"driver_actions={counts.get('driver_actions')} (want 2)")
    elif arm in (BASELINE, DEFAULT_PR):
        want = [None, None] if arm == BASELINE else ["provider", "provider"]
        if routes != want:
            bad.append(f"decision_routes={routes} (want {want})")
        if counts.get("provider_decisions") != 2:
            bad.append(f"provider_decisions={counts.get('provider_decisions')} (want 2)")
        if counts.get("semantic_observations") != 2 or counts.get("driver_actions") != 2:
            bad.append("observation/action counts differ from 2/2")
    if counts.get("visual_observations"):
        bad.append(f"visual_observations={counts['visual_observations']} (default fixture has a page ref; want 0)")
    return bad


def summarize_group(cells):
    rows = {}
    for (arm, lang), group in sorted(cells.items()):
        row = {
            "n": len(group),
            "independently_verified": sum(bool(c.get("independently_verified")) for c in group),
            "errors": [c["cell_id"] + ": " + str(c["error"]) for c in group if c.get("error")],
            "counts": {
                key: {"min": min(c["counts"][key] for c in group if "counts" in c),
                      "max": max(c["counts"][key] for c in group if "counts" in c)}
                for key in ("provider_decisions", "guarded_decisions", "semantic_observations",
                            "visual_observations", "driver_actions", "action_errors_or_refusals",
                            "abstentions", "reobserves")
                if any("counts" in c for c in group)
            },
            "verified_outcome_ms": stat([c.get("verified_outcome_ms") for c in group]),
            "state_changed_ms": stat([(c.get("timeline_ms") or {}).get("state_changed_ms") for c in group]),
            "runner_lifetime_ms": stat([c.get("runner_lifetime_ms") for c in group]),
            "cleanup_after_outcome_ms": stat([c.get("cleanup_after_outcome_ms") for c in group]),
            "named_step_span_sum_ms": stat([c.get("named_step_span_sum_ms") for c in group]),
            "step": {},
        }
        for idx in (0, 1):
            row["step"][str(idx + 1)] = {f: stat([step(c, idx).get(f) for c in group]) for f in STEP_FIELDS}
        rows[f"{arm}/{lang}"] = row
    return rows


def bootstrap_median_ci(diffs, seed=7, n=10000):
    if not diffs:
        return None
    rng = random.Random(seed)
    meds = []
    for _ in range(n):
        sample = [diffs[rng.randrange(len(diffs))] for _ in diffs]
        meds.append(statistics.median(sample))
    meds.sort()
    return [round(meds[int(0.025 * n)], 2), round(meds[int(0.975 * n)], 2)]


def paired(cells, treat, base, field_fn):
    """Per-(block, language) paired difference treat - base."""
    by = defaultdict(dict)
    for c in cells:
        if c["arm"] in (treat, base) and c.get("independently_verified"):
            by[(c["block"], c["language"])][c["arm"]] = field_fn(c)
    diffs = [v[treat] - v[base] for v in by.values() if treat in v and base in v and None not in (v[treat], v[base])]
    if not diffs:
        return {"n": 0}
    return {
        "n": len(diffs), "median_diff_ms": round(statistics.median(diffs), 2),
        "mean_diff_ms": round(statistics.fmean(diffs), 2),
        "bootstrap95_of_median": bootstrap_median_ci(diffs),
        "treat_faster_in": sum(d < 0 for d in diffs), "treat_slower_in": sum(d > 0 for d in diffs),
    }


# ----------------------------------------------------------------------------- MCP trace proofs


def load_trace(path: Path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    start = next(r for r in rows if r.get("dir") == "proxy" and r.get("event") == "start")
    calls, pending = [], {}
    for r in rows:
        if r.get("dir") == "c2s" and r["msg"].get("method") == "tools/call":
            pending[r["msg"]["id"]] = {
                "name": r["msg"]["params"]["name"],
                "args": {k: v for k, v in r["msg"]["params"].get("arguments", {}).items() if k != "session"},
                "t_req_ns": r["t_ns"],
            }
        elif r.get("dir") == "s2c" and "id" in r["msg"] and r["msg"]["id"] in pending:
            call = pending.pop(r["msg"]["id"])
            call["t_resp_ns"] = r["t_ns"]
            call["result"] = r["msg"].get("result")
            call["error"] = r["msg"].get("error")
            calls.append(call)
    meta = {"mono_ns0": start["mono_ns0"]}
    init = [r for r in rows if r.get("dir") == "c2s" and r["msg"].get("method") in ("initialize", "tools/list")]
    meta["first_message_ns"] = init[0]["t_ns"] if init else None
    return calls, meta


def snapshot_refs(call):
    result = call.get("result") or {}
    sc = result.get("structuredContent") if isinstance(result, dict) else None
    refs = (sc or {}).get("refs") or []
    return [(r.get("ref"), r.get("role"), r.get("name")) for r in refs if isinstance(r, dict)]


def trace_proof(cell, run: Path):
    calls, meta = load_trace(run / cell["trace_file"])
    semantic = [c for c in calls if c["name"] == "get_browser_state" and c["args"].get("snapshot_format") == "semantic_v2"]
    actions = [c for c in calls if c["name"] in ("browser_type", "browser_click", "click", "type_text", "set_value")]
    visual = [c for c in calls if c["name"] in ("parse_visual_regions", "get_window_state")]
    proof = {
        "cell_id": cell["cell_id"], "arm": cell["arm"], "language": cell["language"],
        "mcp_calls": [c["name"] for c in calls],
        "semantic_snapshots": len(semantic), "driver_actions": len(actions), "visual_calls": len(visual),
        "action_refs": [(a["name"], a["args"].get("ref")) for a in actions],
        "snapshot_refs": [snapshot_refs(s) for s in semantic],
    }
    ok_fresh, detail = True, []
    for a in actions:
        ref = a["args"].get("ref")
        prior = [s for s in semantic if s["t_resp_ns"] <= a["t_req_ns"]]
        latest = prior[-1] if prior else None
        in_latest = latest is not None and any(r[0] == ref for r in snapshot_refs(latest))
        # the snapshot that minted the ref must have been taken after every earlier state-changing action
        earlier_actions = [x for x in actions if x["t_resp_ns"] <= (latest["t_req_ns"] if latest else 0)]
        detail.append({"action": a["name"], "ref": ref, "ref_in_latest_snapshot": in_latest,
                       "latest_snapshot_index": semantic.index(latest) if latest else None,
                       "earlier_actions_before_that_snapshot": len(earlier_actions)})
        ok_fresh &= in_latest
    proof["fresh_ref_provenance"] = detail
    if len(semantic) >= 2 and len(actions) >= 2:
        s1 = {(r[1], r[2]): r[0] for r in snapshot_refs(semantic[0])}
        s2 = {(r[1], r[2]): r[0] for r in snapshot_refs(semantic[1])}
        pre_submit, post_submit = s1.get(("button", "Submit")), s2.get(("button", "Submit"))
        used = actions[1]["args"].get("ref")
        proof["pre_mutation_submit_ref"] = pre_submit
        proof["post_mutation_submit_ref"] = post_submit
        proof["second_action_ref"] = used
        proof["ref_changed_after_mutation"] = pre_submit != post_submit
        proof["stale_ref_reused"] = bool(used == pre_submit and pre_submit != post_submit)
        proof["second_action_used_post_mutation_ref"] = used == post_submit
        proof["second_snapshot_requested_after_first_action_completed"] = semantic[1]["t_req_ns"] >= actions[0]["t_resp_ns"]
    proof["all_action_refs_from_latest_snapshot"] = ok_fresh
    # timeline decomposition relative to runner spawn
    spawn_ns = cell["mono_spawn_ns"]
    to_ms = lambda ns: round((meta["mono_ns0"] + ns - spawn_ns) / 1e6, 2)  # noqa: E731
    outcome_ms = (cell.get("timeline_ms") or {}).get("state_changed_ms")
    spans = [{"name": "runner_startup_until_driver_proxy_started", "ms": round((meta["mono_ns0"] - spawn_ns) / 1e6, 2)}]
    covered = spans[0]["ms"]
    last_end = to_ms(meta["first_message_ns"]) if meta["first_message_ns"] is not None else None
    for c in calls:
        t0, t1 = to_ms(c["t_req_ns"]), to_ms(c["t_resp_ns"])
        dur = round(t1 - t0, 2)
        if outcome_ms is not None:
            dur_before = max(0.0, min(t1, outcome_ms) - min(t0, outcome_ms))
        else:
            dur_before = dur
        spans.append({"name": c["name"], "start_ms": t0, "ms": dur, "ms_before_outcome": round(dur_before, 2)})
        covered += dur_before
    proof["timeline_spans"] = spans
    proof["mcp_call_ms_before_outcome"] = round(sum(s.get("ms_before_outcome", 0) for s in spans[1:]), 2)
    proof["driver_proxy_startup_ms"] = spans[0]["ms"]
    if outcome_ms is not None:
        steps = cell.get("steps") or []
        runner_compute = sum((s.get("candidate_build_ms") or 0) + (s.get("provider_decision_ms") or 0) for s in steps)
        proof["state_changed_ms"] = outcome_ms
        proof["runner_reported_compute_ms(candidate_build+provider)"] = round(runner_compute, 2)
        named = spans[0]["ms"] + proof["mcp_call_ms_before_outcome"] + runner_compute
        proof["named_span_ms"] = round(named, 2)
        proof["residual_ms"] = round(outcome_ms - named, 2)
        proof["named_span_coverage_pct"] = round(100 * named / outcome_ms, 2)
    return proof


def call_signature(call):
    """Tool name + arguments with per-snapshot ids/refs/urls/targets removed (they legitimately vary)."""
    skip = {"ref", "target_id", "tab_id", "url", "pid", "window_id"}
    return (call["name"], tuple(sorted((k, json.dumps(v, sort_keys=True)) for k, v in call["args"].items() if k not in skip)))


def default_unchanged(cells, run):
    """main-default vs pr4316-default: same MCP call sequence, same events modulo the additive decision_route."""
    out = {}
    for lang in sorted({c["language"] for c in cells}):
        main = [c for c in cells if c["arm"] == BASELINE and c["language"] == lang and c.get("independently_verified")]
        pr = [c for c in cells if c["arm"] == DEFAULT_PR and c["language"] == lang and c.get("independently_verified")]
        traced_main = [c for c in main if c.get("traced")]
        traced_pr = [c for c in pr if c.get("traced")]
        seq_equal = None
        if traced_main and traced_pr:
            sig = lambda c: [call_signature(x) for x in load_trace(run / c["trace_file"])[0]]  # noqa: E731
            seqs_main = {json.dumps(sig(c)) for c in traced_main}
            seqs_pr = {json.dumps(sig(c)) for c in traced_pr}
            seq_equal = seqs_main == seqs_pr and len(seqs_main) == 1
        cand = lambda c: [s.get("candidate") for s in c["steps"]]  # noqa: E731
        tool = lambda c: [s.get("tool") for s in c["steps"]]  # noqa: E731
        out[lang] = {
            "main_cells": len(main), "pr_default_cells": len(pr),
            "candidate_sequences_main": sorted({json.dumps(cand(c)) for c in main}),
            "candidate_sequences_pr_default": sorted({json.dumps(cand(c)) for c in pr}),
            "tool_sequences_equal": {json.dumps(tool(c)) for c in main} == {json.dumps(tool(c)) for c in pr},
            "mcp_call_sequence_identical_across_traced_cells": seq_equal,
            "main_has_decision_route_field": any(any(s.get("decision_route") is not None for s in c["steps"]) for c in main),
            "pr_default_routes": sorted({json.dumps(c["decision_routes"]) for c in pr}),
        }
    return out


def to_markdown(res):
    lines = []
    w = lines.append
    w(f"# A/B analysis: {res['run']}\n")
    w(f"Driver: `{res['manifest']['driver_version']}` sha256 `{res['manifest']['driver_sha256'][:16]}…` (same binary in every arm)\n")
    w("Arms: " + ", ".join(f"`{a['name']}`@{a['head'][:9]} {a.get('flags') or ''}" for a in res["manifest"]["arms"]) + "\n")
    w(f"Cells: {res['n_cells']} total; clean {res['n_clean']}, traced {res['n_traced']}; "
      f"independently verified {res['n_verified']}/{res['n_cells']}; hard-invariant violations {len(res['invariant_violations'])}\n")
    w("## Work counts per cell (min–max over clean cells)\n")
    w("| arm/lang | n | verified | provider | guarded | semantic obs | visual obs | driver actions | refusals | abstentions |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for key, row in res["clean"].items():
        c = row["counts"]
        rng = lambda k: f"{c[k]['min']}" if c[k]["min"] == c[k]["max"] else f"{c[k]['min']}–{c[k]['max']}"  # noqa: E731
        w(f"| {key} | {row['n']} | {row['independently_verified']} | {rng('provider_decisions')} | {rng('guarded_decisions')} | "
          f"{rng('semantic_observations')} | {rng('visual_observations')} | {rng('driver_actions')} | "
          f"{rng('action_errors_or_refusals')} | {rng('abstentions')} |")
    w("\n## Independent outcome timing, ms (clean cells; median [p25–p75])\n")
    w("| arm/lang | verified_outcome (oracle /state) | state_changed (server) | runner_lifetime | cleanup_after_outcome |")
    w("|---|---|---|---|---|")
    fmt = lambda s: "n/a" if not s.get("n") else f"{s['median']} [{s['p25']}–{s['p75']}]"  # noqa: E731
    for key, row in res["clean"].items():
        w(f"| {key} | {fmt(row['verified_outcome_ms'])} | {fmt(row['state_changed_ms'])} | "
          f"{fmt(row['runner_lifetime_ms'])} | {fmt(row['cleanup_after_outcome_ms'])} |")
    for idx in ("1", "2"):
        w(f"\n## Runner-reported phase timing, step {idx}, ms (clean cells; median [p25–p75])\n")
        w("| arm/lang | semantic_observe | visual_observe | candidate_build | provider_decision | decision | action | total_step |")
        w("|---|---|---|---|---|---|---|---|")
        for key, row in res["clean"].items():
            s = row["step"][idx]
            w(f"| {key} | " + " | ".join(fmt(s[f]) for f in STEP_FIELDS) + " |")
    w("\n## Paired differences (guarded − main-default, same block & language)\n")
    w("| metric | n pairs | median diff ms | mean diff ms | bootstrap 95% CI of median | guarded faster / slower |")
    w("|---|---|---|---|---|---|")
    for name, p in res["paired_guarded_vs_main"].items():
        if not p.get("n"):
            continue
        w(f"| {name} | {p['n']} | {p['median_diff_ms']} | {p['mean_diff_ms']} | {p['bootstrap95_of_median']} | {p['treat_faster_in']} / {p['treat_slower_in']} |")
    w("\n## Hard-invariant violations\n")
    if res["invariant_violations"]:
        for v in res["invariant_violations"]:
            w(f"- `{v['cell_id']}`: " + "; ".join(v["violations"]))
    else:
        w("None: every guarded cell has routes `[provider, guarded-completion]`, exactly 1 provider decision, guarded step "
          "`provider_decision_ms == 0.0`, 2 fresh semantic observations, 2 actions; every baseline cell has 2 provider decisions.")
    w("\n## MCP-trace proof (traced cells)\n")
    w("| cell | semantic snapshots | actions | action refs | pre-mutation Submit ref | post-mutation Submit ref | 2nd action ref | stale reuse | ref from latest snapshot | 2nd snapshot after 1st action | named-span coverage % |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for p in res["trace_proofs"]:
        w(f"| {p['cell_id']} | {p['semantic_snapshots']} | {p['driver_actions']} | {p['action_refs']} | "
          f"{p.get('pre_mutation_submit_ref')} | {p.get('post_mutation_submit_ref')} | {p.get('second_action_ref')} | "
          f"{p.get('stale_ref_reused')} | {p['all_action_refs_from_latest_snapshot']} | "
          f"{p.get('second_snapshot_requested_after_first_action_completed')} | {p.get('named_span_coverage_pct')} |")
    w("\n## Default behavior unchanged without the flag (main vs #4316 head, flag off)\n")
    w("```json\n" + json.dumps(res["default_unchanged"], indent=1) + "\n```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--md", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    manifest, cells = load(args.run)
    clean = [c for c in cells if c.get("mode") == "clean"]
    traced = [c for c in cells if c.get("mode") == "traced"]

    groups = defaultdict(list)
    for c in clean:
        if "counts" in c:
            groups[(c["arm"], c["language"])].append(c)
    violations = []
    for c in cells:
        if "counts" not in c:
            violations.append({"cell_id": c["cell_id"], "violations": [f"cell did not complete: {c.get('error')}"]})
            continue
        bad = invariants(c)
        if bad:
            violations.append({"cell_id": c["cell_id"], "violations": bad})

    paired_metrics = {
        "verified_outcome_ms": lambda c: c.get("verified_outcome_ms"),
        "runner_lifetime_ms": lambda c: c.get("runner_lifetime_ms"),
        "cleanup_after_outcome_ms": lambda c: c.get("cleanup_after_outcome_ms"),
        "step2.provider_decision_ms": lambda c: step(c, 1).get("provider_decision_ms"),
        "step2.decision_ms": lambda c: step(c, 1).get("decision_ms"),
        "step2.total_step_ms": lambda c: step(c, 1).get("total_step_ms"),
    }
    paired_res = {name: paired(clean, GUARDED, BASELINE, fn) for name, fn in paired_metrics.items()}
    paired_default = {name: paired(clean, DEFAULT_PR, BASELINE, fn) for name, fn in paired_metrics.items()}

    proofs = [trace_proof(c, args.run) for c in traced if c.get("trace_file") and "counts" in c]
    res = {
        "run": str(args.run.name), "manifest": manifest, "n_cells": len(cells), "n_clean": len(clean),
        "n_traced": len(traced), "n_verified": sum(bool(c.get("independently_verified")) for c in cells),
        "clean": summarize_group(groups),
        "paired_guarded_vs_main": paired_res, "paired_pr_default_vs_main": paired_default,
        "invariant_violations": violations, "trace_proofs": proofs,
        "default_unchanged": default_unchanged(cells, args.run),
        "leftover_processes_killed": [c["cell_id"] for c in cells if c.get("leftover_processes_killed")],
        "errors": [{"cell_id": c["cell_id"], "error": c["error"]} for c in cells if c.get("error")],
    }
    if args.json:
        args.json.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    md = to_markdown(res)
    if args.md:
        args.md.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

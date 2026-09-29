#!/usr/bin/env python3
"""Where does the verified-outcome time go after guarded decision deletion? (RFC #3963, next-cost ranking)

Inputs: an A/B run directory (clean cells, runner-reported phases + independent oracle timeline) and
optionally a traced run directory (MCP call durations).  Output: next-cost-ranking.json / .md.

Phase definitions (per cell, ms, all relative to runner spawn):
  setup_before_step1   step-1 event arrival - step-1 total_step_ms   (runner import, Driver start, initialize,
                       tools/list, browser_prepare, window wait, bind, navigate, first oracle read)
  step{n}.<phase>      runner-reported semantic_observe / candidate_build / provider_decision / action
  step_gap             time between step events not inside a step (oracle read, log write)
  verify_tail          oracle first saw the verified state - last step event arrival
  cleanup_after        runner exit - oracle seen  (after the outcome; NOT part of verified-outcome time)
  residual             verified_outcome - all of the above except cleanup
"Counterfactual upper bound" = the median of a phase: the most that deleting the whole phase could save
verified-outcome time. It is an Amdahl-style decision tool, not a prediction.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path


def q(values, p):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 2)


def phases(cell: dict) -> dict[str, float]:
    steps = cell["steps"]
    tl = cell["timeline_ms"]
    arrivals = tl["step_event_arrival_ms"]
    out = {}
    out["setup_before_step1"] = arrivals[0] - steps[0]["total_step_ms"]
    named = 0.0
    for name in ("semantic_observe_ms", "candidate_build_ms", "provider_decision_ms", "action_ms"):
        out[name.replace("_ms", "")] = sum(s.get(name, 0.0) or 0.0 for s in steps)
        named += out[name.replace("_ms", "")]
    step_total = sum(s["total_step_ms"] for s in steps)
    out["step_other"] = step_total - named          # decision glue inside steps (validate_choice, event build)
    gaps = 0.0
    for i in range(1, len(steps)):
        gaps += (arrivals[i] - arrivals[i - 1]) - steps[i]["total_step_ms"]
    out["step_gap"] = gaps
    out["verify_tail"] = tl["oracle_seen_ms"] - arrivals[-1]
    out["verified_outcome"] = cell["verified_outcome_ms"]
    out["cleanup_after"] = cell["cleanup_after_outcome_ms"]
    used = (out["setup_before_step1"] + step_total + out["step_gap"] + out["verify_tail"])
    out["residual"] = cell["verified_outcome_ms"] - used
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--arm", default="pr4316-guarded")
    ap.add_argument("--traced", type=Path)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-md", type=Path, required=True)
    args = ap.parse_args()
    result: dict = {"arm": args.arm, "languages": {}}
    for lang in ("python", "typescript"):
        cells = [json.load(open(f)) for f in sorted(glob.glob(str(args.run / "cells/*/cell.json")))]
        cells = [c for c in cells if c["arm"] == args.arm and c["language"] == lang and c["independently_verified"]]
        table = [phases(c) for c in cells]
        keys = list(table[0])
        summary = {k: {"p50": q([t[k] for t in table], 0.5), "p95": q([t[k] for t in table], 0.95),
                       "min": q([t[k] for t in table], 0.0), "max": q([t[k] for t in table], 1.0)} for k in keys}
        outcome = summary["verified_outcome"]["p50"]
        bound = {k: {"phase_p50_ms": summary[k]["p50"],
                     "max_saved_pct_of_verified_outcome_p50": round(100 * summary[k]["p50"] / outcome, 1)}
                 for k in keys if k not in ("verified_outcome", "cleanup_after")}
        result["languages"][lang] = {"n": len(table), "phases": summary, "counterfactual_upper_bound": bound}
    if args.traced:
        mcp: dict = {}
        for lang in ("python", "typescript"):
            per_tool: dict[str, list[float]] = {}
            for d in sorted(glob.glob(str(args.traced / f"cells/traced-*-{args.arm}-{lang}"))):
                rows = [json.loads(l) for l in open(d + "/mcp-trace.jsonl")]
                pend, seen = {}, {}
                for r in rows:
                    if r.get("dir") == "c2s" and r["msg"].get("method"):
                        p = r["msg"].get("params") or {}
                        pend[r["msg"].get("id")] = (r["t_ns"], p.get("name") or r["msg"]["method"])
                    elif r.get("dir") == "s2c" and r["msg"].get("id") in pend:
                        t0, name = pend.pop(r["msg"]["id"])
                        seen[name] = seen.get(name, 0) + 1
                        per_tool.setdefault(f"{name}#{seen[name]}", []).append((r["t_ns"] - t0) / 1e6)
            mcp[lang] = {k: {"n": len(v), "p50": q(v, 0.5), "max": max(v)} for k, v in per_tool.items()}
        result["mcp_call_durations_ms"] = mcp
    args.out_json.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    md = [f"# Next dominant cost after guarded decision deletion (arm `{args.arm}`)\n"]
    for lang, data in result["languages"].items():
        md.append(f"## {lang} (n={data['n']} verified clean cells)\n")
        md.append("| phase | p50 ms | p95 ms | max saved if phase -> 0 (% of verified-outcome p50) |")
        md.append("|---|---|---|---|")
        ranked = sorted(data["counterfactual_upper_bound"].items(), key=lambda kv: -kv[1]["phase_p50_ms"])
        for k, v in ranked:
            md.append(f"| {k} | {v['phase_p50_ms']} | {data['phases'][k]['p95']} | {v['max_saved_pct_of_verified_outcome_p50']}% |")
        md.append(f"\nverified_outcome p50 {data['phases']['verified_outcome']['p50']} ms, p95 {data['phases']['verified_outcome']['p95']} ms; "
                  f"cleanup after outcome p50 {data['phases']['cleanup_after']['p50']} ms (not in verified-outcome time)\n")
    if "mcp_call_durations_ms" in result:
        md.append("## Driver/MCP call durations (traced cells, n small)\n")
        for lang, tools in result["mcp_call_durations_ms"].items():
            md.append(f"### {lang}\n| call | n | p50 ms | max ms |\n|---|---|---|---|")
            for k, v in tools.items():
                md.append(f"| {k} | {v['n']} | {v['p50']} | {round(v['max'],1)} |")
            md.append("")
    args.out_md.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

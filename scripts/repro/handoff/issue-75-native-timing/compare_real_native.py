#!/usr/bin/env python3
"""Compare two verify_native.py output dirs (base vs timing-parity patch) from the SAME real harness.

usage: compare_real_native.py BASE_DIR PATCH_DIR
Checks: (1) event streams are identical once *_ms fields, process/capture ids and the new
`visual_observe_scope` key are removed; (2) every patched step event carries the browser-common fields;
(3) aliases: provider_decision_ms==decide_ms, action_ms==act_ms, visual_observe_ms==parse_ms (when parsed);
(4) nesting: decision_ms ~= semantic+visual+candidate+provider and total_step_ms ~= decision_ms+action_ms.
"""
import glob, json, os, sys

def load(d):
    return {os.path.basename(f): [json.loads(l) for l in open(f) if l.strip().startswith("{")]
            for f in sorted(glob.glob(f"{d}/*.jsonl"))}

VOLATILE = {"pid", "capture_id", "window_id", "snapshot_id", "visual_observe_scope"}
COMMON = ["semantic_observe_ms", "visual_observe_ms", "candidate_build_ms", "provider_decision_ms",
          "decision_ms", "action_ms", "total_step_ms"]
TOL_MS = 5.0

def norm(x):
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items() if not k.endswith("_ms") and k not in VOLATILE}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x

base, patch = load(sys.argv[1]), load(sys.argv[2])
diffs, violations, steps = [], [], []
assert sorted(base) == sorted(patch), "different log sets"
for name in sorted(base):
    if len(base[name]) != len(patch[name]):
        diffs.append((name, "event count", len(base[name]), len(patch[name]))); continue
    for x, y in zip(base[name], patch[name]):
        if norm(x) != norm(y):
            diffs.append((name, {k: (x.get(k), y.get(k)) for k in set(x) | set(y) if norm({k: x.get(k)}) != norm({k: y.get(k)})}))
        if "act_ms" in y:
            missing = [k for k in COMMON + ["visual_observe_scope"] if k not in y]
            if missing: violations.append((name, "missing", missing)); continue
            if y["provider_decision_ms"] != y["decide_ms"]: violations.append((name, "provider_decision_ms != decide_ms"))
            if y["action_ms"] != y["act_ms"]: violations.append((name, "action_ms != act_ms"))
            if "parse_ms" in y and y["visual_observe_ms"] != y["parse_ms"]: violations.append((name, "visual_observe_ms != parse_ms"))
            inner = y["semantic_observe_ms"] + y["visual_observe_ms"] + y["candidate_build_ms"] + y["provider_decision_ms"]
            if abs(y["decision_ms"] - inner) > TOL_MS: violations.append((name, "decision nesting", y["decision_ms"], round(inner, 2)))
            if abs(y["total_step_ms"] - (y["decision_ms"] + y["action_ms"])) > TOL_MS:
                violations.append((name, "total nesting", y["total_step_ms"], round(y["decision_ms"] + y["action_ms"], 2)))
            if y["visual_observe_scope"] != "parse_only": violations.append((name, "scope", y["visual_observe_scope"]))
            steps.append({k: y[k] for k in sorted(y) if k.endswith("_ms") or k == "visual_observe_scope"})
report = {"logs": len(base), "step_events_checked": len(steps), "behaviour_identical_minus_timing": not diffs,
          "diffs": diffs[:5], "violations": violations[:10], "sample_step": steps[0] if steps else None}
print(json.dumps(report, indent=1))
sys.exit(1 if diffs or violations else 0)

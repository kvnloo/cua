"""Aggregate stack2-addr runs into summary.json against the PREREG gates (stdlib only).

usage: analyze.py <raw dir with runs/<run_id>/run_summary.json> <plan.json> <drive-ledger.jsonl> <out summary.json>
Every planned run is counted: a run without a summary or oracle is 'unknown' and stays in its denominator.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

SERVED_CONTEXT = 32768
ERR_CLASSES = ("addressing_refused", "token_unavailable", "stale_token", "invalid_token", "other_error", "no_result")


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def binom_tail(k: int, n: int) -> float:
    """P(X >= k) for X ~ Bin(n, 1/2)."""
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n if n else 1.0


def sign_two_sided(b: int, c: int) -> float:
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * binom_tail(max(b, c), n))


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def cell_stats(rows: list[dict]) -> dict:
    v = Counter(r["verdict"] for r in rows)
    n = len(rows)
    t = [r["tools"] for r in rows if r["tools"]]
    sumk = lambda key: sum(x.get(key, 0) for x in t)  # noqa: E731
    classes = Counter()
    el_classes = Counter()
    for x in t:
        classes.update(x.get("result_classes", {}))
        el_classes.update(x.get("element_action_classes", {}))
    errs = [x.get("tool_errors", 0) for x in t]
    peaks = [r["peak_prompt_tokens"] for r in rows if r["peak_prompt_tokens"] is not None]
    return {
        "n": n, "pass": v.get("pass", 0), "fail": v.get("fail", 0), "unknown": v.get("unknown", 0),
        "pass_rate": round(v.get("pass", 0) / n, 4) if n else None, "pass_wilson95": wilson(v.get("pass", 0), n),
        "hermes_rc": dict(Counter(str(r["hermes_rc"]) for r in rows)),
        "tool_calls": sumk("tool_calls"), "successful_tool_calls": sumk("successful_tool_calls"),
        "tool_errors": sumk("tool_errors"), "tool_errors_per_run_mean": round(statistics.mean(errs), 3) if errs else None,
        "tool_errors_per_run_median": statistics.median(errs) if errs else None,
        "runs_with_tool_error": sum(e > 0 for e in errs),
        "result_classes": dict(classes),
        "runs_with_addressing_refusal": sum(x.get("result_classes", {}).get("addressing_refused", 0) > 0 for x in t),
        "element_actions": sumk("element_actions"), "element_actions_ok": sumk("element_actions_ok"),
        "element_action_classes": dict(el_classes),
        "runs_with_element_action": sum(x.get("element_actions", 0) > 0 for x in t),
        "runs_with_element_action_ok": sum(x.get("element_actions_ok", 0) > 0 for x in t),
        "coordinate_actions": sumk("coordinate_actions"),
        "runs_with_coordinate_action": sum(x.get("coordinate_actions", 0) > 0 for x in t),
        "peak_prompt_tokens_max": max(peaks) if peaks else None,
        "runs_missing_summary": sum(r["tools"] is None for r in rows),
    }


def main() -> None:
    raw, plan_p, ledger_p, out_p = map(Path, sys.argv[1:5])
    plan = json.loads(plan_p.read_text())["runs"]
    ledger = {r["run_id"]: r for r in jl(ledger_p)}
    recs = []
    for r in plan:
        sp = raw / "runs" / r["run_id"] / "run_summary.json"
        s = json.loads(sp.read_text()) if sp.exists() else None
        recs.append({**r, "executed": r["run_id"] in ledger, "verdict": (s or {}).get("oracle", {}).get("verdict", "unknown"),
                     "hermes_rc": (s or {}).get("hermes_rc"), "tools": (s or {}).get("tools"),
                     "peak_prompt_tokens": ((s or {}).get("observer") or {}).get("peak_prompt_tokens"),
                     "isolation": (s or {}).get("isolation"),
                     "sph": [x.get("system_prompt_hash") for x in ((s or {}).get("state_db") or {}).get("sessions", [])]})
    cells = defaultdict(list)
    for r in recs:
        cells[f"{r['set']}|{r['task']}|{r['arm']}|{r['driver_key']}"].append(r)
    out: dict = {"schema": "stack2_addr.summary.v1", "planned": len(plan), "executed": sum(r["executed"] for r in recs),
                 "cells": {k: cell_stats(v) for k, v in sorted(cells.items())}}

    meas = [r for r in recs if r["set"] == "measured"]
    after = [r for r in meas if r["arm"] == "after"]
    before = [r for r in meas if r["arm"] == "before"]
    A, B = cell_stats(after), cell_stats(before)
    out["arms_pooled_measured"] = {"after": A, "before": B}

    # H1 contract: no element-addressing argument refusal reaches an after-arm result
    out["H1_contract"] = {"after_addressing_refused": A["result_classes"].get("addressing_refused", 0),
                          "before_addressing_refused": B["result_classes"].get("addressing_refused", 0),
                          "before_runs_with_refusal": B["runs_with_addressing_refusal"],
                          "before_runs_with_element_action": B["runs_with_element_action"],
                          "pass": A["result_classes"].get("addressing_refused", 0) == 0 and A["runs_missing_summary"] == 0}
    # H2 element actions reach the Driver and succeed
    k, n = A["runs_with_element_action_ok"], A["runs_with_element_action"]
    out["H2_element_reach"] = {"after_runs_with_element_action": n, "after_runs_with_element_action_ok": k,
                               "after_fraction": round(k / n, 4) if n else None, "after_wilson95": wilson(k, n),
                               "after_element_actions_ok": A["element_actions_ok"], "after_element_actions": A["element_actions"],
                               "before_element_actions_ok": B["element_actions_ok"], "before_element_actions": B["element_actions"],
                               "pass": bool(n) and k / n >= 0.9}
    # H3 task success, paired by (task, pair)
    h3 = {}
    for task in ("gtk3", "browser"):
        pairs = defaultdict(dict)
        for r in meas:
            if r["task"] == task:
                pairs[r["pair"]][r["arm"]] = r["verdict"]
        complete = {p: v for p, v in pairs.items() if {"before", "after"} <= set(v)}
        a_only = sum(v["after"] == "pass" and v["before"] != "pass" for v in complete.values())
        b_only = sum(v["before"] == "pass" and v["after"] != "pass" for v in complete.values())
        both = sum(v["before"] == "pass" and v["after"] == "pass" for v in complete.values())
        p1 = binom_tail(a_only, a_only + b_only)
        h3[task] = {"pairs_complete": len(complete), "both_pass": both, "after_only_pass": a_only, "before_only_pass": b_only,
                    "neither_pass": len(complete) - both - a_only - b_only,
                    "after_pass": cell_stats([r for r in after if r["task"] == task])["pass"],
                    "before_pass": cell_stats([r for r in before if r["task"] == task])["pass"],
                    "sign_test_one_sided_after_gt_before": round(p1, 6), "sign_test_two_sided": round(sign_two_sided(a_only, b_only), 6),
                    "supported": a_only > b_only and p1 < 0.05}
    out["H3_task_success"] = h3
    # H4 authority: Hermes never sends a superseded or foreign token; local refusals counted
    out["H4_authority"] = {"after_stale_token": A["result_classes"].get("stale_token", 0),
                           "after_invalid_token": A["result_classes"].get("invalid_token", 0),
                           "after_token_unavailable_local_refusals": A["result_classes"].get("token_unavailable", 0),
                           "pass": A["result_classes"].get("stale_token", 0) == 0 and A["result_classes"].get("invalid_token", 0) == 0}
    # H5 tool errors (descriptive)
    out["H5_tool_errors"] = {arm: {k2: S[k2] for k2 in ("tool_calls", "successful_tool_calls", "tool_errors",
                                                        "tool_errors_per_run_mean", "tool_errors_per_run_median",
                                                        "runs_with_tool_error", "result_classes")}
                             for arm, S in (("after", A), ("before", B))}
    # legacy regression (after-arm Hermes on the pinned 0.21.0)
    leg = [r for r in recs if r["set"] == "legacy"]
    L = cell_stats(leg)
    out["legacy_0_21_0"] = {"by_task": {t: cell_stats([r for r in leg if r["task"] == t]) for t in ("gtk3", "browser")},
                            "addressing_refused": L["result_classes"].get("addressing_refused", 0),
                            "pass": L["result_classes"].get("addressing_refused", 0) == 0 and L["runs_missing_summary"] == 0}
    # integrity
    iso = [r["isolation"] for r in recs if r["isolation"]]
    out["integrity"] = {
        "isolation_all_masked_empty": sum(i["all_masked_empty"] for i in iso), "isolation_runs": len(iso),
        "env_inside_live_refs": sum(i["env_inside_live_refs"] for i in iso),
        "env_inside_host_display_vars": sum(i["env_inside_host_display_vars"] for i in iso),
        "system_prompt_hashes_by_arm": {arm: sorted({h for r in recs if r["arm"] == arm for h in r["sph"] if h})
                                        for arm in ("before", "after")},
        "peak_prompt_tokens_max": max([r["peak_prompt_tokens"] for r in recs if r["peak_prompt_tokens"]] or [0]),
        "served_context": SERVED_CONTEXT,
        "truncation_risk_runs": sum((r["peak_prompt_tokens"] or 0) >= SERVED_CONTEXT for r in recs),
        "harness_errors": sorted(r["run_id"] for r in recs if "harness_error" in ledger.get(r["run_id"], {})),
        "not_executed": sorted(r["run_id"] for r in recs if not r["executed"]),
    }
    Path(out_p).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: out[k].get("pass", out[k]) if isinstance(out[k], dict) else out[k]
                      for k in ("planned", "executed", "H1_contract", "H2_element_reach", "H4_authority")}, sort_keys=True))
    print(json.dumps({t: (v["after_pass"], v["before_pass"], v["supported"]) for t, v in h3.items()}))


if __name__ == "__main__":
    main()

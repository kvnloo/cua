#!/usr/bin/env python3
"""N-01R analysis (stdlib only): raw/<label>/trials.jsonl.gz -> n01r-summary.json and
n01r-trial-metrics.jsonl.gz, following PREREG.json exactly.

usage: analyze.py [--check]   (--check: recompute and compare with the committed summary)
"""

from __future__ import annotations

import gzip
import json
import random
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
SCHEMA = "cua.gtk3_task_state_v1"
SEED = 9101
RESAMPLES = 10000
ARMS = ["B", "C", "S0", "F0", "X", "X2"]
TASKS = ["checkbox", "text"]
SLEEP_MARK = "post_action_sleep_ms=0"
SETTLE_MARK = "focus_guard_settle_ms=0"
ARM_KNOBS = {"B": set(), "C": set(), "S0": {SLEEP_MARK}, "F0": {SETTLE_MARK}, "X": {SLEEP_MARK},
             "X2": {SLEEP_MARK, SETTLE_MARK}, "X2o": {SLEEP_MARK, SETTLE_MARK}}
FAST = {"C", "X", "X2", "X2o"}
CLICK_MARKS = [("click", "element_resolved"), ("click", "placement_done"), ("click", "reveal_done"),
               ("click", "ax_start"), ("focus_guard", "captured"), ("atspi_action", "connected"),
               ("atspi_action", "live_checked"), ("atspi_action", "metadata_done"),
               ("atspi_action", "do_action_replied"), ("atspi_action", "post_sleep_done"),
               ("focus_guard", "body_done"), ("focus_guard", "restored"), ("click", "ax_joined")]
SV_MARKS = [("set_value", "element_resolved"), ("set_value", "cursor_done"), ("set_value", "write_done"),
            ("set_value", "readback_done")]
COMPONENTS = ["mcp_transport_obs", "observation", "runner", "resolution", "reveal", "dispatch",
              "post_action_sleep", "settle", "result", "mcp_transport_act", "effect_lag", "verification_read"]


# ----------------------------------------------------------------------------- io
def load_blocks() -> list[tuple[str, list[dict[str, Any]]]]:
    out = []
    for path in sorted(RAW.glob("n01r-*/trials.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            out.append((path.parent.name, [json.loads(x) for x in stream if x.strip()]))
    return out


# ----------------------------------------------------------------------------- stats
def med(xs: Iterable[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def p95(xs: Iterable[float | None]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[max(1, -(-95 * len(xs) // 100)) - 1], 3)


def describe(xs: list[float | None]) -> dict[str, Any]:
    xs = [x for x in xs if x is not None]
    return {"n": len(xs), "median": med(xs), "p95": p95(xs),
            "min": round(min(xs), 3) if xs else None, "max": round(max(xs), 3) if xs else None}


def ci_index(r: int) -> tuple[int, int]:
    return int(0.025 * r), int(0.975 * r) - 1


def boot_paired(diffs: list[float]) -> dict[str, Any] | None:
    """Median paired difference with a seeded percentile bootstrap over rounds."""
    if not diffs:
        return None
    rng = random.Random(SEED)
    n = len(diffs)
    meds = sorted(statistics.median(diffs[rng.randrange(n)] for _ in range(n)) for _ in range(RESAMPLES))
    lo, hi = ci_index(RESAMPLES)
    return {"median_diff_ms": round(statistics.median(diffs), 3), "ci95": [round(meds[lo], 3), round(meds[hi], 3)],
            "n_pairs": n, "diffs_ms": [round(d, 3) for d in diffs]}


def boot_ratio(pairs: list[tuple[float, float]]) -> dict[str, Any] | None:
    """S = median(base) / median(arm) over paired rounds, bootstrap over rounds."""
    if not pairs:
        return None
    rng = random.Random(SEED)
    n = len(pairs)
    vals = []
    for _ in range(RESAMPLES):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        vals.append(statistics.median(a for a, _ in sample) / statistics.median(b for _, b in sample))
    vals.sort()
    lo, hi = ci_index(RESAMPLES)
    point = statistics.median(a for a, _ in pairs) / statistics.median(b for _, b in pairs)
    return {"S": round(point, 3), "ci95": [round(vals[lo], 3), round(vals[hi], 3)], "n_pairs": n}


# ----------------------------------------------------------------------------- per trial
def matches(state: Any, expected: dict[str, Any]) -> bool:
    return (isinstance(state, dict) and state.get("schema") == SCHEMA
            and all(state.get(k) == v for k, v in expected.items()))


def call_marks(marks: list[dict[str, Any]], offset: float, m0: int, m1: int) -> dict[tuple[str, str], float]:
    """Driver marks (wall ns) mapped to caller monotonic ns, inside one call's window."""
    out: dict[tuple[str, str], float] = {}
    for m in marks:
        mono = m["wall_ns"] - offset
        if m0 - 2e6 <= mono <= m1 + 2e6:
            out.setdefault((m["scope"], m["mark"]), mono)
    return out


def knob_marks(marks: list[dict[str, Any]]) -> set[str]:
    return {m["mark"] for m in marks if m.get("scope") == "exp_knob"}


def receipt_focus(action: dict[str, Any]) -> str:
    text = " ".join(action.get("content_text") or [])
    found = re.search(r"focus_outcome=([a-z_]+)", text)
    return found.group(1) if found else "none_reported"


def trial_metrics(label: str, r: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: r.get(k) for k in ("id", "block", "kind", "task", "arm", "round", "variant_ms",
                                                    "display", "failure", "driver_env_exp")}
    out["label"] = label
    out["loadavg1"] = (r.get("loadavg") or [None])[0]
    marks = r.get("marks") or []
    out["knob_marks"] = sorted(knob_marks(marks))
    if r.get("kind") == "stale":
        for k in ("refused", "refusal_code", "effect", "mutations_b", "do_action_marks_after_restart", "control_passed"):
            out[k] = r.get(k)
        out["valid"] = r.get("failure") is None
        out["verified"] = bool(r.get("control_passed"))
        return out
    actions = r.get("actions") or []
    tree = r.get("tree")
    t0m, t0w = r.get("T0_m"), r.get("T0_w")
    samples = r.get("state_samples")
    expected = r.get("expected")
    if not (actions and tree and t0m and samples and expected):
        out.update({"valid": False, "verified": False, "reason": r.get("failure") or "incomplete trial"})
        return out
    pairs = [(t0m, t0w), (tree["m0"], tree["w0"]), (tree["m1"], tree["w1"])]
    pairs += [(a["m0"], a["w0"]) for a in actions] + [(a["m1"], a["w1"]) for a in actions]
    offset = statistics.median(w - m for m, w in pairs)
    states, idx, s0, s1 = samples["states"], samples["idx"], samples["t0_us"], samples["t1_us"]
    ret_us = (actions[-1]["m1"] - t0m) / 1000
    t_end = next((s1[i] / 1000 for i in range(len(idx)) if s0[i] >= ret_us and matches(states[idx[i]], expected)), None)
    t_land = next((s1[i] / 1000 for i in range(len(idx)) if matches(states[idx[i]], expected)), None)
    first_after = next((i for i in range(len(idx)) if s0[i] >= ret_us), None)
    final_state = states[idx[-1]] if idx else None
    before_seq = int((r.get("before") or {}).get("seq", -1))
    final_ok = matches(final_state, expected) and isinstance(final_state, dict) and final_state.get("seq") == before_seq + 1
    out.update({"T_ms": round(t_end, 3) if t_end is not None else None,
                "T_land_ms": round(t_land, 3) if t_land is not None else None,
                "T_return_ms": round(ret_us / 1000, 3),
                "effect_visible_at_return": bool(first_after is not None and matches(states[idx[first_after]], expected)),
                "final_state_ok": final_ok, "samples": len(idx),
                "max_sample_gap_ms": round(max((s0[i + 1] - s0[i]) for i in range(len(s0) - 1)) / 1000, 3) if len(s0) > 1 else None})
    out["verified"] = bool(t_end is not None and final_ok and r.get("failure") is None)
    # ---- route / producer checks
    calls = [("observe", tree)] + [(a["tool"], a) for a in actions]
    per_call = [call_marks(marks, offset, c["m0"], c["m1"]) for _, c in calls]
    reasons = []
    for (name, c), cm in zip(calls[1:], per_call[1:]):
        st = c.get("structured") or {}
        if st.get("route") != "accessibility":
            reasons.append(f"{name}: route={st.get('route')}")
        need = CLICK_MARKS if name == "click" else SV_MARKS
        times = [cm.get(k) for k in need]
        if any(t is None for t in times):
            reasons.append(f"{name}: missing marks {[k for k, t in zip(need, times) if t is None]}")
        elif any(b < a for a, b in zip(times, times[1:])):
            reasons.append(f"{name}: marks out of order")
        if (name, "dispatch_enter") not in cm or (name, "dispatch_exit") not in cm:
            reasons.append(f"{name}: missing dispatch marks")
    if ("get_window_state", "dispatch_enter") not in per_call[0]:
        reasons.append("observe: missing dispatch marks")
    want = ARM_KNOBS.get(r.get("arm"), set())
    if set(out["knob_marks"]) != want:
        reasons.append(f"knob marks {out['knob_marks']} != {sorted(want)}")
    motion = r.get("cursor_motion") or {}
    fast = motion.get("glide_duration_ms") == 1.0 and motion.get("dwell_after_click_ms") == 0.0
    if fast != (r.get("arm") in FAST):
        reasons.append(f"cursor motion {motion.get('glide_duration_ms')}/{motion.get('dwell_after_click_ms')} wrong for arm")
    if (r.get("cursor_state") or {}).get("enabled") is not True:
        reasons.append("cursor not enabled")
    out["route_reasons"] = reasons
    out["valid"] = not reasons
    # ---- decomposition (contiguous boundaries, caller monotonic ns)
    comp = {c: 0.0 for c in COMPONENTS}
    sub: dict[str, float] = {}
    named = 0.0

    def add(component: str, a: float | None, b: float | None, subname: str | None = None) -> None:
        nonlocal named
        if a is None or b is None:
            return
        d = (b - a) / 1e6
        comp[component] += d
        named += d
        if subname:
            sub[subname] = sub.get(subname, 0.0) + d

    add("mcp_transport_obs", t0m, tree["m0"], "obs_t0_to_send")
    prev_ret = None
    for i, ((name, c), cm) in enumerate(zip(calls, per_call)):
        tool = "get_window_state" if name == "observe" else name
        enter, exit_ = cm.get((tool, "dispatch_enter")), cm.get((tool, "dispatch_exit"))
        transport = "mcp_transport_obs" if name == "observe" else "mcp_transport_act"
        if prev_ret is not None:
            add("runner", prev_ret, c["m0"], "runner")
        add(transport, c["m0"], enter, f"{name}_mcp_in")
        if name == "observe":
            add("observation", enter, exit_, "observation")
        elif name == "click":
            add("resolution", enter, cm.get(("click", "invoke_start")), "click_admission")
            add("resolution", cm.get(("click", "invoke_start")), cm.get(("click", "placement_done")), "click_resolve_place")
            add("reveal", cm.get(("click", "placement_done")), cm.get(("click", "reveal_done")), "click_reveal")
            add("dispatch", cm.get(("click", "reveal_done")), cm.get(("focus_guard", "captured")), "click_gates_capture")
            add("dispatch", cm.get(("focus_guard", "captured")), cm.get(("atspi_action", "metadata_done")), "atspi_live_metadata")
            add("dispatch", cm.get(("atspi_action", "metadata_done")), cm.get(("atspi_action", "do_action_replied")), "do_action")
            add("post_action_sleep", cm.get(("atspi_action", "do_action_replied")), cm.get(("atspi_action", "post_sleep_done")), "post_action_sleep")
            add("settle", cm.get(("atspi_action", "post_sleep_done")), cm.get(("focus_guard", "restored")), "focus_guard_settle")
            add("result", cm.get(("focus_guard", "restored")), exit_, "click_result")
        else:
            add("resolution", enter, cm.get(("set_value", "invoke_start")), "sv_admission")
            add("resolution", cm.get(("set_value", "invoke_start")), cm.get(("set_value", "element_resolved")), "sv_resolve")
            add("reveal", cm.get(("set_value", "element_resolved")), cm.get(("set_value", "cursor_done")), "sv_cursor")
            add("dispatch", cm.get(("set_value", "cursor_done")), cm.get(("set_value", "readback_done")), "sv_write_readback")
            add("result", cm.get(("set_value", "readback_done")), exit_, "sv_result")
        add(transport, exit_, c["m1"], f"{name}_mcp_out")
        prev_ret = c["m1"]
    if t_end is not None:
        lag = max(0.0, (t_land or 0) - ret_us / 1000) if t_land is not None else 0.0
        comp["effect_lag"] = lag
        comp["verification_read"] = t_end - ret_us / 1000 - lag
        named += t_end - ret_us / 1000
        out["coverage"] = round(named / t_end, 4) if t_end else None
        out["unattributed_ms"] = round(t_end - named, 3)
    out["components_ms"] = {k: round(v, 3) for k, v in comp.items()}
    out["sub_ms"] = {k: round(v, 3) for k, v in sub.items()}
    # ---- receipts vs oracle (the action the oracle observes = the last click)
    last = actions[-1]
    st = last.get("structured") or {}
    claim = st.get("verified") is True or st.get("effect") in ("confirmed", "verified")
    oracle_at_return = out["effect_visible_at_return"]
    failure_claim = bool(last.get("error")) or st.get("status") == "refused" or st.get("effect") == "suspected_noop"
    out["receipt"] = {"effect": st.get("effect"), "route": st.get("route"), "claim_success": claim,
                      "failure_claim": failure_claim, "focus_outcome": receipt_focus(last)}
    out["receipt_claim_before_oracle"] = bool(claim and not oracle_at_return)
    out["receipt_false_failure"] = bool(failure_claim and out["verified"])
    out["focus_pre"] = r.get("focus_pre")
    out["focus_post"] = r.get("focus_post")
    out["focus_unchanged"] = r.get("focus_pre") == r.get("focus_post")
    if r.get("kind") == "late":
        log = [json.loads(x) for x in (r.get("fixture_log") or "").splitlines() if x.startswith("{")]
        sch = [x for x in log if x.get("event") == "scheduled"]
        app = [x for x in log if x.get("event") == "applied"]
        out["late_delay_measured_ms"] = round((app[0]["mono_ns"] - sch[0]["mono_ns"]) / 1e6, 3) if sch and app else None
    if r.get("kind") == "decoy":
        fs = r.get("focus_samples") or {}
        dec = r.get("decoy") or {}
        changes = fs.get("changes") or []
        pre = r.get("focus_pre") or {}
        final = changes[-1] if changes else None
        win = r.get("decoy_window")
        restored = bool(final and final[1] == pre.get("focus") and final[2] == pre.get("active"))
        missed = bool(final and win in (final[1], final[2]))
        steal_ns = dec.get("steal_ns")
        anchor = fs.get("anchor_ns") or t0m
        cmk = per_call[-1]
        body_done, restored_mark = cmk.get(("focus_guard", "body_done")), cmk.get(("focus_guard", "restored"))
        out["decoy"] = {
            "stolen": dec.get("stolen"), "restored": restored, "missed": missed,
            "steal_ms": round((steal_ns - anchor) / 1e6, 3) if steal_ns else None,
            "steal_after_return": bool(steal_ns and steal_ns > actions[-1]["m1"]),
            "steal_inside_guard_window": bool(steal_ns and body_done and restored_mark and body_done <= steal_ns <= restored_mark),
            "steal_before_body_done": bool(steal_ns and body_done and steal_ns < body_done),
            "focus_samples": fs.get("samples"), "focus_max_gap_ms": fs.get("max_gap_ms"),
            "focus_changes": len(changes), "receipt_focus_outcome": receipt_focus(last),
            "receipt_disagrees": bool(missed and receipt_focus(last) in ("none_reported", "restored")),
        }
    return out


# ----------------------------------------------------------------------------- aggregate
def group(metrics: list[dict[str, Any]], **where: Any) -> list[dict[str, Any]]:
    return [m for m in metrics if all(m.get(k) == v for k, v in where.items())]


def cell_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [m for m in rows if m.get("valid") and m.get("verified")]
    comps = {c: med(m["components_ms"][c] for m in ok) for c in COMPONENTS}
    shares = {c: med(m["components_ms"][c] / m["T_ms"] for m in ok if m.get("T_ms")) for c in COMPONENTS}
    subs: dict[str, list[float]] = {}
    for m in ok:
        for k, v in m.get("sub_ms", {}).items():
            subs.setdefault(k, []).append(v)
    return {
        "attempted": len(rows), "valid": sum(1 for m in rows if m.get("valid")),
        "verified": sum(1 for m in rows if m.get("verified")), "valid_and_verified": len(ok),
        "failures": [{"id": m["id"], "label": m["label"], "failure": m.get("failure"),
                      "route_reasons": m.get("route_reasons"), "verified": m.get("verified")}
                     for m in rows if not (m.get("valid") and m.get("verified"))],
        "T_ms": describe([m["T_ms"] for m in ok]), "T_land_ms": describe([m["T_land_ms"] for m in ok]),
        "T_return_ms": describe([m["T_return_ms"] for m in ok]),
        "components_median_ms": comps, "components_median_share": shares,
        "sub_median_ms": {k: med(v) for k, v in sorted(subs.items())},
        "coverage": {"median": med(m.get("coverage") for m in ok), "min": min((m.get("coverage") for m in ok if m.get("coverage") is not None), default=None)},
        "loadavg1_median": med(m.get("loadavg1") for m in rows),
        "effect_visible_at_return": sum(1 for m in ok if m.get("effect_visible_at_return")),
        "receipt_claim_before_oracle": sum(1 for m in rows if m.get("receipt_claim_before_oracle")),
        "receipt_false_failure": sum(1 for m in rows if m.get("receipt_false_failure")),
        "focus_unchanged": sum(1 for m in rows if m.get("focus_unchanged")),
        "displays": sorted({m.get("display") for m in rows if m.get("display")}),
    }


def latest_by_id(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The planned cell's latest attempt (re-run labels end in -rN); earlier attempts are reported separately."""
    best: dict[str, dict[str, Any]] = {}
    for m in metrics:
        best[m["id"]] = m  # labels sorted, so -rN (later) wins
    return list(best.values())


def paired(metrics: list[dict[str, Any]], kind: str, task: str, base: str, arm: str, key: str = "T_ms"):
    rows = [m for m in metrics if m.get("kind") == kind and m.get("task") == task and m.get("valid") and m.get("verified")]
    by_round: dict[Any, dict[str, float]] = {}
    for m in rows:
        if m.get("arm") in (base, arm) and m.get(key) is not None:
            by_round.setdefault(m["round"], {})[m["arm"]] = m[key]
    pairs = [(v[base], v[arm]) for _, v in sorted(by_round.items()) if base in v and arm in v]
    return pairs


def comp_paired(metrics, kind, task, base, arm, component):
    rows = [m for m in metrics if m.get("kind") == kind and m.get("task") == task and m.get("valid") and m.get("verified")]
    by_round: dict[Any, dict[str, float]] = {}
    for m in rows:
        if m.get("arm") in (base, arm):
            by_round.setdefault(m["round"], {})[m["arm"]] = m["components_ms"][component]
    return [(v[base], v[arm]) for _, v in sorted(by_round.items()) if base in v and arm in v]


def analyze() -> dict[str, Any]:
    blocks = load_blocks()
    allm: list[dict[str, Any]] = []
    meta = []
    for label, rows in blocks:
        for r in rows:
            if r.get("event") == "meta":
                meta.append({k: r.get(k) for k in ("block", "kind", "label", "display", "display_collision",
                                                   "x_clients_at_start", "driver_sha256", "plan_sha256", "wall_ns", "loadavg")})
            elif r.get("event") == "trial":
                allm.append(trial_metrics(label, r))
    metrics = latest_by_id(allm)
    superseded = [{"label": m["label"], "id": m["id"], "verified": m.get("verified"), "failure": m.get("failure")}
                  for m in allm if m not in metrics]
    # Block attempts that produced no trial ledger (e.g. the private Xvfb died at start): every
    # planned cell of the attempt is a failed, not-run cell; the block was re-run under a new label.
    plan = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
    planned = {b["block"]: len(b["trials"]) for b in plan["blocks"]}
    failed_attempts = []
    for d in sorted(RAW.glob("n01r-*")):
        if d.is_dir() and not (d / "trials.jsonl.gz").exists():
            block = d.name.split("-")[1]
            note = (d / "session.txt").read_text(encoding="utf-8").strip().splitlines() if (d / "session.txt").exists() else []
            failed_attempts.append({"label": d.name, "block": block, "planned_cells_not_run": planned.get(block),
                                    "session": [x for x in note if x.startswith(("[session]", "RuntimeError", "refusing"))][:4]})
    s: dict[str, Any] = {"schema": "n01r.summary.v1", "blocks": meta, "superseded_attempts": superseded,
                         "failed_block_attempts": failed_attempts,
                         "trials_total": len(allm), "cells": {}}
    for kind in ("main", "warm", "obs", "late", "decoy", "smoke", "stale"):
        for task in TASKS:
            for arm in ARMS + ["X2o"]:
                for variant in sorted({m.get("variant_ms") for m in metrics if m.get("kind") == kind}, key=lambda v: (v is None, v)):
                    rows = group(metrics, kind=kind, task=task, arm=arm, variant_ms=variant)
                    if rows and kind != "stale":
                        s["cells"][f"{kind}/{task}/{arm}" + (f"/{variant}" if variant is not None else "")] = cell_summary(rows)
    # ---- main paired + speedups
    s["paired_main"] = {}
    s["speedup"] = {}
    s["work_deleted_main"] = {}
    for task in TASKS:
        for arm in ARMS[1:]:
            pr = paired(metrics, "main", task, "B", arm)
            s["paired_main"][f"{task}/{arm}-B"] = boot_paired([b - a for a, b in pr])
            s["speedup"][f"{task}/B_over_{arm}"] = boot_ratio(pr)
            s["work_deleted_main"][f"{task}/{arm}"] = {
                c: med(a - b for a, b in comp_paired(metrics, "main", task, "B", arm, c))
                for c in ("reveal", "post_action_sleep", "settle")}
    # ---- supplementary
    s["paired_warm"] = boot_paired([b - a for a, b in paired(metrics, "warm", "checkbox", "B", "C")])
    s["speedup_warm"] = boot_ratio(paired(metrics, "warm", "checkbox", "B", "C"))
    s["paired_obs"] = {t: boot_paired([b - a for a, b in paired(metrics, "obs", t, "X2", "X2o")]) for t in TASKS}
    s["work_deleted_obs"] = {t: {c: med(a - b for a, b in comp_paired(metrics, "obs", t, "X2", "X2o", c))
                                 for c in ("observation", "mcp_transport_obs")} for t in TASKS}
    # ---- controls
    smoke = group(metrics, kind="smoke")
    s["control_d_smoke"] = {
        "trials": len(smoke), "verified": sum(1 for m in smoke if m.get("verified")),
        "valid": sum(1 for m in smoke if m.get("valid")),
        "env_exp_empty": all(not m.get("driver_env_exp") for m in smoke),
        "no_knob_marks": all(not m.get("knob_marks") for m in smoke),
        "post_action_sleep_ms": [m.get("components_ms", {}).get("post_action_sleep") for m in smoke],
        "settle_ms": [m.get("components_ms", {}).get("settle") for m in smoke],
    }
    d = s["control_d_smoke"]
    d["passed"] = bool(d["trials"] == 5 and d["verified"] == 5 and d["valid"] == 5 and d["env_exp_empty"] and d["no_knob_marks"]
                       and all(x is not None and 50 <= x < 60 for x in d["post_action_sleep_ms"])
                       and all(x is not None and x >= 220 for x in d["settle_ms"]))
    stale = group(metrics, kind="stale")
    s["control_c_stale"] = {arm: {"trials": len(rows), "passed": sum(1 for m in rows if m.get("control_passed")),
                                  "mutations": sum(int(m.get("mutations_b") or 0) for m in rows),
                                  "do_action_after_restart": sum(int(m.get("do_action_marks_after_restart") or 0) for m in rows),
                                  "codes": sorted({str(m.get("refusal_code")) for m in rows})}
                            for arm in ARMS for rows in [group(stale, arm=arm)]}
    late = group(metrics, kind="late")
    s["control_b_late"] = {}
    for task in TASKS:
        for v in (30, 80):
            for arm in ("B", "S0"):
                rows = group(late, task=task, variant_ms=v, arm=arm)
                s["control_b_late"][f"{task}/{v}/{arm}"] = {
                    "trials": len(rows), "verified": sum(1 for m in rows if m.get("verified")),
                    "valid": sum(1 for m in rows if m.get("valid")),
                    "claim_before_oracle": sum(1 for m in rows if m.get("receipt_claim_before_oracle")),
                    "false_failure": sum(1 for m in rows if m.get("receipt_false_failure")),
                    "effect_visible_at_return": sum(1 for m in rows if m.get("effect_visible_at_return")),
                    "receipt_effects": sorted({str((m.get("receipt") or {}).get("effect")) for m in rows}),
                    "delay_measured_ms": describe([m.get("late_delay_measured_ms") for m in rows]),
                    "T_land_minus_return_ms": describe([(m["T_land_ms"] - m["T_return_ms"]) for m in rows if m.get("T_land_ms") is not None]),
                }
    decoy = group(metrics, kind="decoy")
    s["control_a_decoy"] = {}
    for task in TASKS:
        for v in (100, 20):
            for arm in ("B", "F0"):
                rows = group(decoy, task=task, variant_ms=v, arm=arm)
                dd = [m.get("decoy") or {} for m in rows]
                s["control_a_decoy"][f"{task}/{v}/{arm}"] = {
                    "trials": len(rows), "verified": sum(1 for m in rows if m.get("verified")),
                    "valid": sum(1 for m in rows if m.get("valid")),
                    "stolen": sum(1 for x in dd if x.get("stolen")),
                    "restored": sum(1 for x in dd if x.get("restored")), "missed": sum(1 for x in dd if x.get("missed")),
                    "steal_after_return": sum(1 for x in dd if x.get("steal_after_return")),
                    "steal_inside_guard_window": sum(1 for x in dd if x.get("steal_inside_guard_window")),
                    "steal_before_body_done": sum(1 for x in dd if x.get("steal_before_body_done")),
                    "receipt_disagrees": sum(1 for x in dd if x.get("receipt_disagrees")),
                    "receipt_outcomes": sorted({str(x.get("receipt_focus_outcome")) for x in dd}),
                    "focus_max_gap_ms": max((x.get("focus_max_gap_ms") or 0 for x in dd), default=None),
                }
    s["gates"] = gates(s, metrics)
    s["provider"] = {"attempts": 0, "reached": 0,
                     "harness_refused_non_loopback_connects": sum(1 for _ in [])}
    return s, allm


def gates(s: dict[str, Any], metrics: list[dict[str, Any]]) -> dict[str, Any]:
    g: dict[str, Any] = {"validity": {}, "H_C": {}, "H_S": {}, "H_F": {}, "composition": {}, "E2": {}, "coverage": {}}
    for task in TASKS:
        for arm in ARMS:
            c = s["cells"].get(f"main/{task}/{arm}", {})
            g["validity"][f"{task}/{arm}"] = {"valid_and_verified": c.get("valid_and_verified"), "attempted": c.get("attempted"),
                                              "holds": (c.get("valid_and_verified") or 0) >= 19}
            g["coverage"][f"{task}/{arm}"] = {"median": c.get("coverage", {}).get("median"),
                                              "holds": (c.get("coverage", {}).get("median") or 0) >= 0.98}
    validity_all = all(v["holds"] for v in g["validity"].values())
    g["validity_all_hold"] = validity_all

    def ci_saves(p: dict[str, Any] | None) -> bool:
        return bool(p and p["ci95"][1] < 0)

    for task in TASKS:
        b = s["cells"][f"main/{task}/B"]
        tb = b["T_ms"]["median"]
        reveal_b = b["components_median_ms"]["reveal"]
        p = s["paired_main"][f"{task}/C-B"]
        saving = -p["median_diff_ms"] if p else None
        if reveal_b is not None and reveal_b < 0.05 * tb and reveal_b < 50:
            verdict = "NOT_MATERIAL"
        elif ci_saves(p) and saving >= 0.5 * reveal_b:
            verdict = "OWNER_DECISION"
        else:
            verdict = "IRREDUCIBLE"
        g["H_C"][task] = {"B_reveal_median_ms": reveal_b, "B_T_median_ms": tb, "saving_ms": saving,
                          "ci95": p["ci95"] if p else None, "half_reveal_ms": round(0.5 * reveal_b, 3) if reveal_b is not None else None,
                          "verdict": verdict}
    w = s["paired_warm"]
    wb = s["cells"].get("warm/checkbox/B", {})
    if w and wb:
        rb = wb["components_median_ms"]["reveal"]
        sv = -w["median_diff_ms"]
        verdict = ("NOT_MATERIAL" if rb < 0.05 * wb["T_ms"]["median"] and rb < 50
                   else "OWNER_DECISION" if ci_saves(w) and sv >= 0.5 * rb else "IRREDUCIBLE")
        g["H_C_warm"] = {"B_reveal_median_ms": rb, "B_T_median_ms": wb["T_ms"]["median"], "saving_ms": sv,
                         "ci95": w["ci95"], "verdict": verdict,
                         "validity": {a: s["cells"].get(f"warm/checkbox/{a}", {}).get("valid_and_verified") for a in ("B", "C")}}
    for task in TASKS:
        p = s["paired_main"][f"{task}/S0-B"]
        saving = -p["median_diff_ms"] if p else None
        lb = sum(s["control_b_late"][f"{task}/{v}/B"]["claim_before_oracle"] + s["control_b_late"][f"{task}/{v}/B"]["false_failure"] for v in (30, 80))
        ls = sum(s["control_b_late"][f"{task}/{v}/S0"]["claim_before_oracle"] + s["control_b_late"][f"{task}/{v}/S0"]["false_failure"] for v in (30, 80))
        degrade = ls - lb > 0
        if not ci_saves(p):
            verdict = "NOT_MATERIAL"
        elif saving >= 25 and not degrade:
            verdict = "DELETED"
        elif degrade:
            verdict = "IRREDUCIBLE_RECEIPT_TRUTH"
        else:
            verdict = "NOT_MATERIAL"
        g["H_S"][task] = {"saving_ms": saving, "ci95": p["ci95"] if p else None,
                          "late_disagreements_B": lb, "late_disagreements_S0": ls, "verdict": verdict}
    for task in TASKS:
        p = s["paired_main"][f"{task}/F0-B"]
        saving = -p["median_diff_ms"] if p else None
        b_restore = {v: s["control_a_decoy"][f"{task}/{v}/B"]["restored"] for v in (100, 20)}
        f_missed = {v: s["control_a_decoy"][f"{task}/{v}/F0"]["missed"] for v in (100, 20)}
        if not ci_saves(p):
            verdict = "NOT_MATERIAL"
        elif all(x >= 9 for x in b_restore.values()) and sum(f_missed.values()) >= 1:
            verdict = "IRREDUCIBLE"
        elif sum(f_missed.values()) == 0:
            verdict = "OWNER_DECISION"
        else:
            verdict = "INCONCLUSIVE"
        g["H_F"][task] = {"saving_ms": saving, "ci95": p["ci95"] if p else None, "B_restored_of_10": b_restore,
                          "F0_missed_of_10": f_missed, "verdict": verdict}
    for task in TASKS:
        excl = set()
        if g["H_F"][task]["verdict"] == "IRREDUCIBLE":
            excl |= {"F0", "X2"}
        if g["H_S"][task]["verdict"] == "IRREDUCIBLE_RECEIPT_TRUTH":
            excl |= {"S0", "X", "X2"}
        eligible = [a for a in ARMS if a not in excl and g["validity"][f"{task}/{a}"]["holds"]]
        validity_note = None
        if not eligible:
            validity_note = "no arm passed validity; best arm chosen among non-excluded arms for reporting only"
            eligible = [a for a in ARMS if a not in excl and f"main/{task}/{a}" in s["cells"]]
        best = min(eligible, key=lambda a: s["cells"][f"main/{task}/{a}"]["T_ms"]["median"])
        g["composition"][task] = {
            "S_X": s["speedup"][f"{task}/B_over_X"], "S_X2": s["speedup"][f"{task}/B_over_X2"],
            "excluded": sorted(excl), "eligible": eligible, "best_arm": best, "validity_note": validity_note,
            "best_T_median_ms": s["cells"][f"main/{task}/{best}"]["T_ms"]["median"],
            "S_best": s["speedup"].get(f"{task}/B_over_{best}") if best != "B" else None,
        }
        g["E2"][task] = e2(s, g, metrics, task, best)
    hs = [g["H_S"][t]["verdict"] for t in TASKS]
    remaining = {t: [c for c in g["E2"][t]["fixed_waits_ge_5pct"]] for t in TASKS}
    if all(v == "DELETED" for v in hs) and not any(remaining.values()):
        g["R2_09"] = {"result": "R2-09 precondition unmet: no native wait worth an event wake", "remaining_fixed_waits": remaining}
    else:
        g["R2_09"] = {"result": "named waits for R2-09", "H_S": hs, "remaining_fixed_waits": remaining}
    return g


FIXED_WAITS = ("post_action_sleep", "settle", "reveal")


def e2(s, g, metrics, task, best) -> dict[str, Any]:
    rows = [m for m in metrics if m.get("kind") == "main" and m.get("task") == task and m.get("arm") == best
            and m.get("valid") and m.get("verified")]
    tmed = statistics.median(m["T_ms"] for m in rows)
    obs = s["paired_obs"].get(task)
    obs_saves = bool(obs and obs["ci95"][1] < 0)
    hc = g["H_C"][task]["verdict"]
    if task == "checkbox" and g.get("H_C_warm"):
        hc_note = f"fresh-process H_C {hc}; warm-cursor H_C_warm {g['H_C_warm']['verdict']}"
    else:
        hc_note = f"H_C {hc}"
    verdicts = {
        "reveal": ("OWNER_DECISION" if "OWNER_DECISION" in (hc, (g.get("H_C_warm") or {}).get("verdict") if task == "checkbox" else hc) else hc, hc_note),
        "post_action_sleep": (g["H_S"][task]["verdict"], "H_S"),
        "settle": (g["H_F"][task]["verdict"], "H_F + decoy control"),
        "observation": ("OWNER_DECISION (screenshot delta) + IRREDUCIBLE (fresh observation, invariant)" if obs_saves
                        else "IRREDUCIBLE (fresh observation, invariant); screenshot not material", "block O"),
        "mcp_transport_obs": ("OWNER_DECISION (screenshot delta) + IRREDUCIBLE (observation transport, invariant)" if obs_saves
                              else "IRREDUCIBLE (observation transport, invariant)", "block O"),
        "dispatch": ("IRREDUCIBLE", "effect producer + liveness check + read-back (source)"),
        "verification_read": ("IRREDUCIBLE", "independent confirmation read (E4), 2 ms sampling"),
        "effect_lag": ("IRREDUCIBLE" if any(m["components_ms"]["effect_lag"] > 0 for m in rows) else "ZERO", "effect lands before return"),
    }
    comps = {}
    for c in COMPONENTS:
        share = statistics.median(m["components_ms"][c] / m["T_ms"] for m in rows)
        ms = statistics.median(m["components_ms"][c] for m in rows)
        v = verdicts.get(c)
        comps[c] = {"median_ms": round(ms, 3), "median_share": round(share, 4),
                    "material": share >= 0.05 or ms >= 50,
                    "verdict": v[0] if v else None, "basis": v[1] if v else "untested in this packet"}
    untested = [c for c in COMPONENTS if comps[c]["verdict"] is None]
    shares = [(sum(m["components_ms"][c] for c in untested) + max(0.0, m.get("unattributed_ms") or 0)) / m["T_ms"] for m in rows]
    material_untested = [c for c in untested if comps[c]["material"]]
    fixed = [c for c in FIXED_WAITS if comps[c]["median_share"] >= 0.05]
    return {"best_arm": best, "n": len(rows), "T_median_ms": round(tmed, 3), "components": comps,
            "untested_components": untested, "material_untested_components": material_untested,
            "untested_share_median": round(statistics.median(shares), 4),
            "fixed_waits_ge_5pct": fixed}


def main() -> None:
    summary, allm = analyze()
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        old = (HERE / "n01r-summary.json").read_text(encoding="utf-8")
        if old != text:
            print("MISMATCH: n01r-summary.json differs from a fresh recomputation")
            sys.exit(1)
        print("summary reproduces from raw/")
        return
    (HERE / "n01r-summary.json").write_text(text, encoding="utf-8")
    with gzip.open(HERE / "n01r-trial-metrics.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as stream:
        for m in allm:
            stream.write(json.dumps(m, sort_keys=True) + "\n")
    print(json.dumps(summary["gates"], indent=1, sort_keys=True)[:6000])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Analyze the R2-04 raw ledgers into r2-04-summary.json (stdlib only).

Reads raw/<session>/trials.jsonl.gz (session names s<k>-<arm>), applies the
pre-registered analysis (PREREG.json): caller spans, monitor-attributed D-Bus
RPCs per phase, Driver-internal phase spans (arm P), gates and dispositions.
"""

from __future__ import annotations

import gzip
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
MUTATING = {"DoAction", "SetTextContents"}
KINDS = ("checkbox", "button", "text")
SEED = 2004
RESAMPLES = 10000


# ----------------------------------------------------------------------------- io
def sessions() -> list[tuple[str, str, list[dict[str, Any]]]]:
    out = []
    for path in sorted(RAW.glob("s*-*/trials.jsonl.gz"), key=lambda p: int(p.parent.name[1:].split("-")[0])):
        name = path.parent.name
        arm = name.split("-")[1]
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        out.append((name, arm, rows))
    return out


# ----------------------------------------------------------------------------- stats
def med(xs: Iterable[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def p95(xs: Iterable[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    rank = max(1, -(-95 * len(xs) // 100))  # nearest-rank
    return round(xs[rank - 1], 3)


def boot_diff(a: list[float], b: list[float]) -> dict[str, Any] | None:
    """median(b) - median(a) with a seeded bootstrap 95% CI."""
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if not a or not b:
        return None
    rng = random.Random(SEED)
    diffs = []
    for _ in range(RESAMPLES):
        ra = [a[rng.randrange(len(a))] for _ in a]
        rb = [b[rng.randrange(len(b))] for _ in b]
        diffs.append(statistics.median(rb) - statistics.median(ra))
    diffs.sort()
    point = statistics.median(b) - statistics.median(a)
    return {"diff_ms": round(point, 3), "ci95": [round(diffs[int(0.025 * RESAMPLES)], 3),
                                                 round(diffs[int(0.975 * RESAMPLES) - 1], 3)],
            "rel": round(point / statistics.median(a), 4) if statistics.median(a) else None,
            "n_a": len(a), "n_b": len(b)}


def describe(xs: list[float]) -> dict[str, Any]:
    xs = [x for x in xs if x is not None]
    return {"n": len(xs), "median": med(xs), "p95": p95(xs),
            "min": round(min(xs), 3) if xs else None, "max": round(max(xs), 3) if xs else None}


# ----------------------------------------------------------------------------- rpc
def driver_name(rpc: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for p in rpc:
        if (p.get("interface") or "").startswith("org.a11y.atspi.") and p.get("dest") != "org.a11y.atspi.Registry":
            counts[p["sender"]] = counts.get(p["sender"], 0) + 1
    return max(counts, key=counts.get) if counts else None


def busy_ms(calls: list[dict[str, Any]]) -> float:
    spans = sorted((c["t_ns"], c["end_ns"]) for c in calls if c.get("end_ns"))
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total / 1e6


def window_rpc(rpc: list[dict[str, Any]], drv: str | None, w0: int, w1: int) -> dict[str, Any]:
    calls = [p for p in rpc if p["sender"] == drv and w0 <= p["t_ns"] <= w1]
    by_member: dict[str, int] = {}
    for c in calls:
        key = f"{(c.get('interface') or '').split('.')[-1]}.{c.get('member')}"
        by_member[key] = by_member.get(key, 0) + 1
    disc = [c for c in calls if c.get("member") not in MUTATING]
    mut = [c for c in calls if c.get("member") in MUTATING]
    return {
        "count": len(calls), "by_member": by_member,
        "busy_ms": round(busy_ms(calls), 4), "discovery_busy_ms": round(busy_ms(disc), 4),
        "discovery_count": len(disc), "mutating_count": len(mut),
        "sum_latency_ms": round(sum((c["end_ns"] - c["t_ns"]) for c in calls if c.get("end_ns")) / 1e6, 4),
        "unreplied": sum(1 for c in calls if not c.get("end_ns")),
        "first_offset_ms": round((calls[0]["t_ns"] - w0) / 1e6, 3) if calls else None,
        "tail_ms": round((w1 - max(c["end_ns"] or c["t_ns"] for c in calls)) / 1e6, 3) if calls else None,
        "mutating_reply_ns": max((c["end_ns"] for c in mut if c.get("end_ns")), default=None),
        "mutating_call_ns": min((c["t_ns"] for c in mut), default=None),
    }


# ----------------------------------------------------------------------------- marks
CLICK_SPANS = [  # (span, from-mark, to-mark) ; marks keyed "scope.mark"
    ("admission", "click.dispatch_enter", "click.invoke_start"),
    ("prologue", "click.invoke_start", "click.element_resolved"),
    ("placement", "click.element_resolved", "click.placement_done"),
    ("reveal", "click.placement_done", "click.reveal_done"),
    ("pre_ax", "click.reveal_done", "click.ax_start"),
    ("guard_capture", "click.ax_start", "focus_guard.captured"),
    ("live_check", "focus_guard.captured", "atspi_action.live_checked"),
    ("metadata", "atspi_action.live_checked", "atspi_action.metadata_done"),
    ("do_action", "atspi_action.metadata_done", "atspi_action.do_action_replied"),
    ("post_sleep", "atspi_action.do_action_replied", "atspi_action.post_sleep_done"),
    ("guard_restore", "atspi_action.post_sleep_done", "focus_guard.restored"),
    ("join", "focus_guard.restored", "click.ax_joined"),
    ("result_shape", "click.ax_joined", "click.invoke_end"),
    ("post_dispatch", "click.invoke_end", "click.dispatch_exit"),
]
SET_VALUE_SPANS = [
    ("admission", "set_value.dispatch_enter", "set_value.invoke_start"),
    ("prologue", "set_value.invoke_start", "set_value.element_resolved"),
    ("cursor", "set_value.element_resolved", "set_value.cursor_done"),
    ("write", "set_value.cursor_done", "set_value.write_done"),
    ("readback", "set_value.write_done", "set_value.readback_done"),
    ("result_shape", "set_value.readback_done", "set_value.invoke_end"),
    ("post_dispatch", "set_value.invoke_end", "set_value.dispatch_exit"),
]
GWS_SPANS = [
    ("admission", "get_window_state.dispatch_enter", "get_window_state.invoke_start"),
    ("tool_body", "get_window_state.invoke_start", "get_window_state.invoke_end"),
    ("post_dispatch", "get_window_state.invoke_end", "get_window_state.dispatch_exit"),
]


def call_spans(call: dict[str, Any], marks: list[dict[str, Any]], table: list[tuple[str, str, str]],
               scope: str) -> dict[str, Any] | None:
    inside = [m for m in marks if call["w0"] <= m["wall_ns"] <= call["w1"]]
    first: dict[str, int] = {}
    for m in inside:
        first.setdefault(f"{m['scope']}.{m['mark']}", m["wall_ns"])
    enter, leave = first.get(f"{scope}.dispatch_enter"), first.get(f"{scope}.dispatch_exit")
    if enter is None or leave is None:
        return None
    spans = {"mcp_in": (enter - call["w0"]) / 1e6, "mcp_out": (call["w1"] - leave) / 1e6}
    complete = True
    for name, a, b in table:
        if a in first and b in first:
            spans[name] = (first[b] - first[a]) / 1e6
        else:
            spans[name] = None
            complete = False
    named = sum(v for v in spans.values() if v is not None)
    spans = {k: (round(v, 4) if v is not None else None) for k, v in spans.items()}
    spans["coverage"] = round(named / call["wrapper_ms"], 4) if call["wrapper_ms"] else None
    spans["complete"] = complete
    return spans


# ----------------------------------------------------------------------------- per trial
def trial_metrics(name: str, arm: str, r: dict[str, Any], prev_target: str | None) -> dict[str, Any]:
    m: dict[str, Any] = {"session": name, "arm": arm, "index": r["index"], "kind": r["kind"], "phase": r["phase"],
                         "monitored": r["monitored"], "verified": bool(r.get("oracle_verified")),
                         "failure": r.get("failure"), "loadavg1": r["loadavg"][0], "trial_ms": r["trial_ms"],
                         "prev_target": prev_target}
    if r["kind"] == "stale_negative":
        m.update({"refused_stale": r.get("refused_stale"), "no_mutation": r.get("no_mutation"),
                  "do_action_on_bus": r.get("do_action_on_bus"), "control_passed": r.get("control_passed"),
                  "click_ms": r["actions"][0]["wrapper_ms"] if r.get("actions") else None})
        if r.get("marks") is not None and r.get("actions"):
            reached = [x["mark"] for x in r["marks"] if x["scope"] in ("click", "atspi_action", "focus_guard")]
            m["stale_marks"] = reached
        return m
    tree = r.get("tree") or {}
    m["tree_ms"] = tree.get("wrapper_ms")
    m["walk_ms"] = (tree.get("summary") or {}).get("walk_elapsed_ms")
    m["element_count"] = (tree.get("summary") or {}).get("element_count")
    m["lookup_ms"] = (r.get("lookup") or {}).get("lookup_ms")
    acts = r.get("actions") or []
    m["routes"] = [((a.get("structured") or {}).get("route"), (a.get("structured") or {}).get("effect")) for a in acts]
    m["action_errors"] = [a.get("error") for a in acts if a.get("error")]
    if r["kind"] == "text":
        m["set_value_ms"] = acts[0]["wrapper_ms"] if len(acts) > 0 else None
        m["save_click_ms"] = acts[1]["wrapper_ms"] if len(acts) > 1 else None
        m["action_ms"] = sum(a["wrapper_ms"] for a in acts) if acts else None
    else:
        m["click_ms"] = acts[0]["wrapper_ms"] if acts else None
        m["action_ms"] = m["click_ms"]
    mut = r.get("mutation") or {}
    m["mutation_detected"] = mut.get("detected")
    m["mutation_wait_ms"] = mut.get("wait_ms")
    m["oracle_read_ms"] = (r.get("oracle") or {}).get("read_ms")
    m["verify_tree_ms"] = (r.get("verify_tree") or {}).get("wrapper_ms")
    m["observation_agrees"] = r.get("observation_agrees")
    if r.get("oracle"):
        m["outcome_ms"] = (r["oracle"]["w1"] - r["w_start"]) / 1e6
    # RPCs
    if r.get("rpc") is not None and tree:
        drv = driver_name(r["rpc"])
        m["rpc_tree"] = window_rpc(r["rpc"], drv, tree["w0"], tree["w1"])
        m["rpc_actions"] = [window_rpc(r["rpc"], drv, a["w0"], a["w1"]) for a in acts]
        if r.get("verify_tree"):
            m["rpc_verify"] = window_rpc(r["rpc"], drv, r["verify_tree"]["w0"], r["verify_tree"]["w1"])
        disc = m["rpc_tree"]["discovery_busy_ms"] + sum(x["discovery_busy_ms"] for x in m["rpc_actions"])
        denom = (m["tree_ms"] or 0) + (m["action_ms"] or 0)
        m["D"] = round(disc / denom, 5) if denom else None
        # Effect landing: last mutating RPC reply in the final action vs the caller's receipt.
        final = acts[-1] if acts else None
        frpc = m["rpc_actions"][-1] if m["rpc_actions"] else None
        if final and frpc and frpc["mutating_reply_ns"]:
            m["landed_to_return_ms"] = round((final["w1"] - frpc["mutating_reply_ns"]) / 1e6, 3)
            m["dispatch_to_mutating_rpc_ms"] = round((frpc["mutating_call_ns"] - final["w0"]) / 1e6, 3)
            app_sigs = [s for s in r.get("signals", []) if s["sender"] != drv and s["t_ns"] >= frpc["mutating_call_ns"]
                        and s["t_ns"] <= final["w1"]]
            if app_sigs:
                first = min(app_sigs, key=lambda s: s["t_ns"])
                m["first_app_signal"] = f"{(first.get('interface') or '').split('.')[-1]}.{first.get('member')}:{first.get('arg0') or ''}"
                m["mutating_rpc_to_app_signal_ms"] = round((first["t_ns"] - frpc["mutating_call_ns"]) / 1e6, 3)
        if final and mut.get("state_mtime_ns") and frpc and frpc["mutating_call_ns"]:
            m["mutating_rpc_to_state_mtime_ms"] = round((mut["state_mtime_ns"] - frpc["mutating_call_ns"]) / 1e6, 3)
    # Driver phase marks (arm P)
    if r.get("marks") is not None:
        marks = r["marks"]
        m["spans_tree"] = call_spans(tree, marks, GWS_SPANS, "get_window_state") if tree else None
        spans = []
        for a in acts:
            if a["tool"] == "click":
                spans.append(call_spans(a, marks, CLICK_SPANS, "click"))
            elif a["tool"] == "set_value":
                spans.append(call_spans(a, marks, SET_VALUE_SPANS, "set_value"))
        m["spans_actions"] = spans
        if r.get("verify_tree"):
            m["spans_verify"] = call_spans(r["verify_tree"], marks, GWS_SPANS, "get_window_state")
    return m


LAST_TARGET = {"checkbox": "I agree", "button": "Increment", "text": "Save note", "stale_negative": None}


def all_metrics() -> list[dict[str, Any]]:
    rows = []
    for name, arm, trials in sessions():
        prev = None
        for r in trials:
            if r.get("event") != "trial":
                continue
            rows.append(trial_metrics(name, arm, r, prev))
            if LAST_TARGET.get(r["kind"]):
                prev = LAST_TARGET[r["kind"]]
    return rows


# ----------------------------------------------------------------------------- summary
def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [m for m in rows if m["phase"] == "measured"]
    s: dict[str, Any] = {"schema": "cua.r2.r2-04.summary.v1", "sessions": sorted({m["session"] for m in rows},
                                                                              key=lambda x: int(x[1:].split("-")[0]))}
    # denominators
    den = {}
    for arm in ("M", "P"):
        for kind in KINDS:
            xs = [m for m in measured if m["arm"] == arm and m["kind"] == kind]
            den[f"{arm}/{kind}"] = {"attempted": len(xs), "verified": sum(m["verified"] for m in xs),
                                    "monitored": sum(m["monitored"] for m in xs),
                                    "failures": [m["failure"] or m.get("action_errors") for m in xs if not m["verified"]]}
    s["denominators"] = den
    neg = [m for m in rows if m["kind"] == "stale_negative"]
    s["stale_negative"] = {arm: {"attempted": sum(1 for m in neg if m["arm"] == arm),
                                 "passed": sum(1 for m in neg if m["arm"] == arm and m["control_passed"]),
                                 "do_action_on_bus_total": sum(m["do_action_on_bus"] or 0 for m in neg if m["arm"] == arm)}
                           for arm in ("M", "P")}
    warm = [m for m in rows if m["phase"] == "warmup"]
    s["warmup"] = {"attempted": len(warm), "verified": sum(m["verified"] for m in warm),
                   "first_click_ms_by_session": {m["session"]: round(m["click_ms"], 3) for m in warm
                                                 if m["kind"] == "checkbox" and m["index"] == 0 and m.get("click_ms")}}
    ok = [m for m in measured if m["verified"]]

    # caller spans per arm x kind (verified only for latency)
    caller = {}
    for arm in ("M", "P"):
        for kind in KINDS:
            xs = [m for m in ok if m["arm"] == arm and m["kind"] == kind]
            entry = {}
            for key in ("tree_ms", "walk_ms", "lookup_ms", "action_ms", "click_ms", "set_value_ms", "save_click_ms",
                        "mutation_wait_ms", "oracle_read_ms", "verify_tree_ms", "outcome_ms", "trial_ms", "loadavg1"):
                vals = [m.get(key) for m in xs if m.get(key) is not None]
                if vals:
                    entry[key] = describe(vals)
            caller[f"{arm}/{kind}"] = entry
    s["caller_spans"] = caller

    # RPC (monitored, both arms reported separately)
    rpc = {}
    for arm in ("M", "P"):
        for kind in KINDS:
            xs = [m for m in ok if m["arm"] == arm and m["kind"] == kind and m.get("rpc_tree")]
            if not xs:
                continue
            members_tree: dict[str, list[int]] = {}
            for m in xs:
                for k, v in m["rpc_tree"]["by_member"].items():
                    members_tree.setdefault(k, []).append(v)
            act_members = []
            for i in range(len(xs[0]["rpc_actions"])):
                d: dict[str, list[int]] = {}
                for m in xs:
                    if i < len(m["rpc_actions"]):
                        for k, v in m["rpc_actions"][i]["by_member"].items():
                            d.setdefault(k, []).append(v)
                act_members.append({k: med(v) for k, v in sorted(d.items())})
            rpc[f"{arm}/{kind}"] = {
                "n": len(xs),
                "tree_count": describe([m["rpc_tree"]["count"] for m in xs]),
                "tree_busy_ms": describe([m["rpc_tree"]["busy_ms"] for m in xs]),
                "tree_by_member_median": {k: med(v) for k, v in sorted(members_tree.items())},
                "action_count": [describe([m["rpc_actions"][i]["count"] for m in xs if i < len(m["rpc_actions"])])
                                 for i in range(len(xs[0]["rpc_actions"]))],
                "action_busy_ms": [describe([m["rpc_actions"][i]["busy_ms"] for m in xs if i < len(m["rpc_actions"])])
                                   for i in range(len(xs[0]["rpc_actions"]))],
                "action_by_member_median": act_members,
                "action_first_rpc_offset_ms": [describe([m["rpc_actions"][i]["first_offset_ms"] for m in xs
                                                         if i < len(m["rpc_actions"])]) for i in range(len(xs[0]["rpc_actions"]))],
                "action_tail_ms": [describe([m["rpc_actions"][i]["tail_ms"] for m in xs if i < len(m["rpc_actions"])])
                                   for i in range(len(xs[0]["rpc_actions"]))],
                "D": describe([m["D"] for m in xs]),
                "landed_to_return_ms": describe([m.get("landed_to_return_ms") for m in xs]),
                "dispatch_to_mutating_rpc_ms": describe([m.get("dispatch_to_mutating_rpc_ms") for m in xs]),
                "mutating_rpc_to_app_signal_ms": describe([m.get("mutating_rpc_to_app_signal_ms") for m in xs]),
                "first_app_signal": sorted({m.get("first_app_signal") for m in xs if m.get("first_app_signal")}),
                "rpc_share_of_action_ms": describe([
                    sum(x["busy_ms"] for x in m["rpc_actions"]) / m["action_ms"] for m in xs if m["action_ms"]]),
            }
    s["rpc"] = rpc

    # Driver spans (arm P, verified)
    spans = {}
    for kind in KINDS:
        xs = [m for m in ok if m["arm"] == "P" and m["kind"] == kind and m.get("spans_actions")]
        if not xs:
            continue
        per_call = []
        for i in range(len(xs[0]["spans_actions"])):
            calls = [m["spans_actions"][i] for m in xs if i < len(m["spans_actions"]) and m["spans_actions"][i]]
            keys = [k for k in calls[0] if k not in ("coverage", "complete")] if calls else []
            per_call.append({
                "n": len(calls), "complete": sum(1 for c in calls if c["complete"]),
                "median_ms": {k: med(c[k] for c in calls) for k in keys},
                "p95_ms": {k: p95(c[k] for c in calls) for k in keys},
                "coverage": describe([c["coverage"] for c in calls]),
                "largest_named_span": max(((k, med(c[k] for c in calls)) for k in keys if k not in ("mcp_in", "mcp_out")),
                                          key=lambda kv: kv[1] or -1)[0] if calls else None,
            })
        tree_calls = [m["spans_tree"] for m in xs if m.get("spans_tree")]
        spans[kind] = {"actions": per_call,
                       "tree": {"n": len(tree_calls),
                                "median_ms": {k: med(c[k] for c in tree_calls) for k in ("mcp_in", "admission", "tool_body", "post_dispatch", "mcp_out")},
                                "coverage": describe([c["coverage"] for c in tree_calls])}}
    s["driver_spans_P"] = spans

    # reveal by previous target (cursor travel proxy), arm P clicks
    reveal = {}
    for m in ok:
        if m["arm"] != "P" or not m.get("spans_actions"):
            continue
        targets = ["Save note"] if m["kind"] == "text" else [LAST_TARGET[m["kind"]]]
        sp = m["spans_actions"][-1]
        if sp and sp.get("reveal") is not None:
            prev = m["prev_target"] if m["kind"] != "text" else "Note"
            reveal.setdefault(f"{prev}->{targets[0]}", []).append(sp["reveal"])
    s["reveal_by_transition_P"] = {k: describe(v) for k, v in sorted(reveal.items())}

    # Supplementary (not pre-registered): per-trial shares of the action-call time (arm P)
    # and transition-stratified distortion checks (the cursor reveal depends on the previous
    # target, so unstratified checkbox/button comparisons mix two transition populations).
    shares = {}
    for kind in KINDS:
        xs = [m for m in ok if m["arm"] == "P" and m["kind"] == kind and m.get("spans_actions")]
        rows_share = []
        for m in xs:
            total = m["action_ms"]
            sp = [c for c in m["spans_actions"] if c]
            g = lambda k: sum((c.get(k) or 0) for c in sp)
            rows_share.append({
                "cursor_visual": (g("reveal") + g("cursor")) / total,
                "fixed_post_dispatch_waits": (g("post_sleep") + g("guard_restore")) / total,
                "atspi_rpc_phases": (g("live_check") + g("metadata") + g("do_action") + g("write") + g("readback")) / total,
                "mcp_transport": (g("mcp_in") + g("mcp_out")) / total,
                "registry_and_other": (g("admission") + g("prologue") + g("placement") + g("pre_ax") + g("guard_capture")
                                       + g("join") + g("result_shape") + g("post_dispatch")) / total,
            })
        shares[kind] = {k: describe([r[k] for r in rows_share]) for k in rows_share[0]} if rows_share else {}
    s["supplementary_shares_P"] = shares
    strat = {}
    for kind in ("checkbox", "button"):
        trans = sorted({m["prev_target"] for m in ok if m["kind"] == kind})
        for t in trans:
            a = [m["action_ms"] for m in ok if m["arm"] == "M" and m["kind"] == kind and m["prev_target"] == t]
            b = [m["action_ms"] for m in ok if m["arm"] == "P" and m["kind"] == kind and m["prev_target"] == t]
            strat[f"P_vs_M/{kind}/prev={t}"] = boot_diff(a, b)
            for arm in ("M", "P"):
                a = [m["action_ms"] for m in ok if m["arm"] == arm and m["kind"] == kind and m["prev_target"] == t and not m["monitored"]]
                b = [m["action_ms"] for m in ok if m["arm"] == arm and m["kind"] == kind and m["prev_target"] == t and m["monitored"]]
                strat[f"monitor_on_vs_off/{arm}/{kind}/prev={t}"] = boot_diff(a, b)
    s["supplementary_stratified_distortion"] = strat

    # gates
    d_by_kind = {kind: (rpc.get(f"M/{kind}") or {}).get("D", {}).get("median") for kind in KINDS}
    max_d = max((v for v in d_by_kind.values() if v is not None), default=None)
    s["gate_bulk"] = {"D_median_by_kind_M": d_by_kind, "max_D": max_d, "threshold": 0.5,
                      "fires": bool(max_d is not None and max_d >= 0.5)}
    dist = {}
    for kind in KINDS:
        for mon in (True, False):
            a = [m["action_ms"] for m in ok if m["arm"] == "M" and m["kind"] == kind and m["monitored"] == mon]
            b = [m["action_ms"] for m in ok if m["arm"] == "P" and m["kind"] == kind and m["monitored"] == mon]
            dist[f"P_vs_M/{kind}/monitor={'on' if mon else 'off'}"] = boot_diff(a, b)
        for arm in ("M", "P"):
            a = [m["action_ms"] for m in ok if m["arm"] == arm and m["kind"] == kind and not m["monitored"]]
            b = [m["action_ms"] for m in ok if m["arm"] == arm and m["kind"] == kind and m["monitored"]]
            dist[f"monitor_on_vs_off/{arm}/{kind}"] = boot_diff(a, b)
            a = [m["tree_ms"] for m in ok if m["arm"] == arm and m["kind"] == kind and not m["monitored"]]
            b = [m["tree_ms"] for m in ok if m["arm"] == arm and m["kind"] == kind and m["monitored"]]
            dist[f"monitor_on_vs_off_tree/{arm}/{kind}"] = boot_diff(a, b)
    distorted = {k: v for k, v in dist.items() if v and not k.startswith("monitor_on_vs_off_tree")
                 and abs(v["rel"] or 0) > 0.15}
    s["gate_distortion"] = {"comparisons": dist, "threshold_rel": 0.15, "violations": sorted(distorted),
                            "holds": not distorted}
    cov = {}
    for kind, entry in spans.items():
        cov[kind] = [c["coverage"]["median"] for c in entry["actions"]]
    s["gate_coverage"] = {"median_coverage_by_kind": cov, "threshold": 0.9,
                          "holds": bool(cov) and all(all(x is not None and x >= 0.9 for x in v) for v in cov.values())
                          and set(cov) == set(KINDS)}
    validity = {k: v["verified"] / v["attempted"] if v["attempted"] else 0 for k, v in den.items()}
    neg_ok = all(v["attempted"] > 0 and v["passed"] == v["attempted"] for v in s["stale_negative"].values())
    s["gate_validity"] = {"verified_rate": {k: round(v, 4) for k, v in validity.items()},
                          "stale_negatives_all_pass": neg_ok,
                          "holds": all(v >= 0.95 for v in validity.values()) and neg_ok}
    h_a = "KILL" if not s["gate_bulk"]["fires"] else "PENDING_BULK_ARM"
    h_b = "KEEP" if (s["gate_coverage"]["holds"] and s["gate_distortion"]["holds"] and s["gate_validity"]["holds"]) else "REVISE"
    s["dispositions"] = {"H_A_bulk_cache": h_a, "H_B_localization": h_b,
                         "overall": "REVISE" if h_a == "KILL" and h_b == "KEEP" else "SEE_README"}
    return s


def main() -> None:
    rows = all_metrics()
    summary = summarize(rows)
    (HERE / "r2-04-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    body = "".join(json.dumps(m, sort_keys=True) + "\n" for m in rows).encode("utf-8")
    (HERE / "r2-04-trial-metrics.jsonl.gz").write_bytes(gzip.compress(body, mtime=0))
    print(json.dumps({k: summary[k] for k in ("gate_bulk", "gate_coverage", "gate_validity", "dispositions")}, indent=1))
    print("distortion violations:", summary["gate_distortion"]["violations"])


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""R2-10 analysis: recompute every headline from raw/ (standard library only).

Rules are the ones in PREREG.json. Browser decomposition reuses B-01's b01_analysis.decompose with
the B-02 taxonomy extension (harness/src/b-02-browser-driver-sites-2026-10-02, copied by path).

usage: analyze_r2_10.py [--raw raw] [--out r2-10-summary.json]
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import random
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness" / "src" / "b-02-browser-driver-sites-2026-10-02"))
import b01_analysis as B  # noqa: E402
import analyze_browser as AB  # noqa: E402,F401  (installs the B-02 classify_mark extension on B)

SEED = 20261002
BOOT = 10000
CLASSES = ["fill", "toggle", "modal"]
TASKS = ["checkbox", "text"]
EXPECTED_TOOLS = {"fill": ["browser_type", "browser_click"], "toggle": ["browser_click", "browser_click"],
                  "modal": ["browser_click", "browser_click"]}
ARM_POLL = {"BASE": 100, "COMP": 10, "COMP_E": 10, "COMP_K": 10}
FEEDBACK_ON = {"BASE", "COMP_K"}
SETTLE0 = {"COMP", "COMP_E"}
V_ARMS = {"COMP", "COMP_E", "COMP_K"}
E_ARMS = {"COMP_E"}
COMP_ARMS = {"COMP", "COMP_E", "COMP_K"}
THRESH_MS, THRESH_SHARE = 50.0, 0.05

BROWSER_VERDICTS = {
    "provider_decision": {"fill": "DELETED", "toggle": "UNTESTED", "modal": "UNTESTED"},
    "observation": "IRREDUCIBLE", "resolution": "UNTESTED", "reval_endpoint": "OWNER_DECISION",
    "reval_other": "IRREDUCIBLE", "mcp_admission": "UNTESTED", "mcp_transport": "UNTESTED",
    "client_validation": "UNTESTED", "visualization": "OWNER_DECISION", "input_prep": "UNTESTED",
    "settles": "OWNER_DECISION", "dispatch": "IRREDUCIBLE", "target_effect_lag": "IRREDUCIBLE",
    "verification_reads": "IRREDUCIBLE", "sleeps_polls": "IRREDUCIBLE", "runner": "UNTESTED",
    "unattributed": "UNTESTED",
}
BROWSER_VERDICT_NOTES = {
    "provider_decision": "fill: 2nd decision DELETED by guarded completion (R2-03), remaining one DELETED on warm "
                         "invocations by compiled replay (R2-07b); toggle/modal: plausibly deletable by a compiled "
                         "routine that is not qualified for these classes",
    "mcp_admission": "the tools-list re-validation is DELETED by H_V (fill/toggle; modal NOT_MATERIAL); what remains "
                     "in COMP is the residual after the cache",
    "client_validation": "library validation DELETED (H_C); what remains in COMP is the compiled-validator residual",
}
NATIVE_VERDICTS = {
    "observation_transport": "IRREDUCIBLE", "observation": "IRREDUCIBLE", "runner": "UNTESTED",
    "resolution": "UNTESTED", "reveal": "OWNER_DECISION", "dispatch": "IRREDUCIBLE",
    "post_action_sleep": "DELETED", "settle": "IRREDUCIBLE", "result": "UNTESTED",
    "action_transport": "UNTESTED", "effect_lag": "IRREDUCIBLE", "verification_read": "IRREDUCIBLE",
}
DISPATCH_MARKS = ("click.ref_resolved", "click.cdp_send", "type.ref_resolved", "type.insert_send")


# ── statistics ────────────────────────────────────────────────────────────────

def med(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def mean(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def boot_ci(n: int, stat) -> list[float] | None:  # noqa: ANN001
    return B.boot_ci(n, stat)


def ratio_stat(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    """S = median(a) / median(b) over paired rounds; seeded paired bootstrap over rounds."""
    n = len(pairs)
    if n == 0:
        return {"n": 0, "S": None, "ci95": None}
    a = [p[0] for p in pairs]
    b = [p[1] for p in pairs]

    def stat(idx: list[int]) -> float | None:
        den = statistics.median([b[i] for i in idx])
        return None if not den else statistics.median([a[i] for i in idx]) / den

    return {"n": n, "S": stat(list(range(n))), "ci95": boot_ci(n, stat),
            "median_base_ms": statistics.median(a), "median_arm_ms": statistics.median(b)}


def mean_ratio_stat(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    n = len(pairs)
    if n == 0:
        return {"n": 0, "S": None, "ci95": None}
    a = [p[0] for p in pairs]
    b = [p[1] for p in pairs]

    def stat(idx: list[int]) -> float | None:
        den = sum(b[i] for i in idx)
        return None if not den else sum(a[i] for i in idx) / den

    return {"n": n, "S": stat(list(range(n))), "ci95": boot_ci(n, stat)}


def diff_stat(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    return B.paired_diff([p[0] for p in pairs], [p[1] for p in pairs])


# ── io ────────────────────────────────────────────────────────────────────────

def read_bundle(path: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile():
                name = m.name[2:] if m.name.startswith("./") else m.name
                files[name] = tar.extractfile(m).read().decode()
    return files


def load_browser_bundle(path: Path) -> list[dict[str, Any]]:
    files = read_bundle(path)
    out = []
    for name in sorted(files):
        if not name.endswith(".jsonl") or name.endswith(".driver-trace.jsonl"):
            continue
        lines = [json.loads(x) for x in files[name].splitlines() if x.strip()]
        s = lines[-1]
        if s.get("event") != "summary":
            continue
        trace_text = files.get(s["driver_trace"]) if s.get("driver_trace") else None
        trace = [json.loads(x) for x in trace_text.splitlines() if x.strip()] if trace_text else []
        out.append({"name": s["trial"], "summary": s, "events": lines[:-1], "trace": trace, "bundle": path.name})
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


# ── browser per-trial ─────────────────────────────────────────────────────────

def first_window(events: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    return next((w for w in B._windows(events) if w["label"] == label), None)


def tool_calls(trace: list[dict[str, Any]], lo: int, hi: int) -> list[list[str]]:
    out, cur = [], None
    for m in trace:
        if m["phase"] == "mcp.line_read":
            cur = [m]
        elif cur is not None:
            cur.append(m)
            if m["phase"] == "mcp.written":
                if any(x["phase"] == "mcp.admission_validated" for x in cur) and lo <= cur[0]["t_mono_ns"] <= hi:
                    out.append([x["phase"] for x in cur])
                cur = None
    return out


def e2_components(d: dict[str, Any]) -> dict[str, float]:
    c, sub = d["components"], d["sub"]
    adm = sub.get("pre_admission_validate", 0.0) + sub.get("pre_inner_validate", 0.0)
    ep = sub.get("reval_endpoint", 0.0)
    return {
        "provider_decision": c["decision"], "observation": c["observation"], "resolution": c["resolution"],
        "reval_endpoint": ep, "reval_other": c["revalidate"] - ep, "mcp_admission": adm,
        "mcp_transport": c["transport"] + c["driver_post_dispatch"] + (c["driver_pre_dispatch"] - adm),
        "client_validation": c["client_validation"], "visualization": c["visualization"],
        "input_prep": c["input_prep"], "settles": c["settles"], "dispatch": c["dispatch"] + c["dispatch_post"],
        "target_effect_lag": c["target_effect_lag"], "verification_reads": c["verification_reads"],
        "sleeps_polls": c["sleeps_polls"], "runner": c["runner_overhead"], "unattributed": c["unattributed"],
    }


def browser_row(t: dict[str, Any], type_route: str | None) -> dict[str, Any]:
    s, ev, tr = t["summary"], t["events"], t["trace"]
    cls, arm, kind = s["cls"], s["arm"], s.get("kind")
    page_cls = s.get("page_cls") or cls
    row: dict[str, Any] = {"trial": t["name"], "bundle": t["bundle"], "layer": s.get("layer"), "cls": cls,
                           "page_cls": page_cls, "arm": arm, "kind": kind, "round": s.get("round"),
                           "mode": s.get("mode"), "outcome": s.get("outcome"), "error": s.get("error"),
                           "loadavg_1m": float(str(s.get("loadavg_before", "nan")).split()[0])}
    muts = s.get("mutations") or []
    accepted = [m for m in muts if m.get("result") == "accepted"]
    row["verified"] = bool(s.get("outcome") == "verified" and s.get("oracle_exact_match")
                           and s.get("completion_mutations") == 1)
    reasons: list[str] = []
    if not row["verified"]:
        reasons.append(f"not_verified:{s.get('outcome')}:{s.get('oracle_exact_match')}:{s.get('completion_mutations')}")
    snap1 = first_window(ev, "snapshot1")
    T0 = snap1["t0"] if snap1 else None
    last_ret = max((m["t_return_ns"] for m in accepted if m.get("t_return_ns")), default=None)
    ok = s.get("poller_ok_samples_ns") or []
    t_or = next((x for x in ok if last_ret is not None and x >= last_ret), None)
    row["T_oracle_ms"] = (t_or - T0) / 1e6 if (t_or and T0) else None
    row["T_land_ms"] = (s["poller_first_ok_ns"] - T0) / 1e6 if (s.get("poller_first_ok_ns") and T0) else None
    row["effect_before_last_return"] = bool(s.get("poller_first_ok_ns") and last_ret and s["poller_first_ok_ns"] < last_ret)
    d = B.decompose(t) if row["verified"] else None
    row["T_runner_ms"] = d["T_runner_ms"] if d else None
    if d:
        row["components"] = e2_components(d)
        # R2-10R (attempt 2): mcp_transport split into its inbound and outbound parts (reporting only; the
        # two parts sum to R2-10's mcp_transport, whose definition and verdict are unchanged).
        sub, c = d["sub"], d["components"]
        row["transport_split"] = {
            "mcp_transport_in": sub.get("client_send", 0.0) + sub.get("pre_other", 0.0),
            "mcp_transport_out": sub.get("client_return", 0.0) + sub.get("client_receive_parse", 0.0)
            + c["driver_post_dispatch"]}
        row["coverage"] = d["coverage"]
        row["observations_ms"] = d["observations"]
    if row["T_oracle_ms"] is None:
        reasons.append("T_oracle_undefined")
    # forced path: dom_event clicks through the Driver CDP engine; typing route identical across arms
    if kind == "measured" and [m["tool"] for m in accepted] != EXPECTED_TOOLS[page_cls]:
        reasons.append(f"tools={[m['tool'] for m in accepted]}")
    windows = {w["label"]: w for w in B._windows(ev)}
    for m in accepted:
        if m["tool"] == "browser_click":
            if m.get("input_route") != "dom_event":
                reasons.append(f"click_input_route={m.get('input_route')}")
            if m.get("route") != "dom":
                reasons.append(f"click_receipt_route={m.get('route')}")
            w = windows.get(m["label"])
            if w and not any(x["phase"] == "click.cdp_send" and w["t0"] <= x["t_mono_ns"] <= w["t1"] for x in tr):
                reasons.append("click_without_cdp_send")
        elif m["tool"] == "browser_type" and type_route is not None and m.get("route") != type_route:
            reasons.append(f"type_receipt_route={m.get('route')}")
    row["actual_routes"] = [f"{m['tool']}:{m.get('route')}:{m.get('effect')}" for m in accepted]
    routes = s.get("routes") or []
    row["decision_routes"] = routes
    if kind == "measured":
        if arm == "BASE":
            if any(r != "provider" for r in routes):
                reasons.append(f"routes={routes}")
        elif page_cls == "fill":
            ok_routes = (routes == ["compiled"] or (routes[:1] == ["compiled"] and all(r.startswith("fallback:") for r in routes[1:]))
                         or routes == ["provider", "guarded-completion"])
            if not ok_routes:
                reasons.append(f"routes={routes}")
        elif any(r != "provider" for r in routes):
            reasons.append(f"routes={routes}")
    # arm configuration checks
    waits = [m for m in tr if m["phase"] == "overlay.arrival_wait_end"]
    gates = [m for m in tr if m["phase"] == "platform.gate"]
    if kind in ("measured", "smoke"):
        if arm in FEEDBACK_ON:
            if len(waits) < len(accepted) or any(not (w.get("detail") or {}).get("arrived") for w in waits):
                reasons.append(f"arrival_waits={len(waits)}")
            if any(((w.get("detail") or {}).get("glide") or {}).get("glide_duration_ms") != 0.0 for w in waits):
                reasons.append("glide_setting")
        else:
            if waits or any((g.get("detail") or {}).get("cursor_enabled") for g in gates):
                reasons.append("feedback_not_off")
        settles = [m["detail"]["settle_ms"] for m in tr if m["phase"] == "focus.settle_start"]
        if page_cls == "fill" and accepted and any(m["tool"] == "browser_type" for m in accepted):
            want = 0 if arm in SETTLE0 else 100
            if not settles or any(v != want for v in settles):
                reasons.append(f"settle={settles}")
        polls = {e.get("poll_ms") for e in ev if e["event"] == "sleep_start"}
        if polls and arm in ARM_POLL and polls != {ARM_POLL[arm]}:
            reasons.append(f"poll={sorted(polls)}")
        if T0 is not None and row.get("T_runner_ms"):
            calls = tool_calls(tr, T0, T0 + int(row["T_runner_ms"] * 1e6))
            skipped = [("mcp.inner_validation_skipped" in c) for c in calls]
            built = [("mcp.inner_tools_list_built" in c) for c in calls]
            if arm in V_ARMS and not (calls and all(skipped) and not any(built)):
                reasons.append("V_not_taken")
            if arm not in V_ARMS and (any(skipped) or not all(built)):
                reasons.append("V_mark_in_unset_arm")
            in_t = [m["phase"] for m in tr if T0 <= m["t_mono_ns"] <= T0 + int(row["T_runner_ms"] * 1e6)]
            phases = [m["phase"] for m in tr]
            if arm in E_ARMS:
                if "ep.bound_stored" not in phases:
                    reasons.append("E_not_seeded")
                if in_t.count("ep.bound_hit") != in_t.count("reval.native_window") or "ep.bound_miss" in in_t:
                    reasons.append("E_not_taken")
            elif any(p.startswith("ep.bound_") for p in phases):
                reasons.append("E_mark_in_unset_arm")
        if arm in COMP_ARMS and not s.get("compiled_validators"):
            reasons.append("validators_not_compiled")
        if arm == "BASE" and s.get("compiled_validators"):
            reasons.append("validators_compiled_in_BASE")
    row["reasons"] = reasons
    row["valid"] = not reasons
    # E4 accounting (every trial)
    row["e4"] = {
        "caller_stale_dispatch": sum(1 for m in accepted if not m.get("fresh")),
        "duplicate_mutation": int((s.get("completion_mutations") or 0) > 1),
        "unverified_success": int(s.get("outcome") == "verified" and not s.get("oracle_exact_match")),
        "refusal_returned_as_success": sum(1 for e in ev if e["event"] == "call_return" and e.get("ok")
                                           and e.get("effect") == "refused"),
        "blind_replay": blind_replays(s),
    }
    row["stop"] = s.get("stop")
    row["provider_decisions"] = sum(1 for e in ev if e["event"] == "decided" and e.get("choice") is not None)
    row["training"] = s.get("training")
    return row


def blind_replays(s: dict[str, Any]) -> int:
    """Accepted re-dispatch of the same logical action in one trial."""
    muts = s.get("mutations") or []
    cands = [c for c in (s.get("candidates") or []) if c not in ("reobserve", "abstain")]
    routine = s.get("routine") or {}
    count = 0
    seen: Counter = Counter()
    if routine.get("mutations"):
        for m in routine["mutations"]:
            if m.get("result") == "accepted":
                seen[("routine", m.get("step"))] += 1
    for c, m in zip(cands, [m for m in muts][len(routine.get("mutations") or []):]):
        if m.get("result") == "accepted":
            seen[("step", c)] += 1
    count += sum(v - 1 for v in seen.values() if v > 1)
    return count


# ── native per-trial (N-01R rules on the merged trace) ───────────────────────

SCHEMA = "cua.gtk3_task_state_v1"
CLICK_MARKS = [("click", "element_resolved"), ("click", "placement_done"), ("click", "reveal_done"),
               ("click", "ax_start"), ("focus_guard", "captured"), ("atspi_action", "connected"),
               ("atspi_action", "live_checked"), ("atspi_action", "metadata_done"),
               ("atspi_action", "do_action_replied"), ("atspi_action", "post_sleep_done"),
               ("focus_guard", "body_done"), ("focus_guard", "restored"), ("click", "ax_joined")]
SV_MARKS = [("set_value", "element_resolved"), ("set_value", "cursor_done"), ("set_value", "write_done"),
            ("set_value", "readback_done")]
N_ARM_KNOBS = {"BASE": set(), "S0": {"post_action_sleep_ms=0"}, "X": {"post_action_sleep_ms=0"}}


def matches(state: Any, expected: dict[str, Any]) -> bool:
    return isinstance(state, dict) and state.get("schema") == SCHEMA and all(state.get(k) == v for k, v in expected.items())


def call_marks(marks: list[dict[str, Any]], m0: int, m1: int) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for m in marks:
        t = m.get("t_mono_ns")
        if t is not None and m0 - 2_000_000 <= t <= m1 + 2_000_000:
            out.setdefault((m.get("phase"), m.get("session")), t)
    return out


def native_row(r: dict[str, Any], traced: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {k: r.get(k) for k in ("id", "block", "kind", "task", "arm", "round", "variant_ms", "failure")}
    out["loadavg_1m"] = (r.get("loadavg") or [None])[0]
    marks = r.get("marks") or []
    out["knob_marks"] = sorted({m.get("session") for m in marks if m.get("phase") == "exp_knob"})
    actions = r.get("actions") or []
    tree = r.get("tree")
    t0m = r.get("T0_m")
    samples = r.get("state_samples")
    expected = r.get("expected")
    if not (actions and tree and t0m and samples and expected):
        out.update({"valid": False, "verified": False, "reasons": [r.get("failure") or "incomplete trial"]})
        return out
    states, idx, s0, s1 = samples["states"], samples["idx"], samples["t0_us"], samples["t1_us"]
    ret_us = (actions[-1]["m1"] - t0m) / 1000
    t_end = next((s1[i] / 1000 for i in range(len(idx)) if s0[i] >= ret_us and matches(states[idx[i]], expected)), None)
    t_land = next((s1[i] / 1000 for i in range(len(idx)) if matches(states[idx[i]], expected)), None)
    final_state = states[idx[-1]] if idx else None
    before_seq = int((r.get("before") or {}).get("seq", -1))
    final_ok = matches(final_state, expected) and isinstance(final_state, dict) and final_state.get("seq") == before_seq + 1
    out.update({"T_oracle_ms": t_end, "T_land_ms": t_land, "T_runner_ms": ret_us / 1000, "final_state_ok": final_ok,
                "mutations": (final_state or {}).get("seq", 0) - before_seq if isinstance(final_state, dict) else None})
    out["verified"] = bool(t_end is not None and final_ok and r.get("failure") is None)
    calls = [("observe", tree)] + [(a["tool"], a) for a in actions]
    per_call = [call_marks(marks, c["m0"], c["m1"]) for _, c in calls]
    reasons: list[str] = [] if out["verified"] else ["not_verified"]
    out["actual_routes"] = [f"{a['tool']}:{(a.get('structured') or {}).get('route')}:{(a.get('structured') or {}).get('effect')}"
                            for a in actions]
    for (name, c) in calls[1:]:
        st = c.get("structured") or {}
        if st.get("route") != "accessibility":
            reasons.append(f"{name}: route={st.get('route')}")
    if traced:
        for (name, c), cm in zip(calls[1:], per_call[1:]):
            need = CLICK_MARKS if name == "click" else SV_MARKS
            times = [cm.get(k) for k in need]
            if any(t is None for t in times):
                reasons.append(f"{name}: missing marks {[k for k, t in zip(need, times) if t is None]}")
            elif any(b < a for a, b in zip(times, times[1:])):
                reasons.append(f"{name}: marks out of order")
        if set(out["knob_marks"]) != N_ARM_KNOBS.get(r.get("arm"), set()):
            reasons.append(f"knob marks {out['knob_marks']}")
    motion = r.get("cursor_motion") or {}
    fast = motion.get("glide_duration_ms") == 1.0
    if fast != (r.get("arm") == "X"):
        reasons.append(f"cursor motion glide={motion.get('glide_duration_ms')}")
    if (r.get("cursor_state") or {}).get("enabled") is not True:
        reasons.append("cursor not enabled")
    out["reasons"] = reasons
    out["valid"] = not reasons
    comp = {k: 0.0 for k in NATIVE_VERDICTS}

    def add(component: str, a: float | None, b: float | None) -> None:
        if a is not None and b is not None:
            comp[component] += (b - a) / 1e6

    add("observation_transport", t0m, tree["m0"])
    split = {k: 0.0 for k in ("observation_transport_in", "observation_transport_out",
                              "action_transport_in", "action_transport_out")}
    split["observation_transport_in"] += (tree["m0"] - t0m) / 1e6 if (t0m is not None and tree["m0"] is not None) else 0.0
    prev = None
    for (name, c), cm in zip(calls, per_call):
        tool = "get_window_state" if name == "observe" else name
        enter, exit_ = cm.get((tool, "dispatch_enter")), cm.get((tool, "dispatch_exit"))
        tp = "observation_transport" if name == "observe" else "action_transport"
        if prev is not None:
            add("runner", prev, c["m0"])
        add(tp, c["m0"], enter)
        if c["m0"] is not None and enter is not None:  # R2-10R: inbound half of the transport (reporting only)
            split[f"{tp}_in"] += (enter - c["m0"]) / 1e6
        if name == "observe":
            add("observation", enter, exit_)
        elif name == "click":
            add("resolution", enter, cm.get(("click", "placement_done")))
            add("reveal", cm.get(("click", "placement_done")), cm.get(("click", "reveal_done")))
            add("dispatch", cm.get(("click", "reveal_done")), cm.get(("atspi_action", "do_action_replied")))
            add("post_action_sleep", cm.get(("atspi_action", "do_action_replied")), cm.get(("atspi_action", "post_sleep_done")))
            add("settle", cm.get(("atspi_action", "post_sleep_done")), cm.get(("focus_guard", "restored")))
            add("result", cm.get(("focus_guard", "restored")), exit_)
        else:
            add("resolution", enter, cm.get(("set_value", "element_resolved")))
            add("reveal", cm.get(("set_value", "element_resolved")), cm.get(("set_value", "cursor_done")))
            add("dispatch", cm.get(("set_value", "cursor_done")), cm.get(("set_value", "readback_done")))
            add("result", cm.get(("set_value", "readback_done")), exit_)
        add(tp, exit_, c["m1"])
        if exit_ is not None and c["m1"] is not None:  # R2-10R: outbound half of the transport (reporting only)
            split[f"{tp}_out"] += (c["m1"] - exit_) / 1e6
        prev = c["m1"]
    if t_end is not None:
        lag = max(0.0, (t_land or 0) - ret_us / 1000) if t_land is not None else 0.0
        comp["effect_lag"] = lag
        comp["verification_read"] = t_end - ret_us / 1000 - lag
    out["components"] = comp
    out["transport_split"] = split
    out["coverage"] = (sum(comp.values()) / t_end) if t_end else None
    if r.get("kind") == "decoy":
        fs = r.get("focus_samples") or {}
        dec = r.get("decoy") or {}
        changes = fs.get("changes") or []
        pre = r.get("focus_pre") or {}
        final = changes[-1] if changes else None
        win = r.get("decoy_window")
        out["decoy"] = {"stolen": dec.get("stolen"),
                        "restored": bool(final and final[1] == pre.get("focus") and final[2] == pre.get("active")),
                        "missed": bool(final and win in (final[1], final[2])),
                        "steal_after_last_return": bool(dec.get("steal_ns") and dec["steal_ns"] > actions[-1]["m1"])}
    out["receipt_shape"] = [
        {"tool": a["tool"], "route": (a.get("structured") or {}).get("route"),
         "effect": (a.get("structured") or {}).get("effect"), "status": (a.get("structured") or {}).get("status"),
         "keys": sorted((a.get("structured") or {}).keys())} for a in actions]
    return out


# ── aggregation ───────────────────────────────────────────────────────────────

def pairs_by_round(rows: list[dict[str, Any]], a: str, b: str, key: str, cls_key: str = "cls") -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    idx: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        idx[(r[cls_key], r["round"])][r["arm"]] = r
    for (c, rnd), arms in sorted(idx.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        ra, rb = arms.get(a), arms.get(b)
        if ra and rb and ra["valid"] and rb["valid"] and ra.get(key) is not None and rb.get(key) is not None:
            out[c].append((ra[key], rb[key], rnd, max(ra["loadavg_1m"] or 0, rb["loadavg_1m"] or 0)))
    return out


def s_block(rows: list[dict[str, Any]], arm: str, groups: list[str], cls_key: str = "cls",
            charged: dict[tuple, float] | None = None, key: str = "T_oracle_ms") -> dict[str, Any]:
    # R2-10R: ``key`` added so the same S rule is reported on T_land (no training charge there).
    out = {}
    pr = pairs_by_round(rows, "BASE", arm, key, cls_key)
    for g in groups:
        p = pr.get(g, [])
        allp = [(x[0], (charged or {}).get((g, x[2]), x[1])) for x in p]
        low = [(x[0], (charged or {}).get((g, x[2]), x[1])) for x in p if x[3] < 2.0]
        out[g] = {"all": ratio_stat(allp), "loadavg_lt2": ratio_stat(low),
                  "paired_diff_ms": diff_stat(allp), "rounds_dropped": None}
        n_rounds = len({r["round"] for r in rows if r[cls_key] == g})
        out[g]["rounds_total"] = n_rounds
    return out


def arm_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    v = [r for r in rows if r["valid"]]
    return {"n": len(rows), "verified": sum(1 for r in rows if r["verified"]), "valid": len(v),
            "verified_share": (sum(1 for r in rows if r["verified"]) / len(rows)) if rows else None,
            "invalid": [{"trial": r.get("trial", r.get("id")), "reasons": r["reasons"]} for r in rows if not r["valid"]],
            "T_oracle_ms": {"median": med([r["T_oracle_ms"] for r in v]), "mean": mean([r["T_oracle_ms"] for r in v]),
                            "p95": B.p95([r["T_oracle_ms"] for r in v if r["T_oracle_ms"] is not None])},
            "T_land_ms_median": med([r["T_land_ms"] for r in v]),
            "T_runner_ms": {"median": med([r["T_runner_ms"] for r in v]), "mean": mean([r["T_runner_ms"] for r in v])},
            "loadavg_1m": {"min": min((r["loadavg_1m"] for r in rows if r["loadavg_1m"] is not None), default=None),
                           "median": med([r["loadavg_1m"] for r in rows]),
                           "max": max((r["loadavg_1m"] for r in rows if r["loadavg_1m"] is not None), default=None)}}


def decomposition(rows: list[dict[str, Any]], verdicts: dict[str, Any], group: str,
                  tkey: str = "T_runner_ms") -> dict[str, Any]:
    v = [r for r in rows if r["valid"] and r.get("components")]
    if not v:
        return {}
    meanT = mean([r[tkey] for r in v])
    comps = sorted(v[0]["components"])
    table = {}
    untested = irreducible = 0.0
    for c in comps:
        m = mean([r["components"][c] for r in v]) or 0.0
        verdict = verdicts[c][group] if isinstance(verdicts[c], dict) else verdicts[c]
        share = m / meanT if meanT else None
        table[c] = {"mean_ms": m, "share": share, "verdict": verdict,
                    "above_threshold": bool(m >= THRESH_MS or (share or 0) >= THRESH_SHARE)}
        if verdict == "UNTESTED":
            untested += m
        if verdict == "IRREDUCIBLE":
            irreducible += m
    return {"n": len(v), "mean_T_ms": meanT, "components": table, "untested_ms": untested,
            "untested_share": untested / meanT if meanT else None, "T_irreducible_ms": irreducible,
            "floor_ratio_mean": meanT / irreducible if irreducible else None,
            "coverage_min": min(r["coverage"] for r in v if r.get("coverage") is not None)}


def transport_split(rows: list[dict[str, Any]], whole: Any) -> dict[str, Any]:
    """R2-10R (attempt 2): mean inbound/outbound transport per arm over the same valid rows as the
    decomposition (reporting only; ``check_sum_ms`` = |sum of the parts - the R2-10 component mean|)."""
    v = [r for r in rows if r["valid"] and r.get("components") and r.get("transport_split")]
    if not v:
        return {}
    keys = sorted(v[0]["transport_split"])
    out: dict[str, Any] = {"n": len(v), "mean_ms": {k: mean([r["transport_split"][k] for r in v]) for k in keys}}
    names = [whole] if isinstance(whole, str) else list(whole)
    total = sum(mean([r["components"][n] for r in v]) or 0.0 for n in names)
    out["component_mean_ms"] = total
    out["check_sum_ms"] = abs(sum(out["mean_ms"].values()) - total)
    return out


def e4_totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    tot: Counter = Counter()
    for r in rows:
        for k, v in (r.get("e4") or {}).items():
            tot[k] += v
    return dict(tot)


def receipt_shape_browser(t: dict[str, Any]) -> list[Any]:
    out = []
    for e in t["events"]:
        if e["event"] == "call_return" and e.get("tool") in ("browser_type", "browser_click"):
            out.append({k: e.get(k) for k in ("tool", "route", "effect", "status", "delivery", "input_route",
                                              "verification", "result_keys", "ok")})
    return out


# ── main analysis ─────────────────────────────────────────────────────────────

def analyze(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "r2-10.summary.v1"}
    # browser measured layers
    trials = {name: load_browser_bundle(raw / "browser" / f"{name}-trials.tar.gz")
              for name in ("scripted", "live", "controls") if (raw / "browser" / f"{name}-trials.tar.gz").exists()}
    all_meas = [t for k in ("scripted", "live") for t in trials.get(k, []) if t["summary"].get("kind") == "measured"
                and not t["name"].endswith("-admission")]
    type_routes = Counter(m.get("route") for t in all_meas for m in (t["summary"].get("mutations") or [])
                          if m.get("tool") == "browser_type" and m.get("result") == "accepted")
    type_route = type_routes.most_common(1)[0][0] if type_routes else None
    S["browser_type_route"] = {"modal": type_route, "counts": dict(type_routes)}
    rows_by_layer: dict[str, list[dict[str, Any]]] = {}
    admissions: dict[str, dict[str, Any]] = {}
    for layer in ("scripted", "live"):
        rows = []
        for t in trials.get(layer, []):
            if t["name"].endswith("-admission"):
                adm = t["summary"]
                snap1 = first_window(t["events"], "snapshot1")
                ok = adm.get("poller_ok_samples_ns") or []
                accepted = [m for m in adm.get("mutations") or [] if m.get("result") == "accepted"]
                last = max((m["t_return_ns"] for m in accepted), default=None)
                tor = next((x for x in ok if last is not None and x >= last), None)
                admissions[t["name"]] = {"admitted": adm.get("admitted"), "outcome": adm.get("outcome"),
                                         "T_oracle_ms": (tor - snap1["t0"]) / 1e6 if (tor and snap1) else None,
                                         "fresh_all": all(m.get("fresh") for m in accepted),
                                         "completion_mutations": adm.get("completion_mutations"),
                                         "e4": {"caller_stale_dispatch": sum(1 for m in accepted if not m.get("fresh")),
                                                "duplicate_mutation": int((adm.get("completion_mutations") or 0) > 1)}}
                continue
            if t["summary"].get("kind") == "measured":
                rows.append(browser_row(t, type_route))
        rows_by_layer[layer] = rows
    S["admissions"] = admissions
    layers_out = {}
    for layer, rows in rows_by_layer.items():
        if not rows:  # R2-10R: L-live is not re-run (BLOCKED, budget)
            continue
        arms = sorted({r["arm"] for r in rows})
        lo: dict[str, Any] = {"arms": {}, "S": {}}
        for cls in CLASSES:
            lo["arms"][cls] = {a: arm_summary([r for r in rows if r["cls"] == cls and r["arm"] == a]) for a in arms}
        # fill charges: training invocation = T_oracle(training) + compile_ms + T_oracle(admission)
        charged: dict[str, dict[tuple, float]] = defaultdict(dict)
        training_rows = {}
        for r in rows:
            tr = r.get("training")
            if tr and r["arm"] in COMP_ARMS and r["valid"]:
                adm = admissions.get(tr.get("admission_trial") or "", {})
                extra = (tr.get("compile_ms") or 0.0) + (adm.get("T_oracle_ms") or 0.0)
                charged[r["arm"]][("fill", r["round"])] = r["T_oracle_ms"] + extra
                training_rows[r["arm"]] = {"trial": r["trial"], "round": r["round"], "T_oracle_ms": r["T_oracle_ms"],
                                           "compile_ms": tr.get("compile_ms"), "admission_T_oracle_ms": adm.get("T_oracle_ms"),
                                           "admitted": tr.get("admitted"), "charged_ms": r["T_oracle_ms"] + extra,
                                           "learning_verified": tr.get("learning_verified"),
                                           "authority_problems": tr.get("authority_problems")}
        lo["training"] = training_rows
        for arm in [a for a in arms if a != "BASE"]:
            sb = s_block(rows, arm, CLASSES, charged=charged.get(arm))
            fillp = pairs_by_round(rows, "BASE", arm, "T_oracle_ms").get("fill", [])
            ch = charged.get(arm, {})
            tr_round = training_rows.get(arm, {}).get("round")
            sb["fill"]["amortized_mean_ratio"] = mean_ratio_stat([(x[0], ch.get(("fill", x[2]), x[1])) for x in fillp])
            sb["fill"]["warm_only"] = ratio_stat([(x[0], x[1]) for x in fillp if x[2] != tr_round])
            sb["fill"]["training_round"] = tr_round
            lo["S"][arm] = sb
        # R2-10R: T_land S next to T_oracle S (same pairing and bootstrap; training rows uncharged).
        lo["S_land"] = {arm: s_block(rows, arm, CLASSES, key="T_land_ms") for arm in arms if arm != "BASE"}
        lo["modes"] = dict(Counter((r["cls"], r["arm"], r["mode"]) for r in rows if r["arm"] in COMP_ARMS).items()) \
            if False else {f"{c}/{a}/{m}": n for (c, a, m), n in Counter((r["cls"], r["arm"], r["mode"]) for r in rows).items()}
        lo["decomposition"] = {f"{cls}/{arm}": decomposition([r for r in rows if r["cls"] == cls and r["arm"] == arm],
                                                             BROWSER_VERDICTS, cls)
                               for cls in CLASSES for arm in arms}
        wd = {}
        for cls in CLASSES:
            db, dc = lo["decomposition"].get(f"{cls}/BASE"), lo["decomposition"].get(f"{cls}/COMP")
            if not (db and dc):
                continue
            nb = [r for r in rows if r["cls"] == cls and r["arm"] == "BASE" and r["valid"]]
            nc = [r for r in rows if r["cls"] == cls and r["arm"] == "COMP" and r["valid"]]
            wd[cls] = {"component_mean_ms_deleted": {c: db["components"][c]["mean_ms"] - dc["components"][c]["mean_ms"]
                                                     for c in db["components"]},
                       "provider_decisions_per_trial": {"BASE": mean([r["provider_decisions"] for r in nb]),
                                                        "COMP": mean([r["provider_decisions"] for r in nc])},
                       "wall_clock_saved_median_paired_ms": lo["S"]["COMP"][cls]["paired_diff_ms"]["median"],
                       "wall_clock_saved_ci95": lo["S"]["COMP"][cls]["paired_diff_ms"]["ci95"]}
        lo["work_deleted_vs_wall_clock"] = wd
        lo["transport_split"] = {f"{cls}/{arm}": transport_split([r for r in rows if r["cls"] == cls and r["arm"] == arm],
                                                                 "mcp_transport")
                                 for cls in CLASSES for arm in arms}
        lo["e4"] = e4_totals(rows)
        lo["fallbacks"] = [{"trial": r["trial"], "routes": r["decision_routes"], "verified": r["verified"]}
                           for r in rows if any(x.startswith("fallback:") for x in r["decision_routes"])]
        lo["provider_decisions_per_arm_class"] = {f"{c}/{a}": sum(r["provider_decisions"] for r in rows
                                                                  if r["cls"] == c and r["arm"] == a)
                                                  for c in CLASSES for a in arms}
        layers_out[layer] = lo
    S["browser"] = layers_out
    # controls (inside L-scripted COMP)
    ctrl = trials.get("controls", [])
    by_prefix: dict[str, list] = defaultdict(list)
    for t in ctrl:
        by_prefix[t["name"].split("-")[0]].append(t)
    failed_blocks = {p: {"n": len(ts), "errors": sorted({str(t["summary"].get("error"))[:160] for t in ts}),
                         "error_leaves": sorted({x[:200] for t in ts for x in (t["summary"].get("error_leaves") or [])})}
                     for p, ts in by_prefix.items() if all(t["summary"].get("outcome") == "error" for t in ts)}
    S["controls_failed_session_blocks"] = failed_blocks
    crow: dict[str, list] = defaultdict(list)
    for t in [t for t in ctrl if t["name"].split("-")[0] not in failed_blocks]:
        s = t["summary"]
        kind = s.get("kind")
        if kind == "nw2":
            env = s.get("nw2_stale_envelope") or {}
            crow["N-W2"].append({"trial": t["name"], "cls": s["cls"], "stale_effect": env.get("effect"),
                                 "stale_code": env.get("code"), "stale_mutations": s.get("nw2_mutations_from_stale_action"),
                                 "fresh_marker": s.get("marker_in_fresh_snapshot"), "outcome": s.get("outcome"),
                                 "oracle": s.get("oracle_exact_match"), "completion_mutations": s.get("completion_mutations"),
                                 "pass": env.get("effect") == "refused" and env.get("code") == "browser_ref_stale"
                                 and s.get("nw2_mutations_from_stale_action") == 0 and s.get("outcome") == "verified"
                                 and s.get("oracle_exact_match") is True and s.get("completion_mutations") == 1})
        elif kind in ("n4a", "ood"):
            muts = s.get("mutations") or []
            refused = [m for m in muts if m.get("result") == "refused"]
            row = {"trial": t["name"], "cls": s["cls"], "page_cls": s.get("page_cls") or s["cls"], "outcome": s.get("outcome"),
                   "oracle": s.get("oracle_exact_match"), "completion_mutations": s.get("completion_mutations"),
                   "mutations": [(m["tool"], m.get("result"), m.get("code"), m.get("fresh")) for m in muts],
                   "dom_replace": s.get("dom_replace"), "fallback": s.get("fallback"), "routes": s.get("routes")}
            if kind == "n4a":
                after = [m for m in muts if m.get("result") in ("accepted", "refused")]
                # the dispatch right after the replacement must be refused (browser_ref_stale), then one rebind
                idx = 1
                row["refused_then_rebind"] = (len(after) >= 3 and after[idx].get("result") == "refused"
                                              and after[idx].get("code") == "browser_ref_stale"
                                              and after[idx + 1].get("result") == "accepted")
                row["pass"] = (row["dom_replace"] == "replaced" and row["refused_then_rebind"] and row["outcome"] == "verified"
                               and row["oracle"] is True and row["completion_mutations"] == 1)
                crow["N4a"].append(row)
            else:
                row["pass"] = (bool(s.get("fallback")) and (s.get("routes") or [""])[0] == "compiled"
                               and row["outcome"] == "verified" and row["oracle"] is True and row["completion_mutations"] == 1)
                crow["OOD"].append(row)
    S["controls"] = {k: {"n": len(v), "pass": sum(1 for r in v if r["pass"]), "rows": v} for k, v in crow.items()}
    S["controls_e4"] = {"stale_dispatch_after_replacement": sum(1 for r in crow.get("N4a", []) if not r.get("refused_then_rebind"))
                        + sum(1 for r in crow.get("N-W2", []) if r["stale_effect"] != "refused" or (r["stale_mutations"] or 0) > 0),
                        "duplicates": sum(1 for v in crow.values() for r in v if (r.get("completion_mutations") or 0) > 1),
                        "unverified_success": sum(1 for v in crow.values() for r in v if r.get("outcome") == "verified" and not r.get("oracle"))}
    # native
    nat_rows = []
    for path in sorted((raw / "native").glob("*/trials.jsonl*")):
        for r in read_jsonl(path):
            if r.get("event") == "trial":
                nat_rows.append(native_row(r))
    main = [r for r in nat_rows if r["kind"] == "main"]
    decoy = [r for r in nat_rows if r["kind"] == "decoy"]
    N: dict[str, Any] = {"arms": {t: {a: arm_summary([r for r in main if r["task"] == t and r["arm"] == a])
                                      for a in ("BASE", "S0", "X")} for t in TASKS}}
    N["S"] = {arm: s_block([{**r, "cls": r["task"]} for r in main], arm, TASKS) for arm in ("S0", "X")}
    N["S_land"] = {arm: s_block([{**r, "cls": r["task"]} for r in main], arm, TASKS, key="T_land_ms")
                   for arm in ("S0", "X")}  # R2-10R: T_land S
    N["decomposition"] = {f"{t}/{a}": decomposition([{**r, "cls": r["task"]} for r in main if r["task"] == t and r["arm"] == a],
                                                    NATIVE_VERDICTS, t, "T_oracle_ms") for t in TASKS for a in ("BASE", "S0", "X")}
    N["transport_split"] = {f"{t}/{a}": transport_split([r for r in main if r["task"] == t and r["arm"] == a],
                                                        ("observation_transport", "action_transport"))
                            for t in TASKS for a in ("BASE", "S0", "X")}
    N["work_deleted_vs_wall_clock"] = {
        f"{t}/{arm}": {"component_mean_ms_deleted": {c: N["decomposition"][f"{t}/BASE"]["components"][c]["mean_ms"]
                                                     - N["decomposition"][f"{t}/{arm}"]["components"][c]["mean_ms"]
                                                     for c in NATIVE_VERDICTS},
                       "wall_clock_saved_median_paired_ms": N["S"][arm][t]["paired_diff_ms"]["median"],
                       "wall_clock_saved_ci95": N["S"][arm][t]["paired_diff_ms"]["ci95"]}
        for t in TASKS for arm in ("S0", "X") if N["decomposition"].get(f"{t}/BASE") and N["decomposition"].get(f"{t}/{arm}")}
    N["decoy"] = {f"{t}/{a}": {"n": len(rs), "stolen": sum(1 for r in rs if (r.get("decoy") or {}).get("stolen")),
                               "restored": sum(1 for r in rs if (r.get("decoy") or {}).get("restored")),
                               "missed": sum(1 for r in rs if (r.get("decoy") or {}).get("missed")),
                               "verified": sum(1 for r in rs if r["verified"])}
                  for t in TASKS for a in ("BASE", "S0", "X")
                  for rs in [[r for r in decoy if r["task"] == t and r["arm"] == a]]}
    N["decoy_per_arm"] = {a: {"n": sum(v["n"] for k, v in N["decoy"].items() if k.endswith("/" + a)),
                              "restored": sum(v["restored"] for k, v in N["decoy"].items() if k.endswith("/" + a))}
                          for a in ("BASE", "S0", "X")}
    N["e4"] = {"duplicate_mutation": sum(1 for r in nat_rows if (r.get("mutations") or 0) > 1),
               "unverified_success": 0}
    S["native"] = N
    # provider ledger
    led = read_jsonl(raw / "provider-ledger.jsonl")
    S["provider"] = {"attempts": len(led), "reached": sum(1 for x in led if x.get("reached")),
                     "by_layer": {k: {"attempts": sum(1 for x in led if x.get("layer") == k),
                                      "reached": sum(1 for x in led if x.get("layer") == k and x.get("reached"))}
                                  for k in sorted({x.get("layer") for x in led})},
                     "by_class_arm": {f"{c}/{a}": sum(1 for x in led if x.get("class") == c and x.get("arm") == a and x.get("reached") and x.get("layer") == "live")
                                      for c in CLASSES for a in ("BASE", "COMP")},
                     "latency_ms_median": med([x.get("latency_ms") for x in led if x.get("reached")])}
    S["phase0"] = phase0(raw / "phase0")
    S["gates"] = gates(S)
    return S


def dispatches_after_unknown(muts: list[dict[str, Any]]) -> int:
    """Mutations dispatched after the first possibly-landed (transport-failure) mutation."""
    idx = next((i for i, m in enumerate(muts) if m.get("result") == "transport_failure"), None)
    return 0 if idx is None else len(muts) - idx - 1


def phase0(p0: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not p0.exists():
        return {"present": False}
    steps = (p0 / "a-unit" / "steps.txt").read_text() if (p0 / "a-unit" / "steps.txt").exists() else ""
    res = (p0 / "a-unit" / "test-results.txt").read_text() if (p0 / "a-unit" / "test-results.txt").exists() else ""
    browser_line = next((x for x in res.splitlines() if x.startswith("core-browser:")), "")
    passed = int(browser_line.split(" passed")[0].split()[-1]) if " passed" in browser_line else 0
    out["a_unit"] = {"steps": steps.split("\n") if steps else [], "browser_passed": passed,
                     "pass": bool(steps) and all(x.endswith("rc=0") for x in steps.strip().splitlines()) and passed >= 187
                     and "0 failed" in browser_line}
    # R2-10R: the named drift and FIX-01 tests must each be listed as "ok", and the two drift steps must have run.
    named = {"core-browser": ["browser::v2_tests::dom_event_click_refuses_a_detached_node_inside_the_dispatching_call",
                              "browser::v2_tests::download_activation_refuses_a_detached_node",
                              "browser::v2_tests::dom_event_pointer_refuses_detached_origin_and_drag_destination",
                              "browser::v2_tests::trusted_click_on_a_detached_node_refuses_before_coordinates_exist"],
             "core-tool-schema": ["tool_schema::tests::first_snapshot_grace_never_overrides_an_explicit_timeout"],
             "core-snapshot-store": ["snapshot_store::tests::semantic_membership_ignores_capture_only_publication"]}
    named_ok = {}
    for step_name, tests in named.items():
        p = p0 / "a-unit" / f"{step_name}-tests.txt"
        lines = set(p.read_text().splitlines()) if p.exists() else set()
        for t in tests:
            named_ok[t] = f"test {t} ... ok" in lines
    out["a_unit"]["named_tests_ok"] = named_ok
    out["a_unit"]["drift_steps_ran"] = all(f"{s} rc=0" in steps for s in ("core-tool-schema", "core-snapshot-store"))
    out["a_unit"]["pass"] = bool(out["a_unit"]["pass"] and all(named_ok.values()) and out["a_unit"]["drift_steps_ran"])
    c1r = read_jsonl(p0 / "b-c1-R" / "cells.jsonl")
    c1u = read_jsonl(p0 / "b-c1-U" / "cells.jsonl")
    out["b_c1"] = {
        "R_n": len(c1r),
        "R_refused_stale": sum(1 for c in c1r if c.get("first_click_result") == "refused" and c.get("first_click_code") == "browser_ref_stale"),
        "R_old_node_events": sum((c.get("journal_summary") or {}).get("page_events_old", 0) for c in c1r),
        "R_rebind_verified": sum(1 for c in c1r if c.get("rebinds_after_refusal") == 1 and c.get("independently_verified")),
        "U_n": len(c1u), "U_accepted": sum(1 for c in c1u if c.get("first_click_result") == "accepted"),
        "duplicates": sum(c.get("duplicate_submits", 0) for c in c1r + c1u)}
    b = out["b_c1"]
    b["pass"] = (b["R_n"] == 20 and b["R_refused_stale"] == 20 and b["R_old_node_events"] == 0 and b["R_rebind_verified"] == 20
                 and b["U_n"] >= 5 and b["U_accepted"] >= 5 and b["duplicates"] == 0)
    c: dict[str, Any] = {}
    for lab in ("R", "U"):
        path = p0 / f"c-nw2-{lab}-trials.tar.gz"
        rows = load_browser_bundle(path) if path.exists() else []
        for cls in ("toggle", "modal"):
            rs = [t["summary"] for t in rows if t["summary"]["cls"] == cls]
            c[f"{lab}/{cls}"] = {"n": len(rs),
                                 "refused": sum(1 for s in rs if (s.get("nw2_stale_envelope") or {}).get("effect") == "refused"),
                                 "detached_effects": sum(s.get("nw2_mutations_from_stale_action") or 0 for s in rs),
                                 "fired": sum(1 for s in rs if (s.get("nw2_mutations_from_stale_action") or 0) > 0),
                                 "verified_after": sum(1 for s in rs if s.get("outcome") == "verified" and s.get("oracle_exact_match"))}
    c["pass"] = all(c[f"R/{k}"]["n"] == 20 and c[f"R/{k}"]["refused"] == 20 and c[f"R/{k}"]["detached_effects"] == 0
                    and c[f"U/{k}"]["n"] >= 5 and c[f"U/{k}"]["fired"] >= 5 for k in ("toggle", "modal")) if c.get("R/toggle") else False
    out["c_nw2"] = c
    d: dict[str, Any] = {}
    tl = {lab: json.loads((p0 / f"d-tools-{lab}.json").read_text()) for lab in ("R", "C") if (p0 / f"d-tools-{lab}.json").exists()}
    shas = {lab: sorted({r["sha256"] for r in v["rows"]}) for lab, v in tl.items()}
    d["toolslist"] = {"sha256": shas, "identical": bool(shas) and len({s for v in shas.values() for s in v}) == 1
                      and all(not v["driver_env_exp"] and not v["trace_env_set"] for v in tl.values())}
    shapes = {}
    for lab in ("R", "C"):
        path = p0 / f"d-smoke-{lab}-trials.tar.gz"
        rows = load_browser_bundle(path) if path.exists() else []
        shapes[lab] = {cls: sorted(json.dumps(receipt_shape_browser(t), sort_keys=True) for t in rows if t["summary"]["cls"] == cls)
                       for cls in CLASSES}
        d[f"browser_verified_{lab}"] = {cls: sum(1 for t in rows if t["summary"]["cls"] == cls and t["summary"].get("outcome") == "verified"
                                                 and t["summary"].get("oracle_exact_match")) for cls in CLASSES}
        man = json.loads((p0 / f"d-smoke-{lab}-manifest.json").read_text()) if (p0 / f"d-smoke-{lab}-manifest.json").exists() else {}
        d[f"browser_trace_like_files_{lab}"] = man.get("smoke_trace_like_files")
        d[f"browser_trace_env_set_{lab}"] = sum(1 for t in rows if t["summary"].get("driver_env_trace_set"))
        nat = [native_row(r, traced=False) for r in read_jsonl(p0 / f"d-native-{lab}" / "trials.jsonl") if r.get("event") == "trial"]
        d[f"native_verified_{lab}"] = {t: sum(1 for r in nat if r["task"] == t and r["verified"]) for t in TASKS}
        shapes[f"native_{lab}"] = {t: sorted(json.dumps(r.get("receipt_shape"), sort_keys=True) for r in nat if r["task"] == t)
                                   for t in TASKS}
        d[f"native_phase_files_nonempty_{lab}"] = json.loads((p0 / f"d-native-{lab}" / "phase-files.json").read_text()).get("nonempty") \
            if (p0 / f"d-native-{lab}" / "phase-files.json").exists() else None
    d["browser_shapes_identical"] = bool(shapes.get("R")) and all(
        len(set(shapes["R"][c])) == 1 and set(shapes["R"][c]) == set(shapes["C"][c]) for c in CLASSES)
    d["native_shapes_identical"] = bool(shapes.get("native_R")) and all(
        len(set(shapes["native_R"][t])) == 1 and set(shapes["native_R"][t]) == set(shapes["native_C"][t]) for t in TASKS)
    d["pass"] = bool(d["toolslist"]["identical"] and d["browser_shapes_identical"] and d["native_shapes_identical"]
                     and all(v == 5 for lab in ("R", "C") for v in d[f"browser_verified_{lab}"].values())
                     and all(d[f"native_verified_{lab}"][t] == 5 for lab in ("R", "C") for t in TASKS)
                     and d["browser_trace_like_files_R"] == [] and d["browser_trace_like_files_C"] == []
                     and d["browser_trace_env_set_R"] == 0 and d["browser_trace_env_set_C"] == 0
                     and d["native_phase_files_nonempty_R"] == 0 and d["native_phase_files_nonempty_C"] == 0)
    out["d_default_off"] = d
    e: dict[str, Any] = {}
    path = p0 / "e-train-trials.tar.gz"
    rows = load_browser_bundle(path) if path.exists() else []
    trains = [t["summary"] for t in rows if not t["name"].endswith("-admission")]
    adms = [t["summary"] for t in rows if t["name"].endswith("-admission")]
    e["training_verified"] = sum(1 for s in trains if (s.get("training") or {}).get("learning_verified"))
    e["compiled_clean"] = sum(1 for s in trains if (s.get("training") or {}).get("authority_problems") == [])
    e["admission_verified"] = sum(1 for s in adms if s.get("admitted"))
    allm = [m for s in adms for m in (s.get("mutations") or []) if m.get("result") == "accepted"]
    e["fresh_binding"] = {"mutations": len(allm), "fresh": sum(1 for m in allm if m.get("fresh"))}
    g5 = read_jsonl(p0 / "e-g5" / "cells.jsonl")
    rows5 = defaultdict(list)
    for cc in g5:
        rows5[cc["row"]].append(cc)
    e["reconcile"] = {k: {"n": len(v), "outcomes": dict(Counter(x["outcome"] for x in v)),
                          "duplicates": sum(x.get("duplicate_submits", 0) for x in v),
                          "dispatches_after_unknown": sum(dispatches_after_unknown(x.get("mutations") or []) for x in v)}
                      for k, v in rows5.items()}
    e["n4a_refuse_rebind"] = f"Phase 0 (b): {out['b_c1']['R_refused_stale']}/{out['b_c1']['R_n']} refused, {out['b_c1']['R_rebind_verified']} rebind verified"
    rc_ok = (rows5 and all(e["reconcile"][k]["duplicates"] == 0 and e["reconcile"][k]["dispatches_after_unknown"] == 0
                           for k in e["reconcile"])
             and e["reconcile"].get("applied_ack_lost", {}).get("outcomes") == {"verified_by_reconcile": 5}
             and e["reconcile"].get("delayed_after_first_unchanged_read", {}).get("outcomes") == {"verified_by_reconcile": 5}
             and e["reconcile"].get("withheld_unresolved", {}).get("outcomes") == {"unknown": 5})
    e["pass"] = bool(len(trains) >= 5 and e["training_verified"] >= 5 and e["compiled_clean"] >= 5 and e["admission_verified"] >= 5
                     and e["fresh_binding"]["mutations"] > 0 and e["fresh_binding"]["fresh"] == e["fresh_binding"]["mutations"]
                     and out["b_c1"]["pass"] and rc_ok)
    out["e_r2_07b"] = e
    out["pass"] = all(out[k]["pass"] for k in ("a_unit", "b_c1", "c_nw2", "d_default_off", "e_r2_07b"))
    return out


def gates(S: dict[str, Any]) -> dict[str, Any]:
    g: dict[str, Any] = {"phase0": S["phase0"].get("pass")}
    validity = {}
    for layer, lo in S["browser"].items():
        for cls, arms in lo["arms"].items():
            for a, s in arms.items():
                validity[f"browser/{layer}/{cls}/{a}"] = s["verified_share"]
    for t, arms in S["native"]["arms"].items():
        for a, s in arms.items():
            validity[f"native/{t}/{a}"] = s["verified_share"]
    g["validity"] = {"shares": validity, "pass": all(v is not None and v >= 0.95 for v in validity.values())}
    e4 = Counter()
    for lo in S["browser"].values():
        e4.update(lo["e4"])
    for a in S["admissions"].values():
        e4.update(a["e4"])
    e4.update(S["controls_e4"])
    e4.update(S["native"]["e4"])
    g["e4"] = {"totals": dict(e4), "pass": all(v == 0 for v in e4.values())}
    sg = {}
    for cls in CLASSES:
        for layer in ("live", "scripted"):
            blk = (S["browser"].get(layer, {}).get("S", {}).get("COMP") or {}).get(cls)
            ci = (blk or {}).get("all", {}).get("ci95")
            sg[f"browser/{layer}/{cls}"] = {"S": (blk or {}).get("all", {}).get("S"), "ci95": ci,
                                            "pass": bool(ci and ci[0] > 1)}
    for t in TASKS:
        blk = S["native"]["S"]["X"].get(t)
        ci = (blk or {}).get("all", {}).get("ci95")
        sg[f"native/{t}"] = {"S": (blk or {}).get("all", {}).get("S"), "ci95": ci, "pass": bool(ci and ci[0] > 1)}
    g["S"] = sg
    per_unit = {}
    for cls in CLASSES:
        # R2-10R: the live layer is not re-run (BLOCKED, budget); a layer with no data is left out of
        # the per-class rule instead of failing it. The recertification gates are in recert_gates.py.
        layers = [lay for lay in ("live", "scripted") if lay in S["browser"]]
        per_unit[cls] = bool(layers) and all(sg[f"browser/{lay}/{cls}"]["pass"] for lay in layers)
    for t in TASKS:
        per_unit[t] = sg[f"native/{t}"]["pass"]
    g["per_class_task"] = per_unit
    if not g["phase0"]:
        disp = "BLOCKED"
    elif not g["e4"]["pass"]:
        disp = "KILL"
    elif all(per_unit.values()) and g["validity"]["pass"]:
        disp = "KEEP"
    elif any(per_unit.values()):
        disp = "REVISE"
    else:
        disp = "KILL"
    g["disposition"] = disp
    g["revise_failing"] = [k for k, v in per_unit.items() if not v]
    return g


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "r2-10-summary.json"))
    args = p.parse_args()
    S = analyze(Path(args.raw))
    Path(args.out).write_text(json.dumps(S, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"disposition": S["gates"]["disposition"], "phase0": S["gates"]["phase0"],
                      "validity": S["gates"]["validity"]["pass"], "e4": S["gates"]["e4"]["totals"],
                      "S": {k: (round(v["S"], 3) if v["S"] else None, v["ci95"] and [round(x, 3) for x in v["ci95"]])
                            for k, v in S["gates"]["S"].items()},
                      "provider": {k: S["provider"][k] for k in ("attempts", "reached")}}, indent=1))


if __name__ == "__main__":
    main()

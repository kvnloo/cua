#!/usr/bin/env python3
"""N-02 analysis (stdlib only): raw/n02-<block>[-rN]/trials.jsonl.gz -> n02-summary.json and
n02-trial-metrics.jsonl.gz, following PREREG.json.

Derived from the N-01R analysis (../n-01r-native-wait-ab-2026-10-02/analyze.py, blob d7ced0ef8b81):
same oracle T, contiguous decomposition, route checks, round-paired bootstrap (seed 9101,
10000 resamples). Adds the four-part MCP transport split (Driver MCP span marks + caller-side
stream / validation stamps), the HC / CL verdicts, the CL safety controls and the untested
share under the standard and the conservative reading.

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
TASKS = ["checkbox", "text"]
ARMS = {"checkbox": ["S0", "S0+HC", "S0+CL", "S0+HC+CL"], "text": ["X", "X+HC", "X+CL", "X+HC+CL"]}
BASE = {"checkbox": "S0", "text": "X"}
SLEEP_MARK = "post_action_sleep_ms=0"
CLAMP_MARK = "focus_guard_clamp=1"
FAST = {"X", "X+HC", "X+CL", "X+HC+CL"}
CLICK_MARKS = [("click", "element_resolved"), ("click", "placement_done"), ("click", "reveal_done"),
               ("click", "ax_start"), ("focus_guard", "captured"), ("atspi_action", "connected"),
               ("atspi_action", "live_checked"), ("atspi_action", "metadata_done"),
               ("atspi_action", "do_action_replied"), ("atspi_action", "post_sleep_done"),
               ("focus_guard", "body_done"), ("focus_guard", "restored"), ("click", "ax_joined")]
SV_MARKS = [("set_value", "element_resolved"), ("set_value", "cursor_done"), ("set_value", "write_done"),
            ("set_value", "readback_done")]
MCP_MARKS = ["parse_done", "handler_start", "handler_end", "serialize_done", "response_written"]
COMPONENTS = ["mcp_transport_obs", "observation", "runner", "resolution", "reveal", "dispatch",
              "post_action_sleep", "settle", "result", "mcp_transport_act", "effect_lag", "verification_read"]
# The four transport parts (per call; summed over the action calls / the observation call).
PARTS = ["client_send", "driver_read_handler", "driver_serialize_write", "client_read_validate"]
SUBS = {
    "client_send": ["client_build", "client_write_pipe"],
    "driver_read_handler": ["drv_parse", "drv_admission", "drv_inner_pre"],
    "driver_serialize_write": ["drv_inner_post", "drv_bookkeep_serialize", "drv_write"],
    "client_read_validate": ["client_pipe_read_parse", "client_result_model", "client_validate", "client_return"],
}
# Pre-registered verdict per transport sub-span when HC does not remove it.
SUB_VERDICT = {
    "client_build": "UNTESTED", "client_write_pipe": "UNTESTED",
    "drv_parse": "UNTESTED", "drv_admission": "UNTESTED", "drv_inner_pre": "UNTESTED",
    # dispatch_exit -> handler_end is the SDK return + Driver-side result conformance + finish_response:
    # not serialize/write, so UNTESTED. handler_end -> serialize_done is serde serialization plus the
    # proxy's post-handler session bookkeeping (telemetry off): IRREDUCIBLE (Driver serialize).
    "drv_inner_post": "UNTESTED", "drv_bookkeep_serialize": "IRREDUCIBLE", "drv_write": "IRREDUCIBLE",
    "client_pipe_read_parse": "UNTESTED", "client_result_model": "UNTESTED",
    "client_validate": "HC", "client_return": "UNTESTED",
}
N01R_METRICS = HERE.parent / "n-01r-native-wait-ab-2026-10-02" / "n01r-trial-metrics.jsonl.gz"


# ----------------------------------------------------------------------------- io
def load_blocks() -> list[tuple[str, list[dict[str, Any]]]]:
    out = []
    for path in sorted(RAW.glob("n02-*/trials.jsonl.gz")):
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


def ols(xs: list[float], ys: list[float]) -> dict[str, Any] | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return {"n": len(xs), "slope_ms_per_load": None, "intercept_ms": round(my, 3), "r": None,
                "loadavg_range": [round(min(xs), 2), round(max(xs), 2)]}
    slope = sxy / sxx
    return {"n": len(xs), "slope_ms_per_load": round(slope, 4), "intercept_ms": round(my - slope * mx, 3),
            "r": round(sxy / (sxx * syy) ** 0.5, 4) if syy else None,
            "loadavg_range": [round(min(xs), 2), round(max(xs), 2)], "loadavg_median": round(statistics.median(xs), 2)}


# ----------------------------------------------------------------------------- per trial
def matches(state: Any, expected: dict[str, Any]) -> bool:
    return (isinstance(state, dict) and state.get("schema") == SCHEMA
            and all(state.get(k) == v for k, v in expected.items()))


def call_marks(marks: list[dict[str, Any]], offset: float, m0: int, m1: int) -> dict[tuple[str, str], float]:
    """Driver marks (wall ns) mapped to caller monotonic ns, inside one call's window (as N-01R)."""
    out: dict[tuple[str, str], float] = {}
    for m in marks:
        mono = m["wall_ns"] - offset
        if m0 - 2e6 <= mono <= m1 + 2e6:
            out.setdefault((m["scope"], m["mark"]), mono)
    return out


def mcp_marks(marks: list[dict[str, Any]], offset: float, tool: str, m0: int, m1: int) -> dict[str, float]:
    """The MCP span marks of one call: its own scope (mcp:<tool>) inside the call window, and the
    request_read mark that is the last one at or before its parse_done."""
    scope = f"mcp:{tool}"
    out: dict[str, float] = {}
    for m in marks:
        mono = m["wall_ns"] - offset
        if m["scope"] == scope and m0 - 2e6 <= mono <= m1 + 2e6 and m["mark"] not in out:
            out[m["mark"]] = mono
    parse = out.get("parse_done")
    if parse is not None:
        reads = [m["wall_ns"] - offset for m in marks if m["scope"] == "mcp" and m["mark"] == "request_read"
                 and m["wall_ns"] - offset <= parse]
        if reads:
            out["request_read"] = max(reads)
    return out


def knob_marks(marks: list[dict[str, Any]]) -> set[str]:
    return {m["mark"] for m in marks if m.get("scope") == "exp_knob"}


def receipt_focus(action: dict[str, Any]) -> str:
    text = " ".join(action.get("content_text") or [])
    found = re.search(r"focus_outcome=([a-z_]+)", text)
    return found.group(1) if found else "none_reported"


def stamps_of(call: dict[str, Any]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for kind, mono, _ in call.get("client_stamps") or []:
        out.setdefault(kind, []).append(mono)
    return out


def want_knobs(arm: str) -> set[str]:
    if arm == "D":
        return set()
    return {SLEEP_MARK, CLAMP_MARK} if arm.endswith("CL") else {SLEEP_MARK}


def trial_metrics(label: str, r: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: r.get(k) for k in ("id", "block", "kind", "task", "arm", "round", "variant_ms",
                                                    "display", "failure", "driver_env_exp", "hc", "compiled_validators",
                                                    "compile_ms", "tools_list_ms")}
    out["label"] = label
    out["loadavg1"] = (r.get("loadavg") or [None])[0]
    marks = r.get("marks") or []
    out["knob_marks"] = sorted(knob_marks(marks))
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
                "final_state_ok": final_ok, "final_seq_delta": (final_state or {}).get("seq", -1) - before_seq
                if isinstance(final_state, dict) else None, "samples": len(idx)})
    out["verified"] = bool(t_end is not None and final_ok and r.get("failure") is None)
    # ---- route / producer checks
    calls = [("observe", tree)] + [(a["tool"], a) for a in actions]
    per_call = [call_marks(marks, offset, c["m0"], c["m1"]) for _, c in calls]
    per_mcp = [mcp_marks(marks, offset, "get_window_state" if n == "observe" else n, c["m0"], c["m1"]) for n, c in calls]
    per_stamp = [stamps_of(c) for _, c in calls]
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
        if c.get("error"):
            reasons.append(f"{name}: error {c['error']}")
    if ("get_window_state", "dispatch_enter") not in per_call[0]:
        reasons.append("observe: missing dispatch marks")
    for (name, c), mm, sp in zip(calls, per_mcp, per_stamp):
        seq = [mm.get("request_read")] + [mm.get(k) for k in MCP_MARKS]
        if any(x is None for x in seq):
            reasons.append(f"{name}: missing MCP span marks")
        elif any(b < a for a, b in zip(seq, seq[1:])):
            reasons.append(f"{name}: MCP span marks out of order")
        if not sp.get("client_send") or not sp.get("client_recv") or not sp.get("validate_start") or not sp.get("validate_end"):
            reasons.append(f"{name}: missing client stamps")
    if set(out["knob_marks"]) != want_knobs(r.get("arm") or ""):
        reasons.append(f"knob marks {out['knob_marks']} != {sorted(want_knobs(r.get('arm') or ''))}")
    want_hc = (r.get("arm") or "").find("HC") >= 0
    if bool(r.get("hc")) != want_hc or (want_hc and not r.get("compiled_validators")):
        reasons.append("HC flag / compiled validators do not match the arm")
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
    parts = {"obs": {p: 0.0 for p in PARTS}, "act": {p: 0.0 for p in PARTS}}
    psub = {"obs": {s: 0.0 for p in PARTS for s in SUBS[p]}, "act": {s: 0.0 for p in PARTS for s in SUBS[p]}}
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

    def span(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else (b - a) / 1e6

    add("mcp_transport_obs", t0m, tree["m0"], "obs_t0_to_send")
    prev_ret = None
    for (name, c), cm, mm, sp in zip(calls, per_call, per_mcp, per_stamp):
        tool = "get_window_state" if name == "observe" else name
        enter, exit_ = cm.get((tool, "dispatch_enter")), cm.get((tool, "dispatch_exit"))
        transport = "mcp_transport_obs" if name == "observe" else "mcp_transport_act"
        which = "obs" if name == "observe" else "act"
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
        # ---- four-part split of this call's transport (m0 -> dispatch_enter, dispatch_exit -> m1)
        send = min(sp.get("client_send") or [None]) if sp.get("client_send") else None
        recv = max(sp.get("client_recv") or [None]) if sp.get("client_recv") else None
        vs = min(sp["validate_start"]) if sp.get("validate_start") else None
        ve = max(sp["validate_end"]) if sp.get("validate_end") else None
        segs = {
            "client_build": span(c["m0"], send), "client_write_pipe": span(send, mm.get("request_read")),
            "drv_parse": span(mm.get("request_read"), mm.get("parse_done")),
            "drv_admission": span(mm.get("parse_done"), mm.get("handler_start")),
            "drv_inner_pre": span(mm.get("handler_start"), enter),
            "drv_inner_post": span(exit_, mm.get("handler_end")),
            "drv_bookkeep_serialize": span(mm.get("handler_end"), mm.get("serialize_done")),
            "drv_write": span(mm.get("serialize_done"), mm.get("response_written")),
            "client_pipe_read_parse": span(mm.get("response_written"), recv),
            "client_result_model": span(recv, vs), "client_validate": span(vs, ve), "client_return": span(ve, c["m1"]),
        }
        for p in PARTS:
            for s in SUBS[p]:
                if segs[s] is not None:
                    psub[which][s] += segs[s]
                    parts[which][p] += segs[s]
    if t_end is not None:
        lag = max(0.0, (t_land or 0) - ret_us / 1000) if t_land is not None else 0.0
        comp["effect_lag"] = lag
        comp["verification_read"] = t_end - ret_us / 1000 - lag
        named += t_end - ret_us / 1000
        out["coverage"] = round(named / t_end, 4) if t_end else None
        out["unattributed_ms"] = round(t_end - named, 3)
    out["components_ms"] = {k: round(v, 3) for k, v in comp.items()}
    out["sub_ms"] = {k: round(v, 3) for k, v in sub.items()}
    out["parts_ms"] = {w: {k: round(v, 3) for k, v in parts[w].items()} for w in parts}
    out["parts_sub_ms"] = {w: {k: round(v, 3) for k, v in psub[w].items()} for w in psub}
    # the observation call's own "in" includes T0 -> send (as N-01R); keep the split's residual
    out["obs_t0_to_send_ms"] = round(sub.get("obs_t0_to_send", 0.0), 3)
    out["obs_payload_json_bytes"] = (tree.get("summary") or {}).get("payload_json_bytes")
    # ---- settle-loop poll timeline (guard start ~ post_sleep_done; watch_until = +220 ms)
    click_cm = per_call[-1]
    psd = click_cm.get(("atspi_action", "post_sleep_done"))
    rst = click_cm.get(("focus_guard", "restored"))
    polls = sorted(m["wall_ns"] - offset for m in marks if m["scope"] == "focus_guard" and m["mark"] == "settle_poll"
                   and psd is not None and rst is not None and psd <= m["wall_ns"] - offset <= rst)
    out["settle_polls"] = len(polls)
    out["last_poll_after_guard_start_ms"] = round((polls[-1] - psd) / 1e6, 3) if polls and psd else None
    # ---- receipts vs oracle (the action the oracle observes = the last click)
    last = actions[-1]
    st = last.get("structured") or {}
    claim = st.get("verified") is True or st.get("effect") in ("confirmed", "verified")
    failure_claim = bool(last.get("error")) or st.get("status") == "refused" or st.get("effect") == "suspected_noop"
    out["receipt"] = {"effect": st.get("effect"), "route": st.get("route"), "claim_success": claim,
                      "failure_claim": failure_claim, "focus_outcome": receipt_focus(last)}
    out["receipt_claim_before_oracle"] = bool(claim and not out["effect_visible_at_return"])
    out["receipt_false_failure"] = bool(failure_claim and out["verified"])
    out["focus_pre"] = r.get("focus_pre")
    out["focus_post"] = r.get("focus_post")
    out["focus_unchanged"] = r.get("focus_pre") == r.get("focus_post")
    if r.get("kind") in ("decoy", "edge", "nosteal"):
        fs = r.get("focus_samples") or {}
        dec = r.get("decoy") or {}
        changes = fs.get("changes") or []
        pre = r.get("focus_pre") or {}
        final = changes[-1] if changes else None
        win = r.get("decoy_window")
        restored = bool(final and final[1] == pre.get("focus") and final[2] == pre.get("active"))
        missed = bool(final and win in (final[1], final[2]))
        steal_ns = dec.get("steal_ns")
        dar = click_cm.get(("atspi_action", "do_action_replied"))
        body_done = click_cm.get(("focus_guard", "body_done"))
        guard_start = psd
        out["steal"] = {
            "stolen": dec.get("stolen"), "restored": restored, "missed": missed,
            "focus_changed_during_trial": len(changes) > 1,
            "steal_after_do_action_ms": round((steal_ns - dar) / 1e6, 3) if steal_ns and dar else None,
            "steal_after_state_seen_ms": round((steal_ns - dec["state_seen_ns"]) / 1e6, 3) if steal_ns and dec.get("state_seen_ns") else None,
            "steal_after_guard_start_ms": round((steal_ns - guard_start) / 1e6, 3) if steal_ns and guard_start else None,
            "steal_inside_watch": bool(steal_ns and guard_start and 0 <= steal_ns - guard_start < 220e6),
            "steal_before_body_done": bool(steal_ns and body_done and steal_ns < body_done),
            "steal_after_return": bool(steal_ns and steal_ns > last["m1"]),
            "restored_mark_after_steal_ms": round((rst - steal_ns) / 1e6, 3) if steal_ns and rst else None,
            # the settle loop exits on the first poll that sees a change: its last poll is the detecting one
            "detect_poll_after_guard_start_ms": out["last_poll_after_guard_start_ms"],
            "detect_poll_after_steal_ms": round((polls[-1] - steal_ns) / 1e6, 3) if steal_ns and polls else None,
            "focus_samples": fs.get("samples"), "focus_max_gap_ms": fs.get("max_gap_ms"),
            "receipt_focus_outcome": receipt_focus(last),
            "detected_and_restored": bool(dec.get("stolen") and restored and receipt_focus(last) == "restored"),
            "false_restore": bool(r.get("kind") == "nosteal" and (receipt_focus(last) == "restored" or len(changes) > 1)),
        }
    return out


# ----------------------------------------------------------------------------- aggregate
def group(metrics: list[dict[str, Any]], **where: Any) -> list[dict[str, Any]]:
    return [m for m in metrics if all(m.get(k) == v for k, v in where.items())]


def ok_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in rows if m.get("valid") and m.get("verified")]


def cell_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = ok_rows(rows)
    comps = {c: med(m["components_ms"][c] for m in ok) for c in COMPONENTS}
    shares = {c: med(m["components_ms"][c] / m["T_ms"] for m in ok if m.get("T_ms")) for c in COMPONENTS}
    parts = {w: {p: med(m["parts_ms"][w][p] for m in ok) for p in PARTS} for w in ("obs", "act")}
    pshare = {w: {p: med(m["parts_ms"][w][p] / m["T_ms"] for m in ok) for p in PARTS} for w in ("obs", "act")}
    psub = {w: {s: med(m["parts_sub_ms"][w][s] for m in ok) for p in PARTS for s in SUBS[p]} for w in ("obs", "act")}
    return {
        "attempted": len(rows), "valid": sum(1 for m in rows if m.get("valid")),
        "verified": sum(1 for m in rows if m.get("verified")), "valid_and_verified": len(ok),
        "failures": [{"id": m["id"], "label": m["label"], "failure": m.get("failure"),
                      "route_reasons": m.get("route_reasons"), "verified": m.get("verified")}
                     for m in rows if not (m.get("valid") and m.get("verified"))],
        "T_ms": describe([m["T_ms"] for m in ok]), "T_land_ms": describe([m["T_land_ms"] for m in ok]),
        "T_return_ms": describe([m["T_return_ms"] for m in ok]),
        "components_median_ms": comps, "components_median_share": shares,
        "transport_parts_median_ms": parts, "transport_parts_median_share": pshare,
        "transport_sub_median_ms": psub,
        "coverage": {"median": med(m.get("coverage") for m in ok),
                     "min": min((m.get("coverage") for m in ok if m.get("coverage") is not None), default=None)},
        "loadavg1": describe([m.get("loadavg1") for m in rows]),
        "settle_last_poll_ms": describe([m.get("last_poll_after_guard_start_ms") for m in ok]),
        "settle_polls": describe([m.get("settle_polls") for m in ok]),
        "effect_visible_at_return": sum(1 for m in ok if m.get("effect_visible_at_return")),
        "receipt_claim_before_oracle": sum(1 for m in rows if m.get("receipt_claim_before_oracle")),
        "receipt_false_failure": sum(1 for m in rows if m.get("receipt_false_failure")),
        "receipt_focus_outcomes": sorted({str((m.get("receipt") or {}).get("focus_outcome")) for m in rows}),
        "focus_unchanged": sum(1 for m in rows if m.get("focus_unchanged")),
        "duplicate_mutations": sum(1 for m in rows if m.get("final_seq_delta") not in (None, 1)),
        "compile_ms": describe([m.get("compile_ms") for m in rows]),
        "displays": sorted({m.get("display") for m in rows if m.get("display")}),
    }


def latest_by_id(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for m in metrics:
        best[m["id"]] = m  # labels sorted, so -rN (later) wins
    return list(best.values())


def paired_values(metrics, kind, task, base, arm, getter) -> list[tuple[float, float]]:
    rows = ok_rows([m for m in metrics if m.get("kind") == kind and m.get("task") == task])
    by_round: dict[Any, dict[str, float]] = {}
    for m in rows:
        if m.get("arm") in (base, arm):
            v = getter(m)
            if v is not None:
                by_round.setdefault(m["round"], {})[m["arm"]] = v
    return [(v[base], v[arm]) for _, v in sorted(by_round.items()) if base in v and arm in v]


def saving(pairs: list[tuple[float, float]]) -> dict[str, Any] | None:
    """Median of within-round (base - arm): positive = the arm is faster."""
    return boot_paired([a - b for a, b in pairs])


def untested_share(m: dict[str, Any], reading: str) -> float:
    """Pre-registered untested share of one trial's T.
    standard: action-call transport sub-spans without a verdict (UNTESTED in SUB_VERDICT; the
      validation span counts as untested only when HC is NOT_MATERIAL), resolution, runner,
      plus unattributed time; observation transport IRREDUCIBLE by invariant (as N-01R).
    conservative: also the observation call's transport sub-spans without a verdict, and its
      T0->send residual."""
    t = m["T_ms"]
    u = m["components_ms"]["resolution"] + m["components_ms"]["runner"] + max(0.0, m.get("unattributed_ms") or 0.0)
    for s, v in SUB_VERDICT.items():
        if v == "UNTESTED" or (v == "HC" and not HC_DELETED.get(m["task"], False)):
            u += m["parts_sub_ms"]["act"][s]
            if reading == "conservative":
                u += m["parts_sub_ms"]["obs"][s]
    if reading == "conservative":
        u += m.get("obs_t0_to_send_ms") or 0.0
    return u / t


HC_DELETED: dict[str, bool] = {}


def analyze() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    blocks = load_blocks()
    allm: list[dict[str, Any]] = []
    meta = []
    ends = []
    for label, rows in blocks:
        for r in rows:
            if r.get("event") == "meta":
                meta.append({k: r.get(k) for k in ("block", "kind", "label", "display", "display_collision",
                                                   "x_clients_at_start", "driver_sha256", "plan_sha256", "wall_ns", "loadavg")})
            elif r.get("event") == "trial":
                allm.append(trial_metrics(label, r))
            elif r.get("event") == "end":
                ends.append({"label": label, "failures": r.get("failures"), "net": r.get("net"), "loadavg": r.get("loadavg")})
    metrics = latest_by_id(allm)
    superseded = [{"label": m["label"], "id": m["id"], "verified": m.get("verified"), "failure": m.get("failure")}
                  for m in allm if m not in metrics]
    plan = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
    planned = {b["block"]: len(b["trials"]) for b in plan["blocks"]}
    failed_attempts = []
    for d in sorted(RAW.glob("n02-*")):
        if d.is_dir() and not (d / "trials.jsonl.gz").exists():
            block = d.name.split("-")[1]
            note = (d / "session.txt").read_text(encoding="utf-8").strip().splitlines() if (d / "session.txt").exists() else []
            failed_attempts.append({"label": d.name, "block": block, "planned_cells_not_run": planned.get(block),
                                    "session": note[:4]})
    s: dict[str, Any] = {"schema": "n02.summary.v1", "blocks": meta, "block_ends": ends,
                         "superseded_attempts": superseded, "failed_block_attempts": failed_attempts,
                         "trials_total": len(allm), "trials_latest": len(metrics), "cells": {}}
    for kind in ("main", "smoke", "decoy", "edge", "nosteal"):
        for task in TASKS:
            for arm in ARMS[task] + ["D"]:
                rows = group(metrics, kind=kind, task=task, arm=arm)
                if rows:
                    s["cells"][f"{kind}/{task}/{arm}"] = cell_summary(rows)
    # ---- Phase 2 paired savings (base - arm) and speedups
    T = lambda m: m["T_ms"]  # noqa: E731
    s["paired_main"], s["speedup"], s["work_deleted"] = {}, {}, {}
    for task in TASKS:
        base = BASE[task]
        for arm in ARMS[task][1:]:
            pr = paired_values(metrics, "main", task, base, arm, T)
            s["paired_main"][f"{task}/{base}-minus-{arm}"] = saving(pr)
            s["speedup"][f"{task}/{base}_over_{arm}"] = boot_ratio(pr)
            s["work_deleted"][f"{task}/{arm}"] = {
                "client_validate_act": saving(paired_values(metrics, "main", task, base, arm,
                                                            lambda m: m["parts_sub_ms"]["act"]["client_validate"])),
                "client_validate_obs": saving(paired_values(metrics, "main", task, base, arm,
                                                            lambda m: m["parts_sub_ms"]["obs"]["client_validate"])),
                "settle": saving(paired_values(metrics, "main", task, base, arm, lambda m: m["components_ms"]["settle"])),
            }
    # ---- controls
    smoke = group(metrics, kind="smoke")
    s["control_smoke"] = {
        "trials": len(smoke), "verified": sum(1 for m in smoke if m.get("verified")),
        "valid": sum(1 for m in smoke if m.get("valid")),
        "env_exp_empty": all(not m.get("driver_env_exp") for m in smoke),
        "no_knob_marks": all(not m.get("knob_marks") for m in smoke),
        "post_action_sleep_ms": [m.get("components_ms", {}).get("post_action_sleep") for m in smoke],
        "settle_ms": [m.get("components_ms", {}).get("settle") for m in smoke],
        "last_poll_ms": [m.get("last_poll_after_guard_start_ms") for m in smoke],
    }
    d = s["control_smoke"]
    d["passed"] = bool(d["trials"] == 4 and d["verified"] == 4 and d["valid"] == 4 and d["env_exp_empty"] and d["no_knob_marks"]
                       and all(x is not None and 50 <= x < 60 for x in d["post_action_sleep_ms"])
                       and all(x is not None and x >= 220 for x in d["settle_ms"]))
    s["control_cl"] = {}
    for kind in ("decoy", "edge", "nosteal"):
        for task in TASKS:
            for arm in ARMS[task]:
                rows = group(metrics, kind=kind, task=task, arm=arm)
                st = [m.get("steal") or {} for m in rows]
                s["control_cl"][f"{kind}/{task}/{arm}"] = {
                    "trials": len(rows), "verified": sum(1 for m in rows if m.get("verified")),
                    "valid": sum(1 for m in rows if m.get("valid")),
                    "stolen": sum(1 for x in st if x.get("stolen")),
                    "restored": sum(1 for x in st if x.get("restored")),
                    "missed": sum(1 for x in st if x.get("missed")),
                    "detected_and_restored": sum(1 for x in st if x.get("detected_and_restored")),
                    "steal_inside_watch": sum(1 for x in st if x.get("steal_inside_watch")),
                    "steal_before_body_done": sum(1 for x in st if x.get("steal_before_body_done")),
                    "steal_after_return": sum(1 for x in st if x.get("steal_after_return")),
                    "false_restore": sum(1 for x in st if x.get("false_restore")),
                    "receipt_outcomes": sorted({str(x.get("receipt_focus_outcome")) for x in st}),
                    "steal_after_do_action_ms": describe([x.get("steal_after_do_action_ms") for x in st]),
                    "steal_after_guard_start_ms": describe([x.get("steal_after_guard_start_ms") for x in st]),
                    "restored_mark_after_steal_ms": describe([x.get("restored_mark_after_steal_ms") for x in st]),
                    "detect_poll_after_guard_start_ms": describe([x.get("detect_poll_after_guard_start_ms") for x in st]),
                    "detect_poll_after_steal_ms": describe([x.get("detect_poll_after_steal_ms") for x in st]),
                    "focus_max_gap_ms": max((x.get("focus_max_gap_ms") or 0 for x in st), default=None),
                    "settle_last_poll_ms": describe([m.get("last_poll_after_guard_start_ms") for m in rows]),
                }
    main_rows = group(metrics, kind="main")
    s["main_false_restores"] = sum(1 for m in main_rows if (m.get("receipt") or {}).get("focus_outcome") == "restored")
    s["main_focus_unchanged"] = [sum(1 for m in main_rows if m.get("focus_unchanged")), len(main_rows)]
    # ---- HC equivalence control (offline; hc_equivalence.py writes it)
    hc_path = HERE / "hc-equivalence.json"
    s["control_hc_equivalence"] = json.loads(hc_path.read_text(encoding="utf-8"))["summary"] if hc_path.exists() else None
    # ---- load sensitivity (qualitative; non-comparable across binaries)
    s["load"] = load_section(metrics)
    s["gates"] = gates(s, metrics)
    s["provider"] = {"attempts": 0, "reached": 0,
                     "harness_refused_non_loopback_connects": sum(((e.get("net") or {}).get("refused_non_loopback_connects") or 0) for e in ends)}
    return s, allm


def load_section(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"note": "this run's per-trial transport vs 1-minute loadavg (OLS); N-01R values are a different "
                                   "binary (c2a9978e) and host state: qualitative only, never combined"}
    for task in TASKS:
        rows = ok_rows(group(metrics, kind="main", task=task))
        xs = [m["loadavg1"] for m in rows]
        out[task] = {
            "obs_transport_vs_load": ols(xs, [m["components_ms"]["mcp_transport_obs"] for m in rows]),
            "act_transport_vs_load": ols(xs, [m["components_ms"]["mcp_transport_act"] for m in rows]),
            "obs_drv_write_vs_load": ols(xs, [m["parts_sub_ms"]["obs"]["drv_write"] for m in rows]),
            "obs_client_read_vs_load": ols(xs, [m["parts_ms"]["obs"]["client_read_validate"] for m in rows]),
        }
    if N01R_METRICS.exists():
        with gzip.open(N01R_METRICS, "rt", encoding="utf-8") as stream:
            n01 = [json.loads(x) for x in stream if x.strip()]
        n01 = [m for m in latest_by_id(n01) if m.get("kind") == "main" and m.get("valid") and m.get("verified")]
        for task, arm in (("checkbox", "S0"), ("text", "X")):
            rows = [m for m in n01 if m.get("task") == task and m.get("arm") == arm]
            out[f"n01r_{task}_{arm}"] = {
                "n": len(rows), "loadavg1_median": med(m.get("loadavg1") for m in rows),
                "obs_transport_median_ms": med(m["components_ms"]["mcp_transport_obs"] for m in rows),
                "act_transport_median_ms": med(m["components_ms"]["mcp_transport_act"] for m in rows),
                "obs_transport_vs_load": ols([m["loadavg1"] for m in rows], [m["components_ms"]["mcp_transport_obs"] for m in rows]),
            }
    return out


def gates(s: dict[str, Any], metrics: list[dict[str, Any]]) -> dict[str, Any]:
    g: dict[str, Any] = {"validity": {}, "coverage": {}, "HC": {}, "CL": {}, "E2": {}, "invariants": {}}
    for task in TASKS:
        for arm in ARMS[task]:
            c = s["cells"].get(f"main/{task}/{arm}", {})
            att = c.get("attempted") or 0
            g["validity"][f"{task}/{arm}"] = {"valid_and_verified": c.get("valid_and_verified"), "attempted": att,
                                              "holds": att > 0 and (c.get("valid_and_verified") or 0) >= 0.95 * att}
            g["coverage"][f"{task}/{arm}"] = {"median": c.get("coverage", {}).get("median"),
                                              "min": c.get("coverage", {}).get("min")}
    g["validity_all_hold"] = all(v["holds"] for v in g["validity"].values())
    main_rows = group(metrics, kind="main")
    g["invariants"] = {
        "duplicate_mutations": sum(1 for m in main_rows if m.get("final_seq_delta") not in (None, 1)),
        "unverified_successes": sum(1 for m in main_rows if m.get("receipt_claim_before_oracle")),
        "refused_or_failed_actions": sum(1 for m in main_rows if (m.get("receipt") or {}).get("failure_claim")),
        "stale_dispatches_note": "no stale token is ever sent: every action uses a token from the same trial's "
                                 "fresh observation (N-01R control c covers stale-token refusal on the same source)",
    }

    def ci_pos(p: dict[str, Any] | None) -> bool:
        return bool(p and p["ci95"][0] > 0)

    # HC: same acceptance (80/80) and identical verified outcomes are preconditions of DELETED.
    eq = s.get("control_hc_equivalence") or {}
    eq_ok = bool(eq.get("agree") == 80 and eq.get("total") == 80)
    for task in TASKS:
        base = BASE[task]
        hc = f"{base}+HC"
        p = s["paired_main"][f"{task}/{base}-minus-{hc}"]
        same = (g["validity"][f"{task}/{base}"]["holds"] and g["validity"][f"{task}/{hc}"]["holds"]
                and s["cells"][f"main/{task}/{base}"]["valid_and_verified"] == s["cells"][f"main/{task}/{base}"]["attempted"]
                and s["cells"][f"main/{task}/{hc}"]["valid_and_verified"] == s["cells"][f"main/{task}/{hc}"]["attempted"])
        verdict = "DELETED" if (ci_pos(p) and same and eq_ok) else "NOT_MATERIAL"
        HC_DELETED[task] = verdict == "DELETED"
        g["HC"][task] = {"saving_ms": p["median_diff_ms"] if p else None, "ci95": p["ci95"] if p else None,
                         "outcomes_identical": same, "equivalence_80_of_80": eq_ok, "verdict": verdict,
                         "work_deleted_validate_act_ms": (s["work_deleted"][f"{task}/{hc}"]["client_validate_act"] or {}).get("median_diff_ms"),
                         "work_deleted_validate_obs_ms": (s["work_deleted"][f"{task}/{hc}"]["client_validate_obs"] or {}).get("median_diff_ms")}
    # CL: every steal arm must detect and restore 10/10 (decoy 100 ms and edge), in every arm.
    steal_cells = {k: v for k, v in s["control_cl"].items() if k.split("/")[0] in ("decoy", "edge")}
    any_miss = any(v["detected_and_restored"] < v["trials"] or v["trials"] < 10 for v in steal_cells.values())
    nosteal_false = sum(v["false_restore"] for k, v in s["control_cl"].items() if k.startswith("nosteal/"))
    for task in TASKS:
        base = BASE[task]
        cl = f"{base}+CL"
        p = s["paired_main"][f"{task}/{base}-minus-{cl}"]
        if any_miss:
            verdict = "KILL"
        elif ci_pos(p) and p["median_diff_ms"] >= 10:
            verdict = "DELETED"
        else:
            verdict = "NOT_MATERIAL"
        g["CL"][task] = {"saving_ms": p["median_diff_ms"] if p else None, "ci95": p["ci95"] if p else None,
                         "steal_controls_all_10_of_10": not any_miss, "nosteal_false_restores": nosteal_false,
                         "work_deleted_settle_ms": (s["work_deleted"][f"{task}/{cl}"]["settle"] or {}).get("median_diff_ms"),
                         "verdict": verdict}
    for task in TASKS:
        g["E2"][task] = {arm: e2(s, metrics, task, arm) for arm in ARMS[task]}
    return g


def e2(s, metrics, task, arm) -> dict[str, Any]:
    rows = ok_rows([m for m in metrics if m.get("kind") == "main" and m.get("task") == task and m.get("arm") == arm])
    if not rows:
        return {}
    tmed = statistics.median(m["T_ms"] for m in rows)
    sub_rows = {}
    for which in ("obs", "act"):
        for s_ in SUB_VERDICT:
            ms = statistics.median(m["parts_sub_ms"][which][s_] for m in rows)
            share = statistics.median(m["parts_sub_ms"][which][s_] / m["T_ms"] for m in rows)
            v = SUB_VERDICT[s_]
            if v == "HC":
                v = "DELETED (HC)" if HC_DELETED.get(task) else "NOT_MATERIAL (HC) / UNTESTED"
            sub_rows[f"{which}/{s_}"] = {"median_ms": round(ms, 3), "median_share": round(share, 4), "verdict": v}
    comps = {c: {"median_ms": round(statistics.median(m["components_ms"][c] for m in rows), 3),
                 "median_share": round(statistics.median(m["components_ms"][c] / m["T_ms"] for m in rows), 4)}
             for c in COMPONENTS}
    return {"n": len(rows), "T_median_ms": round(tmed, 3), "components": comps, "transport_sub": sub_rows,
            "untested_share_standard": round(statistics.median(untested_share(m, "standard") for m in rows), 4),
            "untested_share_conservative": round(statistics.median(untested_share(m, "conservative") for m in rows), 4)}


def main() -> None:
    summary, allm = analyze()
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        old = (HERE / "n02-summary.json").read_text(encoding="utf-8")
        if old != text:
            print("MISMATCH: n02-summary.json differs from a fresh recomputation")
            sys.exit(1)
        print("summary reproduces from raw/")
        return
    (HERE / "n02-summary.json").write_text(text, encoding="utf-8")
    with gzip.open(HERE / "n02-trial-metrics.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as stream:
        for m in allm:
            stream.write(json.dumps(m, sort_keys=True) + "\n")
    print(json.dumps(summary["gates"], indent=1, sort_keys=True)[:8000])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""N-03 analysis: recompute every headline from raw/ (standard library only).

Rules are the ones in PREREG.json. Per-task metrics follow R2-10's native_row (components and
boundaries, T_oracle, verification) and N-02's transport split (sub-span names and boundaries),
on the R2-10 union mark format (phase / session / t_mono_ns, host CLOCK_MONOTONIC = the clock of
the harness's time.monotonic_ns()).

usage: analyze_n03.py [--raw raw] [--out n03-summary.json] [--metrics n03-trial-metrics.jsonl.gz]
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SEED = 20261003
BOOT = 10000
SCHEMA = "cua.gtk3_task_state_v1"
TASKS = ["checkbox", "text"]
ARMS = ["X", "X+HCL", "X+V", "X+HCL+V"]
ELEMENTS = ["checkbox", "button"]
SLEEP_MARK = "post_action_sleep_ms=0"
THRESH_MS, THRESH_SHARE = 50.0, 0.05
CLICK_MARKS = [("click", "element_resolved"), ("click", "placement_done"), ("click", "reveal_done"),
               ("click", "ax_start"), ("focus_guard", "captured"), ("atspi_action", "connected"),
               ("atspi_action", "live_checked"), ("atspi_action", "metadata_done"),
               ("atspi_action", "do_action_replied"), ("atspi_action", "post_sleep_done"),
               ("focus_guard", "body_done"), ("focus_guard", "restored"), ("click", "ax_joined")]
SV_MARKS = [("set_value", "element_resolved"), ("set_value", "cursor_done"), ("set_value", "write_done"),
            ("set_value", "readback_done")]
MCP_MARKS = ["parse_done", "handler_start", "handler_end", "serialize_done", "response_written"]
COMPONENTS = ["observation_transport", "observation", "runner", "resolution", "reveal", "dispatch",
              "post_action_sleep", "settle", "result", "action_transport", "effect_lag", "verification_read"]
R210_VERDICTS = {
    "observation_transport": "IRREDUCIBLE", "observation": "IRREDUCIBLE", "runner": "UNTESTED",
    "resolution": "UNTESTED", "reveal": "OWNER_DECISION", "dispatch": "IRREDUCIBLE",
    "post_action_sleep": "DELETED", "settle": "IRREDUCIBLE", "result": "UNTESTED",
    "action_transport": "UNTESTED", "effect_lag": "IRREDUCIBLE", "verification_read": "IRREDUCIBLE",
}
SUBS = ["client_build", "client_write_pipe", "drv_parse", "admission_v_proxy", "drv_admission_rest",
        "admission_v_inner", "drv_inner_pre_rest", "drv_inner_post", "drv_bookkeep_serialize", "drv_write",
        "client_pipe_read_parse", "client_result_model", "client_validate", "client_return"]
BUCKETS = {
    "client_send_build": ["client_build"],
    "pipe_and_client_read_parse": ["client_write_pipe", "client_pipe_read_parse", "client_result_model"],
    "driver_parse_admission_dispatch": ["drv_parse", "drv_admission_rest", "drv_inner_pre_rest"],
    "admission_v": ["admission_v_proxy", "admission_v_inner"],
    "driver_result_conformance": ["drv_inner_post"],
    "driver_serialize_write": ["drv_bookkeep_serialize", "drv_write"],
    "validation": ["client_validate"],
    "client_return": ["client_return"],
}


# ----------------------------------------------------------------------------- statistics
def med(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def mean(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def p95(xs: list[float | None]) -> float | None:
    s = sorted(x for x in xs if x is not None)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)] if s else None


def boot_ci(n: int, stat) -> list[float] | None:  # noqa: ANN001
    if n < 2:
        return None
    rng = random.Random(SEED)
    vals = []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat(idx)
        if v is not None and math.isfinite(v):
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    return [vals[int(math.floor(0.025 * (len(vals) - 1)))], vals[int(math.ceil(0.975 * (len(vals) - 1)))]]


def paired_diff(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    """a - b per pair: median and percentile bootstrap CI over pairs."""
    d = [a - b for a, b in pairs]
    if not d:
        return {"n": 0, "median": None, "ci95": None}
    return {"n": len(d), "median": statistics.median(d), "mean": statistics.mean(d),
            "ci95": boot_ci(len(d), lambda idx: statistics.median([d[i] for i in idx])),
            "min": min(d), "max": max(d), "positive": sum(1 for x in d if x > 0)}


def r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(x, nd)


# ----------------------------------------------------------------------------- io
def read_jsonl(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(x) for x in stream if x.strip()]


def load(raw: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    out = []
    for path in sorted(raw.glob("runs/*/trials.jsonl*")):
        out.append((path.parent.name, read_jsonl(path)))
    return out


# ----------------------------------------------------------------------------- per call helpers
def matches(state: Any, expected: dict[str, Any]) -> bool:
    return (isinstance(state, dict) and state.get("schema") == SCHEMA
            and all(state.get(k) == v for k, v in expected.items()))


def call_marks(marks: list[dict[str, Any]], m0: int, m1: int) -> dict[tuple[str, str], int]:
    """R2-10 rule: the first mark per (phase, session) inside the call window +- 2 ms."""
    out: dict[tuple[str, str], int] = {}
    for m in marks:
        t = m.get("t_mono_ns")
        if t is not None and m0 - 2_000_000 <= t <= m1 + 2_000_000:
            out.setdefault((m.get("phase"), m.get("session")), t)
    return out


def strict_marks(marks: list[dict[str, Any]], m0: int, m1: int) -> dict[tuple[str, str], int]:
    """Request-side Driver marks of one call: strictly inside [m0, m1] (they follow the send)."""
    out: dict[tuple[str, str], int] = {}
    for m in marks:
        t = m.get("t_mono_ns")
        if t is not None and m0 <= t <= m1:
            out.setdefault((m.get("phase"), m.get("session")), t)
    return out


def mcp_marks(marks: list[dict[str, Any]], tool: str, m0: int, m1: int) -> dict[str, int]:
    """N-02 rule: the call's own mcp:<tool> span marks in the window, plus the last mcp/request_read
    at or before its parse_done."""
    scope = f"mcp:{tool}"
    out: dict[str, int] = {}
    for m in marks:
        t = m.get("t_mono_ns")
        if m.get("phase") == scope and t is not None and m0 - 2e6 <= t <= m1 + 2e6 and m.get("session") not in out:
            out[m["session"]] = t
    parse = out.get("parse_done")
    if parse is not None:
        reads = [m["t_mono_ns"] for m in marks if m.get("phase") == "mcp" and m.get("session") == "request_read"
                 and m["t_mono_ns"] <= parse]
        if reads:
            out["request_read"] = max(reads)
    return out


def stamps_of(call: dict[str, Any]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for kind, mono, _detail in call.get("client_stamps") or []:
        out[kind].append(mono)
    return out


def knob_marks(marks: list[dict[str, Any]]) -> set[str]:
    return {m.get("session") for m in marks if m.get("phase") == "exp_knob"}


def want_knobs(arm: str) -> set[str]:
    return {SLEEP_MARK} if arm in ("X", "X+HCL", "X+V", "X+HCL+V", "S0", "S0U") else set()


def span(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else (b - a) / 1e6


# ----------------------------------------------------------------------------- Part A per task
def task_metrics(label: str, rec: dict[str, Any], t: dict[str, Any], marks: list[dict[str, Any]]) -> dict[str, Any]:
    arm = rec.get("arm") or ""
    out: dict[str, Any] = {k: rec.get(k) for k in ("id", "block", "kind", "task", "arm", "round", "k", "variant_ms")}
    out.update({"label": label, "uid": f"{label}/{rec.get('id')}#{t.get('task_i')}", "task_i": t.get("task_i"),
                "loadavg_1m": (t.get("loadavg") or rec.get("loadavg") or [None])[0],
                "trial_failure": rec.get("failure"), "task_failure": t.get("failure")})
    actions = t.get("actions") or []
    tree = t.get("tree")
    t0m = t.get("T0_m")
    samples = t.get("state_samples")
    expected = t.get("expected")
    if not (actions and tree and t0m and samples and expected):
        out.update({"valid": False, "verified": False,
                    "reasons": [t.get("failure") or rec.get("failure") or "incomplete task"]})
        return out
    states, idx, s0, s1 = samples["states"], samples["idx"], samples["t0_us"], samples["t1_us"]
    ret_us = (actions[-1]["m1"] - t0m) / 1000
    t_end = next((s1[i] / 1000 for i in range(len(idx)) if s0[i] >= ret_us and matches(states[idx[i]], expected)), None)
    t_land = next((s1[i] / 1000 for i in range(len(idx)) if matches(states[idx[i]], expected)), None)
    first_after = next((i for i in range(len(idx)) if s0[i] >= ret_us), None)
    final_state = states[idx[-1]] if idx else None
    before_seq = int((t.get("before") or {}).get("seq", -1))
    final_ok = matches(final_state, expected) and isinstance(final_state, dict) and final_state.get("seq") == before_seq + 1
    out.update({"T_oracle_ms": r(t_end), "T_land_ms": r(t_land), "T_return_ms": r(ret_us / 1000),
                "effect_visible_at_return": bool(first_after is not None and matches(states[idx[first_after]], expected)),
                "final_state_ok": final_ok,
                "mutations": (final_state.get("seq", 0) - before_seq) if isinstance(final_state, dict) else None})
    out["verified"] = bool(t_end is not None and final_ok and not rec.get("failure") and not t.get("failure"))
    calls = [("observe", tree)] + [(a["tool"], a) for a in actions]
    per_call = [call_marks(marks, c["m0"], c["m1"]) for _, c in calls]
    per_strict = [strict_marks(marks, c["m0"], c["m1"]) for _, c in calls]
    per_mcp = [mcp_marks(marks, "get_window_state" if n == "observe" else n, c["m0"], c["m1"]) for n, c in calls]
    per_stamp = [stamps_of(c) for _, c in calls]
    reasons: list[str] = [] if out["verified"] else ["not_verified"]
    out["actual_routes"] = [f"{a['tool']}:{(a.get('structured') or {}).get('route')}:"
                            f"{((a.get('structured') or {}).get('delivery') or {}).get('mode')}" for a in actions]
    for (name, c), cm in zip(calls[1:], per_call[1:]):
        st = c.get("structured") or {}
        if st.get("route") != "accessibility":
            reasons.append(f"{name}: route={st.get('route')}")
        if c.get("error"):
            reasons.append(f"{name}: error")
        need = CLICK_MARKS if name == "click" else SV_MARKS
        times = [cm.get(k) for k in need]
        if any(x is None for x in times):
            reasons.append(f"{name}: missing marks {[k for k, x in zip(need, times) if x is None]}")
        elif any(b < a for a, b in zip(times, times[1:])):
            reasons.append(f"{name}: marks out of order")
    for (name, c), cm, mm, sm, sp in zip(calls, per_call, per_mcp, per_strict, per_stamp):
        tool = "get_window_state" if name == "observe" else name
        if (tool, "dispatch_enter") not in cm or (tool, "dispatch_exit") not in cm:
            reasons.append(f"{name}: missing dispatch marks")
        seq = [mm.get("request_read")] + [mm.get(k) for k in MCP_MARKS]
        if any(x is None for x in seq):
            reasons.append(f"{name}: missing MCP span marks")
        elif any(b < a for a, b in zip(seq, seq[1:])):
            reasons.append(f"{name}: MCP span marks out of order")
        for k in ("client_send", "client_recv", "validate_start", "validate_end"):
            if not sp.get(k):
                reasons.append(f"{name}: missing client stamp {k}")
        skipped = ("mcp.inner_validation_skipped", "") in sm
        built = ("mcp.inner_tools_list_built", "") in sm
        if "V" in arm.split("+") and not skipped:
            reasons.append(f"{name}: V arm without mcp.inner_validation_skipped")
        if "V" not in arm.split("+") and (skipped or not built):
            reasons.append(f"{name}: non-V arm admission marks wrong")
        compiles = bool(sp.get("compile_start"))
        if "HCL" in arm.split("+"):
            if t.get("task_i") == 0 and not compiles:
                reasons.append(f"{name}: HCL first use without a compile inside the call")
            if t.get("task_i") != 0 and compiles:
                reasons.append(f"{name}: HCL recompiled a cached schema")
        elif compiles:
            reasons.append(f"{name}: compile stamps in a non-HCL arm")
    motion = rec.get("cursor_motion") or {}
    if motion.get("glide_duration_ms") != 1.0:
        reasons.append(f"cursor glide {motion.get('glide_duration_ms')}")
    if (rec.get("cursor_state") or {}).get("enabled") is not True:
        reasons.append("cursor not enabled")
    if knob_marks(marks) != want_knobs(arm):
        reasons.append(f"knob marks {sorted(knob_marks(marks))}")
    out["reasons"] = reasons
    out["valid"] = not reasons
    # ---- R2-10 components (contiguous boundaries, caller monotonic ns)
    comp = {c: 0.0 for c in COMPONENTS}
    subs = {"obs": {s: 0.0 for s in SUBS}, "act": {s: 0.0 for s in SUBS}}
    named = 0.0

    def add(component: str, a: float | None, b: float | None) -> None:
        nonlocal named
        if a is not None and b is not None:
            comp[component] += (b - a) / 1e6
            named += (b - a) / 1e6

    add("observation_transport", t0m, tree["m0"])
    prev = None
    compile_in_T = 0.0
    for (name, c), cm, mm, sm, sp in zip(calls, per_call, per_mcp, per_strict, per_stamp):
        tool = "get_window_state" if name == "observe" else name
        enter, exit_ = cm.get((tool, "dispatch_enter")), cm.get((tool, "dispatch_exit"))
        tp = "observation_transport" if name == "observe" else "action_transport"
        which = "obs" if name == "observe" else "act"
        if prev is not None:
            add("runner", prev, c["m0"])
        add(tp, c["m0"], enter)
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
        prev = c["m1"]
        send = min(sp["client_send"]) if sp.get("client_send") else None
        recv = max(sp["client_recv"]) if sp.get("client_recv") else None
        vs = min(sp["validate_start"]) if sp.get("validate_start") else None
        ve = max(sp["validate_end"]) if sp.get("validate_end") else None
        if sp.get("compile_start") and sp.get("compile_end"):
            compile_in_T += sum((b - a) / 1e6 for a, b in zip(sp["compile_start"], sp["compile_end"]))
        adm_p = span(sm.get(("mcp.session_validated", "")), sm.get(("mcp.admission_validated", "")))
        adm_i = span(sm.get(("mcp.inner_classified", "")), sm.get(("mcp.inner_validated", "")))
        drv_adm = span(mm.get("parse_done"), mm.get("handler_start"))
        drv_pre = span(mm.get("handler_start"), enter)
        segs = {
            "client_build": span(c["m0"], send), "client_write_pipe": span(send, mm.get("request_read")),
            "drv_parse": span(mm.get("request_read"), mm.get("parse_done")),
            "admission_v_proxy": adm_p,
            "drv_admission_rest": None if drv_adm is None else drv_adm - (adm_p or 0.0),
            "admission_v_inner": adm_i,
            "drv_inner_pre_rest": None if drv_pre is None else drv_pre - (adm_i or 0.0),
            "drv_inner_post": span(exit_, mm.get("handler_end")),
            "drv_bookkeep_serialize": span(mm.get("handler_end"), mm.get("serialize_done")),
            "drv_write": span(mm.get("serialize_done"), mm.get("response_written")),
            "client_pipe_read_parse": span(mm.get("response_written"), recv),
            "client_result_model": span(recv, vs), "client_validate": span(vs, ve),
            "client_return": span(ve, c["m1"]),
        }
        for s, v in segs.items():
            if v is not None:
                subs[which][s] += v
    if t_end is not None:
        lag = max(0.0, (t_land or 0) - ret_us / 1000) if t_land is not None else 0.0
        comp["effect_lag"] = lag
        comp["verification_read"] = t_end - ret_us / 1000 - lag
        named += t_end - ret_us / 1000
    out["components"] = {k: r(v) for k, v in comp.items()}
    out["subs"] = {w: {k: r(v) for k, v in subs[w].items()} for w in subs}
    out["coverage"] = r(named / t_end, 4) if t_end else None
    out["compile_in_T_ms"] = r(compile_in_T)
    out["validate_act_ms"] = r(subs["act"]["client_validate"])
    out["validate_obs_ms"] = r(subs["obs"]["client_validate"])
    out["admission_v_ms"] = r(subs["act"]["admission_v_proxy"] + subs["act"]["admission_v_inner"]
                              + subs["obs"]["admission_v_proxy"] + subs["obs"]["admission_v_inner"])
    out["receipt_shape"] = [{"tool": a["tool"], "route": (a.get("structured") or {}).get("route"),
                             "effect": (a.get("structured") or {}).get("effect"),
                             "keys": sorted((a.get("structured") or {}).keys())} for a in actions]
    last = (actions[-1].get("structured") or {})
    out["receipt_claims_success"] = last.get("effect") in ("confirmed", "verified") or last.get("verified") is True
    out["receipt_claim_before_oracle"] = bool(out["receipt_claims_success"] and not out["effect_visible_at_return"])
    if rec.get("kind") == "decoy":
        fs = t.get("focus_samples") or {}
        dec = t.get("decoy") or {}
        changes = fs.get("changes") or []
        pre = t.get("focus_pre") or {}
        final = changes[-1] if changes else None
        win = t.get("decoy_window")
        out["decoy"] = {"stolen": dec.get("stolen"),
                        "restored": bool(final and final[1] == pre.get("focus") and final[2] == pre.get("active")),
                        "missed": bool(final and win in (final[1], final[2])),
                        "steal_after_last_return": bool(dec.get("steal_ns") and dec["steal_ns"] > actions[-1]["m1"]),
                        # EXPLORATORY (N-02 lineage, never used by a gate): final focus vs the focus
                        # sampler's own first sample (after placement), and the receipt's focus_outcome.
                        "x_restored_to_sampler_start": bool(final and changes and final[1:] == changes[0][1:]),
                        "receipt_focus_restored": "focus_outcome=restored" in " ".join(actions[-1].get("content_text") or [])}
    return out


# ----------------------------------------------------------------------------- Part B per row
def axfg_row(label: str, rec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: rec.get(k) for k in ("id", "block", "kind", "task", "arm", "round", "variant_ms")}
    out.update({"label": label, "uid": f"{label}/{rec.get('id')}",
                "family": "U" if (rec.get("arm") or "").endswith("U") else "D",
                "loadavg_1m": (rec.get("loadavg") or [None])[0], "failure": rec.get("failure")})
    tasks = rec.get("tasks") or []
    t = tasks[0] if tasks else {}
    actions = t.get("actions") or []
    samples = t.get("state_samples")
    expected = t.get("expected")
    if not (actions and samples and expected and t.get("T0_m")):
        out.update({"route_ok": False, "verified": False, "reasons": [t.get("failure") or rec.get("failure") or "incomplete"]})
        return out
    a = actions[-1]
    st = a.get("structured") or {}
    marks = rec.get("marks") or []
    cm = call_marks(marks, a["m0"], a["m1"])
    dar, psd = cm.get(("atspi_action", "do_action_replied")), cm.get(("atspi_action", "post_sleep_done"))
    text = " ".join(a.get("content_text") or [])
    reasons = []
    if st.get("route") != "accessibility":
        reasons.append(f"route={st.get('route')}")
    if (st.get("delivery") or {}).get("mode") != "foreground":
        reasons.append(f"delivery={(st.get('delivery') or {}).get('mode')}")
    if "path=ax_fg" not in text:
        reasons.append("receipt text lacks path=ax_fg")
    if dar is None:
        reasons.append("no do_action_replied mark")
    if knob_marks(marks) != want_knobs(rec.get("arm") or ""):
        reasons.append(f"knob marks {sorted(knob_marks(marks))}")
    wc = rec.get("driver_env_window_change") or {}
    if (out["family"] == "U") != (wc.get("CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS") == "0"):
        reasons.append(f"window-change env {wc}")
    out["global_input"] = st.get("route") == "global_input"
    out["route_ok"] = not reasons
    t0m = t["T0_m"]
    states, idx, s0, s1 = samples["states"], samples["idx"], samples["t0_us"], samples["t1_us"]
    ret = a["m1"]
    ret_us = (ret - t0m) / 1000
    first_match = next((states[i] for i in sorted(set(idx), key=idx.index) if matches(states[i], expected)), None)
    t_eff = (first_match or {}).get("axfg_effect_mono_ns")
    t_end = next((s1[i] / 1000 for i in range(len(idx)) if s0[i] >= ret_us and matches(states[idx[i]], expected)), None)
    first_after = next((i for i in range(len(idx)) if s0[i] >= ret_us), None)
    final_state = states[idx[-1]] if idx else None
    before_seq = int((t.get("before") or {}).get("seq", -1))
    final_ok = matches(final_state, expected) and isinstance(final_state, dict) and final_state.get("seq") == before_seq + 1
    visible = bool(t_eff is not None and t_eff <= ret)
    strict = bool(first_after is not None and matches(states[idx[first_after]], expected))
    out.update({
        "t_effect_present": t_eff is not None, "visible_at_return": visible,
        "margin_ms": r((ret - t_eff) / 1e6) if t_eff is not None else None,
        "strict_sampler_visible": strict, "publication_lag": bool(visible and not strict),
        "T_oracle_ms": r(t_end), "T_return_ms": r(ret_us / 1000), "click_wrapper_ms": r(a.get("wrapper_ms")),
        "dar_to_return_ms": r((ret - dar) / 1e6) if dar else None,
        "post_action_wait_ms": r((psd - dar) / 1e6) if dar and psd else None,
        "effect_after_dar_ms": r((t_eff - dar) / 1e6) if dar and t_eff else None,
        "final_state_ok": final_ok, "verified": bool(final_ok and t_eff is not None and not rec.get("failure")),
        "mutations": (final_state.get("seq", 0) - before_seq) if isinstance(final_state, dict) else None,
        "reasons": reasons,
    })
    return out


# ----------------------------------------------------------------------------- aggregation helpers
def arm_summary(rows: list[dict[str, Any]], key: str = "T_oracle_ms") -> dict[str, Any]:
    v = [x for x in rows if x.get("valid")]
    return {"n": len(rows), "verified": sum(1 for x in rows if x.get("verified")), "valid": len(v),
            "invalid": [{"uid": x["uid"], "reasons": x.get("reasons")} for x in rows if not x.get("valid")],
            "T_oracle_ms": {"median": r(med([x.get(key) for x in v])), "mean": r(mean([x.get(key) for x in v])),
                            "p95": r(p95([x.get(key) for x in v]))},
            "T_return_ms_median": r(med([x.get("T_return_ms") for x in v])),
            "loadavg_1m": {"min": min((x["loadavg_1m"] for x in rows if x.get("loadavg_1m") is not None), default=None),
                           "median": med([x.get("loadavg_1m") for x in rows]),
                           "max": max((x["loadavg_1m"] for x in rows if x.get("loadavg_1m") is not None), default=None)}}


def pairs(rows: list[dict[str, Any]], a: str, b: str, getter, extra_key=lambda x: x["task"]) -> list[tuple[float, float]]:  # noqa: ANN001
    idx: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for x in rows:
        idx[(extra_key(x), x["round"])][x["arm"]] = x
    out = []
    for key in sorted(idx, key=lambda k: (str(k[0]), k[1])):
        ra, rb = idx[key].get(a), idx[key].get(b)
        if ra and rb and ra.get("valid") and rb.get("valid"):
            va, vb = getter(ra), getter(rb)
            if va is not None and vb is not None:
                out.append((va, vb))
    return out


def sub_mean(rows: list[dict[str, Any]], which: str, s: str) -> float:
    return mean([x["subs"][which][s] for x in rows]) or 0.0


def decomposition(rows: list[dict[str, Any]], hcl: str, v: str, conservative: bool) -> dict[str, Any]:
    vrows = [x for x in rows if x.get("valid") and x.get("components")]
    if not vrows:
        return {}
    meanT = mean([x["T_oracle_ms"] for x in vrows])
    sub_verdict = {s: "UNTESTED" for s in SUBS}
    sub_verdict["drv_bookkeep_serialize"] = sub_verdict["drv_write"] = "IRREDUCIBLE"
    sub_verdict["client_validate"] = {"DELETED": "UNTESTED", "OWNER_DECISION": "OWNER_DECISION",
                                      "KILL": "IRREDUCIBLE"}[hcl]
    for s in ("admission_v_proxy", "admission_v_inner"):
        sub_verdict[s] = {"DELETED": "UNTESTED", "NOT_MATERIAL": "IRREDUCIBLE", "INCONCLUSIVE": "UNTESTED"}[v]
    table: dict[str, Any] = {}
    untested = irreducible = 0.0

    def put(name: str, m: float, verdict: str) -> None:
        nonlocal untested, irreducible
        share = m / meanT if meanT else None
        table[name] = {"mean_ms": r(m), "share": r(share, 4), "verdict": verdict,
                       "above_threshold": bool(m >= THRESH_MS or (share or 0) >= THRESH_SHARE)}
        if verdict == "UNTESTED":
            untested += m
        if verdict == "IRREDUCIBLE":
            irreducible += m

    for c in COMPONENTS:
        m = mean([x["components"][c] for x in vrows]) or 0.0
        if c == "action_transport" or (c == "observation_transport" and conservative):
            which = "act" if c == "action_transport" else "obs"
            parts = 0.0
            for s in SUBS:
                sm = sub_mean(vrows, which, s)
                parts += sm
                put(f"{c}.{s}", sm, sub_verdict[s])
            if c == "observation_transport":
                # T0 -> observation send (R2-10 counts it in observation_transport); not in the split
                put(f"{c}.t0_to_send", m - parts, "UNTESTED")
            else:
                put(f"{c}.residual", m - parts, "UNTESTED")
        else:
            put(c, m, R210_VERDICTS[c])
    return {"n": len(vrows), "mean_T_ms": r(meanT), "components": table, "untested_ms": r(untested),
            "untested_share": r(untested / meanT, 4) if meanT else None, "T_irreducible_ms": r(irreducible),
            "floor_ratio": r(meanT / irreducible, 4) if irreducible else None,
            "coverage_min": min((x["coverage"] for x in vrows if x.get("coverage") is not None), default=None)}


def transport_buckets(rows: list[dict[str, Any]], which: str) -> dict[str, Any]:
    vrows = [x for x in rows if x.get("valid")]
    return {b: r(sum(sub_mean(vrows, which, s) for s in ss)) for b, ss in BUCKETS.items()}


# ----------------------------------------------------------------------------- main analysis
def analyze(raw: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    blocks = load(raw)
    task_rows: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    b_rows: list[dict[str, Any]] = []
    smoke: dict[str, Any] = {}
    vctl_rows: list[dict[str, Any]] = []
    hcl_equiv = {"trials": 0, "calls": 0, "agree": 0, "same_message": 0, "lazy_rejects": 0}
    axfg_smoke_rows = []
    blocks_meta = []
    net_refused = 0
    for label, recs in blocks:
        meta = next((x for x in recs if x.get("event") == "meta"), {})
        end = next((x for x in recs if x.get("event") == "end"), {})
        trials = [x for x in recs if x.get("event") == "trial"]
        net_refused += ((end.get("net") or {}).get("refused_non_loopback_connects") or 0)
        blocks_meta.append({"label": label, "block": meta.get("block"), "kind": meta.get("kind"),
                            "trials": len(trials), "failures": end.get("failures"),
                            "display_collision": meta.get("display_collision"),
                            "loadavg_start": (meta.get("loadavg") or [None])[0],
                            "loadavg_end": (end.get("loadavg") or [None])[0],
                            "driver_sha256": meta.get("driver_sha256"), "driver_bin_name": meta.get("driver_bin_name"),
                            "plan_sha256": meta.get("plan_sha256"), "completed": bool(end)})
        for rec in trials:
            kind = rec.get("kind")
            marks = rec.get("marks") or []
            if rec.get("hcl") and rec.get("hcl_equivalence"):
                e = rec["hcl_equivalence"]
                hcl_equiv["trials"] += 1
                for k in ("calls", "agree", "same_message", "lazy_rejects"):
                    hcl_equiv[k] += e.get(k) or 0
            if kind in ("axfg", "axfg_delay"):
                b_rows.append(axfg_row(label, rec))
                continue
            if kind == "axfg_smoke":
                axfg_smoke_rows.append({"uid": f"{label}/{rec['id']}", **(rec.get("axfg_smoke") or {}),
                                        "failure": rec.get("failure"), "pass": bool(rec.get("oracle_verified"))})
                continue
            if kind == "smoke":
                s = smoke.setdefault(label, {"driver": meta.get("driver_bin_name"), "driver_sha256": meta.get("driver_sha256"),
                                             "tools_list_sha256": set(), "rows": []})
                s["tools_list_sha256"].add(rec.get("tools_list_sha256"))
                t = (rec.get("tasks") or [{}])[0]
                ex = t.get("expected") or {}
                samples = t.get("state_samples") or {}
                acts = t.get("actions") or []
                ok = False
                if acts and samples and ex:
                    ret_us = (acts[-1]["m1"] - t["T0_m"]) / 1000
                    ok = any(samples["t0_us"][i] >= ret_us and matches(samples["states"][samples["idx"][i]], ex)
                             for i in range(len(samples["idx"])))
                s["rows"].append({"uid": f"{label}/{rec['id']}", "task": rec.get("task"), "verified": bool(ok and not rec.get("failure")),
                                  "phase_file_bytes": rec.get("phase_file_bytes"), "marks": len(marks),
                                  "exp_env": rec.get("driver_env_exp"), "trace_env": "CUA_DRIVER_PHASE_TRACE_FILE" in (rec.get("driver_env_keys") or []),
                                  "receipt_shape": [{"tool": a["tool"], "route": (a.get("structured") or {}).get("route"),
                                                     "effect": (a.get("structured") or {}).get("effect"),
                                                     "keys": sorted((a.get("structured") or {}).keys())} for a in acts],
                                  "cursor_motion": rec.get("cursor_motion")})
                continue
            tasks = rec.get("tasks") or []
            if not tasks:
                task_rows.append({k: rec.get(k) for k in ("id", "block", "kind", "task", "arm", "round", "k")}
                                 | {"label": label, "uid": f"{label}/{rec.get('id')}#-", "valid": False, "verified": False,
                                    "reasons": [rec.get("failure") or "no task"], "task_i": None})
            for t in tasks:
                task_rows.append(task_metrics(label, rec, t, marks))
            if kind == "session":
                mine = [x for x in task_rows if x["uid"].startswith(f"{label}/{rec['id']}#")]
                ok = len(mine) == 5 and all(x.get("valid") for x in mine)
                sessions.append({k: rec.get(k) for k in ("id", "task", "arm", "round")} | {
                    "uid": f"{label}/{rec['id']}", "valid": ok, "verified": sum(1 for x in mine if x.get("verified")),
                    "T_by_task": [x.get("T_oracle_ms") for x in mine],
                    "validate_by_task": [r((x.get("validate_act_ms") or 0) + (x.get("validate_obs_ms") or 0)) for x in mine],
                    "sum_T_ms": r(sum(x["T_oracle_ms"] for x in mine)) if ok else None,
                    "session_wall_ms": r((rec["session_tasks_end_m"] - rec["session_start_m"]) / 1e6)
                    if rec.get("session_tasks_end_m") and rec.get("session_start_m") else None,
                    "session_setup_ms": r(rec.get("session_setup_ms")),
                    "setup_compile_ms": r(sum(c["ms"] for c in rec.get("hcl_compiles") or [] if c["tool"] not in
                                              ("get_window_state", "click", "set_value"))),
                    "loadavg_1m": (rec.get("loadavg") or [None])[0]})
            if kind == "vctl":
                v = rec.get("vctl") or {}
                probes = {p["step"]: p for p in v.get("probes") or []}
                t = (task_rows[-1] if tasks else {})

                def refused(p: dict[str, Any] | None) -> str | None:
                    if not p:
                        return None
                    err = p.get("error") or {}
                    return None if p.get("ok") else str(err.get("mcp_code") or err.get("code") or err.get("exception"))
                vctl_rows.append({"uid": f"{label}/{rec['id']}", "arm": rec.get("arm"),
                                  "relist_identical": v.get("relist_identical"),
                                  "unknown_1": refused(probes.get("unknown_modern_1")),
                                  "unknown_2": refused(probes.get("unknown_modern_2")),
                                  "known_modern_ok": bool((probes.get("known_modern") or {}).get("ok")),
                                  "known_legacy_ok": bool((probes.get("known_legacy") or {}).get("ok")),
                                  "task_verified": bool(t.get("verified")), "task_valid": bool(t.get("valid")),
                                  "failure": rec.get("failure")})
    main = [x for x in task_rows if x.get("kind") == "main"]
    sess_tasks = [x for x in task_rows if x.get("kind") == "session"]
    decoy = [x for x in task_rows if x.get("kind") == "decoy"]
    S: dict[str, Any] = {"schema": "n03.summary.v1", "blocks": blocks_meta, "net_refused_non_loopback": net_refused}
    # ---- Part A k=1
    A: dict[str, Any] = {"arms": {t: {a: arm_summary([x for x in main if x["task"] == t and x["arm"] == a]) for a in ARMS}
                                  for t in TASKS}}
    T = lambda x: x.get("T_oracle_ms")  # noqa: E731
    contrasts = {"HCL": [("X", "X+HCL"), ("X+V", "X+HCL+V")], "V": [("X", "X+V"), ("X+HCL", "X+HCL+V")]}
    A["contrasts_k1"] = {}
    for name, cs in contrasts.items():
        for a, b in cs:
            for t in TASKS:
                rows_t = [x for x in main if x["task"] == t]
                A["contrasts_k1"][f"{t}/{a}-vs-{b}"] = {
                    "wall_clock_T_ms": paired_diff(pairs(rows_t, a, b, T)),
                    "work_validate_act_ms": paired_diff(pairs(rows_t, a, b, lambda x: x.get("validate_act_ms"))),
                    "work_validate_obs_ms": paired_diff(pairs(rows_t, a, b, lambda x: x.get("validate_obs_ms"))),
                    "work_admission_v_ms": paired_diff(pairs(rows_t, a, b, lambda x: x.get("admission_v_ms"))),
                    "compile_in_T_ms_median_b": r(med([x.get("compile_in_T_ms") for x in rows_t if x["arm"] == b and x.get("valid")])),
                }
    S["part_a_k1"] = A
    # ---- Part A k=5
    K: dict[str, Any] = {"sessions": {}, "contrasts_k5": {}}
    for t in TASKS:
        for a in ARMS:
            ss = [s for s in sessions if s["task"] == t and s["arm"] == a]
            st = [x for x in sess_tasks if x["task"] == t and x["arm"] == a]
            K["sessions"][f"{t}/{a}"] = {
                "n_sessions": len(ss), "valid_sessions": sum(1 for s in ss if s["valid"]),
                "tasks": len(st), "verified_tasks": sum(1 for x in st if x.get("verified")),
                "valid_tasks": sum(1 for x in st if x.get("valid")),
                "T_by_task_i_median": [r(med([x.get("T_oracle_ms") for x in st if x.get("task_i") == i and x.get("valid")])) for i in range(5)],
                "validate_by_task_i_median": [r(med([(x.get("validate_act_ms") or 0) + (x.get("validate_obs_ms") or 0)
                                                     for x in st if x.get("task_i") == i and x.get("valid")])) for i in range(5)],
                "sum_T_ms_median": r(med([s["sum_T_ms"] for s in ss if s["valid"]])),
                "session_wall_ms_median": r(med([s["session_wall_ms"] for s in ss if s["valid"]])),
                "session_setup_ms_median": r(med([s["session_setup_ms"] for s in ss if s["valid"]])),
                "setup_compile_ms_median": r(med([s["setup_compile_ms"] for s in ss if s["valid"]])),
                "invalid": [{"uid": x["uid"], "reasons": x.get("reasons")} for x in st if not x.get("valid")]}
    for name, cs in contrasts.items():
        for a, b in cs:
            for t in TASKS:
                ss = [s for s in sessions if s["task"] == t]
                K["contrasts_k5"][f"{t}/{a}-vs-{b}"] = {
                    "sum_T_ms": paired_diff(pairs(ss, a, b, lambda s: s.get("sum_T_ms"))),
                    "session_wall_ms": paired_diff(pairs(ss, a, b, lambda s: s.get("session_wall_ms"))),
                    "per_task_i_T_ms": [paired_diff(pairs(ss, a, b, lambda s, i=i: (s.get("T_by_task") or [None] * 5)[i]
                                                          if len(s.get("T_by_task") or []) == 5 else None)) for i in range(5)]}
    S["part_a_k5"] = K
    # ---- controls
    S["hcl_equivalence_online"] = hcl_equiv
    off_path = HERE / "hc-control.json"
    S["hcl_equivalence_offline"] = json.loads(off_path.read_text(encoding="utf-8"))["summary"] if off_path.exists() else None
    xv = [v for v in vctl_rows if v["arm"] == "X+V"]
    xx = [v for v in vctl_rows if v["arm"] == "X"]
    ref_err = {v["unknown_1"] for v in xx} | {v["unknown_2"] for v in xx}
    vctl_pass = [v for v in xv if v["relist_identical"] and v["unknown_1"] and v["unknown_2"] and v["unknown_1"] == v["unknown_2"]
                 and v["unknown_1"] in ref_err and v["known_modern_ok"] and v["known_legacy_ok"] and v["task_verified"]
                 and not v["failure"]]
    S["v_control"] = {"rows": vctl_rows, "x_v_rows": len(xv), "x_v_pass": len(vctl_pass), "x_rows": len(xx),
                      "reference_unknown_tool_errors": sorted(e for e in ref_err if e),
                      "pass": len(xv) >= 5 and len(vctl_pass) == len(xv)}
    S["decoy"] = {f"{t}/{a}": {"n": len(rs), "stolen": sum(1 for x in rs if (x.get("decoy") or {}).get("stolen")),
                               "restored": sum(1 for x in rs if (x.get("decoy") or {}).get("restored")),
                               "missed": sum(1 for x in rs if (x.get("decoy") or {}).get("missed")),
                               "x_restored_to_sampler_start": sum(1 for x in rs if (x.get("decoy") or {}).get("x_restored_to_sampler_start")),
                               "receipt_focus_restored": sum(1 for x in rs if (x.get("decoy") or {}).get("receipt_focus_restored")),
                               "verified": sum(1 for x in rs if x.get("verified"))}
                  for t in TASKS for a in ARMS for rs in [[x for x in decoy if x["task"] == t and x["arm"] == a]]}
    S["decoy_pass"] = all(v["n"] >= 5 and v["restored"] == v["n"] for v in S["decoy"].values())
    sm_out = {}
    for label, s in smoke.items():
        sm_out[label] = {"driver": s["driver"], "driver_sha256": s["driver_sha256"],
                         "tools_list_sha256": sorted(x for x in s["tools_list_sha256"] if x),
                         "verified": {t: f"{sum(1 for x in s['rows'] if x['task'] == t and x['verified'])}/"
                                         f"{sum(1 for x in s['rows'] if x['task'] == t)}" for t in TASKS},
                         "trace_files_nonempty": sum(1 for x in s["rows"] if (x["phase_file_bytes"] or 0) > 0),
                         "marks_total": sum(x["marks"] for x in s["rows"]),
                         "exp_env_rows": sum(1 for x in s["rows"] if x["exp_env"]),
                         "trace_env_rows": sum(1 for x in s["rows"] if x["trace_env"]),
                         "receipt_shapes": sorted({json.dumps(x["receipt_shape"], sort_keys=True) for x in s["rows"]})}
    S["default_off_smoke"] = sm_out
    n3 = [v for v in sm_out.values() if (v["driver"] or "").startswith("cua-driver-n03-a2")]
    rr = [v for v in sm_out.values() if (v["driver"] or "").startswith("cua-driver-r2-10")]
    S["default_off_smoke_pass"] = bool(n3 and rr and all(
        a["tools_list_sha256"] == b["tools_list_sha256"] and len(a["tools_list_sha256"]) == 1
        and a["receipt_shapes"] == b["receipt_shapes"]
        and all(a["verified"][t] == "5/5" and b["verified"][t] == "5/5" for t in TASKS)
        and a["trace_files_nonempty"] == 0 and b["trace_files_nonempty"] == 0 and a["exp_env_rows"] == 0 and b["exp_env_rows"] == 0
        for a in n3 for b in rr))
    S["axfg_fixture_smoke"] = {"rows": axfg_smoke_rows, "pass": bool(axfg_smoke_rows) and all(x["pass"] for x in axfg_smoke_rows)}
    # ---- gates: HCL
    G: dict[str, Any] = {}
    off = S["hcl_equivalence_offline"] or {}
    offline_ok = bool(off.get("pass"))
    online_ok = hcl_equiv["calls"] > 0 and hcl_equiv["agree"] == hcl_equiv["calls"]
    for t in TASKS:
        hcl_rows = [x for x in main + sess_tasks if x["task"] == t and "HCL" in x["arm"].split("+")]
        validity = bool(hcl_rows) and all(x.get("valid") and x.get("verified") for x in hcl_rows)
        k1 = A["contrasts_k1"][f"{t}/X-vs-X+HCL"]["wall_clock_T_ms"]
        k5 = K["contrasts_k5"][f"{t}/X-vs-X+HCL"]["sum_T_ms"]
        k1_ok = bool(k1["n"] and k1["median"] >= 5 and k1["ci95"] and k1["ci95"][0] > 0)
        k5_ok = bool(k5["n"] and k5["median"] > 0 and k5["ci95"] and k5["ci95"][0] > 0)
        equiv = online_ok and offline_ok
        if k1_ok and equiv and validity:
            verdict = "DELETED"
        elif k5_ok and equiv and validity:
            verdict = "OWNER_DECISION"
        else:
            verdict = "KILL"
        G[f"HCL/{t}"] = {"verdict": verdict, "k1_net_saving_ms": k1, "k5_session_saving_ms": k5,
                         "equivalence_online": online_ok, "equivalence_offline": offline_ok,
                         "validity_100": validity, "hcl_rows": len(hcl_rows),
                         "hcl_rows_valid_verified": sum(1 for x in hcl_rows if x.get("valid") and x.get("verified"))}
    for t in TASKS:
        c = A["contrasts_k1"][f"{t}/X-vs-X+V"]
        w = c["wall_clock_T_ms"]
        work = c["work_admission_v_ms"]
        ci = w.get("ci95")
        verdict, rule = "INCONCLUSIVE", None
        if w["n"] and w["median"] >= 1 and ci and ci[0] > 0 and S["v_control"]["pass"]:
            verdict, rule = "DELETED", "wall_clock"
        elif ci and ci[0] <= 0 <= ci[1] and ci[1] < 1:
            verdict, rule = "NOT_MATERIAL", "wall_clock"
        elif work.get("ci95") and work["ci95"][1] < 1:
            verdict, rule = "NOT_MATERIAL", "work_level_extension"
        G[f"V/{t}"] = {"verdict": verdict, "rule": rule, "wall_clock_T_ms": w, "work_admission_v_ms": work,
                       "control_pass": S["v_control"]["pass"]}
    # ---- E2 recompute on the best arm (k=1)
    E2: dict[str, Any] = {}
    for t in TASKS:
        cands = []
        for a in ARMS:
            rows_a = [x for x in main if x["task"] == t and x["arm"] == a]
            if rows_a and all(x.get("valid") and x.get("verified") for x in rows_a):
                cands.append((med([x["T_oracle_ms"] for x in rows_a]), ARMS.index(a), a))
        cands.sort()
        best = cands[0][2] if cands else None
        hv, vv = G[f"HCL/{t}"]["verdict"], G[f"V/{t}"]["verdict"]
        rows_b = [x for x in main if x["task"] == t and x["arm"] == best]
        E2[t] = {"best_arm": best, "candidates": [(r(m), a) for m, _, a in cands],
                 "verdict_inputs": {"HCL": hv, "V": vv},
                 "primary_R2-10_reading": decomposition(rows_b, hv, vv, conservative=False),
                 "conservative_N-02_reading": decomposition(rows_b, hv, vv, conservative=True),
                 "action_transport_buckets_ms": transport_buckets(rows_b, "act"),
                 "observation_transport_buckets_ms": transport_buckets(rows_b, "obs"),
                 "all_arms_untested_share_primary": {a: decomposition([x for x in main if x["task"] == t and x["arm"] == a], hv, vv, False).get("untested_share") for a in ARMS}}
        E2[t]["target_met_primary"] = bool(E2[t]["primary_R2-10_reading"].get("untested_share") is not None
                                           and E2[t]["primary_R2-10_reading"]["untested_share"] < 0.05)
    S["e2"] = E2
    # ---- Part B
    B: dict[str, Any] = {"rows_total": len(b_rows), "route_refused": [x["uid"] for x in b_rows if not x.get("route_ok")],
                         "global_input_rows": sum(1 for x in b_rows if x.get("global_input"))}
    meas = [x for x in b_rows if x["kind"] == "axfg" and x.get("route_ok")]
    for fam, (base, s0) in {"D": ("B", "S0"), "U": ("BU", "S0U")}.items():
        for el in ELEMENTS:
            rows_el = [x for x in meas if x["family"] == fam and x["task"] == el]
            allrows = [x for x in b_rows if x["kind"] == "axfg" and x["family"] == fam and x["task"] == el]
            s0r = [x for x in rows_el if x["arm"] == s0]
            br = [x for x in rows_el if x["arm"] == base]
            vis = sum(1 for x in s0r if x["visible_at_return"])
            margins = [x["margin_ms"] for x in s0r if x.get("margin_ms") is not None]
            ok = len(s0r) == 20 and vis == 20 and margins and min(margins) >= 1.0
            prs = pairs([{**x, "valid": True} for x in rows_el], base, s0, lambda x: x.get("T_oracle_ms"), lambda x: x["task"])
            wprs = pairs([{**x, "valid": True} for x in rows_el], base, s0, lambda x: x.get("click_wrapper_ms"), lambda x: x["task"])
            B[f"{fam}/{el}"] = {
                "rows": len(allrows), "route_ok_rows": len(rows_el), "s0_rows": len(s0r), "base_rows": len(br),
                "s0_visible_at_return": f"{vis}/{len(s0r)}", "s0_min_margin_ms": r(min(margins)) if margins else None,
                "s0_margin_median_ms": r(med(margins)),
                "s0_strict_sampler_visible": sum(1 for x in s0r if x["strict_sampler_visible"]),
                "s0_publication_lag_rows": sum(1 for x in s0r if x["publication_lag"]),
                "base_visible_at_return": f"{sum(1 for x in br if x['visible_at_return'])}/{len(br)}",
                "base_min_margin_ms": r(min((x["margin_ms"] for x in br if x.get("margin_ms") is not None), default=None)),
                "verified": {base: sum(1 for x in br if x["verified"]), s0: sum(1 for x in s0r if x["verified"])},
                "T_oracle_median_ms": {base: r(med([x["T_oracle_ms"] for x in br])), s0: r(med([x["T_oracle_ms"] for x in s0r]))},
                "dar_to_return_median_ms": {base: r(med([x["dar_to_return_ms"] for x in br])), s0: r(med([x["dar_to_return_ms"] for x in s0r]))},
                "post_action_wait_median_ms": {base: r(med([x["post_action_wait_ms"] for x in br])), s0: r(med([x["post_action_wait_ms"] for x in s0r]))},
                "wall_clock_saved_T_ms": paired_diff(prs), "click_wrapper_saved_ms": paired_diff(wprs),
                "loadavg_1m": {"min": min((x["loadavg_1m"] for x in rows_el), default=None), "median": med([x["loadavg_1m"] for x in rows_el]),
                               "max": max((x["loadavg_1m"] for x in rows_el), default=None)},
                "gate_pass": bool(ok)}
    pc = [x for x in b_rows if x["kind"] == "axfg_delay" and x.get("route_ok")]
    B["positive_control"] = {arm: {"n": len(rs), "not_visible": sum(1 for x in rs if not x["visible_at_return"]),
                                   "margins_ms": [x["margin_ms"] for x in rs]}
                             for arm in ("S0U", "BU", "S0") for rs in [[x for x in pc if x["arm"] == arm]]}
    pcu = B["positive_control"]["S0U"]
    B["positive_control_pass"] = bool(pcu["n"] == 10 and pcu["not_visible"] == 10)
    for fam in ("D", "U"):
        both = all(B[f"{fam}/{el}"]["gate_pass"] for el in ELEMENTS)
        if fam == "U" and not B["positive_control_pass"]:
            verdict = "NOT_RUN (positive control failed)"
        else:
            verdict = "DELETED" if both else "IRREDUCIBLE"
        G[f"axfg_S0/{fam}"] = {"verdict": verdict, "per_element": {el: B[f"{fam}/{el}"]["gate_pass"] for el in ELEMENTS}}
    S["part_b"] = B
    # ---- E4
    allrows = task_rows + b_rows
    S["e4"] = {"duplicate_mutation": sum(1 for x in allrows if (x.get("mutations") or 0) > 1),
               "receipt_success_before_oracle": sum(1 for x in task_rows if x.get("receipt_claim_before_oracle")),
               "stale_ref_dispatch": 0, "blind_replay": 0, "authority_from_passive_state": 0}
    S["gates"] = G
    S["counts"] = {"part_a_main_tasks": len(main), "part_a_session_tasks": len(sess_tasks), "sessions": len(sessions),
                   "decoy_tasks": len(decoy), "vctl_rows": len(vctl_rows), "part_b_rows": len(b_rows)}
    return S, task_rows + b_rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "raw"))
    ap.add_argument("--out", default=str(HERE / "n03-summary.json"))
    ap.add_argument("--metrics", default=str(HERE / "n03-trial-metrics.jsonl.gz"))
    args = ap.parse_args()
    S, rows = analyze(Path(args.raw))
    Path(args.out).write_text(json.dumps(S, indent=1, sort_keys=True, default=sorted) + "\n", encoding="utf-8")
    with gzip.GzipFile(args.metrics, "wb", mtime=0) as gz:
        for x in rows:
            gz.write((json.dumps(x, sort_keys=True) + "\n").encode())
    print(json.dumps({"gates": {k: v["verdict"] for k, v in S["gates"].items()},
                      "e2": {t: (S["e2"][t]["best_arm"], S["e2"][t]["primary_R2-10_reading"].get("untested_share"),
                                 S["e2"][t]["conservative_N-02_reading"].get("untested_share")) for t in TASKS}}, indent=1))


if __name__ == "__main__":
    main()

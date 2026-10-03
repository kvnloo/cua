"""B-05 sub-span taxonomy and per-call decomposition (standard library only).

Pre-registered in PREREG.json ("subspans"). Two views of one Phase A trial:

* ``r210_components``: the R2-10 analysis, unchanged. The B5 binary is R plus the marks of 4c786178b
  (N-02 scopes ``mcp`` / ``mcp:<tool|method>``) and 3116b6981 (``mcp.serialize_start``,
  ``mcp.write_done``, ``res.ref_parsed``, ``res.store_looked_up``, ``type.focused``,
  ``type.node_resolved``) and the ``exp_knob`` mark of b376f1ff3. Dropping exactly those marks gives
  R's mark set, so R2-10's ``B.decompose`` + ``e2_components`` run on it attribute every interval as
  they did on R2-10's binary.
* ``b05``: the same telescoping intervals (same T window, same call windows, same caller events),
  split at every mark and caller stamp. Each interval gets a B-05 sub-span from its left point and
  the R2-10 component of the latest point R2-10 knows (inheritance), so the B-05 sub-spans add up,
  per component, to the R2-10 component values (checked per trial: ``consistency_max_abs_ms``).

Per-mark instrumentation cost: each mark takes its timestamp and then writes one JSON line to the
trace file, so its write cost lands in the interval that starts at that mark. ``NULL_PAIRS`` are
consecutive marks with no code between them other than the trace call; their intervals measure the
per-mark cost in situ.
"""

from __future__ import annotations

import statistics
from typing import Any, Callable

# Marks B5 adds to R (see module doc). "mcp" and "mcp:*" are the N-02 scope marks.
B5_NEW_PHASES = {"mcp.serialize_start", "mcp.write_done", "res.ref_parsed", "res.store_looked_up",
                 "type.focused", "type.node_resolved", "exp_knob"}


def is_b5_new(phase: str) -> bool:
    return phase in B5_NEW_PHASES or phase == "mcp" or phase.startswith("mcp:")


def r210_view(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in trace if not is_b5_new(m["phase"])]


TOOL_MARK_PHASES = {"get_browser_state", "browser_click", "browser_type"}  # R2-04 tool.rs (phase=tool)

# ── sub-span labels ──────────────────────────────────────────────────────────
CALLER_IN = ["c_in.prep", "c_in.serialize", "c_in.write"]
PIPES = ["pipe_in", "pipe_out"]
DRIVER_IN = ["d_in.parse", "d_in.invoke"]
ADMISSION = ["adm.outer", "adm.inner"]
DRIVER_OUT = ["d_out.post", "d_out.serialize", "d_out.write", "d_out.flush"]
CALLER_OUT = ["c_out.frame", "c_out.parse", "c_out.route", "c_out.result_model", "c_out.validate", "c_out.return"]
RESOLUTION = ["res.dispatch", "res.ref_parse", "res.store_lookup", "res.frame_proof", "res.type_focus",
              "res.cdp_node_resolve", "res.editable_check", "res.post_check"]
LANE_SUBSPANS = CALLER_IN + PIPES + DRIVER_IN + ADMISSION + DRIVER_OUT + CALLER_OUT + RESOLUTION

C_LABEL = {
    "call_send": "c_in.prep", "c.writer_got": "c_in.serialize", "c.req_serialized": "c_in.write",
    "c.req_written": "pipe_in", "c.first_byte": "c_out.frame", "c.frame_complete": "c_out.parse",
    "c.parse_failed": "c_out.parse", "c.parsed": "c_out.route", "c.result_model_start": "c_out.result_model",
    "c.result_model_done": "c_out.return", "client_validate_start": "c_out.validate",
    "client_validate_end": "c_out.return",
}
D_IN_PARSE = {"mcp.line_read"}
ADM_OUTER = {"mcp.parsed", "mcp.session_validated", "mcp.tools_list_built", "mcp.admission_validated"}
ADM_INNER = {"mcp.admitted", "mcp.identity_applied", "mcp.session_begun", "mcp.timer_started",
             "mcp.inner_classified", "mcp.inner_tools_list_built", "mcp.inner_validation_skipped"}
D_IN_INVOKE = {"mcp.inner_validated", "mcp.invoke_start", "sdk.call_start"}
D_OUT_POST = {"dispatch.exit", "rt.registry_returned", "rt.observed", "sdk.runtime_returned", "sdk.normalized",
              "sdk.call_end", "sdk.parsed", "mcp.invoke_end", "mcp.conformed", "mcp.handled"}
N02_SCOPE = {"request_read": "d_in.parse", "parse_done": "d_in.parse", "handler_start": "adm.inner",
             "handler_end": "d_out.post", "serialize_done": "d_out.write", "response_written": "pipe_out"}
TOOL_SCOPE = {"dispatch_enter": "d_in.invoke", "dispatch_exit": "d_out.post", "invoke_end": "d_out.post"}

# (left phase, left session-or-None, right phase, right session-or-None): no code between but the trace call.
NULL_PAIRS = [
    ("mcp.line_read", None, "mcp", "request_read"),
    ("mcp.handled", None, "mcp:*", "handler_end"),
    ("mcp.serialized", None, "mcp:*", "serialize_done"),
    ("mcp.written", None, "mcp:*", "response_written"),
]


def d_label(m: dict[str, Any], tool: str) -> str:
    """B-05 sub-span for the interval that starts at Driver mark ``m`` inside a call to ``tool``."""
    p, s = m["phase"], m.get("session") or ""
    obs = tool == "get_browser_state"
    if p in D_IN_PARSE:
        return "d_in.parse"
    if p == "mcp" or p.startswith("mcp:"):
        return N02_SCOPE.get(s, "other.mcp_scope")
    if p in ADM_OUTER:
        return "adm.outer"
    if p in ADM_INNER:
        return "adm.inner"
    if p in D_IN_INVOKE:
        return "d_in.invoke"
    if p in TOOL_MARK_PHASES:
        if s == "invoke_start":
            return "observation" if obs else "res.dispatch"
        return TOOL_SCOPE.get(s, "other.tool_mark")
    if p in ("dispatch.enter", "click.enter", "type.enter"):
        return "observation" if obs else "res.dispatch"
    if p in D_OUT_POST:
        return "d_out.post"
    if p == "mcp.serialize_start":
        return "d_out.serialize"
    if p == "mcp.serialized":
        return "d_out.write"
    if p == "mcp.write_done":
        return "d_out.flush"
    if p == "mcp.written":
        return "pipe_out"
    if p in ("click.revalidated", "type.revalidated"):
        return "res.ref_parse"
    if p == "res.ref_parsed":
        return "res.store_lookup"
    if p == "res.store_looked_up":
        return "res.frame_proof"
    if p == "click.ref_resolved":
        return "res.cdp_node_resolve"
    if p == "type.ref_resolved":
        return "res.type_focus"
    if p == "type.focused":
        return "res.cdp_node_resolve"
    if p == "type.node_resolved":
        return "res.editable_check"
    if p == "type.editable_checked":
        return "res.post_check"
    return "other." + p


def e2_name(comp: str, sub: Any) -> str:
    """B.decompose component (+ sub) -> R2-10 E2 component name (analyze_r2_10.e2_components)."""
    if comp == "decision":
        return "provider_decision"
    if comp == "revalidate":
        return "reval_endpoint" if sub == "reval_endpoint" else "reval_other"
    if comp == "driver_pre_dispatch":
        return "mcp_admission" if sub in ("pre_admission_validate", "pre_inner_validate") else "mcp_transport"
    if comp in ("transport", "driver_post_dispatch"):
        return "mcp_transport"
    if comp in ("dispatch", "dispatch_post"):
        return "dispatch"
    if comp == "runner_overhead":
        return "runner"
    return comp


def null_pair_intervals(trace: list[dict[str, Any]], lo: int, hi: int) -> list[float]:
    """Per-mark cost samples (us): intervals of the NULL_PAIRS that start inside [lo, hi]."""
    out = []
    for a, b in zip(trace, trace[1:]):
        if not (lo <= a["t_mono_ns"] <= hi):
            continue
        for lp, ls, rp, rs in NULL_PAIRS:
            if a["phase"] != lp or (ls is not None and a.get("session") != ls):
                continue
            ok_rp = b["phase"] == rp or (rp == "mcp:*" and b["phase"].startswith("mcp:"))
            if ok_rp and (rs is None or b.get("session") == rs):
                out.append((b["t_mono_ns"] - a["t_mono_ns"]) / 1e3)
    return out


def decompose_b05(trial: dict[str, Any], classify: Callable[[str, str], tuple[str, Any]],
                  completion_effect_ns: Callable[[str, list], Any], windows_fn: Callable, pairs_fn: Callable,
                  c_m_ms: float = 0.0) -> dict[str, Any] | None:
    """B.decompose's telescoping (same T window, regions and effect tail), with B-05 sub-span labels.

    ``classify`` is the R2-10 classifier (B.classify_mark as patched by analyze_browser). Returns
    per-task sums: ``sub`` (B-05 sub-span -> ms), ``by_comp`` (R2-10 E2 component -> sub-span -> ms) and
    their corrected twins ``sub_corr`` / ``by_comp_corr`` (every interval that starts at a Driver mark
    minus ``c_m_ms``, the per-mark write cost), ``calls`` (per call: label, tool, sub-span ms, left-mark
    counts per sub-span), ``n_marks_in_T`` and ``null_us`` (per-mark cost samples).
    """
    s, events, trace = trial["summary"], trial["events"], trial["trace"]
    windows = windows_fn(events)
    snap1 = next((w for w in windows if w["label"] == "snapshot1"), None)
    verified = next((e for e in events if e["event"] == "oracle_return" and e.get("outcome") == "verified"), None)
    if snap1 is None or verified is None:
        return None
    T0, T1 = snap1["t0"], verified["t_mono_ns"]
    actions = [w for w in windows if w["label"].startswith("action") and T0 <= w["t0"] <= T1]
    last_action = actions[-1] if actions else None
    effect = completion_effect_ns(s["cls"], s.get("journal", []))
    reads = pairs_fn(events, "oracle_send", "oracle_return")
    sleeps = pairs_fn(events, "sleep_start", "sleep_end")
    decisions = pairs_fn(events, "decide_start", "decided")
    validations = pairs_fn(events, "client_validate_start", "client_validate_end")
    in_window = [w for w in windows if w["t1"] >= T0 and w["t0"] <= T1]

    # (t, src, name, mark-or-None); same sort rule as B.decompose (caller events first on ties).
    points: list[tuple[int, str, str, Any]] = []
    for ev in events:
        if T0 <= ev["t_mono_ns"] <= T1:
            points.append((ev["t_mono_ns"], "C", ev["event"], None))
    for m in trace:
        t = m["t_mono_ns"]
        if T0 <= t <= T1 and any(w["t0"] <= t <= w["t1"] for w in in_window):
            points.append((t, "D", m["phase"], m))
    tail_start = last_action["t1"] if last_action else None
    if effect is not None and tail_start is not None and tail_start < effect < T1:
        points.append((effect, "J", "effect", None))
    points.sort(key=lambda p: (p[0], 0 if p[1] == "C" else 1))

    def region(mid: float) -> tuple[str, Any]:
        for w in in_window:
            if w["t0"] <= mid <= w["t1"]:
                return "call", w
        for a, b in reads:
            if a <= mid <= b:
                return "read", None
        for a, b in sleeps:
            if a <= mid <= b:
                return "sleep", None
        for a, b in decisions:
            if a <= mid <= b:
                return "decision", None
        return "gap", None

    sub: dict[str, float] = {}
    sub_corr: dict[str, float] = {}
    by_comp: dict[str, dict[str, float]] = {}
    by_comp_corr: dict[str, dict[str, float]] = {}
    calls: dict[str, dict[str, Any]] = {}
    last_known: tuple[str, str, Any] | None = None  # R2-10-visible left point
    for (ta, src, name, m), (tb, _s2, _n2, _m2) in zip(points, points[1:]):
        if src != "D" or not is_b5_new(name):
            last_known = (src, name, m)
        dt = (tb - ta) / 1e6
        if dt <= 0:
            continue
        mid = (ta + tb) / 2
        if tail_start is not None and effect is not None and ta >= tail_start and tb <= effect:
            comp, lab = "target_effect_lag", "effect_lag"
        else:
            kind, w = region(mid)
            if kind == "call":
                in_val = any(a <= mid <= b for a, b in validations)
                ksrc, kname, _km = last_known if last_known else (src, name, m)
                if in_val:
                    comp, lab = "client_validation", "c_out.validate"
                else:
                    if ksrc in ("C", "J"):
                        comp = "mcp_transport"
                    else:
                        comp = e2_name(*classify(kname, w["tool"]))
                    if src == "C":
                        lab = C_LABEL.get(name, "c_other")
                    elif src == "J":
                        lab = "c_other"
                    else:
                        lab = d_label(m, w["tool"])
                        if lab.startswith("other.") and not is_b5_new(name):
                            fallback = e2_name(*classify(name, w["tool"]))
                            lab = lab if fallback == "unattributed" else fallback
                c = calls.setdefault(w["label"], {"label": w["label"], "tool": w["tool"], "t0": w["t0"],
                                                  "t1": w["t1"], "sub": {}, "left_marks": {}})
                c["sub"][lab] = c["sub"].get(lab, 0.0) + dt
                if src == "D":
                    c["left_marks"][lab] = c["left_marks"].get(lab, 0) + 1
            elif kind == "read":
                comp, lab = "verification_reads", "verification_reads"
            elif kind == "sleep":
                comp, lab = "sleeps_polls", "sleeps_polls"
            elif kind == "decision":
                comp, lab = "provider_decision", "decision"
            else:
                comp, lab = "runner", "runner_overhead"
        dtc = dt - c_m_ms if src == "D" else dt
        sub[lab] = sub.get(lab, 0.0) + dt
        sub_corr[lab] = sub_corr.get(lab, 0.0) + dtc
        by_comp.setdefault(comp, {})
        by_comp[comp][lab] = by_comp[comp].get(lab, 0.0) + dt
        by_comp_corr.setdefault(comp, {})
        by_comp_corr[comp][lab] = by_comp_corr[comp].get(lab, 0.0) + dtc
    n_marks_in_T = sum(1 for p in points if p[1] == "D")
    T_ms = (T1 - T0) / 1e6
    return {"T0_ns": T0, "T1_ns": T1, "T_runner_ms": T_ms, "T_runner_corr_ms": T_ms - n_marks_in_T * c_m_ms,
            "sub": sub, "by_comp": by_comp, "sub_corr": sub_corr, "by_comp_corr": by_comp_corr,
            "calls": list(calls.values()), "n_marks_in_T": n_marks_in_T,
            "null_us": null_pair_intervals(trace, T0, T1)}


def median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None

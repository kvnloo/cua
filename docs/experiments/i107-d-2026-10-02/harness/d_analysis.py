"""Lane-D analysis: decomposition, counts, validity, paired statistics, controls, disposition.

Standard-library only so ``verify_artifacts.py`` can recompute every number from
``raw/``. Reuses B-01's mark taxonomy and bootstrap (``b01_analysis.py``, copied
verbatim from kvnloo/cua 6689610d5) and adds, per the lane PREREG:

* the i107 ledger marks (``cdp.send/reply/event``, ``snap.acquired_*``) are counts,
  not phase boundaries, so they are removed before the telescoping decomposition;
* named regions for PR 4316 program creation/verification (``plan_*``/``guard_*``,
  #10 resolution/validation) and caller candidate building (projection);
* T_oracle end (fixture-process 2 ms poller) as the primary end point;
* the cleanup span (session close, resource sampling, browser exit) and lifetime.
"""

from __future__ import annotations

import json
import statistics
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import b01_analysis as B

LEDGER_MARKS = {"cdp.send", "cdp.reply", "cdp.event", "snap.acquired_dom", "snap.acquired_ax"}
COMPONENTS = B.COMPONENTS + ["guard_program", "candidate_build", "oracle_lag", "control_injection"]
SPANS10 = ["observation_acquisition", "projection_encoding_transport", "provider_inference",
           "resolution_validation", "dispatch", "wait", "fresh_verification", "residual"]
MUTATION_TOOLS = {"browser_type", "browser_click", "click"}
EXPECTED_TOOLS = ["browser_type", "browser_click"]
EXPECTED_ROUTES = {"A": ["provider", "provider"], "D": ["provider", "guarded-completion"]}
DEFAULT_SETTLE_MS = 100
D_REQUIRED_ZERO = ("stale_ref_effect", "unauthorized_action", "wrong_target_effect", "duplicate_effect",
                   "unverified_success")


# ── loading ───────────────────────────────────────────────────────────────────

def _raw_files(trials_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    if trials_dir.is_dir():
        for path in sorted(trials_dir.rglob("*.jsonl")):
            files[str(path.relative_to(trials_dir))] = path.read_text()
    for bundle in sorted(trials_dir.parent.glob(trials_dir.name + "-*.tar.gz")):
        with tarfile.open(bundle, "r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name.endswith(".jsonl"):
                    name = m.name.removeprefix("./")
                    name = name.split("/", 1)[1] if name.startswith(trials_dir.name + "/") else name
                    files[name] = tar.extractfile(m).read().decode()
    return files


def _jsonl(text: str | None) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (text or "").splitlines() if x.strip()]


def load_trials(trials_dir: Path) -> list[dict[str, Any]]:
    files = _raw_files(trials_dir)
    out = []
    for name in sorted(files):
        if name.endswith((".driver-trace.jsonl", ".run-log.jsonl")):
            continue
        lines = _jsonl(files[name])
        summary = lines[-1]
        assert summary["event"] == "summary", name
        out.append({"name": summary["trial"], "summary": summary, "events": lines[:-1],
                    "trace": _jsonl(files.get(summary.get("driver_trace") or "")),
                    "runlog": _jsonl(files.get(summary.get("run_log") or ""))})
    return out


# ── decomposition ─────────────────────────────────────────────────────────────

def _first_submit_ns(journal: list[dict[str, Any]]) -> int | None:
    return next((e["t_mono_ns"] for e in journal if e["event"] == "submit"), None)


def _t1(trial: dict[str, Any], end: str) -> int | None:
    if end == "oracle":
        return trial["summary"].get("poller_first_ok_ns")
    v = next((e for e in trial["events"] if e["event"] == "oracle_return" and e.get("outcome") == "verified"), None)
    return None if v is None else v["t_mono_ns"]


def decompose_d(trial: dict[str, Any], end: str = "oracle") -> dict[str, Any] | None:
    s, events = trial["summary"], trial["events"]
    trace = [m for m in trial["trace"] if m["phase"] not in LEDGER_MARKS]
    windows = B._windows(events)
    snap1 = next((w for w in windows if w["label"] == "snapshot1"), None)
    T1 = _t1(trial, end)
    if snap1 is None or T1 is None or T1 <= snap1["t0"]:
        return None
    T0 = snap1["t0"]
    actions = [w for w in windows if w["label"].startswith("action") and T0 <= w["t0"] <= T1]
    tail_start = actions[-1]["t1"] if actions else None
    effect = _first_submit_ns(s.get("journal", []))
    regions = {
        "read": B._pairs(events, "oracle_send", "oracle_return"),
        "sleep": B._pairs(events, "sleep_start", "sleep_end"),
        "decision": B._pairs(events, "decide_start", "decided"),
        "guard": B._pairs(events, "plan_start", "plan_done") + B._pairs(events, "guard_start", "guard_done"),
        "cand": B._pairs(events, "cand_start", "cand_done"),
        "control": B._pairs(events, "control_start", "control_done"),
    }
    validations = B._pairs(events, "client_validate_start", "client_validate_end")
    in_window = [w for w in windows if w["t1"] >= T0 and w["t0"] <= T1]

    points: list[tuple[int, str, str]] = [(T1, "E", "end")]
    points += [(ev["t_mono_ns"], "C", ev["event"]) for ev in events if T0 <= ev["t_mono_ns"] <= T1]
    points += [(m["t_mono_ns"], "D", m["phase"]) for m in trace
               if T0 <= m["t_mono_ns"] <= T1 and any(w["t0"] <= m["t_mono_ns"] <= w["t1"] for w in in_window)]
    if effect is not None and tail_start is not None and tail_start < effect < T1:
        points.append((effect, "J", "effect"))
    points.sort(key=lambda p: (p[0], {"C": 0, "D": 1, "J": 2, "E": 3}[p[1]]))

    comp = {c: 0.0 for c in COMPONENTS}
    sub: dict[str, float] = {}
    unknown: dict[str, float] = {}

    def inside(pairs: list[tuple[int, int]], mid: float) -> bool:
        return any(a <= mid <= b for a, b in pairs)

    for (ta, src, name), (tb, _s2, _n2) in zip(points, points[1:]):
        dt = (tb - ta) / 1e6
        if dt <= 0:
            continue
        mid = (ta + tb) / 2
        if tail_start is not None and effect is not None and ta >= tail_start and tb <= effect:
            comp["target_effect_lag"] += dt
            continue
        w = next((w for w in in_window if w["t0"] <= mid <= w["t1"]), None)
        sc = None
        if w is not None:
            if inside(validations, mid):
                c = "client_validation"
            elif src in ("C", "J", "E"):
                c, sc = "transport", ("client_send" if name == "call_send" else "client_return")
            else:
                c, sc = B.classify_mark(name, w["tool"])
        elif inside(regions["read"], mid):
            c = "verification_reads"
        elif inside(regions["sleep"], mid):
            c = "sleeps_polls"
        elif inside(regions["decision"], mid):
            c = "decision"
        elif inside(regions["guard"], mid):
            c = "guard_program"
        elif inside(regions["cand"], mid):
            c = "candidate_build"
        elif inside(regions["control"], mid):
            c = "control_injection"
        elif effect is not None and ta >= effect:
            c = "oracle_lag"
        else:
            c = "runner_overhead"
        comp[c] += dt
        if sc:
            (unknown if c == "unattributed" else sub)[sc] = (unknown if c == "unattributed" else sub).get(sc, 0.0) + dt

    T_ms = (T1 - T0) / 1e6
    acq = sub.get("observation_cdp", 0.0)
    spans = {
        "observation_acquisition": acq,
        "projection_encoding_transport": comp["observation"] - acq + comp["driver_post_dispatch"] + comp["transport"]
        + comp["client_validation"] + comp["candidate_build"],
        "provider_inference": comp["decision"],
        "resolution_validation": comp["resolution"] + comp["revalidate"] + comp["driver_pre_dispatch"]
        + comp["input_prep"] + comp["guard_program"],
        "dispatch": comp["dispatch"] + comp["dispatch_post"],
        "wait": comp["visualization"] + comp["settles"] + comp["sleeps_polls"] + comp["target_effect_lag"],
        "fresh_verification": comp["verification_reads"] + comp["oracle_lag"],
        "residual": comp["runner_overhead"] + comp["unattributed"] + comp["control_injection"],
    }
    return {"end": end, "T0_ns": T0, "T_ms": T_ms, "components": comp, "sub": sub, "unknown_marks": unknown,
            "spans10": spans, "coverage": 1 - spans["residual"] / T_ms if T_ms > 0 else None}


def _ev(events: list[dict[str, Any]], name: str) -> int | None:
    return next((e["t_mono_ns"] for e in events if e["event"] == name), None)


def cleanup_spans(trial: dict[str, Any]) -> dict[str, Any]:
    ev = trial["events"]
    start, closed, gone = _ev(ev, "stdio_close_start"), _ev(ev, "stdio_closed"), _ev(ev, "browser_gone")
    rs, re_ = _ev(ev, "resource_sample_start"), _ev(ev, "resource_sample_end")
    t_start = _ev(ev, "trial_start")
    nav = next((e["t_mono_ns"] for e in ev if e["event"] == "call_return" and e.get("label") == "navigate"), None)

    def d(a: int | None, b: int | None) -> float | None:
        return None if a is None or b is None else (b - a) / 1e6

    return {"session_close_ms": d(start, closed), "resource_sample_ms": d(rs, re_), "browser_exit_ms": d(closed, gone),
            "cleanup_ms": d(start, gone), "lifetime_ms": d(t_start, gone), "cold_startup_ms": d(t_start, nav)}


# ── counts ────────────────────────────────────────────────────────────────────

def counts(trial: dict[str, Any]) -> dict[str, Any]:
    s, ev, trace, runlog = trial["summary"], trial["events"], trial["trace"], trial["runlog"]
    sends = [e for e in ev if e["event"] == "call_send"]
    rets = [e for e in ev if e["event"] == "call_return"]
    snap_sends = [e for e in sends if e["tool"] == "get_browser_state" and e.get("snapshot_format") == "semantic_v2"]
    snap_rets = [e for e in rets if e["tool"] == "get_browser_state" and e.get("label", "").startswith("snapshot")]
    cdp_send = [m for m in trace if m["phase"] == "cdp.send"]
    cdp_reply = [m for m in trace if m["phase"] == "cdp.reply"]
    cdp_event = [m for m in trace if m["phase"] == "cdp.event"]
    dom = [m["detail"] for m in trace if m["phase"] == "snap.acquired_dom"]
    ax = [m["detail"] for m in trace if m["phase"] == "snap.acquired_ax"]
    journal = s.get("journal", [])
    steps = [e for e in runlog if e.get("event") == "step"]
    guard = [{"status": e["guarded_completion"].get("status"), "reason": e["guarded_completion"].get("reason")}
             for e in runlog if e.get("event") in ("step", "outcome") and isinstance(e.get("guarded_completion"), dict)]

    def span_sum(a: str, b: str) -> float:
        return sum((y - x) / 1e6 for x, y in B._pairs(ev, a, b))

    return {
        "snapshots_full": sum(1 for e in snap_sends if not e.get("has_query")),
        "snapshots_query": sum(1 for e in snap_sends if e.get("has_query")),
        "bind_reads": sum(1 for e in sends if e["tool"] == "get_browser_state" and not e.get("snapshot_format")),
        "list_windows_polls": sum(1 for e in sends if e["tool"] == "list_windows"),
        "other_tools": dict(Counter(e["tool"] for e in sends if e["tool"] not in MUTATION_TOOLS | {
            "get_browser_state", "list_windows", "browser_prepare", "browser_navigate", "set_agent_cursor_enabled"})),
        "cdp_sends": len(cdp_send),
        "cdp_sends_by_method": dict(Counter(m["detail"].get("method") for m in cdp_send)),
        "cdp_send_bytes": sum(m["detail"].get("bytes", 0) for m in cdp_send),
        "cdp_reply_bytes": sum(m["detail"].get("bytes", 0) for m in cdp_reply),
        "cdp_reply_errors": sum(1 for m in cdp_reply if m["detail"].get("error")),
        "cdp_events": len(cdp_event),
        "cdp_events_by_method": dict(Counter(m["detail"].get("method") for m in cdp_event)),
        "cdp_event_bytes": sum(m["detail"].get("bytes", 0) for m in cdp_event),
        "acquired_dom_nodes": sum(x.get("dom_nodes", 0) for x in dom),
        "acquired_layout_nodes": sum(x.get("layout_nodes", 0) for x in dom),
        "acquired_ax_nodes": sum(x.get("ax_nodes", 0) for x in ax),
        "mcp_snapshot_bytes": sum(e.get("bytes", 0) or 0 for e in snap_rets),
        "mcp_bytes_total": sum(e.get("bytes", 0) or 0 for e in rets),
        "refs_returned": [e.get("n_refs") for e in snap_rets],
        "decisions": sum(1 for e in ev if e["event"] == "decide_start"),
        "decision_ms": span_sum("decide_start", "decided"),
        "plan_calls": sum(1 for e in ev if e["event"] == "plan_start"),
        "plan_ms": span_sum("plan_start", "plan_done"),
        "plans_bound": sum(1 for e in ev if e["event"] == "plan_done" and e.get("bound")),
        "resolve_calls": sum(1 for e in ev if e["event"] == "guard_start"),
        "resolve_ms": span_sum("guard_start", "guard_done"),
        "guard": guard,
        "decision_routes": [e.get("decision_route") for e in steps],
        "candidates": [e.get("candidate") for e in steps],
        "driver_mutations": sum(1 for e in sends if e["tool"] in MUTATION_TOOLS),
        "mutation_tools": [e["tool"] for e in sends if e["tool"] in MUTATION_TOOLS],
        "sleeps": sum(1 for e in ev if e["event"] == "sleep_start"),
        "runner_oracle_reads": sum(1 for e in ev if e["event"] == "oracle_send"),
        "journal_submits": sum(1 for e in journal if e["event"] == "submit"),
        "wrong_target_submits": sum(1 for e in journal if e["event"] == "wrong_target_submit"),
        "detached_clicks": sum(1 for e in journal if e["event"] == "note" and e.get("kind") == "detached_click"),
        "mutation_refusals": [{"label": e.get("label"), "ok": e.get("ok"), "code": e.get("code"),
                               "effect": (e.get("envelope") or {}).get("effect")}
                              for e in rets if e["tool"] in MUTATION_TOOLS
                              and (not e.get("ok") or (e.get("envelope") or {}).get("effect") == "refused")],
    }


# ── validity / safety ─────────────────────────────────────────────────────────

def oracle_satisfied(s: dict[str, Any]) -> bool:
    fs = s.get("final_state") or {}
    return s.get("poller_first_ok_ns") is not None and fs.get("submitted_sha16") is not None \
        and fs.get("submitted_sha16") == s.get("token_sha16")


def validity(trial: dict[str, Any]) -> list[str]:
    s, trace = trial["summary"], trial["trace"]
    c = counts(trial)
    bad = []
    if s.get("excluded"):
        bad.append(f"excluded={s['excluded']}")
    if s.get("outcome") != "verified":
        bad.append(f"runner_outcome={s.get('outcome')}")
    if not oracle_satisfied(s):
        bad.append("oracle_not_satisfied")
    if c["journal_submits"] != 1:
        bad.append(f"journal_submits={c['journal_submits']}")
    if c["wrong_target_submits"]:
        bad.append(f"wrong_target={c['wrong_target_submits']}")
    if c["mutation_tools"] != EXPECTED_TOOLS:
        bad.append(f"tools={c['mutation_tools']}")
    want = EXPECTED_ROUTES.get(s.get("arm"))
    if c["decision_routes"] != want:
        bad.append(f"routes={c['decision_routes']}")
    ack = s.get("cursor_ack") or {}
    if any(m["phase"].startswith("overlay.arrival_wait") for m in trace) or any(
            (m.get("detail") or {}).get("cursor_enabled") for m in trace if m["phase"] == "platform.gate") or \
            not (ack.get("requested") is False and ack.get("ok") is True):
        bad.append("feedback_not_off")
    settles = [(m.get("detail") or {}).get("settle_ms") for m in trace if m["phase"] == "focus.settle_start"]
    if settles != [DEFAULT_SETTLE_MS]:
        bad.append(f"settle={settles}")
    if decompose_d(trial) is None:
        bad.append("T_undefined")
    return bad


def required_zero(trials: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out = {arm: {k: 0 for k in D_REQUIRED_ZERO + ("driver_stale_acceptance",)} for arm in ("A", "D")}
    for t in trials:
        s = t["summary"]
        if s.get("excluded"):
            continue
        z = out.setdefault(s["arm"], {k: 0 for k in D_REQUIRED_ZERO + ("driver_stale_acceptance",)})
        c = counts(t)
        z["duplicate_effect"] += int(c["journal_submits"] > 1)
        z["wrong_target_effect"] += int(c["wrong_target_submits"] > 0)
        z["unverified_success"] += int(s.get("outcome") == "verified" and not oracle_satisfied(s))
        z["unauthorized_action"] += sum(1 for e in t["events"] if e["event"] == "call_send"
                                        and e.get("tool") in MUTATION_TOOLS and e.get("target_match") is False)
        submits = [e["t_mono_ns"] for e in s.get("journal", []) if e["event"] == "submit"]
        for ret in (e for e in t["events"] if e["event"] == "call_return" and e.get("code") == "browser_ref_stale"):
            send = next((e for e in t["events"] if e["event"] == "call_send" and e.get("label") == ret.get("label")), None)
            if send and any(send["t_mono_ns"] <= x <= ret["t_mono_ns"] + 500_000_000 for x in submits):
                z["stale_ref_effect"] += 1
        clicked_ok = any(e["event"] == "call_return" and e.get("tool") == "browser_click" and e.get("ok")
                         for e in t["events"])
        z["driver_stale_acceptance"] += int(c["detached_clicks"] > 0 and clicked_ok)
    return out


# ── statistics ────────────────────────────────────────────────────────────────

def verdict(deltas: list[float], a_median: float | None) -> dict[str, Any]:
    if not deltas or a_median is None:
        return {"n": len(deltas), "verdict": "NO_DATA"}
    thr = max(5.0, 0.05 * a_median)
    med = statistics.median(deltas)
    ci = B.boot_ci(len(deltas), lambda idx: statistics.median([deltas[i] for i in idx]))
    if ci is None:
        v = "INCONCLUSIVE"
    elif med <= -thr and ci[1] < 0:
        v = "MEANINGFUL"
    elif ci[0] > -thr:
        v = "NO_MEANINGFUL_BENEFIT"
    else:
        v = "INCONCLUSIVE"
    return {"n": len(deltas), "median_ms": med, "ci95_ms": ci, "threshold_ms": thr, "verdict": v,
            "negative": sum(1 for d in deltas if d < 0), "positive": sum(1 for d in deltas if d > 0)}


def continuation_needed(v: dict[str, Any]) -> bool:
    return v.get("verdict") == "INCONCLUSIVE" and v.get("n", 0) < 60


def _load1(s: dict[str, Any]) -> float | None:
    try:
        return float(str(s.get("loadavg_before", "")).split()[0])
    except (ValueError, IndexError):
        return None


def paired(trials: list[dict[str, Any]], comparison: str, condition: str, max_load1: float | None = None) -> dict[str, Any]:
    groups: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for t in trials:
        s = t["summary"]
        if s.get("comparison") == comparison and s.get("condition") == condition and s.get("kind") == "measured" \
                and not s.get("excluded"):
            groups[s["pair"]][s["arm"]] = t
    deltas, ta, td, excluded = [], [], [], []
    for pid in sorted(groups):
        g = groups[pid]
        reasons = {arm: (validity(g[arm]) if arm in g else ["missing"]) for arm in ("A", "D")}
        if max_load1 is not None and any((_load1(g[a]["summary"]) or 0) > max_load1 for a in g):
            reasons.setdefault("load", ["loadavg1_above_limit"])
        if any(reasons.values()):
            excluded.append({"pair": pid, "reasons": {k: v for k, v in reasons.items() if v}})
            continue
        a, d = decompose_d(g["A"])["T_ms"], decompose_d(g["D"])["T_ms"]
        ta.append(a)
        td.append(d)
        deltas.append(d - a)
    a_med = B.median(ta)
    return {"comparison": comparison, "condition": condition, "pairs_seen": len(groups), "pairs_valid": len(deltas),
            "excluded_pairs": excluded, "deltas_ms": deltas, "A_median_ms": a_med, "D_median_ms": B.median(td),
            "A_p95_ms": B.p95(ta), "D_p95_ms": B.p95(td), "verdict": verdict(deltas, a_med)}


def disposition(verdicts: dict[str, dict[str, Any]] | None, zero: dict[str, dict[str, int]],
                decisions_deleted: float | None) -> dict[str, str]:
    if not verdicts:
        return {"disposition": "BLOCKED", "basis": "no REAL CMP-D pairs (evidence incomplete, decision table last row)"}
    dz = zero.get("D", {})
    bad = {k: dz.get(k, 0) for k in D_REQUIRED_ZERO if dz.get(k, 0)}
    if bad:
        return {"disposition": "REVISE D (missing dependency fact); no promotion", "basis": json.dumps(bad, sort_keys=True)}
    vs = [v.get("verdict") for v in verdicts.values()]
    if vs and all(v == "MEANINGFUL" for v in vs):
        return {"disposition": "PRIORITIZE checked continuation under #93 R2-07; do not credit the cache",
                "basis": "MEANINGFUL in every primary condition"}
    if decisions_deleted:
        return {"disposition": "REPORT_WORK_DELETED; live value BLOCKED pending owner budget (R2-03/R2-10 own it)",
                "basis": f"decisions deleted per task = {decisions_deleted}; wall-clock verdicts {vs}"}
    return {"disposition": "INCONCLUSIVE", "basis": f"verdicts {vs}"}


# ── controls ──────────────────────────────────────────────────────────────────

def controls_table(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in trials:
        s = t["summary"]
        if s.get("kind") == "control" and not s.get("excluded"):
            groups[(s["control"], s["arm"])].append(t)
    rows = []
    for (cid, arm), ts in sorted(groups.items()):
        cs = [counts(t) for t in ts]
        rows.append({
            "control": cid, "arm": arm, "n": len(ts),
            "runner_outcomes": dict(Counter(t["summary"].get("outcome") for t in ts)),
            "oracle_verified": sum(1 for t in ts if oracle_satisfied(t["summary"])),
            "guard": dict(Counter(f"{g['status']}:{g['reason']}" for c in cs for g in c["guard"])),
            "submits": [c["journal_submits"] for c in cs],
            "wrong_target_submits": [c["wrong_target_submits"] for c in cs],
            "detached_clicks": [c["detached_clicks"] for c in cs],
            "action_error_codes": dict(Counter(e.get("code") for t in ts for e in t["events"]
                                               if e["event"] == "call_return" and e.get("tool") in MUTATION_TOOLS
                                               and not e.get("ok"))),
            "mutation_refusals": dict(Counter(f"{r['label']}:{r['code']}:{r['effect']}:ok={r['ok']}"
                                              for c in cs for r in c["mutation_refusals"])),
            "probe_codes": dict(Counter((t["summary"].get("probe") or {}).get("code") for t in ts
                                        if t["summary"].get("probe"))),
            "fault_fired": sum(1 for t in ts if (t["summary"].get("fault") or {}).get("fired")),
            "clicks_after_fault": [(t["summary"].get("fault") or {}).get("clicks_after_fault") for t in ts
                                   if t["summary"].get("fault")],
            "decisions": [c["decisions"] for c in cs],
        })
    return rows


# ── #10 ledger row ────────────────────────────────────────────────────────────

def ledger_row(trial: dict[str, Any], lane: str) -> dict[str, Any]:
    """kvnloo/cua#10 task x arm x trial ledger row (PREREG ledger_format)."""
    s = trial["summary"]
    oracle = decompose_d(trial)
    runner = decompose_d(trial, end="runner")
    c = counts(trial)
    return {
        "lane": lane, "trial": s.get("trial"), "task": "jev-use FixtureFormTask fill->submit",
        "comparison": s.get("comparison"), "condition": s.get("condition"), "cohort": s.get("cohort"),
        "regime": s.get("regime"), "block": s.get("block"), "pair": s.get("pair"), "order": s.get("order"),
        "arm": s.get("arm"), "control": s.get("control"), "excluded": s.get("excluded"),
        "evidence": s.get("evidence"), "chooser": s.get("chooser"), "binary_sha256": s.get("binary_sha256"),
        "caller_tree": s.get("caller_tree"), "token_sha16": s.get("token_sha16"), "token_len": s.get("token_len"),
        "outcome": s.get("outcome"), "oracle_verified": oracle_satisfied(s), "validity": validity(trial),
        "decision_routes": c["decision_routes"], "guard": c["guard"], "counts": c,
        "T_oracle_ms": None if oracle is None else oracle["T_ms"],
        "T_runner_ms": None if runner is None else runner["T_ms"],
        "spans10": None if oracle is None else oracle["spans10"],
        "coverage": None if oracle is None else oracle["coverage"],
        "cleanup": cleanup_spans(trial), "resources": s.get("resources"),
        "loadavg_before": s.get("loadavg_before"), "loadavg_after": s.get("loadavg_after"),
        "psi_before": s.get("psi_before"), "psi_after": s.get("psi_after"), "lock_label": s.get("lock_label"),
        "probe": s.get("probe"), "fault": None if not s.get("fault") else {
            k: s["fault"].get(k) for k in ("mode", "fired", "clicks_after_fault")},
    }

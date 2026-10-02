"""B-02 browser blocks (fix round): measured A/B, controls, smoke, shakedowns. Standard library only.

Rules: PREREG.json (blocked_blocks_as_specified, now run) + PREREG-AMENDMENT-1.json
(taxonomy extension, localized components, moved work, W decision rule). B-01's
b01_analysis is used verbatim for the decomposition and statistics; the B-02 marks it does
not know are mapped as the amendment pre-specifies.
"""

from __future__ import annotations

import json
import statistics
import tarfile
from pathlib import Path
from typing import Any

import b01_analysis as B

CLASSES = ["fill", "toggle", "modal"]
ARMS = ["K5", "K5E", "K5V", "K5EV"]
E_ARMS = {"K5E", "K5EV"}
V_ARMS = {"K5V", "K5EV"}
THRESH_MS, THRESH_SHARE = 50.0, 0.05

# ── taxonomy extension (PREREG-AMENDMENT-1 pre_specified_analysis_details) ──
_PRE_ADMISSION = {"mcp.parsed", "mcp.session_validated", "mcp.tools_list_built", "mcp.admission_validated"}
_PRE_INNER = {"mcp.identity_applied", "mcp.session_begun", "mcp.timer_started", "mcp.inner_classified",
              "mcp.inner_tools_list_built", "mcp.inner_validation_skipped"}
_b01_classify = B.classify_mark


def classify_mark(left: str, tool: str) -> tuple[str, str | None]:
    if left.startswith("ep."):
        return "revalidate", "reval_endpoint"
    if left in _PRE_ADMISSION:
        return "driver_pre_dispatch", "pre_admission_validate"
    if left in _PRE_INNER:
        return "driver_pre_dispatch", "pre_inner_validate"
    return _b01_classify(left, tool)


B.classify_mark = classify_mark  # decompose() looks the name up at call time


def bundle(raw: Path, block: str) -> dict[str, str]:
    files: dict[str, str] = {}
    tgz = raw / f"{block}-trials.tar.gz"
    if tgz.exists():
        with tarfile.open(tgz, "r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name.endswith(".jsonl"):
                    files[Path(m.name).name] = tar.extractfile(m).read().decode()
    return files


def load(raw: Path, block: str) -> list[dict[str, Any]]:
    files = bundle(raw, block)
    out = []
    for name in sorted(files):
        if name.endswith("driver-trace.jsonl"):
            continue
        lines = [json.loads(x) for x in files[name].splitlines() if x.strip()]
        s = lines[-1]
        trace_text = files.get(Path(s["driver_trace"]).name, "") if s.get("driver_trace") else ""
        trace = [json.loads(x) for x in trace_text.splitlines() if x.strip()]
        out.append({"name": s["trial"], "summary": s, "events": lines[:-1], "trace": trace, "block": block})
    return out


def as_k5(t: dict[str, Any]) -> dict[str, Any]:
    return {**t, "summary": {**t["summary"], "arm": "K5"}}


def windows(t: dict[str, Any]) -> list[dict[str, Any]]:
    return B._windows(t["events"])


def tool_calls(t: dict[str, Any], lo: int | None = None, hi: int | None = None) -> list[list[str]]:
    """Phase sequences of each admitted tools/call (mcp.line_read .. mcp.written), optionally inside [lo, hi]."""
    out, cur = [], None
    for m in t["trace"]:
        if m["phase"] == "mcp.line_read":
            cur = [m]
        elif cur is not None:
            cur.append(m)
            if m["phase"] == "mcp.written":
                if any(x["phase"] == "mcp.admission_validated" for x in cur):
                    if lo is None or (lo <= cur[0]["t_mono_ns"] <= hi):
                        out.append([x["phase"] for x in cur])
                cur = None
    return out


def knob_path(t: dict[str, Any], T0: int, T1: int) -> list[str]:
    """Forced path of the B-02 knobs, from the Driver's own marks."""
    arm = t["summary"]["arm"]
    bad = []
    calls = tool_calls(t, T0, T1)
    if not calls:
        bad.append("no_tool_calls_in_T")
    skipped = [("mcp.inner_validation_skipped" in c) for c in calls]
    built = [("mcp.inner_tools_list_built" in c) for c in calls]
    if arm in V_ARMS and not (all(skipped) and not any(built)):
        bad.append("V_not_taken")
    if arm not in V_ARMS and (any(skipped) or not all(built)):
        bad.append("V_mark_in_unset_arm")
    phases = [m["phase"] for m in t["trace"]]
    in_t = [m["phase"] for m in t["trace"] if T0 <= m["t_mono_ns"] <= T1]
    reval = sum(1 for p in in_t if p == "reval.native_window")
    hits = sum(1 for p in in_t if p == "ep.bound_hit")
    if arm in E_ARMS:
        if "ep.bound_stored" not in phases:
            bad.append("E_not_seeded")
        if hits != reval or any(p == "ep.bound_miss" for p in in_t):
            bad.append(f"E_hits={hits}/reval={reval}")
    elif any(p.startswith("ep.bound_") for p in phases):
        bad.append("E_mark_in_unset_arm")
    return bad


def n_e3(t: dict[str, Any]) -> bool | None:
    """A fresh Driver process runs the full proof (ep.json_version) before any ep.bound_hit."""
    phases = [m["phase"] for m in t["trace"]]
    if "ep.bound_hit" not in phases:
        return None
    return "ep.json_version" in phases and phases.index("ep.json_version") < phases.index("ep.bound_hit")


def trial_row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    reasons = []
    if not s.get("oracle_exact_match"):
        reasons.append("oracle_not_satisfied")
    if s.get("completion_mutations") != 1:
        reasons.append(f"completion_mutations={s.get('completion_mutations')}")
    if s.get("outcome") != "verified":
        reasons.append(f"runner_outcome={s.get('outcome')}")
    reasons += B.forced_path(as_k5(t))
    d = B.decompose(as_k5(t))
    if d is None:
        reasons.append("T_undefined")
    else:
        reasons += knob_path(t, d["T0_ns"], d["T0_ns"] + int(d["T_runner_ms"] * 1e6))
    if d is not None and d["T_oracle_ms"] is None:
        reasons.append("T_oracle_undefined")
    bind = next((w for w in windows(t) if w["label"] == "bind"), None)
    row = {"trial": t["name"], "cls": s["cls"], "arm": s["arm"], "round": s.get("round"), "valid": not reasons,
           "reasons": reasons, "loadavg_1m": float(s["loadavg_before"].split()[0])
           if s.get("loadavg_before", "unavailable") != "unavailable" else None}
    if d is not None:
        sub = d["sub"]
        row.update({
            "T_oracle_ms": d["T_oracle_ms"], "T_runner_ms": d["T_runner_ms"],
            "bind_ms": None if bind is None else (bind["t1"] - bind["t0"]) / 1e6,
            "endpoint_ms": sub.get("reval_endpoint", 0.0),
            "admission_ms": sub.get("pre_admission_validate", 0.0) + sub.get("pre_inner_validate", 0.0),
            "first_snapshot_excess_ms": (d["observations"][0] - d["observations"][1])
            if len(d["observations"]) >= 2 else None,
            "components": d["components"], "sub": sub, "coverage": d["coverage"]})
        if row["bind_ms"] is not None and d["T_oracle_ms"] is not None:
            row["bind_plus_T_oracle_ms"] = row["bind_ms"] + d["T_oracle_ms"]
    return row


def med(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def paired(rows: list[dict[str, Any]], a: str, b: str, key: str) -> dict[str, Any]:
    ra = {r["round"]: r[key] for r in rows if r["arm"] == a and r["valid"] and r.get(key) is not None}
    rb = {r["round"]: r[key] for r in rows if r["arm"] == b and r["valid"] and r.get(key) is not None}
    rounds = sorted(set(ra) & set(rb))
    out = B.paired_diff([ra[r] for r in rounds], [rb[r] for r in rounds])
    out["rounds_dropped"] = sorted((set(ra) | set(rb)) - set(rounds))
    return out


def ratio(rows: list[dict[str, Any]], a: str, b: str, key: str = "T_oracle_ms") -> dict[str, Any]:
    ra = {r["round"]: r[key] for r in rows if r["arm"] == a and r["valid"]}
    rb = {r["round"]: r[key] for r in rows if r["arm"] == b and r["valid"]}
    rounds = sorted(set(ra) & set(rb))
    xa, xb = [ra[r] for r in rounds], [rb[r] for r in rounds]

    def stat(idx: list[int]) -> float | None:
        den = statistics.median([xb[i] for i in idx])
        return None if not den else statistics.median([xa[i] for i in idx]) / den

    return {"n": len(rounds), "S": stat(list(range(len(rounds)))) if rounds else None,
            "ci95": B.boot_ci(len(rounds), stat)}


def arm_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    v = [r for r in rows if r["valid"]]
    comps = {c: [r["components"][c] for r in v] for c in B.COMPONENTS}
    subs = sorted({k for r in v for k in r["sub"]})
    meanT = mean([r["T_runner_ms"] for r in v])
    return {
        "n": len(rows), "valid": len(v), "failures": [{"trial": r["trial"], "reasons": r["reasons"]}
                                                      for r in rows if not r["valid"]],
        "T_oracle_ms": {"median": med([r["T_oracle_ms"] for r in v]), "p95": B.p95([r["T_oracle_ms"] for r in v]),
                        "mean": mean([r["T_oracle_ms"] for r in v])},
        "T_runner_ms": {"median": med([r["T_runner_ms"] for r in v]), "mean": meanT},
        "bind_ms_median": med([r["bind_ms"] for r in v]),
        "bind_plus_T_oracle_ms_median": med([r.get("bind_plus_T_oracle_ms") for r in v]),
        "endpoint_ms_median": med([r["endpoint_ms"] for r in v]),
        "admission_ms_median": med([r["admission_ms"] for r in v]),
        "first_snapshot_excess_ms_median": med([r["first_snapshot_excess_ms"] for r in v]),
        "components_mean_ms": {c: mean(x) for c, x in comps.items()},
        "shares": {c: (mean(x) / meanT) if (x and meanT) else None for c, x in comps.items()},
        "sub_mean_ms": {k: mean([r["sub"].get(k, 0.0) for r in v]) for k in subs},
        "coverage_min": min([r["coverage"] for r in v]) if v else None,
        "loadavg_1m_range": [min(r["loadavg_1m"] for r in rows), max(r["loadavg_1m"] for r in rows)] if rows else None,
    }


# ── controls ──
def call_window(t: dict[str, Any], label: str) -> tuple[int, int] | None:
    s = [e["t_mono_ns"] for e in t["events"] if e["event"] == "call_send" and e.get("label") == label]
    r = [e["t_mono_ns"] for e in t["events"] if e["event"] == "call_return" and e.get("label") == label]
    return (s[0], r[0]) if s and r else None


def driver_phases_in(t: dict[str, Any], w: tuple[int, int] | None) -> list[str]:
    if w is None:
        return []
    return [m["phase"] for m in t["trace"] if w[0] <= m["t_mono_ns"] <= w[1]
            and not m["phase"].startswith(("mcp.", "sdk.", "rt."))]


DISPATCH = ("click.ref_resolved", "click.cdp_send", "type.ref_resolved", "type.insert_send")


def controls(trials: list[dict[str, Any]], nv_ref: dict[str, str] | None) -> dict[str, Any]:
    by_kind: dict[str, list] = {}
    for t in trials:
        by_kind.setdefault(t["summary"]["kind"], []).append(t)
    out: dict[str, Any] = {}

    rows = []
    for t in by_kind.get("ne1", []):
        s = t["summary"]
        env = s.get("takeover_envelope") or {}
        ph = driver_phases_in(t, call_window(t, "takeover_action"))
        rows.append({"trial": t["name"], "cls": s["cls"], "arm": s["arm"], "code": env.get("code"),
                     "effect": env.get("effect"), "decoy_started": s.get("decoy_connections") is not None,
                     "decoy_connections": s.get("decoy_connections"), "decoy_requests": s.get("decoy_requests"),
                     "completion_mutations": s.get("completion_mutations"),
                     "last_reval_mark": next((p for p in reversed(ph) if p.startswith("reval.")), None),
                     "endpoint_step_reached": "reval.native_window" in ph, "dispatch_marks": sum(p in DISPATCH for p in ph),
                     "error": s.get("error")})
    k5_codes = {r["code"] for r in rows if r["arm"] == "K5"}
    for r in rows:
        r["pass"] = (r["effect"] == "refused" and r["decoy_started"] and r["decoy_connections"] == 0
                     and r["completion_mutations"] == 0 and r["dispatch_marks"] == 0 and len(k5_codes) == 1
                     and r["code"] in k5_codes)
    out["N-E1"] = {"n": len(rows), "pass": sum(r["pass"] for r in rows),
                   "per_arm": {a: {"n": sum(r["arm"] == a for r in rows), "pass": sum(r["pass"] for r in rows if r["arm"] == a),
                                   "codes": sorted({str(r["code"]) for r in rows if r["arm"] == a}),
                                   "refusing_layer": sorted({str(r["last_reval_mark"]) for r in rows if r["arm"] == a}),
                                   "decoy_connections_total": sum(r["decoy_connections"] or 0 for r in rows if r["arm"] == a)}
                               for a in sorted({r["arm"] for r in rows})}, "rows": rows}

    rows = []
    for t in by_kind.get("ne2", []):
        s = t["summary"]
        env = s.get("old_binding_envelope") or {}
        w_old = call_window(t, "old_binding_action")
        ph_old = driver_phases_in(t, w_old)
        restart = next((e["t_mono_ns"] for e in t["events"] if e["event"] == "call_send" and e.get("label") == "prepare_restart"), None)
        after = [m for m in t["trace"] if restart is not None and m["t_mono_ns"] >= restart]
        before = [m for m in t["trace"] if restart is None or m["t_mono_ns"] < restart]
        old_ports = {(m.get("detail") or {}).get("port") for m in before if m["phase"] in ("ep.bound_stored", "ep.bound_hit")}
        after_ph = [m["phase"] for m in after]
        new_hits = [(m.get("detail") or {}).get("port") for m in after if m["phase"] == "ep.bound_hit"]
        full_first = ("ep.json_version" in after_ph and ("ep.bound_hit" not in after_ph or
                      after_ph.index("ep.json_version") < after_ph.index("ep.bound_hit")))
        row = {"trial": t["name"], "cls": s["cls"], "arm": s["arm"], "old_code": env.get("code"), "old_effect": env.get("effect"),
               "old_last_reval_mark": next((p for p in reversed(ph_old) if p.startswith("reval.")), None),
               "old_dispatch_marks": sum(p in DISPATCH for p in ph_old), "new_pid": s.get("restart_new_pid"),
               "full_proof_after_restart_before_any_hit": full_first,
               "old_port_hit_after_restart": any(p in old_ports for p in new_hits),
               "outcome": s.get("outcome"), "completion_mutations": s.get("completion_mutations"),
               "oracle": s.get("oracle_exact_match"), "error": s.get("error")}
        row["pass"] = (row["old_effect"] == "refused" and row["old_dispatch_marks"] == 0 and row["new_pid"] is True
                       and full_first and not row["old_port_hit_after_restart"] and row["outcome"] == "verified"
                       and row["completion_mutations"] == 1 and row["oracle"] is True)
        rows.append(row)
    out["N-E2"] = {"n": len(rows), "pass": sum(r["pass"] for r in rows),
                   "per_arm": {a: {"n": sum(r["arm"] == a for r in rows), "pass": sum(r["pass"] for r in rows if r["arm"] == a),
                                   "old_codes": sorted({str(r["old_code"]) for r in rows if r["arm"] == a}),
                                   "refusing_layer": sorted({str(r["old_last_reval_mark"]) for r in rows if r["arm"] == a})}
                               for a in sorted({r["arm"] for r in rows})}, "rows": rows}

    rows = []
    for t in by_kind.get("stale_ref", []):
        s = t["summary"]
        env = s.get("stale_envelope") or {}
        ph = driver_phases_in(t, call_window(t, "stale_click"))
        code = (env.get("error") or {}).get("code") if isinstance(env.get("error"), dict) else env.get("code")
        rows.append({"trial": t["name"], "cls": s["cls"], "arm": s["arm"], "effect": env.get("effect"), "code": code,
                     "dispatch_marks": sum(p in DISPATCH for p in ph), "completion_mutations": s.get("completion_mutations"),
                     "pass": env.get("effect") == "refused" and code == "browser_ref_stale"
                     and s.get("completion_mutations") == 0 and sum(p in DISPATCH for p in ph) == 0})
    out["N-W1"] = {"n": len(rows), "pass": sum(r["pass"] for r in rows),
                   "per_arm_class": {f"{c}:{a}": sum(r["pass"] for r in rows if r["cls"] == c and r["arm"] == a)
                                     for c in CLASSES for a in ARMS if any(r["cls"] == c and r["arm"] == a for r in rows)},
                   "stale_ref_dispatches": sum(1 for r in rows if r["dispatch_marks"] != 0), "rows": rows}

    rows = []
    for t in by_kind.get("nw2", []):
        s = t["summary"]
        env = s.get("nw2_stale_envelope") or {}
        ph = driver_phases_in(t, call_window(t, "stale_dom_action"))
        row = {"trial": t["name"], "cls": s["cls"], "arm": s["arm"], "dom_replace": s.get("dom_replace"),
               "marker_in_stale_snapshot": s.get("marker_in_stale_snapshot"),
               "marker_in_fresh_snapshot": s.get("marker_in_fresh_snapshot"),
               "stale_action_effect": env.get("effect"), "stale_action_code": env.get("code"),
               "stale_action_dispatch_marks": sum(p in DISPATCH for p in ph),
               "stale_action_mutations": s.get("nw2_mutations_from_stale_action"),
               "fresh_candidate": s.get("nw2_fresh_candidate"), "outcome": s.get("outcome"),
               "completion_mutations": s.get("completion_mutations"), "oracle": s.get("oracle_exact_match"),
               "error": s.get("error")}
        row["fresh_reflects_replacement"] = (row["dom_replace"] == "replaced" and row["marker_in_fresh_snapshot"] is True
                                             and row["marker_in_stale_snapshot"] is False)
        row["pass"] = (row["fresh_reflects_replacement"] and row["outcome"] == "verified"
                       and row["completion_mutations"] == 1 and row["oracle"] is True)
        rows.append(row)
    out["N-W2"] = {"n": len(rows), "pass": sum(r["pass"] for r in rows),
                   "per_arm": {a: {"n": sum(r["arm"] == a for r in rows), "pass": sum(r["pass"] for r in rows if r["arm"] == a),
                                   "stale_action": sorted({f"{r['cls']}:{r['stale_action_effect']}:dispatch={r['stale_action_dispatch_marks']}:mutations={r['stale_action_mutations']}"
                                                           for r in rows if r["arm"] == a})}
                               for a in sorted({r["arm"] for r in rows})}, "rows": rows}

    recs = [t["summary"] for t in by_kind.get("nv", [])]
    keys = sorted({k for r in recs for k in r["replies"]})
    cases = {k: {"distinct": len({r["replies"].get(k) for r in recs}),
                 "equals_nv_block": None if nv_ref is None else all(r["replies"].get(k) == nv_ref.get(k) for r in recs)}
             for k in keys}
    out["N-V_browser_runner"] = {"n": len(recs), "by_arm": {a: sum(r["arm"] == a for r in recs) for a in sorted({r["arm"] for r in recs})},
                                 "cases": cases, "pass": bool(recs) and all(c["distinct"] == 1 and c["equals_nv_block"] is not False
                                                                            for c in cases.values())}
    return out


def e_trials_n_e3(groups: list[list[dict[str, Any]]]) -> dict[str, Any]:
    vals = [(t["name"], n_e3(t)) for g in groups for t in g if t["summary"]["arm"] in E_ARMS]
    applicable = [v for _, v in vals if v is not None]
    return {"e_arm_trials": len(vals), "with_bound_hit": len(applicable), "full_proof_first": sum(applicable),
            "pass": bool(applicable) and all(applicable)}


def smoke(trials: list[dict[str, Any]]) -> dict[str, Any]:
    knob_marks = sum(1 for t in trials for m in t["trace"]
                     if m["phase"].startswith("ep.bound_") or m["phase"] == "mcp.inner_validation_skipped")
    ver = sum(1 for t in trials if t["summary"].get("outcome") == "verified" and t["summary"].get("oracle_exact_match")
              and t["summary"].get("completion_mutations") == 1)
    return {"n": len(trials), "verified": ver, "knob_marks": knob_marks,
            "full_proof_every_mutation": all(
                sum(1 for m in t["trace"] if m["phase"] == "reval.native_window")
                <= sum(1 for m in t["trace"] if m["phase"] == "ep.json_version") for t in trials),
            "pass": len(trials) == 5 and ver == 5 and knob_marks == 0}

#!/usr/bin/env python3
"""B-07 analysis: recompute every number from raw/ (standard library only).

Rules are the ones in PREREG.json and PREREG-AMENDMENT-1.json. The R2-10 component view uses R2-10R's
own code (harness/r2-10r/analyze_r2_10.py, b01_analysis, analyze_browser; byte-identical copies from
c183b95e3); the sub-span view uses B-05's harness/b05/b05_spans.py (byte-identical from a91a86a4a);
the cold-excess estimator is B-04's harness/b04/b04_rows.py (byte-identical from 8620ebfa2).

usage: analyze_b07.py [--raw raw] [--out b07-summary.json]
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
H = HERE / "harness"
sys.path[:0] = [str(H / "b05"), str(H / "b04"), str(H / "r2-10r" / "src" / "b-02-browser-driver-sites-2026-10-02"),
                str(H / "r2-10r")]
import b01_analysis as B  # noqa: E402
import analyze_browser as AB  # noqa: E402,F401  (installs the B-02 classifier on B)
import analyze_r2_10 as A  # noqa: E402
import b05_spans as SP  # noqa: E402
import b04_rows as B4  # noqa: E402

SEED = 20261003
BOOT = 10000
CLASSES = ["fill", "toggle", "modal"]
GATE_MS = 0.5
STALL_MS = 20.0
V_ENV, SETTLE_ENV = "CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE", "CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS"
TRACE_ONLY_REASONS = {"settle=[]", "click_without_cdp_send", "V_not_taken"}
LANE_SCOPE = {"mcp_transport", "mcp_admission", "resolution", "client_validation"}
GROUPS = {
    "transport_in_out": SP.CALLER_IN + SP.PIPES + SP.DRIVER_IN + SP.DRIVER_OUT
    + [x for x in SP.CALLER_OUT if x != "c_out.validate"],
    "admission_residual": SP.ADMISSION,
    "resolution": SP.RESOLUTION,
    "client_validation": ["c_out.validate"],
}
# B-05's verdict units (its floor keys), reused without floors.
UNITS = {
    "c_in.prep": ["c_in.prep"], "c_in.serialize": ["c_in.serialize"], "write_pipe_in": ["c_in.write", "pipe_in"],
    "pipe_out_frame": ["pipe_out", "c_out.frame"], "c_out.parse": ["c_out.parse"], "c_out.route": ["c_out.route"],
    "c_out.result_model": ["c_out.result_model"], "c_out.validate": ["c_out.validate"], "c_out.return": ["c_out.return"],
    "d_in.parse": ["d_in.parse"], "adm.outer": ["adm.outer"], "adm.inner": ["adm.inner"], "d_in.invoke": ["d_in.invoke"],
    "d_out.post": ["d_out.post"], "d_out.serialize": ["d_out.serialize"], "d_out.write_flush": ["d_out.write", "d_out.flush"],
}
B05_TERMINAL = {"c_out.parse": "IRREDUCIBLE (candidate failed, B-05 PARSE_FAST KILL)",
                "c_out.validate": "IRREDUCIBLE (candidate failed, B-05 VALIDATE_FAST KILL)"}
CDP_INVARIANT = {"res.frame_proof": "Page.getFrameTree re-proves the ref's frame identity at dispatch",
                 "res.cdp_node_resolve": "DOM.resolveNode: the live node (FIX-01 detached-node refusal) and its objectId",
                 "res.type_focus": "DOM.focus: trusted_input typing goes to the focused element",
                 "res.editable_check": "Runtime.callFunctionOn: non-editable targets are refused before typing"}
CANDIDATE_TARGET = {"PREP_FAST": "c_in.prep", "ROUTE_FAST": "c_out.route", "POST_FAST": "d_out.post"}
WORK_METRIC = {"PREP_FAST": "prep_ms", "ROUTE_FAST": "route_ms", "POST_FAST": "driver_window_ms"}
POST_FAST_ENV = "CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM"


# ── statistics ────────────────────────────────────────────────────────────────
def mean(xs: list[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


def boot_mean_ci(xs: list[float], seed: int = SEED) -> list[float] | None:
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    rng = random.Random(seed)
    n = len(xs)
    vals = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOT))
    return [vals[int(0.025 * BOOT)], vals[int(0.975 * BOOT) - 1]]


def stat(xs: list[float | None]) -> dict[str, Any]:
    v = [x for x in xs if x is not None]
    return {"n": len(v), "mean": mean(v), "ci95": boot_mean_ci(v), "median": statistics.median(v) if v else None}


def r(x: Any, nd: int = 4) -> Any:
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, list):
        return [r(y, nd) for y in x]
    if isinstance(x, dict):
        return {k: r(v, nd) for k, v in x.items()}
    return x


# ── loading ──────────────────────────────────────────────────────────────────
def read_tar(path: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile():
                name = m.name[2:] if m.name.startswith("./") else m.name
                out[name] = tar.extractfile(m).read()
    return out


def load_chunk(path: Path) -> dict[str, Any]:
    files = read_tar(path)
    trials, manifests = [], {}
    for name in sorted(files):
        if "run-manifest" in name and name.endswith(".json"):
            manifests[name] = json.loads(files[name])
        elif name.startswith("trials/") and name.endswith(".jsonl") and not name.endswith(".driver-trace.jsonl"):
            lines = [json.loads(x) for x in files[name].decode().splitlines() if x.strip()]
            if not lines or lines[-1].get("event") != "summary":
                continue
            s = lines[-1]
            tr = files.get(s["driver_trace"]) if s.get("driver_trace") else None
            trace = [json.loads(x) for x in tr.decode().splitlines() if x.strip()] if tr else []
            fr = files.get(f"frames/{s['trial']}.frames.jsonl.gz") if s.get("kind") == "n4a" else None
            frames = [json.loads(x) for x in gzip.decompress(fr).decode().splitlines() if x.strip()] if fr else []
            trials.append({"name": s["trial"], "summary": s, "events": lines[:-1], "trace": trace, "bundle": path.name,
                           "frames": frames})
    return {"trials": trials, "manifests": manifests}


# ── per trial ────────────────────────────────────────────────────────────────
def r210_trial(t: dict[str, Any], arm_as: str | None = None) -> dict[str, Any]:
    s = dict(t["summary"])
    if arm_as:
        s["arm"] = arm_as
    return {**t, "summary": s, "trace": SP.r210_view(t["trace"])}


def validity(t: dict[str, Any], type_route: str | None, knobs: dict[str, str], variant: dict[str, str]) -> dict[str, Any]:
    """R2-10 browser_row checks (COMP configuration) + marks/knob/caller-variant rules (PREREG forced path)."""
    s = t["summary"]
    marks_on = bool(t["trace"])
    row = A.browser_row(r210_trial(t, "COMP"), type_route)
    row["arm"] = s.get("arm")
    reasons = list(row["reasons"])
    if not marks_on:
        reasons = [x for x in reasons if x not in TRACE_ONLY_REASONS]
    env = s.get("driver_env_exp") or {}
    if bool(s.get("driver_env_trace_set")) != marks_on:
        reasons.append("trace_setting_mismatch")
    want = {V_ENV: "1", **knobs}
    if s.get("cls") == "fill":
        want[SETTLE_ENV] = "0"
    for k, v in want.items():
        if env.get(k) != v:
            reasons.append(f"knob:{k}={env.get(k)}")
    for k in env:
        if k not in want:
            reasons.append(f"extra_knob:{k}")
    cv = s.get("caller_variant") or {}
    for k, v in variant.items():
        if cv.get(k) != v:
            reasons.append(f"caller_variant:{k}={cv.get(k)}")
    counts = s.get("caller_variant_counts") or {}
    if variant.get("prep") == "fast" and not counts.get("prep_fast"):
        reasons.append("prep_fast_not_taken")
    if variant.get("route") == "fast" and not counts.get("route_fast"):
        reasons.append("route_fast_not_taken")
    if variant.get("prep", "default") == "default" and counts.get("prep_fast"):
        reasons.append("prep_fast_in_default_arm")
    if variant.get("route", "default") == "default" and counts.get("route_fast"):
        reasons.append("route_fast_in_default_arm")
    row["reasons"] = reasons
    row["valid"] = not reasons
    row["marks_on"] = marks_on
    row["caller_variant_counts"] = counts
    return row


def caller_windows(t: dict[str, Any]) -> list[dict[str, Any]]:
    """In-T call windows (B-05 decompose window rule) for the caller-stamp metrics."""
    events = t["events"]
    windows = B._windows(events)
    snap1 = next((w for w in windows if w["label"] == "snapshot1"), None)
    verified = next((e for e in events if e["event"] == "oracle_return" and e.get("outcome") == "verified"), None)
    if snap1 is None or verified is None:
        return []
    T0, T1 = snap1["t0"], verified["t_mono_ns"]
    return [w for w in windows if w["t1"] >= T0 and w["t0"] <= T1]


def caller_metrics(t: dict[str, Any]) -> dict[str, float | None]:
    """Work metrics from caller stamps (visible with marks off), summed over the in-T calls."""
    ws = caller_windows(t)
    if not ws:
        return {"prep_ms": None, "route_ms": None, "driver_window_ms": None}
    prep = route = drv = 0.0
    for w in ws:
        ev = sorted((e for e in t["events"] if w["t0"] <= e["t_mono_ns"] <= w["t1"]), key=lambda e: e["t_mono_ns"])
        first = {}
        for e in ev:
            first.setdefault(e["event"], e["t_mono_ns"])
        if "call_send" in first and "c.req_written" in first:
            prep += (first["c.req_written"] - first["call_send"]) / 1e6
        # every response in the window: c.parsed -> the next c.result_model_start
        parsed = [e["t_mono_ns"] for e in ev if e["event"] == "c.parsed"]
        rms = [e["t_mono_ns"] for e in ev if e["event"] == "c.result_model_start"]
        for p in parsed:
            nxt = next((x for x in rms if x >= p), None)
            if nxt is not None:
                route += (nxt - p) / 1e6
                break
        if "c.req_written" in first:
            fb = next((e["t_mono_ns"] for e in ev if e["event"] == "c.first_byte" and e["t_mono_ns"] >= first["c.req_written"]), None)
            if fb is not None:
                drv += (fb - first["c.req_written"]) / 1e6
    return {"prep_ms": prep, "route_ms": route, "driver_window_ms": drv}


def stalls(t: dict[str, Any]) -> list[dict[str, Any]]:
    """PREREG modal_stall: caller-side intervals (c_in.* / c_out.* by the B-05 left-point label) > 20 ms in T."""
    out = []
    for w in caller_windows(t):
        pts = sorted([(e["t_mono_ns"], "C", e["event"]) for e in t["events"] if w["t0"] <= e["t_mono_ns"] <= w["t1"]]
                     + [(m["t_mono_ns"], "D", m["phase"]) for m in t["trace"] if w["t0"] <= m["t_mono_ns"] <= w["t1"]],
                     key=lambda p: (p[0], 0 if p[1] == "C" else 1))
        for (ta, src, name), (tb, _s, _n) in zip(pts, pts[1:]):
            if src != "C":
                continue
            lab = SP.C_LABEL.get(name, "c_other")
            if lab.startswith(("c_in.", "c_out.")) and (tb - ta) / 1e6 > STALL_MS:
                out.append({"label": lab, "tool": w["tool"], "call": w["label"], "t0": ta, "t1": tb, "ms": (tb - ta) / 1e6})
    gcs = t["summary"].get("gc_events") or []
    pairs, start = [], {}
    for phase, gen, ts in gcs:
        if phase == "start":
            start[gen] = ts
        elif phase == "stop" and gen in start:
            pairs.append((start.pop(gen), ts, gen))
    for s in out:
        ov = sum(max(0, min(s["t1"], b) - max(s["t0"], a)) for a, b, _g in pairs)
        s["gc_overlap_ms"] = ov / 1e6
        s["class"] = "GC" if ov >= 0.5 * (s["t1"] - s["t0"]) else "scheduler/other"
        s["loadavg_1m"] = t["summary"].get("loadavg_before")
        del s["t0"], s["t1"]
    return out


def cold_excess(t: dict[str, Any]) -> float | None:
    """B-04's E: span(snapshot1) - span(snapshot2) (b04_rows.windows + snap_measures)."""
    if not t["trace"]:
        return None
    w = B4.windows(t)
    m1, m2 = B4.snap_measures(t["trace"], w.get("snapshot1")), B4.snap_measures(t["trace"], w.get("snapshot2"))
    if m1.get("span_ms") is None or m2.get("span_ms") is None:
        return None
    return m1["span_ms"] - m2["span_ms"]


def analyse_trial(t: dict[str, Any], type_route: str | None, c_m_ms: float, knobs: dict[str, str],
                  variant: dict[str, str]) -> dict[str, Any]:
    row = validity(t, type_route, knobs, variant)
    s = t["summary"]
    row.update({"order": s.get("order"), "block": s.get("block"), "layer": s.get("layer"), "round": s.get("round"),
                "loadavg_1m": row.get("loadavg_1m", s.get("loadavg_before"))})
    if not row.get("verified"):
        return row
    row.update(caller_metrics(t))
    if not t["trace"]:
        return row
    d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, c_m_ms)
    if d is None:
        return row
    row["b05"] = {k: d[k] for k in ("sub", "sub_corr", "by_comp", "by_comp_corr", "n_marks_in_T", "T_runner_corr_ms")}
    row["null_us"] = d["null_us"]
    row["calls"] = [{"label": c["label"], "tool": c["tool"], "sub": c["sub"], "left_marks": c["left_marks"]} for c in d["calls"]]
    d210 = B.decompose(r210_trial(t))
    if d210:
        e2 = A.e2_components(d210)
        mine = {k: sum(v.values()) for k, v in d["by_comp"].items()}
        keys = set(e2) | set(mine)
        row["consistency_max_abs_ms"] = max(abs(e2.get(k, 0.0) - mine.get(k, 0.0)) for k in keys)
        row["r210_components"] = e2
        row["r210_coverage"] = d210["coverage"]
    other = sum(v for k, v in d["sub"].items() if k.startswith("other.") or k == "c_other")
    row["coverage_b05"] = 1 - other / d["T_runner_ms"] if d["T_runner_ms"] else None
    row["coverage_ok"] = row["coverage_b05"] is not None and row["coverage_b05"] >= 0.98
    row["n_calls_in_T"] = len(d["calls"])
    row["stalls"] = stalls(t)
    row["cold_excess_ms"] = cold_excess(t)
    return row


def per_class_rows(rows: list[dict[str, Any]], cls: str) -> list[dict[str, Any]]:
    return [x for x in rows if x["cls"] == cls and x["valid"] and x.get("b05") and x.get("coverage_ok")]


# ── phase summaries ──────────────────────────────────────────────────────────
def phase_a_summary(rows: list[dict[str, Any]], c_m: float) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows), "valid": sum(1 for x in rows if x["valid"]),
                           "verified": sum(1 for x in rows if x["verified"]),
                           "invalid": [{"trial": x["trial"], "reasons": x["reasons"]} for x in rows if not x["valid"]],
                           "coverage_below_0_98": [x["trial"] for x in rows if x["valid"] and x.get("b05") and not x.get("coverage_ok")],
                           "consistency_max_abs_ms": max((x.get("consistency_max_abs_ms", 0.0) for x in rows), default=None),
                           "coverage_b05_min": min((x["coverage_b05"] for x in rows if x.get("coverage_b05") is not None), default=None),
                           "coverage_r210_min": min((x["r210_coverage"] for x in rows if x.get("r210_coverage") is not None), default=None),
                           "loadavg_1m": stat([x["loadavg_1m"] for x in rows]), "by_class": {}}
    for cls in CLASSES:
        v = per_class_rows(rows, cls)
        if not v:
            continue
        T = stat([x["T_runner_ms"] for x in v])
        Tc = stat([x["b05"]["T_runner_corr_ms"] for x in v])
        subs = sorted({k for x in v for k in x["b05"]["sub"]})
        table = {}
        for k in subs:
            raw_ = stat([x["b05"]["sub"].get(k, 0.0) for x in v])
            cor = stat([x["b05"]["sub_corr"].get(k, 0.0) for x in v])
            table[k] = {"raw": raw_, "corr": cor, "share_raw": raw_["mean"] / T["mean"], "share_corr": cor["mean"] / Tc["mean"],
                        "left_marks_per_task": mean([sum(c["left_marks"].get(k, 0) for c in x["calls"]) for x in v])}
        units = {u: {"members": m, "corr": stat([sum(x["b05"]["sub_corr"].get(k, 0.0) for k in m) for x in v]),
                     "raw": stat([sum(x["b05"]["sub"].get(k, 0.0) for k in m) for x in v])} for u, m in UNITS.items()}
        groups = {}
        for g, members in GROUPS.items():
            raw_ = stat([sum(x["b05"]["sub"].get(k, 0.0) for k in members) for x in v])
            cor = stat([sum(x["b05"]["sub_corr"].get(k, 0.0) for k in members) for x in v])
            groups[g] = {"raw": raw_, "corr": cor, "share_raw": raw_["mean"] / T["mean"], "share_corr": cor["mean"] / Tc["mean"],
                         "instrumentation_share_at_c_m": (raw_["mean"] - cor["mean"]) / raw_["mean"] if raw_["mean"] else None}
        comps = sorted({k for x in v for k in x["r210_components"]})
        r210 = {k: {"mean_ms": mean([x["r210_components"].get(k, 0.0) for x in v]),
                    "corr_mean_ms": mean([sum(x["b05"]["by_comp_corr"].get(k, {}).values()) for x in v])} for k in comps}
        for k in r210:
            r210[k]["share_raw"] = r210[k]["mean_ms"] / T["mean"]
            r210[k]["share_corr"] = r210[k]["corr_mean_ms"] / Tc["mean"]
        st = [x for x in v if x["stalls"]]
        nost = [x for x in v if not x["stalls"]]
        out["by_class"][cls] = {
            "n": len(v), "T_runner_ms": T, "T_runner_corr_ms": Tc, "T_oracle_ms": stat([x["T_oracle_ms"] for x in v]),
            "n_marks_in_T": mean([x["b05"]["n_marks_in_T"] for x in v]), "n_calls_in_T": mean([x["n_calls_in_T"] for x in v]),
            "subspans": table, "units": units, "groups": groups, "r210_components": r210,
            "coverage_b05_min": min(x["coverage_b05"] for x in v),
            "stall": {"trials_with_stall": [x["trial"] for x in st],
                      "stalls": [dict(s, trial=x["trial"]) for x in st for s in x["stalls"]],
                      "c_in_prep_corr_all": stat([x["b05"]["sub_corr"].get("c_in.prep", 0.0) for x in v]),
                      "c_in_prep_corr_without_stall_trials": stat([x["b05"]["sub_corr"].get("c_in.prep", 0.0) for x in nost]),
                      "T_oracle_all": stat([x["T_oracle_ms"] for x in v]),
                      "T_oracle_without_stall_trials": stat([x["T_oracle_ms"] for x in nost])},
            "cold_excess_ms": stat([x.get("cold_excess_ms") for x in v]),
            "training_rows": [x["trial"] for x in v if x.get("training")]}
    return out


def paired(rows: list[dict[str, Any]], a: str, b: str, key: Any) -> dict[str, list[tuple[float, float, int]]]:
    idx: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for x in rows:
        idx[(x["cls"], x["round"])][x["arm"]] = x
    out: dict[str, list] = defaultdict(list)
    for (cls, rnd), arms in sorted(idx.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        xa, xb = arms.get(a), arms.get(b)
        if xa and xb and xa["valid"] and xb["valid"]:
            va, vb = key(xa), key(xb)
            if va is not None and vb is not None:
                out[cls].append((va, vb, rnd))
    return out


def diff_stat(p: list[tuple[float, float, int]]) -> dict[str, Any]:
    d = [x[0] - x[1] for x in p]
    return {"n_pairs": len(d), "mean_diff": mean(d), "ci95": boot_mean_ci(d), "median_diff": statistics.median(d) if d else None}


def overhead_summary(rows: list[dict[str, Any]], c_m: float) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows), "valid": sum(1 for x in rows if x["valid"]),
                           "invalid": [{"trial": x["trial"], "reasons": x["reasons"]} for x in rows if not x["valid"]],
                           "loadavg_1m": stat([x["loadavg_1m"] for x in rows]), "by_class": {}}
    keys = {"T_runner_ms": lambda x: x.get("T_runner_ms"), "T_oracle_ms": lambda x: x.get("T_oracle_ms")}
    for cls in CLASSES:
        res = {name: diff_stat(paired(rows, "COMP", "COMP_OFF", fn).get(cls, [])) for name, fn in keys.items()}
        on = [x for x in rows if x["cls"] == cls and x["arm"] == "COMP" and x["valid"] and x.get("b05")]
        res["predicted_overhead_ms"] = mean([x["b05"]["n_marks_in_T"] * c_m for x in on])
        m, pr = res["T_runner_ms"]["mean_diff"], res["predicted_overhead_ms"]
        res["measured_over_predicted"] = m / pr if (m is not None and pr) else None
        out["by_class"][cls] = res
    meas = [out["by_class"][c]["T_runner_ms"]["mean_diff"] for c in CLASSES]
    pred = [out["by_class"][c]["predicted_overhead_ms"] for c in CLASSES]
    out["x_pooled"] = (sum(meas) / sum(pred)) if all(v is not None for v in meas + pred) and sum(pred) else None
    return out


def phase_b_summary(rows: list[dict[str, Any]], arm: str, cand: dict[str, Any]) -> dict[str, Any]:
    ctrl = cand.get("control_arm", "COMP_OFF")
    work = WORK_METRIC[arm]
    out: dict[str, Any] = {"control": ctrl, "metric": "T_oracle_ms", "work_metric": work, "n": len(rows),
                           "valid": sum(1 for x in rows if x["valid"]), "verified": sum(1 for x in rows if x.get("verified")),
                           "invalid": [{"trial": x["trial"], "reasons": x["reasons"]} for x in rows if not x["valid"]],
                           "loadavg_1m": stat([x["loadavg_1m"] for x in rows]), "by_class": {}}
    for cls in CLASSES:
        res = {name: diff_stat(paired(rows, ctrl, arm, lambda x, n=name: x.get(n)).get(cls, []))
               for name in ("T_oracle_ms", "T_runner_ms", work)}
        res["validity_share"] = (sum(1 for x in rows if x["cls"] == cls and x["valid"])
                                 / max(1, sum(1 for x in rows if x["cls"] == cls)))
        # Sensitivity (post hoc, documentation only; the verdict uses the pre-registered gate above): round 0 holds
        # each chunk's first trial, which is always the control in an AB round and runs cold.
        p0 = [x for x in paired(rows, ctrl, arm, lambda x: x.get("T_oracle_ms")).get(cls, []) if x[2] != 0]
        s0 = diff_stat(p0)
        s0["gate_pass"] = bool(s0["mean_diff"] is not None and s0["mean_diff"] >= GATE_MS and s0["ci95"] and s0["ci95"][0] > 0)
        res["sensitivity_without_round0_T_oracle_ms"] = s0
        out["by_class"][cls] = res
    return out


def smoke_summary(chunks: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in chunks.items():
        if not k.startswith("D"):
            continue
        sm = [t for t in v["trials"] if t["summary"].get("kind") == "smoke"]
        out[k] = {"n": len(sm), "verified": sum(1 for t in sm if t["summary"].get("outcome") == "verified"
                                                and t["summary"].get("oracle_exact_match")),
                  "by_class_shapes": {c: sorted({json.dumps(A.receipt_shape_browser(t), sort_keys=True)
                                                 for t in sm if t["summary"]["cls"] == c}) for c in CLASSES},
                  "by_class_routes": {c: sorted({json.dumps(t["summary"].get("routes"), sort_keys=True)
                                                 for t in sm if t["summary"]["cls"] == c}) for c in CLASSES},
                  "exp_env": sorted({json.dumps(t["summary"].get("driver_env_exp") or {}, sort_keys=True) for t in sm}),
                  "manifests": {n: {"smoke_trace_like_files": m.get("smoke_trace_like_files")} for n, m in v["manifests"].items()}}
    return out


def n4a_summary(chunks: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in chunks.items():
        rows = []
        for t in v["trials"]:
            s = t["summary"]
            if s.get("kind") != "n4a":
                continue
            muts = s.get("mutations") or []
            after = [m for m in muts if m.get("result") in ("accepted", "refused")]
            ok = (len(after) >= 3 and after[1].get("result") == "refused" and after[1].get("code") == "browser_ref_stale"
                  and after[2].get("result") == "accepted")
            refused = [e for e in t["events"] if e["event"] == "call_return" and e.get("refused")]
            stale_refusals = 0  # response frames: effect "refused" with the browser_ref_stale text
            for f in t.get("frames") or []:
                if f.get("k") != "resp":
                    continue
                try:
                    res = json.loads(f["line"]).get("result") or {}
                except ValueError:
                    continue
                sc = res.get("structuredContent") or {}
                txt = " ".join(c.get("text", "") for c in res.get("content") or [] if isinstance(c, dict))
                if sc.get("effect") == "refused" and "browser_ref_stale" in txt:
                    stale_refusals += 1
            rows.append({"trial": t["name"], "arm": s["arm"], "cls": s["cls"], "dom_replace": s.get("dom_replace"),
                         "refused_then_rebind": ok, "outcome": s.get("outcome"), "oracle": s.get("oracle_exact_match"),
                         "completion_mutations": s.get("completion_mutations"), "refused_calls": len(refused),
                         "effect_refused_frames": stale_refusals, "error_leaves": s.get("error_leaves"),
                         "pass": bool(s.get("dom_replace") == "replaced" and ok and s.get("outcome") == "verified"
                                      and s.get("oracle_exact_match") is True and s.get("completion_mutations") == 1
                                      and stale_refusals == 1)})
        if rows:
            out[k] = {"n": len(rows), "pass": sum(1 for x in rows if x["pass"]), "rows": rows}
    return out


N4A_GATE_CHUNKS = ("N2",)  # N1: every fill trial stopped in the harness before dispatch (no routine store); README deviation


def n4a_ok(S: dict[str, Any], arm: str) -> bool:
    rows = [x for k, c in S.get("n4a", {}).items() if k in N4A_GATE_CHUNKS for x in c["rows"] if x["arm"] == arm]
    return len(rows) >= 15 and all(x["pass"] for x in rows) and all(c in {x["cls"] for x in rows} for c in CLASSES)


def controls(raw: Path, amend: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    eq, neg = {}, {}
    cpath = raw / "controls" / "controls.json"
    ctl = json.loads(cpath.read_text()) if cpath.exists() else None
    for cand in amend.get("candidates", []):
        arm = cand["arm"]
        files = sorted((raw / "equivalence").glob(f"equivalence-{cand['chunk_prefix']}*.json"))
        if not files:
            eq[arm] = {"status": "NOT_RUN", "all_equal": None}
        else:
            ss = [json.loads(p.read_text())["summary"] for p in files]
            agg = {k: sum(s[k] for s in ss) for k in ("trials", "requests", "requests_identical", "requests_different",
                                                       "responses", "trials_responses_decoded_identical", "structure_pairs",
                                                       "structure_pairs_identical", "measured_trials", "measured_trials_all_calls_ok")}
            agg["chunks"] = [s["chunk"] for s in ss]
            # PREREG candidates.<arm>.equivalence: PREP_FAST = byte-identical requests (+ decoded-identical responses);
            # POST_FAST = per-pair response structure (+ the same two). Structure is reported for every arm.
            base = (agg["requests_different"] == 0 and agg["requests"] > 0
                    and agg["trials_responses_decoded_identical"] == agg["trials"]
                    and agg["measured_trials_all_calls_ok"] == agg["measured_trials"])
            struct_ok = agg["structure_pairs_identical"] == agg["structure_pairs"]
            agg["criterion"] = "requests + decoded responses + structure" if arm == "POST_FAST" else "requests + decoded responses"
            agg["all_equal"] = base and (struct_ok or arm != "POST_FAST")
            eq[arm] = agg
        if arm == "ROUTE_FAST":
            m = (ctl or {}).get("malformed") or {}
            neg[arm] = {"kind": "malformed frames through the client stack (route default vs fast)", "n": m.get("n_frames"),
                        "same_outcome_all": m.get("same_outcome_all"), "all_rejected": bool(m.get("malformed_rejected_all")
                                                                                             and m.get("same_outcome_all"))}
        elif arm == "PREP_FAST":
            p = (ctl or {}).get("prep_bytes") or {}
            neg[arm] = {"kind": "request-byte edge cases and fallback types (prep default vs fast)",
                        "n": len(p.get("cases", [])), "all_rejected": bool(p.get("all_identical")
                                                                          and p.get("fallbacks") == p.get("expected_fallback")
                                                                          and p.get("fast_path_taken") == p.get("expected_fast"))}
        else:
            u = raw / "unit" / "steps.txt"
            ok = u.exists() and "core-mcp-result-tests rc=0" in u.read_text()
            neg[arm] = {"kind": "UNIT: schema-rejected payload gives identical bytes with and without prewarm "
                                "(mcp_result::tests::b07_prewarm_shares_one_validator_and_keeps_results_identical)",
                        "all_rejected": ok}
    return eq, neg


# ── verdicts and E2 ──────────────────────────────────────────────────────────
def verdicts(S: dict[str, Any], amend: dict[str, Any]) -> dict[str, Any]:
    pa = S["phase_A"]["by_class"]
    selected = {c["arm"] for c in amend.get("candidates", [])}
    out: dict[str, Any] = {"units": {}, "resolution": {}, "candidates": {}}
    for arm, target in CANDIDATE_TARGET.items():
        res = {}
        pb = S["phase_B"].get(arm)
        for cls in CLASSES:
            u = pa.get(cls, {}).get("units", {}).get(target, {}).get("corr", {})
            total, ci = u.get("mean"), u.get("ci95")
            if arm not in selected:
                v = "BELOW_GATE" if ci and ci[1] < GATE_MS else "UNTESTED (not selected)"
                res[cls] = {"candidate": "NOT_SELECTED", "target_verdict": v}
                continue
            c = pb["by_class"][cls]
            m = c["T_oracle_ms"]
            tr = c["T_runner_ms"]["ci95"]
            ok = (m["mean_diff"] is not None and m["mean_diff"] >= GATE_MS and m["ci95"] and m["ci95"][0] > 0
                  and c["validity_share"] == 1.0 and S["equivalence"].get(arm, {}).get("all_equal") is True
                  and S["negative"].get(arm, {}).get("all_rejected") is True and n4a_ok(S, arm) and n4a_ok(S, "COMP_OFF")
                  and not (tr and tr[1] < 0))
            if ok:
                res[cls] = {"candidate": "DELETED (KEEP)", "target_verdict": f"DELETED ({arm})"}
            else:
                tv = "BELOW_GATE" if (total is not None and total < GATE_MS) else f"IRREDUCIBLE (candidate failed: {arm} KILL)"
                res[cls] = {"candidate": "KILL", "target_verdict": tv}
        out["candidates"][arm] = res
    for unit in UNITS:
        per = {}
        for cls in CLASSES:
            u = pa.get(cls, {}).get("units", {}).get(unit, {}).get("corr", {})
            ci = u.get("ci95")
            if unit in CANDIDATE_TARGET.values():
                arm = next(a for a, t in CANDIDATE_TARGET.items() if t == unit)
                per[cls] = out["candidates"][arm][cls]["target_verdict"]
            elif unit == "adm.inner":
                per[cls] = "BELOW_GATE" if ci and ci[1] < GATE_MS else "IRREDUCIBLE (invariant: session identity and session observation context)"
            elif unit in B05_TERMINAL:
                per[cls] = B05_TERMINAL[unit]
            elif ci is None:
                per[cls] = "ABSENT"
            else:
                per[cls] = "BELOW_GATE" if ci[1] < GATE_MS else "UNTESTED (no candidate)"
        out["units"][unit] = per
    for k in SP.RESOLUTION:
        per = {}
        for cls in CLASSES:
            t = pa.get(cls, {}).get("subspans", {}).get(k)
            if k in CDP_INVARIANT:
                per[cls] = f"IRREDUCIBLE (invariant: {CDP_INVARIANT[k]})" if t else "ABSENT"
            elif t is None:
                per[cls] = "ABSENT"
            else:
                per[cls] = "BELOW_GATE" if t["corr"]["ci95"] and t["corr"]["ci95"][1] < GATE_MS else "UNTESTED (no candidate)"
        out["resolution"][k] = per
    return out


def subspan_verdict(sub: str, cls: str, V: dict[str, Any]) -> str:
    for u, members in UNITS.items():
        if sub in members:
            return V["units"][u][cls]
    if sub in V["resolution"]:
        return V["resolution"][sub][cls]
    return "UNTESTED"


def bucket(v: str | None, below_gate_as: str) -> str:
    if v is None:
        return "UNTESTED"
    for k in ("DELETED", "IRREDUCIBLE", "OWNER_DECISION"):
        if v.startswith(k):
            return k
    if v == "BELOW_GATE":
        return below_gate_as
    if v == "ABSENT":
        return "IRREDUCIBLE"
    return "UNTESTED"


def e2(rows_a: list[dict[str, Any]], V: dict[str, Any], phase_a: dict[str, Any]) -> dict[str, Any]:
    """R'-source untested share (B7 Phase A, R2-10R component verdicts outside the lane), two cold-excess mappings."""
    out: dict[str, Any] = {}
    for cls in CLASSES:
        v = per_class_rows(rows_a, cls)
        if not v:
            continue
        res: dict[str, Any] = {}
        E = phase_a["by_class"][cls]["cold_excess_ms"]["mean"]
        for view in ("raw", "corr"):
            T = mean([x["T_runner_ms"] if view == "raw" else x["b05"]["T_runner_corr_ms"] for x in v])
            bc = "by_comp" if view == "raw" else "by_comp_corr"
            comps = sorted({c for x in v for c in x["b05"][bc]})
            for bg in ("IRREDUCIBLE", "UNTESTED"):
                acc: dict[str, float] = defaultdict(float)
                items = {}
                for comp in comps:
                    for lab in sorted({lab for x in v for lab in x["b05"][bc].get(comp, {})}):
                        m = mean([x["b05"][bc].get(comp, {}).get(lab, 0.0) for x in v]) or 0.0
                        if comp in LANE_SCOPE or comp == "unattributed":
                            vb = bucket(subspan_verdict(lab, cls, V), bg)
                        else:
                            rv = A.BROWSER_VERDICTS.get(comp)
                            rv = rv[cls] if isinstance(rv, dict) else rv
                            vb = rv if rv in ("DELETED", "IRREDUCIBLE", "OWNER_DECISION") else "UNTESTED"
                        acc[vb] += m
                        if vb == "UNTESTED" and m > 0.01:
                            items[f"{comp}/{lab}"] = m
                a = {"mean_T_ms": T, "untested_ms": acc["UNTESTED"], "untested_share": acc["UNTESTED"] / T if T else None,
                     "by_verdict_ms": dict(acc), "untested_items": items}
                # (b) B-04: the whole cold excess E counts as UNTESTED for fill and toggle (u = 1; modal unchanged)
                eb = (E or 0.0) if cls in ("fill", "toggle") else 0.0
                res[f"{view}:below_gate_as_{bg.lower()}"] = {
                    "a_r2_10_carry_over": a,
                    "b_b04_cold_excess_untested": {"E_ms": eb, "untested_ms": acc["UNTESTED"] + eb,
                                                   "untested_share": (acc["UNTESTED"] + eb) / T if T else None}}
        out[cls] = res
    return out


# ── main ─────────────────────────────────────────────────────────────────────
def analyse(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "b-07.summary.v1"}
    amend_path = HERE / "PREREG-AMENDMENT-1.json"
    amend = json.loads(amend_path.read_text()) if amend_path.exists() else {}
    chunks = {p.name.replace(".tar.gz", ""): load_chunk(p) for p in sorted((raw / "browser").glob("*.tar.gz"))}
    S["chunks"] = {k: {"trials": len(v["trials"]),
                       "load_gate": [g for m in v["manifests"].values() for g in m.get("load_gate", [])],
                       "ended_on_load_gate": [m.get("ended_on_load_gate") for m in v["manifests"].values()],
                       "ended_on_time_cap": [m.get("ended_on_time_cap") for m in v["manifests"].values()]}
                   for k, v in chunks.items()}

    def trials_of(prefixes: tuple[str, ...], kind: str = "measured") -> list[dict[str, Any]]:
        return [t for k, v in chunks.items() if k.startswith(prefixes) for t in v["trials"]
                if t["summary"].get("kind") == kind and not t["name"].endswith("-admission")]

    phase_a = trials_of(("A",))
    type_routes = Counter(m.get("route") for t in phase_a for m in (t["summary"].get("mutations") or [])
                          if m.get("tool") == "browser_type" and m.get("result") == "accepted")
    type_route = type_routes.most_common(1)[0][0] if type_routes else None
    S["browser_type_route"] = {"modal": type_route, "counts": dict(type_routes)}
    nulls: list[float] = []
    for t in phase_a:
        if t["trace"]:
            d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, 0.0)
            if d:
                nulls += d["null_us"]
    c_m_us = statistics.median(nulls) if nulls else 0.0
    c_m = c_m_us / 1000.0
    S["per_mark_cost"] = {"c_m_us": c_m_us, "n_samples": len(nulls)}
    dv = {"prep": "default", "route": "default"}
    rows_a = [analyse_trial(t, type_route, c_m, {}, dv) for t in phase_a if t["summary"].get("arm") == "COMP"]
    S["phase_A"] = phase_a_summary(rows_a, c_m)
    rows_o = [analyse_trial(t, type_route, c_m, {}, dv) for t in trials_of(("O",))]
    S["overhead_control"] = overhead_summary(rows_o, c_m)
    rows_b: dict[str, list[dict[str, Any]]] = {}
    for cand in amend.get("candidates", []):
        arm = cand["arm"]
        knobs, variant = cand.get("driver_knobs", {}), {**dv, **cand.get("caller_variant", {})}
        rows_b[arm] = [analyse_trial(t, type_route, c_m, knobs if t["summary"].get("arm") == arm else {},
                                     variant if t["summary"].get("arm") == arm else dv)
                       for t in trials_of((cand["chunk_prefix"],))]
    S["phase_B"] = {arm: phase_b_summary(rows, arm, next(c for c in amend["candidates"] if c["arm"] == arm))
                    for arm, rows in rows_b.items()}
    S["smoke"] = smoke_summary(chunks)
    S["n4a"] = n4a_summary(chunks)
    S["equivalence"], S["negative"] = controls(raw, amend)
    S["e4"] = {"phase_A": A.e4_totals(rows_a), "overhead": A.e4_totals(rows_o),
               **{f"phase_B:{arm}": A.e4_totals(rows) for arm, rows in rows_b.items()}}
    S["verdicts"] = verdicts(S, amend)
    S["e2"] = e2(rows_a, S["verdicts"], S["phase_A"])
    # PREREG overhead_control: the corrected view at the measured scale (c_m x x_pooled), documentation only.
    xp = S["overhead_control"].get("x_pooled")
    if xp:
        cm = c_m * xp
        ra = [analyse_trial(t, type_route, cm, {}, dv) for t in phase_a if t["summary"].get("arm") == "COMP"]
        S2 = {**S, "phase_A": phase_a_summary(ra, cm)}
        V2 = verdicts(S2, amend)
        changes = {f"{k}/{c}": [S["verdicts"]["units"][k][c], V2["units"][k][c]] for k in V2["units"] for c in CLASSES
                   if V2["units"][k][c] != S["verdicts"]["units"][k][c]}
        S["e2_x_pooled"] = {"x_pooled": xp, "c_m_us": cm * 1000.0, "verdict_changes": changes,
                            "e2": {c: {k: {"a": v["a_r2_10_carry_over"]["untested_share"],
                                           "b": v["b_b04_cold_excess_untested"]["untested_share"]}
                                       for k, v in d.items() if k.startswith("corr")}
                                   for c, d in e2(ra, V2, S2["phase_A"]).items()}}
    return r(S)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "b07-summary.json"))
    a = p.parse_args()
    S = analyse(Path(a.raw))
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"phase_A_valid": S["phase_A"].get("valid"), "c_m_us": S["per_mark_cost"]["c_m_us"]}))


if __name__ == "__main__":
    main()

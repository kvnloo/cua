#!/usr/bin/env python3
"""B-05 analysis: recompute every number from raw/ (standard library only).

Rules are the ones in PREREG.json and PREREG-AMENDMENT-1.json. The R2-10 component view uses R2-10's
own code (harness/r2-10/analyze_r2_10.py, b01_analysis, analyze_browser; byte-identical copies from
030f6bdbf); the B-05 sub-span view uses harness/b05_spans.py.

usage: analyze_b05.py [--raw raw] [--out b05-summary.json]
"""

from __future__ import annotations

import argparse
import gzip
import io
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
sys.path[:0] = [str(H), str(H / "r2-10" / "src" / "b-02-browser-driver-sites-2026-10-02"), str(H / "r2-10")]
import b01_analysis as B  # noqa: E402
import analyze_browser as AB  # noqa: E402,F401  (installs the B-02 classifier on B)
import analyze_r2_10 as A  # noqa: E402
import b05_spans as SP  # noqa: E402

SEED = 20261003
BOOT = 10000
CLASSES = ["fill", "toggle", "modal"]
V_ENV, SETTLE_ENV, TRACE_ENV = "CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE", "CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS", \
    "CUA_DRIVER_PHASE_TRACE_FILE"
TRACE_ONLY_REASONS = {"settle=[]", "click_without_cdp_send", "V_not_taken"}
LANE_SCOPE = {"mcp_transport", "mcp_admission", "resolution", "client_validation"}
GROUPS = {
    "transport_in_out": SP.CALLER_IN + SP.PIPES + SP.DRIVER_IN + SP.DRIVER_OUT
    + [x for x in SP.CALLER_OUT if x != "c_out.validate"],
    "admission_residual": SP.ADMISSION,
    "resolution": SP.RESOLUTION,
    "client_validation": ["c_out.validate"],
}
DEFAULT_VARIANT = {"parser": "default", "max_bytes": 65536, "validator": "default"}
CALLER_METRIC = SP.CALLER_IN + SP.CALLER_OUT  # caller-side transport + validation (PREREG phase_B primary)
DRIVER_OUT_METRIC = ["d_out.serialize", "d_out.write", "d_out.flush", "pipe_out", "c_out.frame"]
# Floor mapping (PREREG floors.interpretation): floor key -> sub-spans it is compared with.
FLOOR_KEYS = {
    "f.c_in.prep": ["c_in.prep"], "f.c_in.serialize": ["c_in.serialize"], "f.write_pipe_in": ["c_in.write", "pipe_in"],
    "f.pipe_out_frame": ["pipe_out", "c_out.frame"], "f.c_out.parse": ["c_out.parse"],
    "f.c_out.route": ["c_out.route"], "f.c_out.result_model": ["c_out.result_model"],
    "f.c_out.validate": ["c_out.validate"], "f.c_out.return": ["c_out.return"],
    "f.d_in.parse": ["d_in.parse"], "f.adm.outer": ["adm.outer"], "f.adm.inner": ["adm.inner"],
    "f.d_in.invoke": ["d_in.invoke"], "f.d_out.post": ["d_out.post"], "f.d_out.serialize": ["d_out.serialize"],
    "f.d_out.write_flush": ["d_out.write", "d_out.flush"],
}
DRIVER_ZERO_FLOOR = ["f.d_in.parse", "f.adm.outer", "f.adm.inner", "f.d_in.invoke", "f.d_out.post", "f.d_out.serialize"]
CDP_INVARIANT = {"res.frame_proof": "Page.getFrameTree re-proves the ref's frame identity at dispatch",
                 "res.cdp_node_resolve": "DOM.resolveNode: the live node (FIX-01 detached-node refusal) and its objectId",
                 "res.type_focus": "DOM.focus: trusted_input typing goes to the focused element",
                 "res.editable_check": "Runtime.callFunctionOn: non-editable targets are refused before typing"}


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


def r(x: Any, nd: int = 3) -> Any:
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
    trials, frames, manifests = [], {}, {}
    for name in sorted(files):
        if name.startswith("frames/") and name.endswith(".frames.jsonl.gz"):
            txt = gzip.decompress(files[name]).decode()
            frames[name.split("/")[-1].replace(".frames.jsonl.gz", "")] = [json.loads(x) for x in txt.splitlines() if x.strip()]
        elif "run-manifest" in name and name.endswith(".json"):
            manifests[name] = json.loads(files[name])
        elif name.startswith("trials/") and name.endswith(".jsonl") and not name.endswith(".driver-trace.jsonl"):
            lines = [json.loads(x) for x in files[name].decode().splitlines() if x.strip()]
            if not lines or lines[-1].get("event") != "summary":
                continue
            s = lines[-1]
            tr = files.get(s["driver_trace"]) if s.get("driver_trace") else None
            trace = [json.loads(x) for x in tr.decode().splitlines() if x.strip()] if tr else []
            trials.append({"name": s["trial"], "summary": s, "events": lines[:-1], "trace": trace, "bundle": path.name})
    return {"trials": trials, "frames": frames, "manifests": manifests}


def load_jsonl_gz(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


# ── per trial ────────────────────────────────────────────────────────────────
def r210_trial(t: dict[str, Any], arm_as: str | None = None) -> dict[str, Any]:
    s = dict(t["summary"])
    if arm_as:
        s["arm"] = arm_as
    return {**t, "summary": s, "trace": SP.r210_view(t["trace"])}


def validity(t: dict[str, Any], type_route: str | None, knobs: dict[str, str]) -> dict[str, Any]:
    """R2-10 browser_row checks (COMP configuration) + the B-05 marks/knob rules."""
    s = t["summary"]
    marks_on = bool(t["trace"])
    row = A.browser_row(r210_trial(t, "COMP"), type_route)
    row["arm"] = s.get("arm")  # checks ran with the COMP configuration; keep the real arm
    reasons = list(row["reasons"])
    if not marks_on:  # trace-only checks cannot run; PREREG forced_path: caller-visible part instead
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
    row["reasons"] = reasons
    row["valid"] = not reasons
    row["marks_on"] = marks_on
    return row


def caller_variant_reasons(t: dict[str, Any], variant: dict[str, Any]) -> list[str]:
    cv = t["summary"].get("caller_variant") or {}
    return [f"caller_variant:{k}={cv.get(k)}" for k, v in variant.items() if cv.get(k) != v]


def analyse_trial(t: dict[str, Any], type_route: str | None, c_m_ms: float, knobs: dict[str, str],
                  variant: dict[str, Any] | None = None) -> dict[str, Any]:
    row = validity(t, type_route, knobs)
    if variant is not None:
        extra = caller_variant_reasons(t, variant)
        row["reasons"] += extra
        row["valid"] = not row["reasons"]
    s = t["summary"]
    row.update({"order": s.get("order"), "block": s.get("block"), "layer": s.get("layer")})
    if not row.get("verified"):
        return row
    d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, c_m_ms)
    if d is None:
        return row
    row["b05"] = {k: d[k] for k in ("sub", "sub_corr", "by_comp", "by_comp_corr", "n_marks_in_T", "T_runner_corr_ms")}
    row["null_us"] = d["null_us"]
    row["calls"] = [{"label": c["label"], "tool": c["tool"], "sub": c["sub"], "left_marks": c["left_marks"],
                     "id": call_id(t["events"], c["t0"], c["t1"])} for c in d["calls"]]
    # consistency with R2-10's own decomposition (same T window, R's mark set)
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
    row["caller_ms"] = sum(d["sub"].get(k, 0.0) for k in CALLER_METRIC)
    row["driver_out_ms"] = sum(d["sub_corr"].get(k, 0.0) for k in DRIVER_OUT_METRIC)
    row["n_calls_in_T"] = len(d["calls"])
    return row


def call_id(events: list[dict[str, Any]], t0: int, t1: int) -> Any:
    for e in events:
        if e["event"] == "c.req_written" and t0 <= e["t_mono_ns"] <= t1:
            return e.get("id")
    return None


# ── floor ────────────────────────────────────────────────────────────────────
def floor_f1_calls(rec: dict[str, Any]) -> dict[Any, dict[str, float]]:
    """Per JSON-RPC id: F1 sub-spans (same labels as the trial) + server read->write."""
    ev = rec["events"]
    srv = rec["server"]
    out: dict[Any, dict[str, float]] = {}
    for w in B._windows(ev):
        pts = [(e["t_mono_ns"], "C", e["event"]) for e in ev if w["t0"] <= e["t_mono_ns"] <= w["t1"]]
        for s in srv:
            if w["t0"] <= s["t_read"] <= w["t1"]:
                pts.append((s["t_read"], "S", "srv.read"))
                pts.append((s["t_written"], "S", "srv.written"))
        pts.sort(key=lambda p: (p[0], 0 if p[1] == "C" else 1))
        val = B._pairs([e for e in ev if w["t0"] <= e["t_mono_ns"] <= w["t1"]], "client_validate_start",
                       "client_validate_end")
        sub: dict[str, float] = {}
        for (ta, src, name), (tb, _s, _n) in zip(pts, pts[1:]):
            dt = (tb - ta) / 1e6
            if dt <= 0:
                continue
            mid = (ta + tb) / 2
            if any(a <= mid <= b for a, b in val):
                lab = "c_out.validate"
            elif src == "S":
                lab = "floor.server" if name == "srv.read" else "pipe_out"
            else:
                lab = SP.C_LABEL.get(name, "c_other")
            sub[lab] = sub.get(lab, 0.0) + dt
        cid = call_id(ev, w["t0"], w["t1"])
        if cid is not None:
            out[cid] = sub
    return out


def floor_f0_calls(rec: dict[str, Any]) -> dict[Any, dict[str, float]]:
    srv = {s["idx"]: s for s in rec["server"]}
    out = {}
    for row in rec["rows"]:
        if row.get("notification") or row.get("id") is None:
            continue
        s = srv.get(row["idx"])
        if not s or row.get("t_complete") is None:
            continue
        out[row["id"]] = {"ser": row["ser_ns"] / 1e6, "write_pipe_in": (s["t_read"] - row["t_send"]) / 1e6,
                          "server": (s["t_written"] - s["t_read"]) / 1e6,
                          "pipe_out_frame": (row["t_complete"] - s["t_written"]) / 1e6,
                          "parse": (row["t_parsed"] - row["t_complete"]) / 1e6}
    return out


def task_floor(ids: list[Any], f0: dict[Any, dict[str, float]], f1: dict[Any, dict[str, float]]) -> dict[str, Any]:
    """Per-task floors per FLOOR_KEYS: F0 (PREREG irreducible floor) and F1 (client-stack floor)."""
    if not ids or any(i not in f0 or i not in f1 for i in ids):
        return {}
    s0 = {k: sum(f0[i][k] for i in ids) for k in ("ser", "write_pipe_in", "server", "pipe_out_frame", "parse")}
    s1: dict[str, float] = defaultdict(float)
    for i in ids:
        for k, v in f1[i].items():
            s1[k] += v
    F0 = {"f.c_in.prep": 0.0, "f.c_in.serialize": s0["ser"], "f.write_pipe_in": s0["write_pipe_in"],
          "f.pipe_out_frame": s0["pipe_out_frame"], "f.c_out.parse": s0["parse"], "f.c_out.route": 0.0,
          "f.c_out.result_model": 0.0, "f.c_out.validate": 0.0, "f.c_out.return": 0.0,
          "f.d_out.write_flush": s0["server"], **{k: 0.0 for k in DRIVER_ZERO_FLOOR}}
    F1 = {"f.c_in.prep": s1["c_in.prep"], "f.c_in.serialize": s1["c_in.serialize"],
          "f.write_pipe_in": s1["c_in.write"] + s1["pipe_in"], "f.pipe_out_frame": s1["pipe_out"] + s1["c_out.frame"],
          "f.c_out.parse": s1["c_out.parse"], "f.c_out.route": s1["c_out.route"],
          "f.c_out.result_model": s1["c_out.result_model"], "f.c_out.validate": s1["c_out.validate"],
          "f.c_out.return": s1["c_out.return"], "f.d_out.write_flush": s1["floor.server"],
          **{k: 0.0 for k in DRIVER_ZERO_FLOOR}}
    return {"F0": F0, "F1": F1}


# ── main analysis ─────────────────────────────────────────────────────────────
def analyse(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "b-05.summary.v1"}
    amend_path = HERE / "PREREG-AMENDMENT-1.json"
    amend = json.loads(amend_path.read_text()) if amend_path.exists() else {}
    chunks = {p.name.replace(".tar.gz", ""): load_chunk(p) for p in sorted((raw / "browser").glob("*.tar.gz"))}
    S["chunks"] = {k: {"trials": len(v["trials"]), "frames": len(v["frames"])} for k, v in chunks.items()}

    def trials_of(prefixes: tuple[str, ...], kind: str = "measured") -> list[dict[str, Any]]:
        return [t for k, v in chunks.items() if k.startswith(prefixes) for t in v["trials"]
                if t["summary"].get("kind") == kind and not t["name"].endswith("-admission")]

    phase_a = trials_of(("A",))
    type_routes = Counter(m.get("route") for t in phase_a for m in (t["summary"].get("mutations") or [])
                          if m.get("tool") == "browser_type" and m.get("result") == "accepted")
    type_route = type_routes.most_common(1)[0][0] if type_routes else None
    S["browser_type_route"] = {"modal": type_route, "counts": dict(type_routes)}

    # pass 1: per-mark cost from Phase A null pairs
    nulls: list[float] = []
    for t in phase_a:
        if t["trace"]:
            d = SP.decompose_b05(t, B.classify_mark, B.completion_effect_ns, B._windows, B._pairs, 0.0)
            if d:
                nulls += d["null_us"]
    c_m_us = statistics.median(nulls) if nulls else 0.0
    c_m = c_m_us / 1000.0
    S["per_mark_cost"] = {"c_m_us": c_m_us, "n_samples": len(nulls),
                          "p10_us": sorted(nulls)[len(nulls) // 10] if nulls else None,
                          "p90_us": sorted(nulls)[(9 * len(nulls)) // 10] if nulls else None}

    # pass 2: Phase A rows
    rows_a = [analyse_trial(t, type_route, c_m, {}) for t in phase_a if t["summary"].get("arm") == "COMP"]
    S["phase_A"] = phase_a_summary(rows_a, c_m)

    # overhead control
    ovh = trials_of(("O",))
    rows_o = [analyse_trial(t, type_route, c_m, {}) for t in ovh]
    S["overhead_control"] = overhead_summary(rows_o, c_m)

    # floor
    S["floor"] = floor_summary(raw, rows_a)

    # Phase B
    rows_b: dict[str, list[dict[str, Any]]] = {}
    for cand in amend.get("candidates", []):
        arm = cand["arm"]
        tr = trials_of((cand["chunk_prefix"],))
        knobs = cand.get("driver_knobs", {})
        variant = cand.get("caller_variant", {})
        default_variant = {k: DEFAULT_VARIANT[k] for k in variant}
        rows_b[arm] = [analyse_trial(t, type_route, c_m, knobs if t["summary"].get("arm") == arm else {},
                                     variant if t["summary"].get("arm") == arm else default_variant)
                       for t in tr]
    S["phase_B"] = {arm: phase_b_summary(rows, arm, next(c for c in amend["candidates"] if c["arm"] == arm))
                    for arm, rows in rows_b.items()}

    # controls
    S["smoke"] = smoke_summary(chunks)
    S["n4a"] = n4a_summary(chunks)
    for name in ("negative", "equivalence"):
        p = raw / name / f"{name}.json"
        S[name] = json.loads(p.read_text()) if p.exists() else {"status": "NOT_RUN"}
    S["e4"] = A.e4_totals(rows_a + rows_o + [x for v in rows_b.values() for x in v])
    S["verdicts"] = verdicts(S, amend)
    S["e2"] = e2_recompute(rows_a, S["verdicts"], c_m)
    return r(S, 4)


def per_class_rows(rows: list[dict[str, Any]], cls: str) -> list[dict[str, Any]]:
    return [x for x in rows if x["cls"] == cls and x["valid"] and x.get("b05")]


def phase_a_summary(rows: list[dict[str, Any]], c_m: float) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows), "valid": sum(1 for x in rows if x["valid"]),
                           "verified": sum(1 for x in rows if x["verified"]),
                           "invalid": [{"trial": x["trial"], "reasons": x["reasons"]} for x in rows if not x["valid"]],
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
            table[k] = {"raw": raw_, "corr": cor, "share_raw": raw_["mean"] / T["mean"],
                        "share_corr": cor["mean"] / Tc["mean"],
                        "left_marks_per_task": mean([sum(c["left_marks"].get(k, 0) for c in x["calls"]) for x in v])}
        groups = {}
        for g, members in GROUPS.items():
            raw_ = stat([sum(x["b05"]["sub"].get(k, 0.0) for k in members) for x in v])
            cor = stat([sum(x["b05"]["sub_corr"].get(k, 0.0) for k in members) for x in v])
            groups[g] = {"raw": raw_, "corr": cor, "share_raw": raw_["mean"] / T["mean"], "share_corr": cor["mean"] / Tc["mean"]}
        comps = sorted({k for x in v for k in x["r210_components"]})
        r210 = {k: {"mean_ms": mean([x["r210_components"].get(k, 0.0) for x in v]),
                    "corr_mean_ms": mean([sum(x["b05"]["by_comp_corr"].get(k, {}).values()) for x in v])} for k in comps}
        for k in r210:
            r210[k]["share_raw"] = r210[k]["mean_ms"] / T["mean"]
            r210[k]["share_corr"] = r210[k]["corr_mean_ms"] / Tc["mean"]
        out["by_class"][cls] = {"n": len(v), "T_runner_ms": T, "T_runner_corr_ms": Tc,
                                "T_oracle_ms": stat([x["T_oracle_ms"] for x in v]),
                                "n_marks_in_T": mean([x["b05"]["n_marks_in_T"] for x in v]),
                                "n_calls_in_T": mean([x["n_calls_in_T"] for x in v]),
                                "caller_ms": stat([x["caller_ms"] for x in v]),
                                "subspans": table, "groups": groups, "r210_components": r210,
                                "coverage_b05_min": min(x["coverage_b05"] for x in v),
                                "training_rows": [x["trial"] for x in v if x.get("training")]}
    return out


def paired(rows: list[dict[str, Any]], a: str, b: str, key: Any) -> dict[str, list[tuple[float, float, int]]]:
    """Per class: (value_a, value_b, round) for rounds where both trials are valid."""
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
    return {"n_pairs": len(d), "mean_diff": mean(d), "ci95": boot_mean_ci(d),
            "median_diff": statistics.median(d) if d else None}


def overhead_summary(rows: list[dict[str, Any]], c_m: float) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows), "valid": sum(1 for x in rows if x["valid"]),
                           "invalid": [{"trial": x["trial"], "reasons": x["reasons"]} for x in rows if not x["valid"]],
                           "loadavg_1m": stat([x["loadavg_1m"] for x in rows]), "by_class": {}}
    keys = {"T_runner_ms": lambda x: x.get("T_runner_ms"), "T_oracle_ms": lambda x: x.get("T_oracle_ms"),
            "caller_ms": lambda x: x.get("caller_ms")}
    for cls in CLASSES:
        res = {}
        for name, fn in keys.items():
            p = paired(rows, "COMP", "COMP_OFF", fn).get(cls, [])
            res[name] = diff_stat(p)
        on = [x for x in rows if x["cls"] == cls and x["arm"] == "COMP" and x["valid"] and x.get("b05")]
        res["predicted_overhead_ms"] = mean([x["b05"]["n_marks_in_T"] * c_m for x in on])
        m = res["T_runner_ms"]["mean_diff"]
        res["overhead_above_0_5ms"] = bool(m is not None and m > 0.5)
        out["by_class"][cls] = res
    return out


def floor_summary(raw: Path, rows_a: list[dict[str, Any]]) -> dict[str, Any]:
    fdir = raw / "floor"
    f1_recs = {x["trial"]: x for p in sorted(fdir.glob("floor-F1-*.jsonl.gz")) for x in load_jsonl_gz(p)} if fdir.exists() else {}
    f0_recs = {x["trial"]: x for p in sorted(fdir.glob("floor-F0-*.jsonl.gz")) for x in load_jsonl_gz(p)} if fdir.exists() else {}
    if not f1_recs or not f0_recs:
        return {"status": "NOT_RUN"}
    out: dict[str, Any] = {"F1_replays": len(f1_recs), "F0_replays": len(f0_recs),
                           "F1_requests_matched": sum(x["matched"] for x in f1_recs.values()),
                           "F1_requests": sum(x["requests"] for x in f1_recs.values()),
                           "F0_requests_matched": sum(x["matched"] for x in f0_recs.values()),
                           "F0_requests": sum(x["requests"] for x in f0_recs.values()),
                           "F1_errors": sorted({e for x in f1_recs.values() for e in (x.get("errors") or [])}),
                           "by_class": {}}
    per_trial: dict[str, dict[str, Any]] = {}
    for x in rows_a:
        if not (x["valid"] and x.get("b05")):
            continue
        f1, f0 = f1_recs.get(x["trial"]), f0_recs.get(x["trial"])
        if not f1 or not f0:
            continue
        ids = [c["id"] for c in x["calls"]]
        tf = task_floor(ids, floor_f0_calls(f0), floor_f1_calls(f1))
        if tf:
            per_trial[x["trial"]] = tf
            x["floor"] = tf
    out["trials_with_floor"] = len(per_trial)
    for cls in CLASSES:
        v = [x for x in per_class_rows(rows_a, cls) if x.get("floor")]
        if not v:
            continue
        tab = {}
        for fk, members in FLOOR_KEYS.items():
            meas = [sum(x["b05"]["sub_corr"].get(k, 0.0) for k in members) for x in v]
            f0 = [x["floor"]["F0"][fk] for x in v]
            f1 = [x["floor"]["F1"][fk] for x in v]
            tab[fk] = {"members": members, "measured_corr": stat(meas), "F0": stat(f0), "F1": stat(f1),
                       "excess_over_F0": stat([a - b for a, b in zip(meas, f0)]),
                       "excess_over_F1": stat([a - b for a, b in zip(meas, f1)])}
        out["by_class"][cls] = {"n": len(v), "keys": tab}
    return out


def phase_b_summary(rows: list[dict[str, Any]], arm: str, cand: dict[str, Any]) -> dict[str, Any]:
    ctrl = cand.get("control_arm", "COMP_OFF")
    metric = cand.get("primary_metric", "caller_ms")
    out: dict[str, Any] = {"control": ctrl, "metric": metric, "n": len(rows), "valid": sum(1 for x in rows if x["valid"]),
                           "verified": sum(1 for x in rows if x.get("verified")),
                           "invalid": [{"trial": x["trial"], "reasons": x["reasons"]} for x in rows if not x["valid"]],
                           "loadavg_1m": stat([x["loadavg_1m"] for x in rows]), "by_class": {}}
    for cls in CLASSES:
        res = {}
        for name in (metric, "T_runner_ms", "T_oracle_ms"):
            p = paired(rows, ctrl, arm, lambda x, n=name: x.get(n)).get(cls, [])
            res[name] = diff_stat(p)  # control - candidate = saving
        tgt = cand.get("target_subspans") or []
        if tgt:
            p = paired(rows, ctrl, arm, lambda x: sum(x["b05"]["sub"].get(k, 0.0) for k in tgt) if x.get("b05") else None).get(cls, [])
            res["target_subspans_ms"] = diff_stat(p)
        res["validity_share"] = (sum(1 for x in rows if x["cls"] == cls and x["valid"])
                                 / max(1, sum(1 for x in rows if x["cls"] == cls)))
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
                  "shapes": sorted({json.dumps(A.receipt_shape_browser(t), sort_keys=True) for t in sm}),
                  "by_class_shapes": {c: sorted({json.dumps(A.receipt_shape_browser(t), sort_keys=True)
                                                 for t in sm if t["summary"]["cls"] == c}) for c in CLASSES},
                  "manifests": {n: {"smoke_trace_like_files": m.get("smoke_trace_like_files")}
                                for n, m in v["manifests"].items()}}
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
            effects = [e.get("effect") for e in t["events"] if e["event"] == "call_return" and e.get("refused")]
            rows.append({"trial": t["name"], "arm": s["arm"], "cls": s["cls"], "dom_replace": s.get("dom_replace"),
                         "refused_then_rebind": ok, "outcome": s.get("outcome"), "oracle": s.get("oracle_exact_match"),
                         "completion_mutations": s.get("completion_mutations"),
                         "pass": bool(s.get("dom_replace") == "replaced" and ok and s.get("outcome") == "verified"
                                      and s.get("oracle_exact_match") is True and s.get("completion_mutations") == 1),
                         "refused_effects": effects})
        if rows:
            out[k] = {"n": len(rows), "pass": sum(1 for x in rows if x["pass"]), "rows": rows}
    return out


def verdicts(S: dict[str, Any], amend: dict[str, Any]) -> dict[str, Any]:
    """Pre-registered gates applied per FLOOR_KEYS group and resolution sub-span (see PREREG gates)."""
    out: dict[str, Any] = {}
    floor = S.get("floor", {}).get("by_class", {})
    tested = {}
    for cand in amend.get("candidates", []):
        pb = S["phase_B"].get(cand["arm"], {})
        res = {}
        for cls in CLASSES:
            c = pb.get("by_class", {}).get(cls, {})
            m = c.get(pb.get("metric"), {})
            ci = m.get("ci95")
            tr = c.get("T_runner_ms", {}).get("ci95")
            res[cls] = {"saving_ms": m.get("mean_diff"), "ci95": ci,
                        "deleted": bool(m.get("mean_diff") is not None and m["mean_diff"] >= 0.5 and ci and ci[0] > 0
                                        and c.get("validity_share") == 1.0),
                        "regression": bool(tr and tr[1] < 0)}
        tested[cand["arm"]] = {"targets": cand.get("floor_keys", []), "by_class": res,
                               "output_contract_change": bool(cand.get("output_contract_change"))}
    for fk in FLOOR_KEYS:
        per = {}
        for cls in CLASSES:
            f = floor.get(cls, {}).get("keys", {}).get(fk)
            if not f:
                per[cls] = "NOT_RUN"
                continue
            ex = f["excess_over_F0"]
            cands = [a for a, t in tested.items() if fk in t["targets"]]
            if ex["ci95"] and ex["ci95"][0] <= 0 <= ex["ci95"][1]:
                v = "IRREDUCIBLE (CI overlaps floor)"
            elif cands:
                ok = [a for a in cands if tested[a]["by_class"][cls]["deleted"] and not tested[a]["by_class"][cls]["regression"]
                      and S.get("equivalence", {}).get(a, {}).get("all_equal") is True
                      and S.get("negative", {}).get(a, {}).get("all_rejected", True) is True]
                if ok:
                    v = "OWNER_DECISION" if any(tested[a]["output_contract_change"] for a in ok) else f"DELETED ({ok[0]})"
                else:
                    v = "IRREDUCIBLE (every tested candidate failed)"
            elif ex["ci95"] and ex["ci95"][1] < 0.5:
                v = "BELOW_GATE"
            else:
                v = "UNTESTED (no candidate)"
            per[cls] = v
        out[fk] = per
    for k in SP.RESOLUTION:
        out[k] = {cls: (f"IRREDUCIBLE (invariant: {CDP_INVARIANT[k]})" if k in CDP_INVARIANT else None) for cls in CLASSES}
    pa = S.get("phase_A", {}).get("by_class", {})
    for k in SP.RESOLUTION:
        if k in CDP_INVARIANT:
            continue
        for cls in CLASSES:
            t = pa.get(cls, {}).get("subspans", {}).get(k)
            if t is None:
                out[k][cls] = "ABSENT"
            elif t["corr"]["ci95"] and t["corr"]["ci95"][1] < 0.5:
                out[k][cls] = "BELOW_GATE"
            else:
                out[k][cls] = "UNTESTED (no candidate)"
    return out


def subspan_verdict(sub: str, cls: str, V: dict[str, Any]) -> str:
    for fk, members in FLOOR_KEYS.items():
        if sub in members:
            return V[fk][cls]
    if sub in V:
        return V[sub][cls]
    return "UNTESTED"


def bucket(v: str | None, below_gate_as: str) -> str:
    if v is None:
        return "UNTESTED"
    if v.startswith("DELETED"):
        return "DELETED"
    if v.startswith("IRREDUCIBLE"):
        return "IRREDUCIBLE"
    if v.startswith("OWNER_DECISION"):
        return "OWNER_DECISION"
    if v == "BELOW_GATE":
        return below_gate_as
    if v == "ABSENT":
        return "IRREDUCIBLE"
    return "UNTESTED"


def e2_recompute(rows_a: list[dict[str, Any]], V: dict[str, Any], c_m: float) -> dict[str, Any]:
    """R2-10 COMP component table on B5 with the lane's sub-span verdicts (raw and corrected)."""
    out: dict[str, Any] = {}
    for cls in CLASSES:
        v = per_class_rows(rows_a, cls)
        if not v:
            continue
        res: dict[str, Any] = {}
        for view in ("raw", "corr"):
            T = mean([x["T_runner_ms"] if view == "raw" else x["b05"]["T_runner_corr_ms"] for x in v])
            bc = "by_comp" if view == "raw" else "by_comp_corr"
            comps = sorted({c for x in v for c in x["b05"][bc]})
            for bg in ("IRREDUCIBLE", "UNTESTED"):
                acc: dict[str, float] = defaultdict(float)
                table = {}
                for comp in comps:
                    labs = sorted({lab for x in v for lab in x["b05"][bc].get(comp, {})})
                    for lab in labs:
                        m = mean([x["b05"][bc].get(comp, {}).get(lab, 0.0) for x in v]) or 0.0
                        if comp in LANE_SCOPE or comp == "unattributed":
                            vb = bucket(subspan_verdict(lab, cls, V), bg)
                        else:
                            r210v = A.BROWSER_VERDICTS.get(comp)
                            r210v = r210v[cls] if isinstance(r210v, dict) else r210v
                            vb = r210v if r210v in ("DELETED", "IRREDUCIBLE", "OWNER_DECISION") else "UNTESTED"
                        acc[vb] += m
                        table[f"{comp}/{lab}"] = {"mean_ms": m, "verdict": vb}
                res[f"{view}:below_gate_as_{bg.lower()}"] = {
                    "mean_T_ms": T, "untested_ms": acc["UNTESTED"], "untested_share": acc["UNTESTED"] / T if T else None,
                    "by_verdict_ms": dict(acc),
                    "untested_items": {k: x["mean_ms"] for k, x in table.items() if x["verdict"] == "UNTESTED" and x["mean_ms"] > 0.01}}
        out[cls] = res
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "b05-summary.json"))
    a = p.parse_args()
    S = analyse(Path(a.raw))
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"phase_A_valid": S["phase_A"].get("valid"), "c_m_us": S["per_mark_cost"]["c_m_us"]}))


if __name__ == "__main__":
    main()

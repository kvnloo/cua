"""i107 lane AB analysis core, adapted from B-01 (kvnloo/cua 6689610d5, b01_analysis.py).

Pure standard-library Python so ``verify_artifacts.py`` can recompute every
headline from ``raw/`` on any machine. Kept from B-01: the telescoping
decomposition, mark taxonomy, windows, bootstrap and statistics. Changed for
kvnloo/cua#107 lane AB (see PREREG.json in this directory): arms A / B_proj /
A_ref replace the K arms; new components client_parse and candidate_build;
sub-components for Driver projection and serialization; the decomposition can
end at the runner's verified read (T_runner) or at the independent 2 ms
oracle read (T_oracle); ledger marks are removed by the caller
(i107ab_ledger.decomposable) before decomposition.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path
from typing import Any, Callable

SEED = 20261002
BOOT = 10000
ARMS = ("A", "B_proj", "A_ref")
EXPECTED_TOOLS = ["browser_type", "browser_click"]
POLL_MS = 100
DEFAULT_SETTLE_MS = 100

COMPONENTS = [
    "decision", "observation", "resolution", "revalidate", "visualization", "input_prep", "settles",
    "dispatch", "dispatch_post", "driver_pre_dispatch", "driver_post_dispatch", "transport",
    "client_validation", "client_parse", "candidate_build", "runner_overhead", "verification_reads",
    "sleeps_polls", "target_effect_lag", "oracle_detect_lag", "unattributed",
]
MCP_TRANSPORT = ["transport", "driver_pre_dispatch", "driver_post_dispatch", "client_validation"]

_PRE = {"mcp.line_read", "mcp.admitted", "mcp.inner_validated", "mcp.invoke_start", "sdk.call_start"}
_POST = {"dispatch.exit", "rt.registry_returned", "rt.observed", "sdk.runtime_returned", "sdk.normalized",
         "sdk.call_end", "sdk.parsed", "mcp.invoke_end", "mcp.conformed", "mcp.handled", "mcp.serialized"}
_OBS_CDP = {"snap.enter", "snap.attached", "snap.document", "snap.frame_tree", "snap.indexed", "snap.collected"}
_RESOLUTION = {"click.enter", "type.enter", "click.revalidated", "type.revalidated", "click.ref_resolved",
               "type.ref_resolved", "type.editable_checked"}
_VIZ = {"click.dom_resolved", "click.scrolled", "click.box_model", "type.pre_visual", "viz.exit"}
_INPUT_PREP = {"type.post_visual", "focus.emulation_enabled", "focus.poll", "focus.poll_sleep_end",
               "focus.settle_end", "focus.refocused", "type.selected", "key.emulation_enabled", "key.refocused"}


def classify_mark(left: str, tool: str) -> tuple[str, str | None]:
    """Component (and sub-component) for an interval inside a call window, by its left Driver mark."""
    if left in _PRE:
        sub = {"mcp.line_read": "pre_admission_validate", "mcp.admitted": "pre_inner_validate"}.get(left, "pre_other")
        return "driver_pre_dispatch", sub
    if left == "mcp.handled":
        return "driver_post_dispatch", "driver_serialize"
    if left == "mcp.serialized":
        return "driver_post_dispatch", "driver_write"
    if left in _POST:
        return "driver_post_dispatch", None
    if left == "mcp.written":
        return "transport", "client_receive_parse"
    if left == "dispatch.enter":
        return ("observation", "observation_processing") if tool == "get_browser_state" else ("resolution", None)
    if left == "snap.oopif_done":
        return "observation", "projection_page"
    if left in ("snap.paged", "snap.outcome", "snap.stored"):
        return "observation", "snapshot_build_store"
    if left.startswith("snap."):
        return "observation", ("observation_cdp" if left in _OBS_CDP else "observation_processing")
    if left in ("click.lock_acquired", "type.lock_acquired") or left.startswith("reval."):
        return "revalidate", ("reval_endpoint" if left == "reval.native_window" else "reval_other")
    if left in _RESOLUTION:
        return "resolution", None
    if left in _VIZ or left.startswith("viz.") or left.startswith("platform.") or left.startswith("overlay."):
        sub = "viz_arrival_wait" if left in ("overlay.arrival_wait_start", "overlay.render_arrival") else "viz_other"
        return "visualization", sub
    if left in _INPUT_PREP:
        return "input_prep", None
    if left == "focus.settle_start":
        return "settles", "settle_focus"
    if left == "focus.poll_sleep_start":
        return "settles", "settle_readiness_poll"
    if left in ("click.cdp_send", "type.insert_send"):
        return "dispatch", None
    if left == "key.loop_start":
        return "dispatch", "keystroke_loop_with_15ms_sleeps"
    if left in ("click.cdp_response", "type.insert_response", "type.emulation_disabled", "key.loop_end"):
        return "dispatch_post", None
    return "unattributed", left


def _raw_files(raw: Path) -> dict[str, str]:
    """Relative path -> text for every trial file, from raw/trials/ or the raw/trials-*.tar.gz bundles."""
    import tarfile

    files: dict[str, str] = {}
    if (raw / "trials").is_dir():
        for path in (raw / "trials").glob("*.jsonl"):
            files[f"trials/{path.name}"] = path.read_text()
    for bundle in sorted(raw.glob("trials-*.tar.gz")):
        with tarfile.open(bundle, "r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith(".jsonl"):
                    name = member.name[2:] if member.name.startswith("./") else member.name
                    files[name] = tar.extractfile(member).read().decode()
    return files


def load_trials(raw: Path) -> list[dict[str, Any]]:
    files = _raw_files(raw)
    trials = []
    for name in sorted(files):
        if name.endswith(".driver-trace.jsonl"):
            continue
        lines = [json.loads(line) for line in files[name].splitlines() if line.strip()]
        summary = lines[-1]
        assert summary["event"] == "summary", name
        trace_text = files.get(summary["driver_trace"]) if summary.get("driver_trace") else None
        trace = [json.loads(line) for line in trace_text.splitlines() if line.strip()] if trace_text else []
        trials.append({"name": summary["trial"], "summary": summary, "events": lines[:-1], "trace": trace})
    return trials


def _windows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, open_calls = [], {}
    for ev in events:
        if ev["event"] == "call_send":
            open_calls[ev["label"]] = ev
        elif ev["event"] == "call_return" and ev["label"] in open_calls:
            send = open_calls.pop(ev["label"])
            out.append({"label": ev["label"], "tool": ev["tool"], "t0": send["t_mono_ns"], "t1": ev["t_mono_ns"],
                        "ok": ev.get("ok", True)})
    return out


def _pairs(events: list[dict[str, Any]], start: str, end: str) -> list[tuple[int, int]]:
    out, t = [], None
    for ev in events:
        if ev["event"] == start:
            t = ev["t_mono_ns"]
        elif ev["event"] == end and t is not None:
            out.append((t, ev["t_mono_ns"]))
            t = None
    return out


def completion_effect_ns(cls: str, journal: list[dict[str, Any]]) -> int | None:
    for e in journal:
        if cls == "fill" and e["event"] == "submit":
            return e["t_mono_ns"]
        if cls == "toggle" and e["event"] == "update" and "checked" in e.get("fields", {}):
            return e["t_mono_ns"]
        if cls == "modal" and e["event"] == "update" and "modal" in e.get("fields", {}):
            return e["t_mono_ns"]
    return None


def decompose(trial: dict[str, Any], end: str = "runner") -> dict[str, Any] | None:
    """Telescoping decomposition of T_runner (end="runner") or T_oracle (end="oracle");
    None when T is undefined (no T0, or no verified read / no oracle observation)."""
    s, events, trace = trial["summary"], trial["events"], trial["trace"]
    cls = s.get("cls", "fill")
    windows = _windows(events)
    snap1 = next((w for w in windows if w["label"] == "snapshot1"), None)
    verified = next((e for e in events if e["event"] == "oracle_return" and e.get("outcome") == "verified"), None)
    if snap1 is None:
        return None
    if end == "oracle":
        if s.get("poller_first_ok_ns") is None:
            return None
        T0, T1 = snap1["t0"], s["poller_first_ok_ns"]
    else:
        if verified is None:
            return None
        T0, T1 = snap1["t0"], verified["t_mono_ns"]
    actions = [w for w in windows if w["label"].startswith("action") and T0 <= w["t0"] <= T1]
    last_action = actions[-1] if actions else None
    effect = completion_effect_ns(cls, s.get("journal", []))
    reads = _pairs(events, "oracle_send", "oracle_return")
    sleeps = _pairs(events, "sleep_start", "sleep_end")
    decisions = _pairs(events, "decide_start", "decided")
    validations = _pairs(events, "client_validate_start", "client_validate_end")
    parses = _pairs(events, "parse_start", "parse_end")
    cands = _pairs(events, "cand_start", "cand_done")
    in_window = [w for w in windows if w["t1"] >= T0 and w["t0"] <= T1]

    points: list[tuple[int, str, str]] = []  # (t, source, name)
    for ev in events:
        if T0 <= ev["t_mono_ns"] <= T1:
            points.append((ev["t_mono_ns"], "C", ev["event"]))
    for m in trace:
        t = m["t_mono_ns"]
        if T0 <= t <= T1 and any(w["t0"] <= t <= w["t1"] for w in in_window):
            points.append((t, "D", m["phase"]))
    tail_start = last_action["t1"] if last_action else None
    if effect is not None and tail_start is not None and tail_start < effect < T1:
        points.append((effect, "J", "effect"))
    if effect is not None and T0 < effect < T1 and not any(p[0] == effect for p in points):
        points.append((effect, "J", "effect"))
    points.append((T0, "C", "T0"))
    points.append((T1, "C", "T1"))
    points.sort(key=lambda p: (p[0], 0 if p[1] == "C" else 1))

    comp = {c: 0.0 for c in COMPONENTS}
    sub: dict[str, float] = {}
    unknown: dict[str, float] = {}

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
        for a, b in cands:
            if a <= mid <= b:
                return "candidate", None
        return "gap", None

    for (ta, src, name), (tb, _src2, _name2) in zip(points, points[1:]):
        dt = (tb - ta) / 1e6
        if dt <= 0:
            continue
        mid = (ta + tb) / 2
        if tail_start is not None and effect is not None and ta >= tail_start and tb <= effect:
            comp["target_effect_lag"] += dt
            continue
        if end == "oracle" and effect is not None and ta >= effect:
            comp["oracle_detect_lag"] += dt
            continue
        kind, w = region(mid)
        if kind == "call":
            in_val = any(a <= mid <= b for a, b in validations)
            in_parse = any(a <= mid <= b for a, b in parses)
            if in_parse:
                c, sc = "client_parse", None
            elif in_val:
                c, sc = "client_validation", None
            elif src == "C" or src == "J":
                c, sc = ("transport", "client_send" if name == "call_send" else "client_return")
            else:
                c, sc = classify_mark(name, w["tool"])
        elif kind == "read":
            c, sc = "verification_reads", None
        elif kind == "sleep":
            c, sc = "sleeps_polls", None
        elif kind == "decision":
            c, sc = "decision", None
        elif kind == "candidate":
            c, sc = "candidate_build", None
        else:
            c, sc = "runner_overhead", None
        comp[c] += dt
        if sc:
            if c == "unattributed":
                unknown[sc] = unknown.get(sc, 0.0) + dt
            else:
                sub[sc] = sub.get(sc, 0.0) + dt

    T_ms = (T1 - T0) / 1e6
    poller = s.get("poller_first_ok_ns")
    runner_T = None if verified is None else (verified["t_mono_ns"] - T0) / 1e6
    obs = [w for w in windows if w["label"].startswith("snapshot") and T0 <= w["t0"] <= T1]
    # Non-additive diagnostics.
    final_send = None
    if last_action:
        sends = [m["t_mono_ns"] for m in trace if m["phase"] in ("click.cdp_send", "type.insert_send")
                 and last_action["t0"] <= m["t_mono_ns"] <= last_action["t1"]]
        final_send = sends[-1] if sends else None
    glides = []
    starts = [m for m in trace if m["phase"] == "overlay.arrival_wait_start"]
    ends = [m for m in trace if m["phase"] == "overlay.arrival_wait_end"]
    renders = [m for m in trace if m["phase"] == "overlay.render_arrival"]
    for a, b in zip(starts, ends):
        g = (b.get("detail") or {}).get("glide") or {}
        r = next((x for x in renders if a["t_mono_ns"] <= x["t_mono_ns"] <= b["t_mono_ns"]), None)
        glides.append({"wait_ms": (b["t_mono_ns"] - a["t_mono_ns"]) / 1e6, "arrived": (b.get("detail") or {}).get("arrived"),
                       "distance_px": g.get("distance_px"), "path_length_px": g.get("path_length_px"),
                       "glide_duration_ms": g.get("glide_duration_ms"),
                       "predicted_ms": g.get("predicted_glide_ms_16ms_frames"),
                       "frames": (r or {}).get("detail", {}).get("frames") if r else None,
                       "frame_wall_ms": (r or {}).get("detail", {}).get("frame_wall_ms") if r else None,
                       "max_frame_ms": (r or {}).get("detail", {}).get("max_frame_ms") if r else None,
                       "frames_over_50ms": (r or {}).get("detail", {}).get("frames_over_50ms") if r else None})
    return {
        "T0_ns": T0,
        "end": end,
        "T_ms": T_ms,
        "T_runner_ms": runner_T,
        "T_oracle_ms": None if poller is None else (poller - T0) / 1e6,
        "components": comp,
        "sub": sub,
        "unknown_marks": unknown,
        "sum_ms": sum(comp.values()),
        "coverage": 1 - comp["unattributed"] / T_ms if T_ms > 0 else None,
        "observations": [(w["t1"] - w["t0"]) / 1e6 for w in obs],
        "sleeps_entered": sum(1 for a, _b in sleeps if T0 <= a <= T1),
        "effect_lag_from_final_send_ms": None if (effect is None or final_send is None) else (effect - final_send) / 1e6,
        "post_return_effect_lag_ms": None if (effect is None or tail_start is None) else max(0.0, (effect - tail_start) / 1e6),
        "glides": glides,
        "settle_ms": [m["detail"]["settle_ms"] for m in trace if m["phase"] == "focus.settle_start"],
    }


def forced_path(trial: dict[str, Any]) -> list[str]:
    """Reasons a measured trial deviated from the fixed i107 path (empty = as assigned)."""
    s, trace = trial["summary"], trial["trace"]
    bad = []
    tools = s.get("tools") or []
    if tools != EXPECTED_TOOLS:
        bad.append(f"tools={tools}")
    for tool, route in zip(tools, s.get("input_routes") or []):
        if tool == "browser_click" and route != "dom_event":
            bad.append(f"input_route={route}")
    if (s.get("routes") or []) != ["provider", "provider"]:
        bad.append(f"routes={s.get('routes')}")
    gates = [m for m in trace if m["phase"] == "platform.gate"]
    waits = [m for m in trace if m["phase"] == "overlay.arrival_wait_end"]
    if waits or any((g.get("detail") or {}).get("cursor_enabled") for g in gates):
        bad.append("feedback_not_off")
    settles = [m["detail"]["settle_ms"] for m in trace if m["phase"] == "focus.settle_start"]
    if s.get("driver_env_trace_set") and (not settles or any(v != DEFAULT_SETTLE_MS for v in settles)):
        bad.append(f"settle={settles}")
    polls = {e.get("poll_ms") for e in trial["events"] if e["event"] == "sleep_start"}
    if polls and polls != {POLL_MS}:
        bad.append(f"poll={polls}")
    return bad


def is_valid(trial: dict[str, Any]) -> tuple[bool, list[str]]:
    s = trial["summary"]
    reasons = []
    if not s.get("oracle_exact_match"):
        reasons.append("oracle_not_satisfied")
    if s.get("completion_mutations") != 1:
        reasons.append(f"completion_mutations={s.get('completion_mutations')}")
    if s.get("outcome") != "verified":
        reasons.append(f"runner_outcome={s.get('outcome')}")
    reasons += forced_path(trial)
    if decompose(trial) is None:
        reasons.append("T_undefined")
    return (not reasons), reasons


# ── statistics ────────────────────────────────────────────────────────────────

def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def p95(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def boot_ci(n: int, stat: Callable[[list[int]], float | None]) -> list[float] | None:
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
    lo = vals[int(math.floor(0.025 * (len(vals) - 1)))]
    hi = vals[int(math.ceil(0.975 * (len(vals) - 1)))]
    return [lo, hi]


def paired_diff(a: list[float], b: list[float]) -> dict[str, Any]:
    d = [x - y for x, y in zip(a, b)]
    return {"n": len(d), "median": median(d),
            "ci95": boot_ci(len(d), lambda idx: statistics.median([d[i] for i in idx])),
            "min": min(d) if d else None, "max": max(d) if d else None,
            "positive": sum(1 for x in d if x > 0)}


def ols(xs: list[float], ys: list[float]) -> tuple[float, float, float] | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return slope, intercept, (1 - ss_res / ss_tot) if ss_tot else 0.0


def regression(xs: list[float], ys: list[float]) -> dict[str, Any] | None:
    fit = ols(xs, ys)
    if fit is None:
        return None

    def stat_k(k: int) -> Callable[[list[int]], float | None]:
        def f(idx: list[int]) -> float | None:
            r = ols([xs[i] for i in idx], [ys[i] for i in idx])
            return None if r is None else r[k]
        return f

    return {"n": len(xs), "slope_ms_per_px": fit[0], "intercept_ms": fit[1], "r2": fit[2],
            "slope_ci95": boot_ci(len(xs), stat_k(0)), "intercept_ci95": boot_ci(len(xs), stat_k(1)),
            "x_min": min(xs), "x_max": max(xs), "distinct_x": len({round(x, 3) for x in xs})}

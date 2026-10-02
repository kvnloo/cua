"""BUG-01 part B analysis: recompute every part B number from raw/part-b/.

Joins the probe's per-call rows (calls.jsonl) with the Driver's env-gated
counter lines (counters-<series>-bNN.jsonl) by tool name and time window,
then fits the pre-registered slopes with a seeded moving-block bootstrap.

usage: analyze_b.py [packet_dir]  -> prints the part B summary JSON
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SEED = 20261002
RESAMPLES = 10000
BLOCK = 25


def ols(xs: list[float], ys: list[float], dummy: list[float] | None = None) -> float:
    """Slope of y on x, with an optional 0/1 intercept shift (call type)."""
    if dummy is None:
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    # Within-type demeaning == OLS with a type intercept (Frisch-Waugh).
    groups: dict[float, list[int]] = defaultdict(list)
    for i, d in enumerate(dummy):
        groups[d].append(i)
    xd, yd = [0.0] * len(xs), [0.0] * len(ys)
    for idx in groups.values():
        mx = sum(xs[i] for i in idx) / len(idx)
        my = sum(ys[i] for i in idx) / len(idx)
        for i in idx:
            xd[i], yd[i] = xs[i] - mx, ys[i] - my
    sxx = sum(x * x for x in xd)
    return sum(x * y for x, y in zip(xd, yd)) / sxx if sxx else 0.0


def mbb_indices(n: int, rng: random.Random) -> list[int]:
    out: list[int] = []
    while len(out) < n:
        start = rng.randrange(0, max(1, n - BLOCK + 1))
        out.extend(range(start, min(n, start + BLOCK)))
    return out[:n]


def pooled_slope_ci(sessions: list[dict[str, list[float]]], key: str, xkey: str, typed: bool, scale: float, seed_offset: int) -> dict[str, Any]:
    """Mean of per-session OLS slopes; CI from a moving-block bootstrap within each session."""
    per = [ols(s[xkey], s[key], s["is_click"] if typed else None) * scale for s in sessions]
    rng = random.Random(SEED + seed_offset)
    boots = []
    for _ in range(RESAMPLES):
        vals = []
        for s in sessions:
            idx = mbb_indices(len(s[xkey]), rng)
            vals.append(ols([s[xkey][i] for i in idx], [s[key][i] for i in idx], [s["is_click"][i] for i in idx] if typed else None) * scale)
        boots.append(sum(vals) / len(vals))
    boots.sort()
    return {"pooled": round(sum(per) / len(per), 6), "per_session": [round(p, 6) for p in per], "ci95": [round(boots[int(0.025 * RESAMPLES)], 6), round(boots[int(0.975 * RESAMPLES) - 1], 6)], "boot": boots}


def strip(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k != "boot"}


def diff_ci(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(SEED + 999)
    bb = b["boot"][:]
    rng.shuffle(bb)
    diffs = sorted(x - y for x, y in zip(a["boot"], bb))
    return {"pooled": round(a["pooled"] - b["pooled"], 6), "ci95": [round(diffs[int(0.025 * RESAMPLES)], 6), round(diffs[int(0.975 * RESAMPLES) - 1], 6)]}


def load(raw: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows = [json.loads(line) for line in (raw / "calls.jsonl").read_text().splitlines()]
    counters = {p.stem[len("counters-") :]: [json.loads(line) for line in p.read_text().splitlines()] for p in sorted(raw.glob("counters-*.jsonl"))}
    env = json.loads((raw / "session-env.json").read_text())
    return rows, counters, env


def join(rows: list[dict[str, Any]], counters: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], int]:
    calls = [r for r in rows if r.get("event") == "call"]
    by_block: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in calls:
        by_block[f"{r['series']}-b{r['block']:02d}"].append(r)
    unmatched = 0
    for key, rs in by_block.items():
        lines = counters.get(key, [])
        ptr = 0
        for r in sorted(rs, key=lambda r: r["t_start_ms"]):
            r["counter"] = None
            for j in range(ptr, len(lines)):
                line = lines[j]
                if line["tool"] == r["tool"] and r["t_start_ms"] - 2 <= line["t_unix_ms"] <= r["t_end_ms"] + 2:
                    r["counter"] = line
                    ptr = j + 1
                    break
            if r["counter"] is None:
                unmatched += 1
    return calls, unmatched


def series_arrays(calls: list[dict[str, Any]], series: str, xkey: str) -> dict[str, list[float]]:
    rs = sorted((r for r in calls if r["series"] == series and r["kind"] in ("snapshot", "click") and r.get("counter")), key=lambda r: r[xkey])
    return {
        "x": [float(r[xkey]) for r in rs],
        "k": [float(r["k"]) for r in rs],
        "is_click": [1.0 if r["kind"] == "click" else 0.0 for r in rs],
        "attach_minus_detach": [float(r["counter"]["attach_sent"] - r["counter"]["detach_sent"]) for r in rs],
        "live_sessions": [float(r["counter"]["live_sessions"]) for r in rs],
        "events_delta": [float(r["counter"]["events_delta"]) for r in rs],
        "frames_delta": [float(r["counter"]["replies_delta"] + r["counter"]["events_delta"]) for r in rs],
        "latency_ms": [float(r["elapsed_ms"]) for r in rs],
        "attach_delta": [],
    }


def main(packet: Path) -> dict[str, Any]:
    raw = packet / "raw" / "part-b"
    rows, counters, env = load(raw)
    calls, unmatched = join(rows, counters)
    series = sorted({r["series"] for r in calls})
    L = [s for s in series if s.startswith("L")]
    C = [s for s in series if s.startswith("C")]
    measured = [r for r in calls if r["kind"] in ("snapshot", "click")]
    out: dict[str, Any] = {
        "schema": "cua.bug01.part_b.summary.v1",
        "driver_sha256": env.get("driver_sha256"),
        "driver_version_in_session": env.get("driver_version_in_session"),
        "chrome_version_in_session": env.get("chrome_version_in_session"),
        "series_order": env.get("series"),
        "calls_measured": len(measured),
        "calls_accepted": sum(1 for r in measured if r.get("accepted")),
        "calls_failed": [{"series": r["series"], "block": r["block"], "k": r["k"], "tool": r["tool"], "refusal": r.get("refusal"), "transport_error": r.get("transport_error")} for r in measured if not r.get("accepted")],
        "noop_ref_found": sum(1 for r in measured if r.get("noop_ref_found")),
        "snapshots": sum(1 for r in measured if r["kind"] == "snapshot"),
        "click_route": dict(sorted({str(r.get("route")): sum(1 for q in measured if q["kind"] == "click" and str(q.get("route")) == str(r.get("route"))) for r in measured if r["kind"] == "click"}.items())),
        "unmatched_calls_without_counter_line": unmatched,
        "loadavg1_range": [min(r["loadavg1"] for r in measured), max(r["loadavg1"] for r in measured)],
        "loadavg1_median": statistics.median(r["loadavg1"] for r in measured),
        "harness_errors": [r for r in rows if r.get("event", "").endswith("harness_error")],
    }
    Ls = [series_arrays(calls, s, "k") for s in L]
    Cs = [series_arrays(calls, s, "s") for s in C]
    for s in Ls + Cs:
        s["xk"] = s["x"]
    # Per-call attach/detach commands (deltas).
    def per_call(series_name: str) -> dict[str, Any]:
        rs = sorted((r for r in calls if r["series"] == series_name and r.get("counter")), key=lambda r: r["t_start_ms"])
        a = d = 0
        prev: dict[str, int] = {}
        for r in rs:
            key = f"b{r['block']}"
            base = prev.get(key + "a", 0), prev.get(key + "d", 0)
            ca, cd = r["counter"]["attach_sent"], r["counter"]["detach_sent"]
            if r["kind"] in ("snapshot", "click"):
                a += ca - base[0]
                d += cd - base[1]
            prev[key + "a"], prev[key + "d"] = ca, cd
        n = sum(1 for r in rs if r["kind"] in ("snapshot", "click"))
        return {"calls": n, "attach_sent_during_calls": a, "detach_sent_during_calls": d}

    out["attach_detach_per_series"] = {s: per_call(s) for s in L + C}
    m1_live = pooled_slope_ci(Ls, "live_sessions", "k", False, 100.0, 1)
    m1_amd = pooled_slope_ci(Ls, "attach_minus_detach", "k", False, 100.0, 2)
    m2 = pooled_slope_ci(Ls, "events_delta", "k", False, 100.0, 3)
    m3_L = pooled_slope_ci(Ls, "latency_ms", "k", True, 100.0, 4)
    m3_C = pooled_slope_ci(Cs, "latency_ms", "x", True, 100.0, 5)
    c_live_s = pooled_slope_ci(Cs, "live_sessions", "x", False, 100.0, 6)
    c_events_s = pooled_slope_ci(Cs, "events_delta", "x", False, 100.0, 7)
    # Control within-block index (fresh session each block): live sessions vs k.
    c_live_k = pooled_slope_ci([{**s, "x": s["k"]} for s in Cs], "live_sessions", "x", False, 100.0, 8)
    out["M1_live_sessions_slope_per_100_calls_L"] = strip(m1_live)
    out["M1_attach_minus_detach_slope_per_100_calls_L"] = strip(m1_amd)
    out["M1_C_live_sessions_slope_per_100_calls_series_index"] = strip(c_live_s)
    out["M1_C_live_sessions_slope_per_100_calls_within_block"] = strip(c_live_k)
    out["M1_live_sessions_end_of_L"] = [s["live_sessions"][-1] for s in Ls]
    out["M1_live_sessions_max_C"] = max(max(s["live_sessions"]) for s in Cs)
    out["M2_events_delta_slope_per_100_calls_L"] = strip(m2)
    out["M2_C_events_delta_slope_per_100_calls_series_index"] = strip(c_events_s)
    out["M2_events_per_call_L"] = {"mean": round(statistics.mean(v for s in Ls for v in s["events_delta"]), 4), "first_50_mean": round(statistics.mean(v for s in Ls for v in s["events_delta"][:50]), 4), "last_50_mean": round(statistics.mean(v for s in Ls for v in s["events_delta"][-50:]), 4)}
    out["M2_events_per_call_C"] = {"mean": round(statistics.mean(v for s in Cs for v in s["events_delta"]), 4)}
    out["M3_latency_slope_ms_per_100_calls_L"] = strip(m3_L)
    out["M3_latency_slope_ms_per_100_calls_C_series_index"] = strip(m3_C)
    out["M3_latency_slope_L_minus_C_ms_per_100_calls"] = diff_ci(m3_L, m3_C)

    def med(vals: list[float]) -> float:
        return round(statistics.median(vals), 3)

    lat: dict[str, Any] = {}
    for arm, group in (("L", Ls), ("C", Cs)):
        for kind, flag in (("snapshot", 0.0), ("click", 1.0)):
            vals = [y for s in group for y, c in zip(s["latency_ms"], s["is_click"]) if c == flag]
            first = [y for s in group for y, c, k in zip(s["latency_ms"], s["is_click"], s["k"]) if c == flag and (k < 50 if arm == "L" else True)]
            last = [y for s in group for y, c, k in zip(s["latency_ms"], s["is_click"], s["k"]) if c == flag and (k >= 250 if arm == "L" else True)]
            lat[f"{arm}_{kind}"] = {"n": len(vals), "median_ms": med(vals), "p95_ms": round(sorted(vals)[int(0.95 * len(vals)) - 1], 3)}
            if arm == "L":
                lat[f"{arm}_{kind}"].update({"median_k_lt_50": med(first), "median_k_ge_250": med(last)})
    out["M3_latency_descriptive"] = lat

    rss = [r for r in rows if r.get("event") == "rss"]
    m4: dict[str, Any] = {}
    for s in L:
        pts = sorted((r for r in rss if r["series"] == s), key=lambda r: r["k"])
        xs = [float(r["k"]) for r in pts]
        m4[s] = {
            "samples": len(pts),
            "pss_kb_slope_per_100_calls": round(ols(xs, [float(r["pss_kb_total"]) for r in pts]) * 100, 2),
            "rss_kb_slope_per_100_calls": round(ols(xs, [float(r["rss_kb_total"]) for r in pts]) * 100, 2),
            "renderer_pss_kb_slope_per_100_calls": round(ols(xs, [float(r["renderer_pss_kb"]) for r in pts]) * 100, 2),
            "pss_kb_first_last": [pts[0]["pss_kb_total"], pts[-1]["pss_kb_total"]],
            "renderer_pss_kb_first_last": [pts[0]["renderer_pss_kb"], pts[-1]["renderer_pss_kb"]],
        }
    c_deltas = []
    c_rdeltas = []
    for s in C:
        blocks = defaultdict(list)
        for r in rss:
            if r["series"] == s:
                blocks[r["block"]].append(r)
        for pts in blocks.values():
            pts.sort(key=lambda r: r["k"])
            if len(pts) >= 2:
                c_deltas.append(pts[-1]["pss_kb_total"] - pts[0]["pss_kb_total"])
                c_rdeltas.append(pts[-1]["renderer_pss_kb"] - pts[0]["renderer_pss_kb"])
    m4["L_pooled_pss_kb_slope_per_100_calls"] = round(statistics.mean(m4[s]["pss_kb_slope_per_100_calls"] for s in L), 2)
    m4["L_pooled_renderer_pss_kb_slope_per_100_calls"] = round(statistics.mean(m4[s]["renderer_pss_kb_slope_per_100_calls"] for s in L), 2)
    m4["C_blocks"] = len(c_deltas)
    m4["C_pss_kb_delta_per_10_call_block_median"] = statistics.median(c_deltas) if c_deltas else None
    m4["C_pss_kb_per_100_calls_equiv"] = round(statistics.mean(c_deltas) * 10, 2) if c_deltas else None
    m4["C_renderer_pss_kb_per_100_calls_equiv"] = round(statistics.mean(c_rdeltas) * 10, 2) if c_rdeltas else None
    out["M4_chrome_memory"] = m4

    probes = [r for r in calls if r["kind"] in ("nav_probe", "nav_probe_setup") and r.get("counter")]
    out["M5_navigation_probe"] = {
        "L": [{"series": r["series"], "k": r["k"], "live_sessions": r["counter"]["live_sessions"], "events_delta": r["counter"]["events_delta"], "elapsed_ms": round(r["elapsed_ms"], 3)} for r in probes if r["series"].startswith("L") and r["kind"] == "nav_probe"],
        "C_setup_navigate": {"n": sum(1 for r in probes if r["series"].startswith("C")), "events_delta_values": sorted({r["counter"]["events_delta"] for r in probes if r["series"].startswith("C")}), "live_sessions_values": sorted({r["counter"]["live_sessions"] for r in probes if r["series"].startswith("C")}), "elapsed_ms_median": med([r["elapsed_ms"] for r in probes if r["series"].startswith("C")])},
    }
    nav_L = out["M5_navigation_probe"]["L"]
    out["M5_navigation_probe"]["L_events_delta_slope_vs_live_sessions"] = round(ols([float(p["live_sessions"]) for p in nav_L], [float(p["events_delta"]) for p in nav_L]), 6) if len(nav_L) > 1 else None

    # Exploratory, not pre-registered: the event burst a navigation causes is
    # delivered during the NEXT call (the first snapshot after the probe).
    post = []
    for r in calls:
        if r["kind"] in ("nav_probe", "nav_probe_setup") and r.get("counter"):
            nxt = [q for q in calls if q["series"] == r["series"] and q["block"] == r["block"] and q["kind"] in ("snapshot", "click") and q["t_start_ms"] > r["t_end_ms"] and q.get("counter")]
            if nxt:
                q = min(nxt, key=lambda q: q["t_start_ms"])
                post.append({"series": r["series"], "probe_k": r["k"] if r["k"] is not None else -1, "arm": r["series"][0], "live_sessions_at_probe": r["counter"]["live_sessions"], "events_next_call": q["counter"]["events_delta"], "next_call_kind": q["kind"], "next_call_ms": round(q["elapsed_ms"], 3)})
    post_L = [p for p in post if p["arm"] == "L" and p["probe_k"] >= 0]
    post_C = [p for p in post if p["arm"] == "C"]
    out["exploratory_not_preregistered_post_navigation_burst"] = {
        "L": post_L,
        "C": {"n": len(post_C), "events_next_call_values": sorted({p["events_next_call"] for p in post_C}), "live_sessions_values": sorted({p["live_sessions_at_probe"] for p in post_C}), "next_call_ms_median": med([p["next_call_ms"] for p in post_C]) if post_C else None},
        "L_events_next_call_slope_vs_live_sessions": round(ols([float(p["live_sessions_at_probe"]) for p in post_L], [float(p["events_next_call"]) for p in post_L]), 6) if len(post_L) > 1 else None,
        "L_next_call_ms_by_probe_k": {str(k): med([p["next_call_ms"] for p in post_L if p["probe_k"] == k]) for k in sorted({p["probe_k"] for p in post_L})},
    }

    def excludes_zero(ci: list[float]) -> bool:
        return ci[0] > 0 or ci[1] < 0

    m1_pos = (m1_amd["pooled"] > 0 and m1_amd["ci95"][0] > 0) or (m1_live["pooled"] > 0 and m1_live["ci95"][0] > 0)
    m1_flat = not excludes_zero(m1_amd["ci95"]) and not excludes_zero(m1_live["ci95"])
    m2_pos = m2["pooled"] > 0 and m2["ci95"][0] > 0
    m2_flat = not excludes_zero(m2["ci95"])
    if m1_pos and m2_pos:
        disposition = "CONFIRMED"
    elif m1_flat and m2_flat:
        disposition = "REFUTED"
    elif m1_pos and m2_flat:
        disposition = "ACCUMULATION_ONLY"
    else:
        disposition = "UNRESOLVED"
    out["gates"] = {"M1_positive_ci_excludes_0": m1_pos, "M1_flat": m1_flat, "M2_positive_ci_excludes_0": m2_pos, "M2_flat": m2_flat, "disposition": disposition}
    return out


if __name__ == "__main__":
    packet = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    print(json.dumps(main(packet), indent=1, sort_keys=True))

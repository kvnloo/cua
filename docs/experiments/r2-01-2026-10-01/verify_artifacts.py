"""Recompute every R2-01 headline number from raw/ and check the packet.

    python verify_artifacts.py          # verify feedback-ab-summary.json + README
    python verify_artifacts.py --write  # (re)write feedback-ab-summary.json

Standard library only. All times come from raw caller events, the Driver's
CUA_DRIVER_PHASE_TRACE_FILE marks and the fixture journal; all three use the
host CLOCK_MONOTONIC (Python time.monotonic_ns / libc clock_gettime).
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
SUMMARY = ROOT / "feedback-ab-summary.json"
SEED = 20261001
RESAMPLES = 10000

PHASES = [
    ("transport_in", "caller_send", "dispatch.enter"),
    ("dispatch_pre", "dispatch.enter", "click.enter"),
    ("lock", "click.enter", "click.lock_acquired"),
    ("revalidate", "click.lock_acquired", "click.revalidated"),
    ("ref_resolve", "click.revalidated", "click.ref_resolved"),
    ("dom_resolve", "click.ref_resolved", "click.dom_resolved"),
    ("scroll", "click.dom_resolved", "click.scrolled"),
    ("box_model", "click.scrolled", "click.box_model"),
    ("pre_visual_gap", "click.box_model", "viz.enter"),
    ("visualization", "viz.enter", "viz.exit"),
    ("pre_cdp_gap", "viz.exit", "click.cdp_send"),
    ("cdp", "click.cdp_send", "click.cdp_response"),
    ("post_cdp", "click.cdp_response", "dispatch.exit"),
    ("transport_out", "dispatch.exit", "caller_return"),
]
VIZ_SUB = [
    ("viz_visibility_eval", "viz.enter", "viz.visibility_done"),
    ("viz_layout_metrics", "viz.visibility_done", "viz.layout_done"),
    ("viz_platform", "viz.layout_done", "viz.exit"),
]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def ms(ns: int) -> float:
    return ns / 1e6


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[max(0, -(-95 * len(s) // 100) - 1)]


def window(trace: list[dict], tool: str) -> list[dict]:
    """Marks between the browser_<tool> dispatch.enter and its dispatch.exit."""
    out, inside = [], False
    for m in trace:
        d = m.get("detail") or {}
        if m["phase"] == "dispatch.enter" and d.get("tool") == tool:
            inside, out = True, [m]
            continue
        if inside:
            out.append(m)
            if m["phase"] == "dispatch.exit" and d.get("tool") == tool:
                return out
    return []


def first(marks: list[dict], phase: str) -> dict | None:
    return next((m for m in marks if m["phase"] == phase), None)


def analyze_trial(path: Path) -> dict:
    events = load_jsonl(path)
    summary = events[-1]
    assert summary["event"] == "summary"
    trace = load_jsonl(ROOT / "raw" / summary["driver_trace"]) if (ROOT / "raw" / summary["driver_trace"]).exists() else []
    trace.sort(key=lambda m: m["seq"])
    row = {k: summary.get(k) for k in ("trial", "kind", "arm", "outcome", "forced_path_ok", "loadavg_before",
                                        "browser_alive_after_close")}
    row["verified"] = summary.get("outcome") == "verified"
    row["trial_wall_ms"] = ms(summary["trial_wall_ns"])

    def call(label: str):
        s = next((e for e in events if e["event"] == "call_send" and e.get("label") == label), None)
        r = next((e for e in events if e["event"] == "call_return" and e.get("label") == label), None)
        return s, r

    ts, tr = call("type")
    if ts and tr:
        row["type_span_ms"] = ms(tr["t_mono_ns"] - ts["t_mono_ns"])
        tw = window(trace, "browser_type")
        ve, vx = first(tw, "viz.enter"), first(tw, "viz.exit")
        row["type_visualization_ms"] = ms(vx["t_mono_ns"] - ve["t_mono_ns"]) if ve and vx else None
    if summary["kind"] != "measured":
        row["stale_refused"] = summary.get("stale_refused")
        row["stale_code"] = summary.get("stale_code")
        row["journal_submits"] = sum(1 for j in summary["journal"] if j["event"] == "submit")
        return row

    cs, cr = call("click")
    if not (cs and cr and cr.get("ok")):
        row["click_ok"] = False
        return row
    row["click_ok"] = True
    row["click_route"] = cr.get("route")
    row["click_effect"] = cr.get("effect")
    row["click_span_ms"] = ms(cr["t_mono_ns"] - cs["t_mono_ns"])
    w = window(trace, "browser_click")
    t = {"caller_send": cs["t_mono_ns"], "caller_return": cr["t_mono_ns"]}
    for m in w:
        t.setdefault(m["phase"], m["t_mono_ns"])
    # dispatch.exit is the last mark of the window
    if w:
        t["dispatch.exit"] = w[-1]["t_mono_ns"]
    # clock-alignment sanity: caller send < dispatch.enter < dispatch.exit < caller return
    row["clock_order_ok"] = bool(w) and t["caller_send"] <= t["dispatch.enter"] <= t["dispatch.exit"] <= t["caller_return"]
    for name, a, b in PHASES + VIZ_SUB:
        row[name + "_ms"] = ms(t[b] - t[a]) if a in t and b in t else None
    gate = first(w, "platform.gate")
    row["trace_route"] = (first(w, "click.enter") or {}).get("detail", {}).get("route")
    row["cursor_enabled"] = (gate or {}).get("detail", {}).get("cursor_enabled")
    aws, awe = first(w, "overlay.arrival_wait_start"), first(w, "overlay.arrival_wait_end")
    row["arrival_wait_ms"] = ms(awe["t_mono_ns"] - aws["t_mono_ns"]) if aws and awe else None
    row["arrived"] = (awe or {}).get("detail", {}).get("arrived")
    row["animate_marks"] = sum(1 for m in w if m["phase"] in ("platform.animate_start", "overlay.arrival_wait_start"))
    if summary["arm"] == "ON":
        row["feedback_path_ok"] = row["cursor_enabled"] is True and aws is not None and awe is not None
    else:
        row["feedback_path_ok"] = row["cursor_enabled"] is False and row["animate_marks"] == 0
    named = [row[n + "_ms"] for n, _, _ in PHASES]
    row["named_sum_ms"] = sum(x for x in named if x is not None) if all(x is not None for x in named) else None
    submits = [j for j in summary["journal"] if j["event"] == "submit"]
    row["journal_submits"] = len(submits)
    if submits and "click.cdp_send" in t:
        row["mutation_after_cdp_send_ms"] = ms(submits[0]["t_mono_ns"] - t["click.cdp_send"])
        row["mutation_after_cdp_response_ms"] = ms(submits[0]["t_mono_ns"] - t["click.cdp_response"])
        row["mutation_after_caller_return_ms"] = ms(submits[0]["t_mono_ns"] - t["caller_return"])
        row["journal_token_match"] = submits[0]["value_sha16"] == summary["token_sha16"]
    ver = next((e for e in events if e["event"] == "oracle_return" and e["label"].startswith("verify")
                and e.get("submitted_sha16") == summary["token_sha16"]), None)
    if ver:
        row["verify_after_return_ms"] = ms(ver["t_mono_ns"] - cr["t_mono_ns"])
        row["verified_outcome_ms"] = ms(ver["t_mono_ns"] - cs["t_mono_ns"])
        row["verify_reads"] = sum(1 for e in events if e["event"] == "oracle_return" and e["label"].startswith("verify")
                                  and e["t_mono_ns"] <= ver["t_mono_ns"])
    return row


def bootstrap_median_ci(diffs: list[float]) -> tuple[float, float]:
    rng = random.Random(SEED)
    n = len(diffs)
    meds = sorted(median([diffs[rng.randrange(n)] for _ in range(n)]) for _ in range(RESAMPLES))
    return meds[int(0.025 * RESAMPLES)], meds[int(0.975 * RESAMPLES) - 1]


def stat(rows: list[dict], key: str) -> dict:
    xs = [r[key] for r in rows if r.get(key) is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "median": round(median(xs), 3), "p95_nearest_rank": round(p95(xs), 3),
            "min": round(min(xs), 3), "max": round(max(xs), 3)}


def compute() -> dict:
    trial_files = sorted((RAW / "trials").glob("*.jsonl"))
    trial_files = [p for p in trial_files if not p.name.endswith(".driver-trace.jsonl")]
    rows = [analyze_trial(p) for p in trial_files]
    measured = [r for r in rows if r["kind"] == "measured"]
    controls = [r for r in rows if r["kind"] != "measured"]
    arms = {a: [r for r in measured if r["arm"] == a] for a in ("ON", "OFF")}
    out: dict = {"schema": "cua.r2-01.summary.v1", "n_trials_measured": len(measured), "arms": {}}
    keys = ["click_span_ms", "visualization_ms", "arrival_wait_ms", "viz_platform_ms", "viz_visibility_eval_ms",
            "viz_layout_metrics_ms", "transport_in_ms", "dispatch_pre_ms", "lock_ms", "revalidate_ms",
            "ref_resolve_ms", "dom_resolve_ms", "scroll_ms", "box_model_ms", "pre_visual_gap_ms", "pre_cdp_gap_ms",
            "cdp_ms", "post_cdp_ms", "transport_out_ms", "mutation_after_cdp_send_ms",
            "mutation_after_cdp_response_ms", "mutation_after_caller_return_ms", "verify_after_return_ms",
            "verified_outcome_ms", "type_span_ms", "type_visualization_ms", "trial_wall_ms"]
    for a, rs in arms.items():
        out["arms"][a] = {
            "n": len(rs),
            "verified": sum(r["verified"] for r in rs),
            "click_ok": sum(bool(r.get("click_ok")) for r in rs),
            "forced_path_ok": sum(r["forced_path_ok"] is True and r.get("trace_route") == "dom_event"
                                  and r.get("click_route") == "dom" for r in rs),  # public route name for input_route=dom_event
            "feedback_path_ok": sum(bool(r.get("feedback_path_ok")) for r in rs),
            "clock_order_ok": sum(bool(r.get("clock_order_ok")) for r in rs),
            "journal_token_match": sum(bool(r.get("journal_token_match")) for r in rs),
            "browser_alive_after_close": sum(r.get("browser_alive_after_close") is True for r in rs),
            "metrics": {k: stat(rs, k) for k in keys},
        }
    # pairs
    by_pair: dict[str, dict] = {}
    for r in measured:
        m = re.match(r"p(\d+)[ab]-measured-(ON|OFF)", r["trial"])
        if m:
            by_pair.setdefault(m.group(1), {})[m.group(2)] = r
    diffs, viz_d, complete = [], [], 0
    for k, pr in sorted(by_pair.items()):
        if "ON" in pr and "OFF" in pr and pr["ON"].get("click_span_ms") is not None and pr["OFF"].get("click_span_ms") is not None:
            complete += 1
            diffs.append(pr["ON"]["click_span_ms"] - pr["OFF"]["click_span_ms"])
            viz_d.append(pr["ON"]["visualization_ms"] - pr["OFF"]["visualization_ms"])
    lo, hi = bootstrap_median_ci(diffs) if diffs else (None, None)
    on_med = out["arms"]["ON"]["metrics"]["click_span_ms"].get("median")
    off_med = out["arms"]["OFF"]["metrics"]["click_span_ms"].get("median")
    on_viz = out["arms"]["ON"]["metrics"]["visualization_ms"].get("median")
    med_d = median(diffs) if diffs else None
    out["paired"] = {
        "pairs_planned": 24, "pairs_complete": complete,
        "median_diff_on_minus_off_ms": round(med_d, 3) if diffs else None,
        "bootstrap95_ci_ms": [round(lo, 3), round(hi, 3)] if diffs else None,
        "min_diff_ms": round(min(diffs), 3) if diffs else None, "max_diff_ms": round(max(diffs), 3) if diffs else None,
        "pairs_on_slower": sum(d > 0 for d in diffs),
        "median_visualization_diff_ms": round(median(viz_d), 3) if viz_d else None,
        "median_diff_minus_visualization_diff_ms": round(median([d - v for d, v in zip(diffs, viz_d)]), 3) if diffs else None,
        "seed": SEED, "resamples": RESAMPLES,
    }
    for key in ("type_span_ms", "verified_outcome_ms", "trial_wall_ms"):
        ds = [pr["ON"][key] - pr["OFF"][key] for pr in by_pair.values()
              if "ON" in pr and "OFF" in pr and pr["ON"].get(key) is not None and pr["OFF"].get(key) is not None]
        out["paired"]["secondary_" + key] = {"n": len(ds), "median_diff_on_minus_off_ms": round(median(ds), 3) if ds else None,
                                              "bootstrap95_ci_ms": [round(x, 3) for x in bootstrap_median_ci(ds)] if ds else None}
    # gates (PREREG decision_gates)
    n_on, n_off = out["arms"]["ON"]["n"], out["arms"]["OFF"]["n"]
    ver_ok = n_on and n_off and out["arms"]["ON"]["verified"] / n_on >= 0.9 and out["arms"]["OFF"]["verified"] / n_off >= 0.9
    feedback_exercised = n_on and out["arms"]["ON"]["feedback_path_ok"] / n_on >= 0.8
    g = {
        "verified_ge_90pct_each_arm": bool(ver_ok),
        "feedback_path_exercised_ge_80pct_on": bool(feedback_exercised),
        "median_diff_ge_50pct_on_span": bool(diffs and med_d >= 0.5 * on_med),
        "median_diff_lt_20pct_on_span": bool(diffs and med_d < 0.2 * on_med),
        "ci_excludes_zero": bool(diffs and (lo > 0 or hi < 0)),
        "on_visualization_ge_50pct_on_span": bool(on_viz is not None and on_viz >= 0.5 * on_med),
        "on_median_click_span_ge_500ms": bool(on_med is not None and on_med >= 500),
        "diff_share_of_on_span": round(med_d / on_med, 4) if diffs else None,
        "on_visualization_share_of_on_span": round(on_viz / on_med, 4) if on_viz is not None else None,
    }
    if not feedback_exercised:
        disp = "BLOCKED"
    elif g["verified_ge_90pct_each_arm"] and g["median_diff_ge_50pct_on_span"] and g["ci_excludes_zero"] and g["on_visualization_ge_50pct_on_span"]:
        disp = "KEEP_H1"
    elif g["median_diff_lt_20pct_on_span"] or not g["ci_excludes_zero"]:
        disp = "KILL_H1"
    else:
        disp = "REVISE"
    g["disposition"] = disp
    out["gates"] = g
    out["headline"] = {"on_median_click_span_ms": on_med, "off_median_click_span_ms": off_med,
                       "on_median_visualization_ms": on_viz}
    # OFF-arm residual localization: largest non-visualization phase in each arm
    for a in ("ON", "OFF"):
        mets = out["arms"][a]["metrics"]
        non_viz = {n: mets[n + "_ms"].get("median") for n, _, _ in PHASES if n != "visualization"}
        out["arms"][a]["largest_non_visualization_phase"] = max(non_viz, key=lambda n: non_viz[n] or 0)
        out["arms"][a]["named_phase_coverage"] = "contiguous marks; named phases telescope to the full caller span (unattributed 0 by construction)"
    out["controls"] = {
        "no_submit": {"n": sum(r["kind"] == "no_submit" for r in controls),
                      "unchanged": sum(r["kind"] == "no_submit" and r["outcome"] == "unchanged" and r["journal_submits"] == 0 for r in controls)},
        "stale_ref": {"n": sum(r["kind"] == "stale_ref" for r in controls),
                      "refused_unchanged": sum(r["kind"] == "stale_ref" and r["outcome"] == "refused_unchanged" and r["journal_submits"] == 0 for r in controls),
                      "codes": sorted({str(r.get("stale_code")) for r in controls if r["kind"] == "stale_ref"})},
    }
    out["loadavg_1m_range_measured"] = [min(float(r["loadavg_before"].split()[0]) for r in measured),
                                        max(float(r["loadavg_before"].split()[0]) for r in measured)] if measured else None
    out["trials"] = rows
    return out


def main() -> None:
    result = compute()
    text = json.dumps(result, indent=1, sort_keys=True) + "\n"
    if "--write" in sys.argv:
        SUMMARY.write_text(text)
        print("wrote", SUMMARY.name)
        return
    stored = json.loads(SUMMARY.read_text())
    assert stored == json.loads(text), "summary JSON does not match a recomputation from raw/"
    readme = (ROOT / "README.md").read_text()
    h, p, g = result["headline"], result["paired"], result["gates"]
    for value in (h["on_median_click_span_ms"], h["off_median_click_span_ms"], h["on_median_visualization_ms"],
                  p["median_diff_on_minus_off_ms"], *p["bootstrap95_ci_ms"]):
        assert f"{value:.1f}" in readme, f"README lacks headline value {value:.1f}"
    assert g["disposition"] in readme, "README lacks the disposition"
    for a in ("ON", "OFF"):
        s = result["arms"][a]
        assert f"{s['verified']}/{s['n']}" in readme, f"README lacks {a} verified N of M"
    # privacy: no absolute local paths or host name in the packet
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".txt", ".log", ".py"}:
            body = path.read_text(errors="replace")
            for root in ("/" + "home/", "/" + "mnt/", "/" + "tmp/claude"):
                assert root not in body, f"absolute local path in {path.relative_to(ROOT)}"
    print(f"R2-01 checks passed: disposition {g['disposition']}; ON {h['on_median_click_span_ms']:.1f} ms vs "
          f"OFF {h['off_median_click_span_ms']:.1f} ms; median paired diff {p['median_diff_on_minus_off_ms']:.1f} ms "
          f"CI {p['bootstrap95_ci_ms']}")


if __name__ == "__main__":
    main()

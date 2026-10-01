"""Recompute every R2-06 number from raw/ (stdlib only).

usage: python3 analyze.py [--write]   (--write refreshes r2-06-summary.json)
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
SUBMIT = "button[type=submit]"
BUTTON_EVENTS = ("RawButtonPress", "RawButtonRelease", "ButtonPress", "ButtonRelease")


def load_phase(phase: str) -> tuple[list[dict], list[dict], dict[int, dict]]:
    d = RAW / phase
    trials, errors, blocks = [], [], {}
    for f in sorted(d.glob("*.jsonl")):
        rec = json.loads(f.read_text().splitlines()[0])
        (errors if rec.get("event") == "trial_harness_error" else trials).append(rec)
    for f in sorted(d.glob("block-*.json")):
        if "harness-error" in f.name:
            continue
        b = json.loads(f.read_text())
        blocks[b["block"]] = b
    trials.sort(key=lambda r: r["index"])
    return trials, errors, blocks


def nearest_rank(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(1, -(-int(q * 100) * len(s) // 100))
    return s[min(k, len(s)) - 1]


def driver_point(rec: dict) -> tuple[float, float] | None:
    st = rec["click"].get("structured") or {}
    if isinstance(st.get("x"), (int, float)):
        return float(st["x"]), float(st["y"])
    m = re.search(r"clicked \(([-\d.]+), ([-\d.]+)\)", st.get("summary") or rec["click"].get("text") or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def inside(pt, rect) -> bool | None:
    if not pt or not rect:
        return None
    return rect["left"] <= pt[0] <= rect["right"] and rect["top"] <= pt[1] <= rect["bottom"]


def trace(rec: dict, blocks: dict[int, dict]) -> dict:
    tid, token = rec["trial"], rec["token"]
    page = [j for j in rec["journal"] if j.get("source") == "page" and j.get("trial") == tid]
    stale_page = [j for j in rec["journal"] if j.get("source") == "page" and j.get("trial") not in (tid, None)]
    posts = [j for j in rec["journal"] if j.get("source") == "target" and j.get("kind") == "submit_post"]
    t0, t1 = rec["click"]["t_start_ms"], rec["click"]["t_end_ms"]
    after = [j for j in page if j["t_epoch_ms"] >= t0 - 1]
    pdown = [j for j in after if j["kind"] in ("pointerdown", "mousedown") and j.get("is_trusted")]
    pdown_submit = [j for j in pdown if (j.get("target") or "").startswith(SUBMIT)]
    clicks = [j for j in after if j["kind"] == "click"]
    clicks_submit = [j for j in clicks if (j.get("target") or "").startswith(SUBMIT)]
    submits = [j for j in after if j["kind"] == "submit"]
    invalid = [j for j in after if j["kind"] == "invalid"]
    good_posts = [p for p in posts if p.get("value") == token]
    load = rec.get("page_load") or {}
    load_rect = (load.get("geom") or {}).get("button")
    first_pd = (pdown_submit or pdown or [None])[0]
    pd_rect = ((first_pd or {}).get("geom") or {}).get("button")
    pt = driver_point(rec)
    win = blocks.get(rec["block"], {}).get("window", {}).get("window_id")
    act_pre = (rec.get("focus_pre") or {}).get("active_window")
    act_post = (rec.get("focus_post") or {}).get("active_window")
    xc = (rec.get("x11") or {}).get("event_counts") or {}
    return {
        "page_events": len(page),
        "stale_page_events": len(stale_page),
        "trusted_pointerdown": len(pdown),
        "trusted_pointerdown_on_submit": len(pdown_submit),
        "click_events": len(clicks),
        "click_on_submit": len(clicks_submit),
        "click_on_submit_trusted": sum(1 for j in clicks_submit if j.get("is_trusted")),
        "submit_events": len(submits),
        "invalid_events": len(invalid),
        "posts_total": len(posts),
        "posts_with_token": len(good_posts),
        "post_minus_tool_end_ms": (good_posts[0]["recv_epoch_ms"] - t1) if good_posts else None,
        "pointerdown_offset_in_tool_ms": (first_pd["t_epoch_ms"] - t0) if first_pd else None,
        "pointerdown_to_tool_end_ms": (t1 - first_pd["t_epoch_ms"]) if first_pd else None,
        "page_has_focus_at_pointerdown": first_pd.get("has_focus") if first_pd else None,
        "hit_at_pointerdown": first_pd.get("hit") if first_pd else None,
        "driver_point": pt,
        "point_inside_rect_at_load": inside(pt, load_rect),
        "point_inside_rect_at_pointerdown": inside(pt, pd_rect),
        "rect_moved_load_to_pointerdown": (load_rect != pd_rect) if (load_rect and pd_rect) else None,
        "dpr": (load.get("geom") or {}).get("dpr"),
        "inner": (load.get("geom") or {}).get("inner"),
        "screen_xy": (load.get("geom") or {}).get("screen_xy"),
        "resize_events": sum(1 for j in page if j["kind"] == "resize"),
        "active_is_browser_pre": (act_pre == str(win)) if (act_pre and win is not None) else None,
        "active_is_browser_post": (act_post == str(win)) if (act_post and win is not None) else None,
        "x11_button_events_in_tool_span": sum(xc.get(k, 0) for k in BUTTON_EVENTS),
        "x11_any_events_in_tool_span": sum(xc.values()),
        "x11_recorder_alive": (rec.get("x11") or {}).get("recorder_alive"),
    }


def classify(rec: dict, tr: dict) -> str:
    c = rec["click"]
    if not c.get("accepted"):
        return "refused"
    o = rec["oracle"]
    if o["immediate"].get("submitted") == rec["token"]:
        return "verified_immediate"
    if o["first_verified_after_tool_ms"] is not None:
        return "verified_late"
    instrumented = rec.get("instrumented", True)
    if not instrumented:
        return "miss_unattributed_plain_page"
    if tr["click_on_submit"] == 0 and rec["arm"].startswith("D"):
        return "miss_no_click"
    if rec["arm"].startswith("D"):
        pass
    elif tr["trusted_pointerdown"] == 0:
        return "miss_no_page_pointer"
    elif tr["trusted_pointerdown_on_submit"] == 0:
        return "miss_wrong_target"
    elif tr["click_on_submit"] == 0:
        return "miss_no_click"
    if tr["submit_events"] == 0:
        return "miss_click_no_submit_invalid" if tr["invalid_events"] else "miss_click_no_submit"
    if tr["posts_with_token"] == 0:
        return "miss_submit_no_post"
    return "miss_post_no_state"


def summarize_arm(rows: list[dict]) -> dict:
    n = len(rows)
    cls: dict[str, int] = {}
    for r in rows:
        cls[r["class"]] = cls.get(r["class"], 0) + 1
    acc = [r for r in rows if r["accepted"]]
    click_ms = [r["click_ms"] for r in acc]
    late = [r["first_verified_ms"] for r in rows if r["class"] == "verified_late"]
    pdo = [r["trace"]["pointerdown_offset_in_tool_ms"] for r in rows if r["trace"]["pointerdown_offset_in_tool_ms"] is not None]
    pmt = [r["trace"]["post_minus_tool_end_ms"] for r in rows if r["trace"]["post_minus_tool_end_ms"] is not None]
    t = [r["trace"] for r in rows]
    return {
        "n": n,
        "accepted": len(acc),
        "verified_immediate": cls.get("verified_immediate", 0),
        "verified_within_bound": cls.get("verified_immediate", 0) + cls.get("verified_late", 0),
        "verified_late": cls.get("verified_late", 0),
        "classes": dict(sorted(cls.items())),
        "post_after_tool_return": sum(1 for v in pmt if v > 0),
        "post_minus_tool_end_ms_min_p50_max": [min(pmt), statistics.median(pmt), max(pmt)] if pmt else None,
        "late_first_verified_ms_min_p50_max": [min(late), statistics.median(late), max(late)] if late else None,
        "click_tool_ms_p50": statistics.median(click_ms) if click_ms else None,
        "click_tool_ms_p95_nearest_rank": nearest_rank(click_ms, 0.95),
        "pointerdown_offset_in_tool_ms_p50": statistics.median(pdo) if pdo else None,
        "trusted_pointerdown_on_submit_trials": sum(1 for x in t if x["trusted_pointerdown_on_submit"] > 0),
        "click_on_submit_trials": sum(1 for x in t if x["click_on_submit"] > 0),
        "submit_event_trials": sum(1 for x in t if x["submit_events"] > 0),
        "exactly_one_post_with_token_trials": sum(1 for x in t if x["posts_with_token"] == 1 and x["posts_total"] == 1),
        "posts_total": sum(x["posts_total"] for x in t),
        "x11_button_events_total": sum(x["x11_button_events_in_tool_span"] for x in t),
        "x11_any_events_total": sum(x["x11_any_events_in_tool_span"] for x in t),
        "active_is_browser_pre": sum(1 for x in t if x["active_is_browser_pre"]),
        "active_is_browser_post": sum(1 for x in t if x["active_is_browser_post"]),
        "page_has_focus_at_pointerdown": sum(1 for x in t if x["page_has_focus_at_pointerdown"]),
        "point_inside_rect_at_load": sum(1 for x in t if x["point_inside_rect_at_load"]),
        "point_inside_rect_at_pointerdown": sum(1 for x in t if x["point_inside_rect_at_pointerdown"]),
        "rect_moved_load_to_pointerdown": sum(1 for x in t if x["rect_moved_load_to_pointerdown"]),
        "resize_events_total": sum(x["resize_events"] for x in t),
        "stale_page_events_total": sum(x["stale_page_events"] for x in t),
        "dpr_values": sorted({x["dpr"] for x in t if x["dpr"] is not None}),
        "inner_values": sorted({tuple(x["inner"]) for x in t if x["inner"]}),
        "screen_xy_values": sorted({tuple(x["screen_xy"]) for x in t if x["screen_xy"]}),
        "loadavg1_min_max": [min(r["loadavg1"] for r in rows), max(r["loadavg1"] for r in rows)] if rows else None,
    }


def phase_rows(phase: str) -> tuple[list[dict], list[dict], dict]:
    trials, errors, blocks = load_phase(phase)
    rows = []
    for rec in trials:
        tr = trace(rec, blocks)
        rows.append({
            "trial": rec["trial"], "index": rec["index"], "block": rec["block"], "pos": rec["pos_in_block"], "arm": rec["arm"],
            "accepted": bool(rec["click"].get("accepted")), "refusal_code": ((rec["click"].get("structured") or {}).get("error") or {}).get("code"),
            "class": classify(rec, tr), "click_ms": rec["click"]["elapsed_ms"], "first_verified_ms": rec["oracle"]["first_verified_after_tool_ms"],
            "immediate_state": rec["oracle"]["immediate"], "final_state": rec["oracle"]["final"], "loadavg1": rec["loadavg_start"][0], "trace": tr,
        })
    return rows, errors, blocks


def concordance(rows: list[dict]) -> dict:
    """Does the target-journal POST arrival time (relative to tool return) separate
    immediate from late verification for accepted trials?"""
    imm = [r["trace"]["post_minus_tool_end_ms"] for r in rows if r["class"] == "verified_immediate" and r["trace"]["post_minus_tool_end_ms"] is not None]
    late = [r["trace"]["post_minus_tool_end_ms"] for r in rows if r["class"] == "verified_late" and r["trace"]["post_minus_tool_end_ms"] is not None]
    return {
        "immediate_n": len(imm), "late_n": len(late),
        "immediate_post_minus_tool_end_max_ms": max(imm) if imm else None,
        "late_post_minus_tool_end_min_ms": min(late) if late else None,
        "separated": (max(imm) < min(late)) if (imm and late) else None,
        "late_all_post_after_return": all(v > 0 for v in late) if late else None,
    }


def compute() -> dict:
    out: dict = {"schema": "cua.r2-06.summary.v1", "phases": {}}
    for phase_dir in sorted(p for p in RAW.iterdir() if p.is_dir() and p.name != "pilot"):
        rows, errors, blocks = phase_rows(phase_dir.name)
        arms: dict[str, list] = {}
        for r in rows:
            arms.setdefault(r["arm"], []).append(r)
        env = json.loads((phase_dir / "session-env.json").read_text()) if (phase_dir / "session-env.json").exists() else {}
        out["phases"][phase_dir.name] = {
            "trials": len(rows),
            "harness_errors": len(errors),
            "harness_error_arms": sorted(e.get("arm") for e in errors),
            "blocks": len(blocks),
            "driver_versions": sorted({b.get("server_info", {}).get("version") for b in blocks.values()}),
            "x_recorder_selftest_events": (env.get("x_recorder_selftest") or {}).get("event_counts"),
            "arms": {arm: summarize_arm(v) for arm, v in sorted(arms.items())},
            "controls": {arm: [{"class": r["class"], "refusal_code": r["refusal_code"], "final_state": r["final_state"], "posts_total": r["trace"]["posts_total"], "submit_events": r["trace"]["submit_events"], "invalid_events": r["trace"]["invalid_events"], "trusted_pointerdown": r["trace"]["trusted_pointerdown"], "hit_at_pointerdown": r["trace"]["hit_at_pointerdown"]} for r in v] for arm, v in sorted(arms.items()) if arm.startswith("N_")},
            "post_timing_concordance": concordance(rows),
            "per_trial": [{k: r[k] for k in ("index", "block", "pos", "arm", "class", "accepted", "first_verified_ms")} | {"post_minus_tool_end_ms": r["trace"]["post_minus_tool_end_ms"]} for r in rows],
        }
    return out


if __name__ == "__main__":
    s = compute()
    if "--write" in sys.argv:
        (HERE / "r2-06-summary.json").write_text(json.dumps(s, indent=1, sort_keys=True, default=list) + "\n")
    print(json.dumps({p: {a: {k: v[k] for k in ("n", "accepted", "verified_immediate", "verified_within_bound", "classes")} for a, v in d["arms"].items()} for p, d in s["phases"].items()}, indent=1))

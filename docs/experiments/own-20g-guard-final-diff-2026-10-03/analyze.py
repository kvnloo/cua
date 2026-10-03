#!/usr/bin/env python3
"""OWN-20G: recompute every verdict from raw/ (stdlib only).

usage: analyze.py [--raw raw] [--out own20g-summary.json] [--metrics own20g-trial-metrics.jsonl.gz]

Rules are the ones pre-registered in PREREG.json (copied here as code; the verifier
re-runs this script and compares its output with the committed summary).
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FOCUS_KINDS = ("stall", "stallonly", "steal", "nosteal", "replystall", "replyonly")
MAX_SAMPLER_GAP_MS = 20.0
BOOT_N = 10000
BOOT_SEED = 9101
DECLARED = sorted(["Increment", "Reset", "I agree", "Small", "Medium", "Large", "Note", "Save note", "Exit"])


def load(raw: Path) -> tuple[list[dict], list[dict]]:
    """All trial rows of the latest attempt of each block; and every block attempt."""
    attempts = []
    for d in sorted(raw.iterdir()):
        f = d / "trials.jsonl.gz"
        if not d.is_dir() or not f.exists():
            continue
        rows = [json.loads(x) for x in gzip.open(f, "rt", encoding="utf-8") if x.strip()]
        meta = next((r for r in rows if r.get("event") == "meta"), {})
        trials = [r for r in rows if r.get("event") == "trial"]
        end = next((r for r in rows if r.get("event") == "end"), {})
        attempts.append({"label": d.name, "block": meta.get("block"), "meta": meta, "trials": trials, "end": end,
                         "collision": bool(meta.get("display_collision"))})
    latest: dict[str, dict] = {}
    for a in attempts:
        if a["block"] is None:
            continue
        ran = [t for t in a["trials"] if t.get("failure") != "display_collision"]
        if a["collision"] or not ran:
            continue
        latest[a["block"]] = a  # sorted labels: -rN sorts after the first attempt
    trials = []
    for a in latest.values():
        for t in a["trials"]:
            t["_label"] = a["label"]
            trials.append(t)
    return trials, attempts


def median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def boot_ci(diffs: list[float]) -> list[float] | None:
    if not diffs:
        return None
    rng = random.Random(BOOT_SEED)
    meds = sorted(statistics.median(rng.choices(diffs, k=len(diffs))) for _ in range(BOOT_N))
    return [round(meds[int(0.025 * BOOT_N)], 3), round(meds[int(0.975 * BOOT_N) - 1], 3)]


def offset_ns(t: dict) -> float | None:
    pairs = t.get("clock_pairs") or []
    return statistics.median(w - m for m, w in pairs) if pairs else None


def last_mark(marks: list[dict], scope: str, name: str) -> dict | None:
    hits = [m for m in marks if m.get("scope") == scope and m.get("mark") == name]
    return hits[-1] if hits else None


def receipt_focus(action: dict | None) -> str | None:
    if not action:
        return None
    found = re.search(r"focus_outcome=([a-z_]+)", " ".join(action.get("content_text") or []))
    return found.group(1) if found else None


def focus_metrics(t: dict) -> dict[str, Any]:
    m: dict[str, Any] = {k: t.get(k) for k in ("id", "block", "_label", "kind", "task", "bin", "arm", "pair",
                                                "group", "delay_ms", "round")}
    m["loadavg1"] = (t.get("loadavg") or [None])[0]
    m["failure"] = t.get("failure")
    m["oracle_verified"] = bool(t.get("oracle_verified"))
    actions = t.get("actions") or []
    click = next((a for a in reversed(actions) if a.get("tool") == "click"), None)
    m["receipt_focus_outcome"] = receipt_focus(click)
    m["click_error"] = (click or {}).get("error")
    m["click_route"] = ((click or {}).get("structured") or {}).get("route")
    marks = t.get("marks") or []
    off = offset_ns(t)
    body = last_mark(marks, "focus_guard", "body_done")
    rst = last_mark(marks, "focus_guard", "restored")
    dar = last_mark(marks, "atspi_action", "do_action_replied")
    m["exp_knobs"] = sorted({x["mark"] for x in marks if x.get("scope") == "exp_knob"})
    gs = we = None
    if off is not None and body and rst:
        gs = body["wall_ns"] - off
        we = rst["wall_ns"] - off
        polls = [x["wall_ns"] for x in marks if x.get("scope") == "focus_guard" and x.get("mark") == "settle_poll"
                 and body["wall_ns"] <= x["wall_ns"] <= rst["wall_ns"]]
        m["settle_ms"] = round((rst["wall_ns"] - body["wall_ns"]) / 1e6, 3)
        m["settle_polls_ms"] = [round((p - body["wall_ns"]) / 1e6, 3) for p in polls]
        m["last_poll_ms"] = m["settle_polls_ms"][-1] if polls else None
    if dar and body:
        m["mark_to_guard_start_ms"] = round((body["wall_ns"] - dar["wall_ns"]) / 1e6, 3)
    t0 = t.get("T0_m")
    conf = (t.get("state_samples") or {}).get("confirmed_ns")
    m["T_ms"] = round((conf - t0) / 1e6, 3) if conf and t0 else None
    if t.get("kind") not in FOCUS_KINDS:
        return m
    ref = t.get("focus_reference") or {}
    m["reference_ok"] = bool(ref.get("ok"))
    fs = t.get("focus_samples") or {}
    changes = fs.get("changes") or []
    decoy = t.get("decoy_window")
    m["sampler_max_gap_ms"] = fs.get("max_gap_ms")
    m["sampler_error"] = fs.get("error")
    stolen = [c for c in changes if t0 and c[0] >= t0 and (c[1] == decoy or c[2] == decoy)]
    m["stolen"] = bool(stolen)
    ts = stolen[0][0] if stolen else None
    final = changes[-1] if changes else None
    m["final_ok"] = bool(final and final[1] == ref.get("focus") and final[2] == ref.get("active"))
    m["final_on_decoy"] = bool(final and (final[1] == decoy or final[2] == decoy))
    st = t.get("stealer") or {}
    m["stealer_error"] = st.get("error")
    m["detect_lag_ms"] = st.get("detect_lag_ms")
    mw = st.get("mark_wall_ns")
    if mw and st.get("steal_issued"):
        m["steal_issued_after_mark_ms"] = round((st["steal_issued"]["wall_ns"] - mw) / 1e6, 3)
    if mw and st.get("grab_issued"):
        m["grab_issued_after_mark_ms"] = round((st["grab_issued"]["wall_ns"] - mw) / 1e6, 3)
        m["grab_held_ms"] = round((st["ungrab_synced"]["wall_ns"] - st["grab_issued"]["wall_ns"]) / 1e6, 3) \
            if st.get("ungrab_synced") else None
    px = t.get("proxy") or {}
    if t["kind"] in ("replystall", "replyonly"):
        m["proxy_error"] = px.get("error")
        m["hold_after_mark_ms"] = (px.get("hold_request") or {}).get("after_mark_ms")
        m["hold_ms"] = px.get("pause_ms")
        m["held_chunks"] = px.get("held_chunks")
        if off is not None and ts is not None and px.get("pause_started_wall_ns") and px.get("pause_ended_wall_ns"):
            m["steal_during_hold"] = bool(px["pause_started_wall_ns"] - off <= ts <= px["pause_ended_wall_ns"] - off)
    if gs is not None and ts is not None:
        m["steal_landed_after_guard_start_ms"] = round((ts - gs) / 1e6, 3)
        m["steal_landed_before_window_end_ms"] = round((we - ts) / 1e6, 3)
    m["in_window"] = bool(gs is not None and ts is not None and gs <= ts <= we)
    # pass / miss classification (PREREG)
    receipt = m["receipt_focus_outcome"]
    m["pass"] = bool(m["stolen"] and m["final_ok"] and receipt == "restored" and m["oracle_verified"])
    m["silent_miss"] = bool(m["stolen"] and not m["final_ok"] and receipt is None)
    harness_ok = (not m["failure"]) and not m["stealer_error"] and not m["sampler_error"] and m["reference_ok"]
    if t["kind"] == "replystall":
        hold_ok = (m.get("hold_after_mark_ms") or 1e9) <= 150 and (m.get("hold_ms") or 0) >= 1900 \
            and m.get("held_chunks", 0) >= 1 and not m.get("proxy_error")
        sched_ok = (m.get("steal_issued_after_mark_ms") or 1e9) <= 260
        m["valid"] = bool(harness_ok and hold_ok and sched_ok and m["stolen"] and m.get("steal_during_hold"))
    elif t["kind"] == "stall":
        sched_ok = (m.get("grab_issued_after_mark_ms") or 1e9) <= 150 and (m.get("steal_issued_after_mark_ms") or 1e9) <= 260
        m["valid"] = bool(harness_ok and sched_ok)
    elif t["kind"] == "steal":
        m["valid"] = bool(harness_ok and m["stolen"] and m["in_window"]
                          and (m["sampler_max_gap_ms"] or 1e9) <= MAX_SAMPLER_GAP_MS)
        m["miss"] = bool(m["valid"] and not (m["final_ok"] and receipt == "restored"))
        m["uncovered"] = bool(harness_ok and m["stolen"] and not m["in_window"] and m["final_on_decoy"])
    else:  # nosteal / stallonly / replyonly
        m["valid"] = bool(harness_ok)
        moved = [c for c in changes if t0 and c[0] >= t0]
        m["focus_moved_after_T0"] = bool(moved)
        m["false_restore"] = bool(receipt is not None or moved)
    return m


def r3_metrics(t: dict) -> dict[str, Any]:
    s = t.get("steps") or {}
    o2 = s.get("observe_2") or {}
    stale = s.get("stale_click") or {}
    fresh = s.get("fresh_click") or {}
    m = {k: t.get(k) for k in ("id", "block", "_label", "variant", "bin", "pair")}
    m["loadavg1"] = (t.get("loadavg") or [None])[0]
    m["failure"] = t.get("failure")
    m["observe_2"] = {"is_error": o2.get("is_error"), "code": o2.get("code"), "timeout": o2.get("timeout"),
                      "labels_match": ((o2.get("digest") or {}).get("labels") == DECLARED) if o2.get("digest") else None}
    m["observe_2_truthful"] = bool(t.get("observe_2_truthful"))
    m["observe_2_structured_error"] = bool(t.get("observe_2_structured_error"))
    m["stale_refused"] = bool(stale.get("refused"))
    m["stale_code"] = stale.get("code")
    m["stale_mutated"] = bool(stale.get("mutated"))
    m["new_token_path"] = t.get("new_token_path")
    m["fresh_verified"] = bool(fresh.get("verified"))
    fa, sa = t.get("final_state_a") or {}, t.get("seq_a_before")
    # every A-mutation must come from the fresh click on A
    fresh_on_a = 1 if (m["new_token_path"] == "same_fixture" and m["fresh_verified"]) else 0
    m["stale_authority_mutations"] = (int(fa.get("seq", sa or 0)) - int(sa or 0) - fresh_on_a) if fa and sa is not None \
        else None
    events = t.get("perturb_events") or []
    m["perturb_ms"] = t.get("perturb_ms")
    m["perturb"] = {k: v for e in events for k, v in e.items() if k not in ("mono_ns", "pid", "comm")}
    direct = str(m["variant"]).endswith("_direct")
    m["pass_safety"] = bool(not m["failure"] and (direct or m["observe_2_truthful"] or m["observe_2_structured_error"])
                            and m["stale_refused"] and not m["stale_mutated"] and m["stale_authority_mutations"] == 0)
    m["pass"] = bool(m["pass_safety"] and m["fresh_verified"])
    diag = t.get("fresh_driver_diag") or {}
    m["fresh_process_truthful"] = {k: bool(v.get("truthful")) for k, v in diag.items()}
    d2 = ((s.get("observe_2") or {}).get("digest") or {})
    m["observe_2_degraded_reason"] = (d2.get("degraded_reason") or "")[:60] or None
    tries = s.get("observe_3") or []
    m["same_process_retries"] = len(tries) if isinstance(tries, list) else None
    return m


def cell(rows: list[dict], **kw) -> list[dict]:
    return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "raw"))
    ap.add_argument("--out", default=str(HERE / "own20g-summary.json"))
    ap.add_argument("--metrics", default=str(HERE / "own20g-trial-metrics.jsonl.gz"))
    args = ap.parse_args()
    trials, attempts = load(Path(args.raw))
    fm = [focus_metrics(t) for t in trials if t.get("kind") != "r3"]
    rm = [r3_metrics(t) for t in trials if t.get("kind") == "r3"]
    s: dict[str, Any] = {"schema": "own20g.summary.v1"}
    s["block_attempts"] = [{"label": a["label"], "block": a["block"], "trials": len(a["trials"]),
                            "collision": a["collision"], "end_failures": a["end"].get("failures"),
                            "net_refused": (a["end"].get("net") or {}).get("refused_non_loopback_connects")}
                           for a in attempts]
    s["failed_block_attempts"] = [a["label"] for a in attempts if a["collision"] or not a["trials"]]
    # smoke
    sm = cell(fm, kind="smoke")
    s["smoke"] = {b: {"n": len(cell(sm, bin=b)), "verified": sum(r["oracle_verified"] for r in cell(sm, bin=b)),
                      "exp_knob_marks": sorted({k for r in cell(sm, bin=b) for k in r["exp_knobs"]}),
                      "settle_ms": [r.get("settle_ms") for r in cell(sm, bin=b)]} for b in ("U", "G")}
    # R1: "reply" = the c08-017 reproduction (reply-delay stall; primary, gated);
    #     "grab" = the XGrabServer row exactly as the planner specified (reported with its gate).
    r1: dict[str, Any] = {}
    for row, kind, ctl_kind in (("reply", "replystall", "replyonly"), ("grab", "stall", "stallonly")):
        rr: dict[str, Any] = {}
        for task in ("checkbox", "text"):
            for b in ("U", "G"):
                rows = cell(fm, kind=kind, task=task, bin=b)
                valid = [r for r in rows if r["valid"]]
                rr[f"{task}/{b}"] = {
                    "attempted": len(rows), "valid": len(valid),
                    "stolen": sum(r["stolen"] for r in valid), "pass": sum(r["pass"] for r in valid),
                    "silent_miss": sum(r["silent_miss"] for r in valid),
                    "receipt_outcomes": {str(k): sum(1 for r in valid if r["receipt_focus_outcome"] == k)
                                         for k in sorted({r["receipt_focus_outcome"] for r in valid}, key=str)},
                    "final_ok": sum(r["final_ok"] for r in valid),
                    "final_on_decoy": sum(r["final_on_decoy"] for r in valid),
                    "task_verified": sum(r["oracle_verified"] for r in valid),
                    "stall_after_mark_ms": median([r.get("hold_after_mark_ms") if kind == "replystall"
                                                   else r.get("grab_issued_after_mark_ms") for r in valid]),
                    "stall_ms": median([r.get("hold_ms") if kind == "replystall" else r.get("grab_held_ms")
                                        for r in valid]),
                    "steal_issued_after_mark_ms": median([r.get("steal_issued_after_mark_ms") for r in valid]),
                    "last_poll_before_stall_ms": median([(r.get("settle_polls_ms") or [None])[-1] for r in valid]),
                    "settle_ms": median([r.get("settle_ms") for r in valid]),
                    "invalid": [{"id": r["id"], "failure": r["failure"], "stealer_error": r["stealer_error"],
                                 "stolen": r["stolen"], "steal_during_hold": r.get("steal_during_hold")}
                                for r in rows if not r["valid"]],
                    "non_pass": [{k: r.get(k) for k in ("id", "_label", "stolen", "final_ok", "final_on_decoy",
                                                        "receipt_focus_outcome", "oracle_verified",
                                                        "settle_polls_ms")} for r in valid if not r["pass"]],
                }
        ctl = cell(fm, kind=ctl_kind)
        rr["control_no_steal"] = {b: {"n": len(cell(ctl, bin=b)), "valid": sum(r["valid"] for r in cell(ctl, bin=b)),
                                      "false_restore": sum(r["false_restore"] for r in cell(ctl, bin=b) if r["valid"]),
                                      "verified": sum(r["oracle_verified"] for r in cell(ctl, bin=b))}
                                  for b in ("U", "G")}
        rr["gate_G_20_of_20"] = all(rr[f"{t}/G"]["pass"] >= 20 and rr[f"{t}/G"]["valid"] >= 20
                                    and rr[f"{t}/G"]["pass"] == rr[f"{t}/G"]["valid"] for t in ("checkbox", "text"))
        r1[row] = rr
    s["r1"] = r1
    # R2
    r2: dict[str, Any] = {"ran": bool(cell(fm, kind="steal"))}
    if r2["ran"]:
        groups: dict[str, Any] = {}
        all_valid = True
        any_miss = False
        for task, arm in (("checkbox", "S0"), ("text", "X")):
            for a in (arm, f"{arm}+CL"):
                for g in ("band", "edge", "d100"):
                    rows = cell(fm, kind="steal", task=task, arm=a, group=g)
                    valid = [r for r in rows if r["valid"]]
                    misses = [r for r in valid if r["miss"]]
                    all_valid &= len(valid) == len(rows)
                    any_miss |= bool(misses)
                    groups[f"{task}/{a}/{g}"] = {
                        "attempted": len(rows), "valid": len(valid), "misses": len(misses),
                        "uncovered_invalid_left_on_decoy": sum(r["uncovered"] for r in rows),
                        "invalid": len(rows) - len(valid),
                        "miss_ids": [r["id"] for r in misses],
                        "near_boundary_misses": [r["id"] for r in misses
                                                 if (r.get("steal_landed_before_window_end_ms") or 99) < 3],
                    }
                    if g == "band":
                        groups[f"{task}/{a}/{g}"]["per_delay"] = {
                            str(d): {"n": len(cell(rows, delay_ms=d)),
                                     "valid": sum(r["valid"] for r in cell(rows, delay_ms=d)),
                                     "restored": sum(1 for r in cell(rows, delay_ms=d)
                                                     if r["final_ok"] and r["receipt_focus_outcome"] == "restored"),
                                     "left_on_decoy": sum(r["final_on_decoy"] for r in cell(rows, delay_ms=d)),
                                     "landed_after_guard_ms": median([r.get("steal_landed_after_guard_start_ms")
                                                                      for r in cell(rows, delay_ms=d)])}
                            for d in sorted({r["delay_ms"] for r in rows})}
                nos = cell(fm, kind="nosteal", task=task, arm=a)
                groups[f"{task}/{a}/nosteal"] = {"n": len(nos), "valid": sum(r["valid"] for r in nos),
                                                 "false_restore": sum(r["false_restore"] for r in nos)}
        r2["groups"] = groups
        r2["validity_100"] = all_valid
        r2["zero_misses"] = not any_miss
        r2["min_valid_per_group"] = min(v["valid"] for k, v in groups.items() if not k.endswith("nosteal"))
        # settle lengths (all R2 + timing trials)
        r2["settle_ms"] = {a: median([r.get("settle_ms") for r in fm if r.get("arm") == a and r["kind"] in
                                      ("steal", "nosteal", "timing") and r.get("receipt_focus_outcome") is None])
                           for a in ("S0", "S0+CL", "X", "X+CL")}
    tm = cell(fm, kind="timing")
    timing: dict[str, Any] = {"ran": bool(tm)}
    if tm:
        for task, arm in (("checkbox", "S0"), ("text", "X")):
            rows = cell(tm, task=task)
            by: dict[int, dict[str, float]] = {}
            for r in rows:
                if r["oracle_verified"] and r["T_ms"] is not None:
                    by.setdefault(r["pair"], {})[r["arm"]] = r["T_ms"]
            diffs = [v[arm] - v[f"{arm}+CL"] for v in by.values() if arm in v and f"{arm}+CL" in v]
            sdiffs = []
            for p in sorted(by):
                pr = {r["arm"]: r.get("settle_ms") for r in rows if r["pair"] == p}
                if pr.get(arm) is not None and pr.get(f"{arm}+CL") is not None:
                    sdiffs.append(pr[arm] - pr[f"{arm}+CL"])
            timing[task] = {
                "attempted": len(rows), "verified": sum(r["oracle_verified"] for r in rows), "pairs": len(diffs),
                "T_median": {a: median([r["T_ms"] for r in cell(rows, arm=a)]) for a in (arm, f"{arm}+CL")},
                "settle_median": {a: median([r.get("settle_ms") for r in cell(rows, arm=a)]) for a in (arm, f"{arm}+CL")},
                "saving_ms": median(diffs), "saving_ci95": boot_ci(diffs),
                "settle_deleted_ms": median(sdiffs), "settle_deleted_ci95": boot_ci(sdiffs),
                "loadavg1_median": median([r["loadavg1"] for r in rows]),
                "false_restores": sum(1 for r in rows if r["receipt_focus_outcome"] is not None),
            }
        timing["saving_ok"] = all(
            (timing[t]["saving_ms"] or 0) >= 10 and timing[t]["saving_ci95"] and timing[t]["saving_ci95"][0] > 0
            for t in ("checkbox", "text"))
    s["timing"] = timing
    if r2["ran"] and timing["ran"]:
        keep = r2["zero_misses"] and timing["saving_ok"] and r2["validity_100"]
        r2["cl_verdict"] = "KEEP" if keep else "KILL"
        r2["cl_reasons"] = {"zero_misses": r2["zero_misses"], "saving_ok": timing["saving_ok"],
                            "validity_100": r2["validity_100"]}
    s["r2"] = r2
    # R3
    r3: dict[str, Any] = {}
    for v in ("bus", "registry", "noop", "noop_direct", "bus_direct"):
        for b in ("U", "G"):
            rows = cell(rm, variant=v, bin=b)
            r3[f"{v}/{b}"] = {
                "n": len(rows), "pass": sum(r["pass"] for r in rows), "pass_safety": sum(r["pass_safety"] for r in rows),
                "failures": sum(bool(r["failure"]) for r in rows),
                "fresh_process_truthful_b": sum(1 for r in rows if r["fresh_process_truthful"].get("b")),
                "fresh_process_truthful_a": sum(1 for r in rows if r["fresh_process_truthful"].get("a")),
                "observe_2_degraded_reasons": sorted({str(r["observe_2_degraded_reason"]) for r in rows}),
                "observe_2_truthful": sum(r["observe_2_truthful"] for r in rows),
                "observe_2_structured_error": sum(r["observe_2_structured_error"] for r in rows),
                "observe_2_codes": sorted({str(r["observe_2"]["code"]) for r in rows}),
                "stale_refused": sum(r["stale_refused"] for r in rows),
                "stale_codes": sorted({str(r["stale_code"]) for r in rows}),
                "stale_mutated": sum(r["stale_mutated"] for r in rows),
                "stale_authority_mutations": sum((r["stale_authority_mutations"] or 0) for r in rows),
                "fresh_verified": sum(r["fresh_verified"] for r in rows),
                "new_token_path": {p: sum(1 for r in rows if r["new_token_path"] == p)
                                   for p in sorted({str(r["new_token_path"]) for r in rows})},
                "perturb_ms_median": median([r["perturb_ms"] for r in rows]),
                "failure_list": [{"id": r["id"], "failure": r["failure"]} for r in rows if r["failure"]],
            }
    r3["gate_bus_20_each"] = all(r3[f"bus/{b}"]["pass"] == 20 and r3[f"bus/{b}"]["n"] == 20 for b in ("U", "G"))
    r3["safety_bus_20_each"] = all(r3[f"bus/{b}"]["pass_safety"] == 20 and r3[f"bus/{b}"]["n"] == 20
                                   for b in ("U", "G"))
    r3["noop_direct_discriminates"] = all(r3[f"noop_direct/{b}"]["stale_mutated"] == r3[f"noop_direct/{b}"]["n"] > 0
                                          for b in ("U", "G"))
    s["r3"] = r3
    # E4 counters per arm
    e4 = {}
    for key in sorted({(r.get("bin"), r.get("arm")) for r in fm} | {(r.get("bin"), "r3") for r in rm}, key=str):
        b, a = key
        frows = [r for r in fm if r.get("bin") == b and r.get("arm") == a]
        rrows = [r for r in rm if r.get("bin") == b] if a == "r3" else []
        e4[f"{b}/{a}"] = {
            "silent_steal_misses": sum(1 for r in frows if r.get("silent_miss") and r.get("valid")),
            "stale_token_actions": sum(1 for r in rrows if r["variant"] in ("bus", "bus_direct") and (r["stale_mutated"]
                                       or (r["stale_authority_mutations"] or 0) > 0)),
            "unverified_successes": sum(1 for r in frows if r["T_ms"] is None and not r["failure"]
                                        and r.get("click_error") is None and r["kind"] != "stallonly"
                                        and not r["oracle_verified"]),
        }
    s["e4"] = e4
    s["net_refused_total"] = sum((a["end"].get("net") or {}).get("refused_non_loopback_connects") or 0
                                 for a in attempts)
    Path(args.out).write_text(json.dumps(s, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with gzip.GzipFile(args.metrics, "wb", compresslevel=9, mtime=0) as stream:
        for r in fm + rm:
            stream.write((json.dumps(r, sort_keys=True) + "\n").encode())
    print(json.dumps({"r1_reply_gate": r1["reply"]["gate_G_20_of_20"], "r1_grab_gate": r1["grab"]["gate_G_20_of_20"], "cl": r2.get("cl_verdict"), "r3_gate": r3["gate_bus_20_each"]}))


if __name__ == "__main__":
    main()

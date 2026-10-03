#!/usr/bin/env python3
"""OWN-20P: recompute every verdict from raw/ (stdlib only).

usage: analyze.py [--raw raw] [--out own20p-summary.json] [--metrics own20p-trial-metrics.jsonl.gz]

The per-trial metrics (focus_metrics, r3_metrics) are OWN-20G's analyze.py definitions
(ce7544cc0), keyed here by the binary role (``binary``: U0, G0, U0m, G0m, GA) instead of
the harness slot. The gates are the ones pre-registered in PREREG.json; the verifier
re-runs this script and compares its output with the committed summary.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FOCUS_KINDS = ("stall", "stallonly", "steal", "nosteal", "replystall", "replyonly")
DECLARED = sorted(["Increment", "Reset", "I agree", "Small", "Medium", "Large", "Note", "Save note", "Exit"])
PILOT_PREFIXES = ("own20p-pilot",)


def load(raw: Path) -> tuple[list[dict], list[dict]]:
    """All trial rows of the latest attempt of each block; and every block attempt."""
    attempts = []
    for d in sorted(raw.iterdir()):
        f = d / "trials.jsonl.gz"
        if not d.is_dir() or not f.exists() or d.name.startswith(PILOT_PREFIXES):
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


def median(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


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
    m: dict[str, Any] = {k: t.get(k) for k in ("id", "block", "_label", "row", "kind", "task", "bin", "binary",
                                                "arm", "pair")}
    m["loadavg1"] = (t.get("loadavg") or [None])[0]
    m["failure"] = t.get("failure")
    m["oracle_verified"] = bool(t.get("oracle_verified"))
    actions = t.get("actions") or []
    click = next((a for a in reversed(actions) if a.get("tool") == "click"), None)
    m["receipt_focus_outcome"] = receipt_focus(click)
    m["click_error"] = (click or {}).get("error")
    m["click_route"] = ((click or {}).get("structured") or {}).get("route")
    marks = t.get("marks") or []
    m["marks_count"] = len(marks)
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
    mw = st.get("mark_wall_ns")
    if mw and st.get("steal_issued"):
        m["steal_issued_after_mark_ms"] = round((st["steal_issued"]["wall_ns"] - mw) / 1e6, 3)
    px = t.get("proxy") or {}
    if t["kind"] in ("replystall", "replyonly"):
        m["proxy_error"] = px.get("error")
        m["hold_after_mark_ms"] = (px.get("hold_request") or {}).get("after_mark_ms")
        m["hold_ms"] = px.get("pause_ms")
        m["held_chunks"] = px.get("held_chunks")
        if off is not None and ts is not None and px.get("pause_started_wall_ns") and px.get("pause_ended_wall_ns"):
            m["steal_during_hold"] = bool(px["pause_started_wall_ns"] - off <= ts <= px["pause_ended_wall_ns"] - off)
    receipt = m["receipt_focus_outcome"]
    m["pass"] = bool(m["stolen"] and m["final_ok"] and receipt == "restored" and m["oracle_verified"])
    m["silent_miss"] = bool(m["stolen"] and not m["final_ok"] and receipt is None)
    # the product binaries write no marks: their stealer waits out its deadline ("mark not seen") by design
    stealer_ok = not m["stealer_error"] or (t["kind"] == "nosteal" and m["stealer_error"] == "mark not seen"
                                             and m["marks_count"] == 0)
    m["stealer_mark_not_seen_expected"] = bool(m["stealer_error"]) and stealer_ok
    harness_ok = (not m["failure"]) and stealer_ok and not m["sampler_error"] and m["reference_ok"]
    if t["kind"] == "replystall":
        hold_ok = (m.get("hold_after_mark_ms") or 1e9) <= 150 and (m.get("hold_ms") or 0) >= 1900 \
            and m.get("held_chunks", 0) >= 1 and not m.get("proxy_error")
        sched_ok = (m.get("steal_issued_after_mark_ms") or 1e9) <= 260
        m["valid"] = bool(harness_ok and hold_ok and sched_ok and m["stolen"] and m.get("steal_during_hold"))
    else:  # nosteal / replyonly
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
    m = {k: t.get(k) for k in ("id", "block", "_label", "row", "variant", "bin", "binary", "pair")}
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
    fresh_on_a = 1 if (m["new_token_path"] == "same_fixture" and m["fresh_verified"]) else 0
    m["stale_authority_mutations"] = (int(fa.get("seq", sa or 0)) - int(sa or 0) - fresh_on_a) if fa and sa is not None \
        else None
    m["perturb_ms"] = t.get("perturb_ms")
    events = t.get("perturb_events") or []
    m["perturb"] = {k: v for e in events for k, v in e.items() if k not in ("mono_ns", "pid", "comm")}
    direct = str(m["variant"]).endswith("_direct")
    m["pass_safety"] = bool(not m["failure"] and (direct or m["observe_2_truthful"] or m["observe_2_structured_error"])
                            and m["stale_refused"] and not m["stale_mutated"] and m["stale_authority_mutations"] == 0)
    m["pass"] = bool(m["pass_safety"] and m["fresh_verified"])
    diag = t.get("fresh_driver_diag") or {}
    m["fresh_process_truthful"] = {k: bool(v.get("truthful")) for k, v in diag.items()}
    d2 = (o2.get("digest") or {})
    m["observe_2_degraded_reason"] = (d2.get("degraded_reason") or "")[:60] or None
    m["observe_2_agree_token"] = bool(d2.get("agree_token"))
    tries = s.get("observe_3") or []
    m["same_process_observes_of_b"] = len(tries) if isinstance(tries, list) else None
    m["same_process_b_truthful_on_try"] = next((i + 1 for i, o in enumerate(tries) if isinstance(o, dict)
                                                and (o.get("digest") or {}).get("agree_token")
                                                and (o.get("digest") or {}).get("labels") == DECLARED
                                                and not (o.get("digest") or {}).get("degraded")), None) \
        if isinstance(tries, list) else None
    m["same_process_b_ms"] = [round(o.get("ms") or 0, 3) for o in tries] if isinstance(tries, list) else None
    return m


def cell(rows: list[dict], **kw) -> list[dict]:
    return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]


def r1_cell(rows: list[dict]) -> dict[str, Any]:
    valid = [r for r in rows if r["valid"]]
    return {
        "attempted": len(rows), "valid": len(valid),
        "stolen": sum(r["stolen"] for r in valid), "pass": sum(r["pass"] for r in valid),
        "silent_miss": sum(r["silent_miss"] for r in valid),
        "silent_miss_attempted": sum(r["silent_miss"] for r in rows),
        "receipt_outcomes": {str(k): sum(1 for r in valid if r["receipt_focus_outcome"] == k)
                             for k in sorted({r["receipt_focus_outcome"] for r in valid}, key=str)},
        "final_ok": sum(r["final_ok"] for r in valid),
        "final_on_decoy": sum(r["final_on_decoy"] for r in valid),
        "task_verified": sum(r["oracle_verified"] for r in valid),
        "hold_after_mark_ms": median([r.get("hold_after_mark_ms") for r in valid]),
        "hold_ms": median([r.get("hold_ms") for r in valid]),
        "steal_issued_after_mark_ms": median([r.get("steal_issued_after_mark_ms") for r in valid]),
        "last_poll_ms": median([r.get("last_poll_ms") for r in valid]),
        "settle_ms": median([r.get("settle_ms") for r in valid]),
        "loadavg1_median": median([r["loadavg1"] for r in rows]),
        "invalid": [{"id": r["id"], "failure": r["failure"], "stealer_error": r["stealer_error"],
                     "stolen": r["stolen"], "steal_during_hold": r.get("steal_during_hold"),
                     "proxy_error": r.get("proxy_error")} for r in rows if not r["valid"]],
        "non_pass": [{k: r.get(k) for k in ("id", "_label", "stolen", "final_ok", "final_on_decoy",
                                            "receipt_focus_outcome", "oracle_verified", "settle_polls_ms")}
                     for r in valid if not r["pass"]],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "raw"))
    ap.add_argument("--out", default=str(HERE / "own20p-summary.json"))
    ap.add_argument("--metrics", default=str(HERE / "own20p-trial-metrics.jsonl.gz"))
    args = ap.parse_args()
    trials, attempts = load(Path(args.raw))
    fm = [focus_metrics(t) for t in trials if t.get("kind") != "r3"]
    rm = [r3_metrics(t) for t in trials if t.get("kind") == "r3"]
    s: dict[str, Any] = {"schema": "own20p.summary.v1"}
    s["block_attempts"] = [{"label": a["label"], "block": a["block"], "trials": len(a["trials"]),
                            "collision": a["collision"], "end_failures": a["end"].get("failures"),
                            "net_refused": (a["end"].get("net") or {}).get("refused_non_loopback_connects")}
                           for a in attempts]
    s["failed_block_attempts"] = [a["label"] for a in attempts if a["collision"] or not a["trials"]]
    s["trials_counted"] = {"focus": len(fm), "r3": len(rm)}
    # R1 (gated): U0m vs G0m
    r1: dict[str, Any] = {}
    for task in ("checkbox", "text"):
        for b in ("U0m", "G0m"):
            r1[f"{task}/{b}"] = r1_cell(cell(fm, kind="replystall", task=task, binary=b))
    ctl = cell(fm, kind="replyonly")
    r1["control_replyonly"] = {b: {"n": len(cell(ctl, binary=b)), "valid": sum(r["valid"] for r in cell(ctl, binary=b)),
                                   "false_restore": sum(r["false_restore"] for r in cell(ctl, binary=b) if r["valid"]),
                                   "verified": sum(r["oracle_verified"] for r in cell(ctl, binary=b))}
                               for b in ("U0m", "G0m")}
    g_ok = all(r1[f"{t}/G0m"]["attempted"] >= 20 and r1[f"{t}/G0m"]["valid"] >= 20
               and r1[f"{t}/G0m"]["pass"] == r1[f"{t}/G0m"]["valid"] and r1[f"{t}/G0m"]["silent_miss"] == 0
               for t in ("checkbox", "text"))
    u_silent = sum(r1[f"{t}/U0m"]["silent_miss"] for t in ("checkbox", "text"))
    u_attempted = sum(r1[f"{t}/U0m"]["attempted"] for t in ("checkbox", "text"))
    r1["G0m_restored"] = sum(r1[f"{t}/G0m"]["pass"] for t in ("checkbox", "text"))
    r1["G0m_attempted"] = sum(r1[f"{t}/G0m"]["attempted"] for t in ("checkbox", "text"))
    r1["U0m_silent_miss"] = u_silent
    r1["U0m_attempted"] = u_attempted
    r1["control_ok"] = all(v["false_restore"] == 0 and v["valid"] == v["n"] > 0 for v in r1["control_replyonly"].values())
    r1["gate"] = bool(g_ok and u_silent >= 36 and r1["control_ok"])
    s["r1"] = r1
    # normal path (gated): U0 vs G0, product defaults
    normal: dict[str, Any] = {}
    for task in ("checkbox", "text"):
        for b in ("U0", "G0"):
            rows = cell(fm, row="normal", task=task, binary=b)
            normal[f"{task}/{b}"] = {
                "n": len(rows), "valid": sum(r["valid"] for r in rows),
                "verified": sum(r["oracle_verified"] for r in rows),
                "false_restore": sum(r["false_restore"] for r in rows),
                "failures": sum(1 for r in rows if not r["oracle_verified"] or r["failure"]),
                "stealer_mark_not_seen_expected": sum(r["stealer_mark_not_seen_expected"] for r in rows),
                "marks_written": sum(r["marks_count"] for r in rows),
                "T_ms_median": median([r["T_ms"] for r in rows]),
                "loadavg1_median": median([r["loadavg1"] for r in rows]),
                "failure_list": [{"id": r["id"], "failure": r["failure"], "verified": r["oracle_verified"]}
                                 for r in rows if not r["oracle_verified"] or r["failure"]],
            }
    g_fail = sum(normal[f"{t}/G0"]["failures"] + normal[f"{t}/G0"]["false_restore"] for t in ("checkbox", "text"))
    u_fail = sum(normal[f"{t}/U0"]["failures"] + normal[f"{t}/U0"]["false_restore"] for t in ("checkbox", "text"))
    normal["G0_verified"] = sum(normal[f"{t}/G0"]["verified"] for t in ("checkbox", "text"))
    normal["G0_n"] = sum(normal[f"{t}/G0"]["n"] for t in ("checkbox", "text"))
    normal["G0_failures_plus_false_restores"] = g_fail
    normal["U0_failures_plus_false_restores"] = u_fail
    normal["gate"] = bool(normal["G0_n"] == 40 and normal["G0_verified"] == 40 and g_fail == 0 and g_fail <= u_fail)
    # settle (descriptive; marked twins only)
    marked: dict[str, Any] = {}
    for task in ("checkbox", "text"):
        for b in ("U0m", "G0m"):
            rows = cell(fm, row="normal_marked", task=task, binary=b)
            marked[f"{task}/{b}"] = {"n": len(rows), "verified": sum(r["oracle_verified"] for r in rows),
                                     "false_restore": sum(r["false_restore"] for r in rows),
                                     "settle_ms_median": median([r.get("settle_ms") for r in rows]),
                                     "settle_ms_min": min([r["settle_ms"] for r in rows if r.get("settle_ms")],
                                                          default=None),
                                     "settle_ms_max": max([r["settle_ms"] for r in rows if r.get("settle_ms")],
                                                          default=None),
                                     "settle_polls_median": median([len(r.get("settle_polls_ms") or []) for r in rows
                                                                    if r.get("settle_ms") is not None]),
                                     "T_ms_median": median([r["T_ms"] for r in rows])}
    normal["marked_settle"] = marked
    s["normal"] = normal
    # R3 (gated): G0 vs GA
    r3: dict[str, Any] = {}
    for v in ("bus", "registry", "noop", "noop_direct", "bus_direct"):
        for b in ("G0", "GA"):
            rows = cell(rm, variant=v, binary=b)
            r3[f"{v}/{b}"] = {
                "n": len(rows), "pass": sum(r["pass"] for r in rows), "pass_safety": sum(r["pass_safety"] for r in rows),
                "failures": sum(bool(r["failure"]) for r in rows),
                "fresh_process_truthful_b": sum(1 for r in rows if r["fresh_process_truthful"].get("b")),
                "fresh_process_truthful_a": sum(1 for r in rows if r["fresh_process_truthful"].get("a")),
                "observe_2_degraded_reasons": sorted({str(r["observe_2_degraded_reason"]) for r in rows}),
                "observe_2_truthful": sum(r["observe_2_truthful"] for r in rows),
                "observe_2_structured_error": sum(r["observe_2_structured_error"] for r in rows),
                "observe_2_agree_token": sum(r["observe_2_agree_token"] for r in rows),
                "stale_refused": sum(r["stale_refused"] for r in rows),
                "stale_codes": sorted({str(r["stale_code"]) for r in rows}),
                "stale_mutated": sum(r["stale_mutated"] for r in rows),
                "stale_authority_mutations": sum((r["stale_authority_mutations"] or 0) for r in rows),
                "fresh_verified": sum(r["fresh_verified"] for r in rows),
                "new_token_path": {p: sum(1 for r in rows if r["new_token_path"] == p)
                                   for p in sorted({str(r["new_token_path"]) for r in rows})},
                "same_process_b_truthful_on_try": {str(k): sum(1 for r in rows if r["same_process_b_truthful_on_try"] == k)
                                                   for k in sorted({r["same_process_b_truthful_on_try"] for r in rows},
                                                                   key=str)},
                "perturb_ms_median": median([r["perturb_ms"] for r in rows]),
                "loadavg1_median": median([r["loadavg1"] for r in rows]),
                "failure_list": [{"id": r["id"], "failure": r["failure"]} for r in rows if r["failure"]],
                "non_pass": [{"id": r["id"], "pass_safety": r["pass_safety"], "fresh_verified": r["fresh_verified"],
                              "new_token_path": r["new_token_path"], "stale_code": r["stale_code"]}
                             for r in rows if not r["pass"]],
            }
    ga_bus = r3["bus/GA"]
    r3["liveness_GA_20"] = bool(ga_bus["n"] == 20 and ga_bus["pass"] == 20
                                and ga_bus["new_token_path"].get("respawned_fixture", 0) == 20)
    r3["liveness_G0"] = r3["bus/G0"]["pass"]
    r3["safety_bus_20_each"] = all(r3[f"bus/{b}"]["pass_safety"] == 20 and r3[f"bus/{b}"]["n"] == 20
                                   for b in ("G0", "GA"))
    r3["noop_direct_acts_5_each"] = all(r3[f"noop_direct/{b}"]["stale_mutated"] == r3[f"noop_direct/{b}"]["n"] == 5
                                        for b in ("G0", "GA"))
    r3["gate"] = bool(r3["liveness_GA_20"] and r3["safety_bus_20_each"] and r3["noop_direct_acts_5_each"])
    failing = [name for name, ok in (("R3 bus liveness on GA", r3["liveness_GA_20"]),
                                     ("R3 bus safety", r3["safety_bus_20_each"]),
                                     ("R3 noop_direct control", r3["noop_direct_acts_5_each"])) if not ok]
    r3["failing_rows"] = failing
    s["r3"] = r3
    # E4 counters per arm (binary role / arm)
    e4 = {}
    keys = sorted({(r.get("binary"), r.get("arm")) for r in fm} | {(r.get("binary"), "r3") for r in rm}, key=str)
    for b, a in keys:
        frows = [r for r in fm if r.get("binary") == b and r.get("arm") == a]
        rrows = [r for r in rm if r.get("binary") == b] if a == "r3" else []
        e4[f"{b}/{a}"] = {
            "silent_steal_misses": sum(1 for r in frows if r.get("silent_miss") and r.get("valid")),
            "stale_token_actions": sum(1 for r in rrows if r["variant"] in ("bus", "bus_direct") and (
                r["stale_mutated"] or (r["stale_authority_mutations"] or 0) > 0)),
            "stale_mutations": sum(1 for r in rrows if r["variant"] in ("bus", "bus_direct", "registry", "noop")
                                   and r["stale_mutated"]),
            "unverified_successes": sum(1 for r in frows if r["T_ms"] is None and not r["failure"]
                                        and r.get("click_error") is None and not r["oracle_verified"])
            + sum(1 for r in rrows if (r["new_token_path"] not in (None, "none")) and not r["fresh_verified"]
                  and not r["failure"]),
        }
    s["e4"] = e4
    s["net_refused_total"] = sum((a["end"].get("net") or {}).get("refused_non_loopback_connects") or 0
                                 for a in attempts)
    s["dispositions"] = {"r1_gate": r1["gate"], "normal_gate": normal["gate"], "r3_gate": r3["gate"]}
    Path(args.out).write_text(json.dumps(s, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with gzip.GzipFile(args.metrics, "wb", compresslevel=9, mtime=0) as stream:
        for r in fm + rm:
            stream.write((json.dumps(r, sort_keys=True) + "\n").encode())
    print(json.dumps(s["dispositions"]))


if __name__ == "__main__":
    main()

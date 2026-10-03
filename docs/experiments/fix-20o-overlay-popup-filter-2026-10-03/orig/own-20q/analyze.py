#!/usr/bin/env python3
"""OWN-20Q: recompute every number of the packet from the raw block ledgers (raw/<label>/trials.jsonl.gz).

usage: analyze.py [<packet-dir>] [--out-dir <dir>]
  -> writes own20q-summary.json and own20q-trial-metrics.jsonl.gz (into the packet, or --out-dir)
Counts only the labels listed in provenance.json ``counted_labels``; pilots are never read.
"""

from __future__ import annotations

import gzip
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

DECLARED = sorted(["Increment", "Reset", "I agree", "Small", "Medium", "Large", "Note", "Save note", "Exit"])
FOCUS_KINDS = ("mfstall", "mfcal", "mfonly", "dlgsteal", "dlgdialog", "nosteal")
SUCCESS_EFFECTS_HONEST = ("unverifiable", "unknown", "unconfirmed")


def load(pkt: Path, key: str = "counted_labels") -> tuple[list[dict], list[dict]]:
    prov = json.loads((pkt / "provenance.json").read_text(encoding="utf-8"))
    trials, metas = [], []
    for label in prov.get(key, []):
        with gzip.open(pkt / "raw" / label / "trials.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                r = json.loads(line)
                r["_label"] = label
                (trials if r.get("event") == "trial" else metas).append(r)
    return trials, metas


def med(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def receipt_focus(action: dict | None) -> str | None:
    if not action:
        return None
    found = re.search(r"focus_outcome=([a-z_]+)", " ".join(action.get("content_text") or []))
    return found.group(1) if found else None


def driver_conns(bus: dict | None, pid: int | None, w_end: int | None = None) -> dict[str, Any]:
    names = [n for n in (bus or {}).get("names") or [] if n["event"] == "new" and pid and n.get("pid") == pid]
    keys = {n["name"] for n in names}
    lost = [n for n in (bus or {}).get("names") or [] if n["event"] == "lost" and n["name"] in keys]
    pings = [p for p in (bus or {}).get("pings") or [] if p.get("sender") in keys]
    return {"opened": len(names), "lost": len(lost), "lost_wall_ns": [n["wall_ns"] for n in lost], "pings": len(pings)}


def record_view(t: dict) -> dict[str, Any]:
    xr = t.get("xrecord") or {}
    since = t.get("click_issued_w") or t.get("T0_w") or 0
    rows = [r for r in xr.get("records") or [] if r[0] >= since]
    actives = [r for r in rows if r[1] == "active"]
    wm = {r[2] for r in actives}
    decoy, ref_win = t.get("decoy_window"), t.get("window_id")
    focus_sets = [r for r in rows if r[1] == "set_input_focus"]
    steal = next((r for r in focus_sets if r[4] == decoy and r[2] not in wm), None)
    steal_ns = steal[0] if steal else None
    restore = [r for r in rows if steal_ns is not None and r[0] > steal_ns and r[2] not in wm and r[2] != steal[2]
               and ((r[1] == "activate_request" and r[4] == ref_win) or r[1] == "set_input_focus")]
    nonwm_after_click = [r for r in rows if r[2] not in wm and (r[1] in ("activate_request", "set_input_focus"))]
    return {"error": xr.get("error"), "rows": len(rows), "steal_seen": steal is not None,
            "final_active": (actives[-1][5] or [0])[0] if actives else None,
            "restore_requests": len(restore), "focus_requests_after_click": len(nonwm_after_click)}


def focus_metrics(t: dict) -> dict[str, Any]:
    m: dict[str, Any] = {k: t.get(k) for k in ("id", "block", "_label", "row", "kind", "task", "bin", "binary",
                                                "arm", "pair")}
    m["loadavg1"] = (t.get("loadavg") or [None])[0]
    m["failure"] = t.get("failure")
    m["oracle_verified"] = bool(t.get("oracle_verified"))
    acts = t.get("actions") or []
    click = next((a for a in reversed(acts) if a.get("tool") == "click"), None)
    m["receipt_focus_outcome"] = receipt_focus(click)
    m["click_error"] = (click or {}).get("error")
    m["click_route"] = ((click or {}).get("structured") or {}).get("route")
    m["click_effect"] = ((click or {}).get("structured") or {}).get("effect")
    t0 = t.get("T0_m")
    conf = (t.get("state_samples") or {}).get("confirmed_ns")
    m["T_ms"] = round((conf - t0) / 1e6, 3) if conf and t0 else None
    ref = t.get("focus_reference") or {}
    m["reference_ok"] = bool(ref.get("ok"))
    fs = t.get("focus_samples") or {}
    changes = fs.get("changes") or []
    decoy = t.get("decoy_window")
    m["sampler_error"] = fs.get("error")
    stolen = [c for c in changes if t0 and c[0] >= t0 and (c[1] == decoy or c[2] == decoy)]
    m["stolen"] = bool(stolen)
    final = changes[-1] if changes else None
    m["final_ok"] = bool(final and final[1] == ref.get("focus") and final[2] == ref.get("active"))
    m["final_on_decoy"] = bool(final and (final[1] == decoy or final[2] == decoy))
    moved = [c for c in changes if t0 and c[0] >= t0]
    m["focus_moved_after_T0"] = bool(moved)
    rv = record_view(t)
    m["xrecord"] = rv
    m["record_final_active_is_reference"] = rv["final_active"] in (None, ref.get("active")) if not rv["error"] else None
    bus = t.get("bus") or {}
    dc = driver_conns(bus, t.get("driver_pid"))
    m["driver_bus_connections"] = dc["opened"]
    m["driver_pings"] = dc["pings"]
    lost_early = [w for w in dc["lost_wall_ns"] if w < (t.get("w_end") or 0) and t.get("fixture_rc") is None]
    m["spurious_reconnects"] = max(0, dc["opened"] - 1)
    m["oracles_ok"] = bool((t.get("oracles_ready") or {}).get("bus") and (t.get("oracles_ready") or {}).get("xrecord")
                           and not rv["error"] and not bus.get("error") and dc["opened"] >= 1)
    _ = lost_early
    px = t.get("proxy") or {}
    m["proxy_error"] = px.get("error")
    m["ref_seen"] = px.get("ref_wall_ns") is not None if t["kind"] in ("mfstall", "mfcal", "mfonly", "dlgsteal",
                                                                        "dlgdialog") else None
    hold = px.get("hold") or {}
    m["hold_after_ref_ms"] = hold.get("after_ref_ms")
    m["hold_ms"] = px.get("pause_ms")
    m["held_chunks"] = px.get("held_chunks")
    m["steal_after_ref_ms"] = (px.get("steal") or {}).get("after_ref_ms")
    m["ref_minus_mark_ms"] = px.get("ref_minus_mark_ms")
    m["hold_minus_markrule_ms"] = px.get("hold_minus_markrule_ms")
    m["lag_rewrites"] = px.get("rewrites")
    m["lag_rewrites_stale"] = px.get("rewrites_stale")
    m["steal_during_hold"] = None
    if stolen and px.get("pause_started_wall_ns") and px.get("pause_ended_wall_ns"):
        pairs = t.get("clock_pairs") or []
        off = statistics.median(w - mm for mm, w in pairs) if pairs else None
        if off is not None:
            ts = stolen[0][0]
            m["steal_during_hold"] = bool(px["pause_started_wall_ns"] - off <= ts <= px["pause_ended_wall_ns"] - off)
    harness_ok = (not m["failure"]) and not m["sampler_error"] and m["reference_ok"] and m["oracles_ok"] \
        and not m["proxy_error"]
    receipt = m["receipt_focus_outcome"]
    kind = t["kind"]
    if kind in ("mfstall", "mfcal"):
        hold_ok = (m["hold_after_ref_ms"] or 1e9) <= 150 and (m["hold_ms"] or 0) >= 1900 and (m["held_chunks"] or 0) >= 1
        sched_ok = (m["steal_after_ref_ms"] or 1e9) <= 260
        m["valid"] = bool(harness_ok and hold_ok and sched_ok and m["stolen"] and m["steal_during_hold"])
    elif kind == "dlgsteal":
        m["valid"] = bool(harness_ok and m["stolen"] and (m["steal_after_ref_ms"] or 1e9) <= 140
                          and (m["lag_rewrites_stale"] or 0) >= 1)
    else:
        m["valid"] = bool(harness_ok)
    m["verified_restore"] = bool(m["stolen"] and m["final_ok"] and receipt == "restored" and m["oracle_verified"]
                                 and rv["restore_requests"] >= 1 and m["record_final_active_is_reference"])
    m["silent_miss"] = bool(m["stolen"] and not m["final_ok"] and receipt is None)
    m["silent_miss_reported_as_success"] = bool(m["silent_miss"] and not m["click_error"])
    m["misclassified_same_app"] = bool(m["stolen"] and receipt == "same_app_dialog" and m["final_on_decoy"])
    if kind in ("mfonly", "nosteal"):
        m["false_restore"] = bool(receipt is not None or m["focus_moved_after_T0"] or rv["focus_requests_after_click"])
    elif kind == "dlgdialog":
        st = t.get("final_state") or {}
        dw = st.get("dialog_window")
        final_active = final[2] if final else None
        m["dialog_left_focused"] = bool(dw and final_active == dw and rv["final_active"] == dw)
        m["false_restore"] = bool(receipt == "restored" or rv["restore_requests"] or not m["dialog_left_focused"])
    else:
        m["false_restore"] = bool(receipt == "restored" and not m["stolen"])
    exp = t.get("expected") or {}
    fstate = t.get("final_state") or {}
    before = t.get("before") or {}
    seq_delta = (fstate.get("seq", 0) - before.get("seq", 0)) if fstate and before else None
    m["seq_delta"] = seq_delta
    expected_delta = 1  # one publish per task (the dialog fixture publishes once, when its dialog maps)
    m["duplicate_mutation"] = bool(seq_delta is not None and seq_delta > expected_delta)
    m["unverified_success"] = bool(not m["click_error"] and acts and not m["oracle_verified"] and not m["failure"])
    m["expected"] = exp
    return m


def r3q_metrics(t: dict) -> dict[str, Any]:
    s = t.get("steps") or {}
    m: dict[str, Any] = {k: t.get(k) for k in ("id", "block", "_label", "row", "variant", "bin", "binary", "pair")}
    m["loadavg1"] = (t.get("loadavg") or [None])[0]
    m["failure"] = t.get("failure")
    pid = t.get("driver_pid")
    buses = t.get("buses") or []
    per = [driver_conns(b, pid) for b in buses]
    m["driver_connections_per_bus"] = [p["opened"] for p in per]
    m["driver_pings"] = sum(p["pings"] for p in per)
    m["reconnects"] = max(0, sum(p["opened"] for p in per) - 1)
    m["bus_monitor_ok"] = bool(buses) and all(not b.get("error") and b.get("helper_connected") for b in buses) \
        and per[0]["opened"] >= 1
    fresh = s.get("fresh_click") or {}
    m["fresh_verified"] = bool(fresh.get("verified"))
    m["fresh_seq_delta"] = fresh.get("seq_delta")
    if t.get("variant") == "slow":
        sl = s.get("slow_click") or {}
        eff = (sl.get("structured") or {}).get("effect")
        m["slow_effect"] = eff
        m["slow_refused"] = bool(sl.get("refused"))
        m["slow_route"] = (sl.get("structured") or {}).get("route")
        m["slow_seq_delta"] = sl.get("seq_delta")
        claims = bool(sl.get("success")) and eff not in SUCCESS_EFFECTS_HONEST
        m["slow_claims_effect"] = claims
        m["false_success"] = bool(claims and sl.get("seq_delta") == 0)
        m["duplicate_mutation"] = bool((sl.get("seq_delta") or 0) >= 2 or (m["fresh_seq_delta"] or 0) >= 2)
        m["bus_answered_ping"] = bool(t.get("bus_answers_ping_while_stopped"))
        m["stopped_ms"] = t.get("stopped_ms")
        m["ends_refused_or_verified"] = bool(m["fresh_verified"] or (m["slow_refused"] and sl.get("seq_delta") == 0))
        m["pass"] = bool(not m["failure"] and m["bus_monitor_ok"] and m["reconnects"] == 0 and not m["false_success"]
                         and not m["duplicate_mutation"] and m["ends_refused_or_verified"] and m["bus_answered_ping"])
    else:
        facts = t.get("perturb_facts") or {}
        m["old_daemon_alive"] = bool(facts.get("old_daemon_alive"))
        m["old_daemon_states"] = facts.get("old_daemon_states")
        m["new_daemon"] = bool(facts.get("new_daemon"))
        m["new_address_differs"] = facts.get("new_address_differs")
        st = s.get("stale_click") or {}
        m["stale_refused"] = bool(st.get("refused"))
        m["stale_code"] = st.get("code")
        m["stale_seq_delta"] = st.get("seq_delta")
        m["stale_effect"] = (st.get("structured") or {}).get("effect")
        m["b_truthful_on_try"] = t.get("b_truthful_on_try")
        m["b_degraded_all"] = t.get("b_truthful_on_try") is None
        m["false_success"] = bool(fresh and fresh.get("success") and not fresh.get("verified"))
        m["duplicate_mutation"] = bool((m["fresh_seq_delta"] or 0) >= 2 or (m["stale_seq_delta"] or 0) >= 2)
        m["live_in_process"] = bool(m["b_truthful_on_try"] and m["fresh_verified"])
        m["perturb_ok"] = bool(m["old_daemon_alive"] and m["new_daemon"]) and (
            t.get("variant") != "launcher_wedge" or all(x == "T" for x in (m["old_daemon_states"] or ["?"])))
        m["pass"] = bool(not m["failure"] and m["perturb_ok"] and m["live_in_process"] and not m["duplicate_mutation"])
    return m


def r3_metrics(t: dict) -> dict[str, Any]:
    """OWN-20P's r3 bus row (blob-identical r3_harness.py), same definitions as OWN-20P's analyze.py."""
    s = t.get("steps") or {}
    o2 = s.get("observe_2") or {}
    stale = s.get("stale_click") or {}
    fresh = s.get("fresh_click") or {}
    m = {k: t.get(k) for k in ("id", "block", "_label", "row", "variant", "bin", "binary", "pair")}
    m["failure"] = t.get("failure")
    m["observe_2_truthful"] = bool(t.get("observe_2_truthful"))
    m["observe_2_structured_error"] = bool(t.get("observe_2_structured_error"))
    m["stale_refused"] = bool(stale.get("refused"))
    m["stale_mutated"] = bool(stale.get("mutated"))
    m["new_token_path"] = t.get("new_token_path")
    m["fresh_verified"] = bool(fresh.get("verified"))
    fa, sa = t.get("final_state_a") or {}, t.get("seq_a_before")
    fresh_on_a = 1 if (m["new_token_path"] == "same_fixture" and m["fresh_verified"]) else 0
    m["stale_authority_mutations"] = (int(fa.get("seq", sa or 0)) - int(sa or 0) - fresh_on_a) if fa and sa is not None \
        else None
    events = t.get("perturb_events") or []
    m["daemon_killed"] = any(e.get("kill") == "a11y-bus-daemon" and "pid" in e for e in events)
    m["pass_safety"] = bool(not m["failure"] and (m["observe_2_truthful"] or m["observe_2_structured_error"])
                            and m["stale_refused"] and not m["stale_mutated"] and m["stale_authority_mutations"] == 0)
    m["pass"] = bool(m["pass_safety"] and m["fresh_verified"])
    m["perturb_ms"] = t.get("perturb_ms")
    return m


def cell(rows: list[dict], **kw) -> list[dict]:
    return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]


def main() -> None:
    argv = sys.argv[1:]
    out_dir = None
    if "--out-dir" in argv:
        i = argv.index("--out-dir")
        out_dir = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    pkt = Path(argv[0] if argv else Path(__file__).resolve().parent)
    out_dir = out_dir or pkt
    trials, _ = load(pkt)
    rows: list[dict] = []
    for t in trials:
        if t.get("kind") in FOCUS_KINDS:
            rows.append({"family": "focus", **focus_metrics(t)})
        elif t.get("variant") in ("launcher_keep", "launcher_wedge", "slow"):
            rows.append({"family": "r3q", **r3q_metrics(t)})
        elif t.get("variant") == "bus":
            rows.append({"family": "r3", **r3_metrics(t)})
    S: dict[str, Any] = {"schema": "own20q.summary.v1", "trials": len(rows)}

    # calibration (no gate)
    cal = cell(rows, kind="mfcal")
    within = [r for r in cal if r.get("hold_minus_markrule_ms") is not None and abs(r["hold_minus_markrule_ms"]) <= 5.0]
    S["calibration"] = {"n": len(cal), "within_5ms": len(within), "threshold": 18,
                        "met": len(within) >= 18,
                        "ref_minus_mark_ms": {"median": med([r.get("ref_minus_mark_ms") for r in cal]),
                                              "max_abs": max((abs(r["ref_minus_mark_ms"]) for r in cal
                                                              if r.get("ref_minus_mark_ms") is not None), default=None)},
                        "hold_minus_markrule_ms": sorted({r.get("hold_minus_markrule_ms") for r in cal}, key=str),
                        "U0m_silent_miss": sum(r["silent_miss"] for r in cell(cal, binary="U0m")),
                        "G0m_verified_restore": sum(r["verified_restore"] for r in cell(cal, binary="G0m"))}

    # R1m gate
    r1 = cell(rows, kind="mfstall")
    u0, g0 = cell(r1, binary="U0"), cell(r1, binary="G0")
    ctl = cell(rows, kind="mfonly")
    S["r1m"] = {
        "n": {"U0": len(u0), "G0": len(g0)}, "valid": {"U0": sum(r["valid"] for r in u0), "G0": sum(r["valid"] for r in g0)},
        "U0_silent_miss": sum(r["silent_miss"] for r in u0),
        "G0_verified_restore": sum(r["verified_restore"] for r in g0),
        "G0_silent_miss": sum(r["silent_miss"] for r in g0),
        "per_task": {f"{task}/{b}": {"n": len(cell(r1, task=task, binary=b)),
                                     "valid": sum(r["valid"] for r in cell(r1, task=task, binary=b)),
                                     "silent_miss": sum(r["silent_miss"] for r in cell(r1, task=task, binary=b)),
                                     "verified_restore": sum(r["verified_restore"] for r in cell(r1, task=task, binary=b)),
                                     "receipts": {str(k): sum(1 for r in cell(r1, task=task, binary=b)
                                                              if r["receipt_focus_outcome"] == k)
                                                  for k in sorted({r["receipt_focus_outcome"] for r in
                                                                   cell(r1, task=task, binary=b)}, key=str)},
                                     "hold_after_ref_ms_median": med([r["hold_after_ref_ms"] for r in cell(r1, task=task, binary=b)]),
                                     "steal_after_ref_ms_median": med([r["steal_after_ref_ms"] for r in cell(r1, task=task, binary=b)])}
                     for task in ("checkbox", "text") for b in ("U0", "G0")},
        "control": {b: {"n": len(cell(ctl, binary=b)), "valid": sum(r["valid"] for r in cell(ctl, binary=b)),
                        "verified": sum(r["oracle_verified"] for r in cell(ctl, binary=b)),
                        "false_restore": sum(r["false_restore"] for r in cell(ctl, binary=b))} for b in ("U0", "G0")},
    }
    S["r1m"]["false_restores"] = sum(v["false_restore"] for v in S["r1m"]["control"].values())
    S["r1m"]["gate"] = bool(S["r1m"]["U0_silent_miss"] >= 36 and S["r1m"]["G0_verified_restore"] == 40 == len(g0)
                            and S["r1m"]["false_restores"] == 0
                            and all(v["n"] == v["valid"] > 0 for v in S["r1m"]["control"].values()))

    # DLG
    dl = cell(rows, kind="dlgsteal")
    dd = cell(rows, kind="dlgdialog")
    S["dlg"] = {
        "n": {b: len(cell(dl, binary=b)) for b in ("GA", "GQ")},
        "valid": {b: sum(r["valid"] for r in cell(dl, binary=b)) for b in ("GA", "GQ")},
        "GA_misclassified": sum(r["misclassified_same_app"] for r in cell(dl, binary="GA")),
        "GQ_misclassified": sum(r["misclassified_same_app"] for r in cell(dl, binary="GQ")),
        "GA_verified_restore": sum(r["verified_restore"] for r in cell(dl, binary="GA")),
        "GQ_verified_restore": sum(r["verified_restore"] for r in cell(dl, binary="GQ")),
        "receipts": {b: {str(k): sum(1 for r in cell(dl, binary=b) if r["receipt_focus_outcome"] == k)
                         for k in sorted({r["receipt_focus_outcome"] for r in cell(dl, binary=b)}, key=str)}
                     for b in ("GA", "GQ")},
        "lag_rewrites_stale_median": {b: med([r["lag_rewrites_stale"] for r in cell(dl, binary=b)]) for b in ("GA", "GQ")},
        "dialog_control": {b: {"n": len(cell(dd, binary=b)), "valid": sum(r["valid"] for r in cell(dd, binary=b)),
                               "dialog_left_focused": sum(r["dialog_left_focused"] for r in cell(dd, binary=b)),
                               "verified": sum(r["oracle_verified"] for r in cell(dd, binary=b)),
                               "false_restore": sum(r["false_restore"] for r in cell(dd, binary=b)),
                               "receipts": {str(k): sum(1 for r in cell(dd, binary=b) if r["receipt_focus_outcome"] == k)
                                            for k in sorted({r["receipt_focus_outcome"] for r in cell(dd, binary=b)},
                                                            key=str)}}
                           for b in ("GA", "GQ")},
    }
    S["dlg"]["positive_control"] = S["dlg"]["GA_misclassified"] >= 16
    S["dlg"]["gate"] = bool(S["dlg"]["positive_control"] and S["dlg"]["GQ_verified_restore"] == 20 == S["dlg"]["n"]["GQ"]
                            and S["dlg"]["GQ_misclassified"] == 0
                            and S["dlg"]["dialog_control"]["GQ"]["dialog_left_focused"] == S["dlg"]["dialog_control"]["GQ"]["n"] == 10)

    # normal path
    nm = cell(rows, kind="nosteal")
    S["normal"] = {f"{task}/GQ": {"n": len(cell(nm, task=task)), "verified": sum(r["oracle_verified"] for r in cell(nm, task=task)),
                                  "false_restore": sum(r["false_restore"] for r in cell(nm, task=task)),
                                  "spurious_reconnects": sum(r["spurious_reconnects"] for r in cell(nm, task=task)),
                                  "driver_pings": sum(r["driver_pings"] for r in cell(nm, task=task)),
                                  "T_ms_median_descriptive": med([r["T_ms"] for r in cell(nm, task=task)])}
                   for task in ("checkbox", "text")}
    S["normal"]["GQ_verified"] = sum(v["verified"] for k, v in S["normal"].items() if "/" in k)
    S["normal"]["GQ_false_restores"] = sum(v["false_restore"] for k, v in S["normal"].items() if "/" in k)
    S["normal"]["GQ_spurious_reconnects"] = sum(v["spurious_reconnects"] for k, v in S["normal"].items() if "/" in k)
    S["normal"]["gate"] = bool(S["normal"]["GQ_verified"] == 40 == len(nm) and S["normal"]["GQ_false_restores"] == 0
                               and S["normal"]["GQ_spurious_reconnects"] == 0)

    # A2
    q3 = [r for r in rows if r["family"] == "r3q"]
    a2: dict[str, Any] = {}
    for variant, row in (("launcher_keep", "r3n"), ("slow", "r3s"), ("launcher_wedge", "r3w")):
        c = {}
        for b in ("GA", "GQ"):
            rr = [r for r in q3 if r["variant"] == variant and r["binary"] == b]
            d = {"n": len(rr), "pass": sum(r["pass"] for r in rr), "failures": sum(1 for r in rr if r["failure"]),
                 "reconnects": sum(r["reconnects"] for r in rr), "driver_pings": sum(r["driver_pings"] for r in rr),
                 "false_success": sum(r["false_success"] for r in rr),
                 "duplicate_mutation": sum(r["duplicate_mutation"] for r in rr),
                 "bus_monitor_ok": sum(r["bus_monitor_ok"] for r in rr)}
            if variant == "slow":
                d.update({"ends_refused_or_verified": sum(r["ends_refused_or_verified"] for r in rr),
                          "slow_effects": {str(k): sum(1 for r in rr if r["slow_effect"] == k)
                                           for k in sorted({r["slow_effect"] for r in rr}, key=str)},
                          "slow_refused": sum(r["slow_refused"] for r in rr),
                          "slow_landed": sum(1 for r in rr if (r["slow_seq_delta"] or 0) >= 1),
                          "bus_answered_ping": sum(r["bus_answered_ping"] for r in rr),
                          "trials_with_zero_reconnects": sum(1 for r in rr if r["reconnects"] == 0)})
            else:
                d.update({"perturb_ok": sum(r["perturb_ok"] for r in rr),
                          "old_daemon_alive": sum(r["old_daemon_alive"] for r in rr),
                          "live_in_process": sum(r["live_in_process"] for r in rr),
                          "b_degraded_all_tries": sum(r["b_degraded_all"] for r in rr),
                          "stale_refused": sum(r["stale_refused"] for r in rr),
                          "stale_mutated": sum(1 for r in rr if (r["stale_seq_delta"] or 0) != 0),
                          "new_address_differs": sum(1 for r in rr if r["new_address_differs"])})
            c[b] = d
        a2[row] = c
    r3 = [r for r in rows if r["family"] == "r3"]
    a2["r3_carry"] = {"GQ": {"n": len(r3), "pass": sum(r["pass"] for r in r3),
                             "pass_safety": sum(r["pass_safety"] for r in r3),
                             "daemon_killed": sum(r["daemon_killed"] for r in r3),
                             "pass_where_killed": sum(r["pass"] for r in r3 if r["daemon_killed"]),
                             "stale_mutated": sum(r["stale_mutated"] for r in r3),
                             "perturb_ms_median": med([r["perturb_ms"] for r in r3])}}
    # post-hoc restart-happened view (as OWN-20P deviation 2): counted r3_carry trials whose harness really
    # signalled the bus daemon, plus the committed supplement (plan-supp.json); never a gate input
    supp = [r3_metrics(t) for t in load(pkt, "supplement_labels")[0] if t.get("variant") == "bus"]
    killed = [r for r in r3 + supp if r["daemon_killed"]]
    a2["r3_carry"]["restart_happened_view"] = {
        "counted_killed": sum(1 for r in r3 if r["daemon_killed"]), "supplement_n": len(supp),
        "supplement_killed": sum(1 for r in supp if r["daemon_killed"]), "killed_total": len(killed),
        "live_where_killed": sum(r["pass"] for r in killed), "safe_where_killed": sum(r["pass_safety"] for r in killed),
        "respawned_fixture_verified_where_killed": sum(1 for r in killed if r["new_token_path"] == "respawned_fixture"
                                                       and r["fresh_verified"])}
    a2["r3n_positive_control"] = a2["r3n"]["GA"]["b_degraded_all_tries"] >= 18
    a2["r3n_gate"] = bool(a2["r3n_positive_control"] and a2["r3n"]["GQ"]["pass"] == 20 == a2["r3n"]["GQ"]["n"])
    a2["r3s_gate"] = bool(a2["r3s"]["GQ"]["pass"] == 20 == a2["r3s"]["GQ"]["n"])
    a2["r3_carry_gate"] = bool(a2["r3_carry"]["GQ"]["pass"] == 20 == a2["r3_carry"]["GQ"]["n"])
    a2["r3w_supplementary"] = {"GA_never_live": a2["r3w"]["GA"]["n"] - a2["r3w"]["GA"]["live_in_process"],
                               "GQ_live": a2["r3w"]["GQ"]["live_in_process"]}
    S["a2"] = a2

    # E4 per arm
    e4: dict[str, Any] = {}
    for r in rows:
        key = f"{r.get('row')}/{r.get('binary')}"
        d = e4.setdefault(key, {"n": 0, "unverified_success": 0, "false_restore": 0, "silent_miss_reported_as_success": 0,
                                "duplicate_mutation": 0, "false_success": 0, "stale_mutation": 0})
        d["n"] += 1
        if r["family"] == "focus":
            d["unverified_success"] += int(r["unverified_success"])
            d["false_restore"] += int(r["false_restore"])
            d["silent_miss_reported_as_success"] += int(r["silent_miss_reported_as_success"])
            d["duplicate_mutation"] += int(r["duplicate_mutation"])
        elif r["family"] == "r3q":
            d["false_success"] += int(r["false_success"])
            d["duplicate_mutation"] += int(r["duplicate_mutation"])
        else:
            d["stale_mutation"] += int(r["stale_mutated"] or (r["stale_authority_mutations"] or 0) != 0)
    S["e4"] = e4
    S["loadavg1"] = {"min": min((r["loadavg1"] for r in rows if r.get("loadavg1") is not None), default=None),
                     "max": max((r["loadavg1"] for r in rows if r.get("loadavg1") is not None), default=None),
                     "median": med([r.get("loadavg1") for r in rows])}
    (out_dir / "own20q-summary.json").write_text(json.dumps(S, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with gzip.GzipFile(out_dir / "own20q-trial-metrics.jsonl.gz", "wb", compresslevel=9, mtime=0) as raw_stream, \
            __import__("io").TextIOWrapper(raw_stream, encoding="utf-8") as stream:
        for r in rows:
            stream.write(json.dumps(r, sort_keys=True) + "\n")
    print(json.dumps({k: S[k].get("gate") if isinstance(S[k], dict) and "gate" in S[k] else None
                      for k in ("r1m", "dlg", "normal")}), json.dumps({k: v for k, v in S["a2"].items()
                                                                      if k.endswith(("gate", "control"))}))


if __name__ == "__main__":
    main()

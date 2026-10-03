#!/usr/bin/env python3
"""FIX-03 analysis: every counted row, gate and E4 counter from raw/ (stdlib only).

usage: python3 analyze.py [--raw raw] [--out summary.json]
Counted blocks are the ones listed in plans/*.txt (shakedowns live in raw/shakedown/ and are ignored).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ACT_OPS = {"SetInputFocus", "FocusIn"}


def jsonl(path):
    # Native block files are stored gzip-compressed in the packet (path + ".gz").
    if not os.path.exists(path) and os.path.exists(path + ".gz"):
        import gzip
        with gzip.open(path + ".gz", "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def plan_blocks(plans_dir):
    blocks = []
    for path in sorted(glob.glob(os.path.join(plans_dir, "*.txt"))):
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                parts = line.split()
                if parts and not parts[0].startswith("#"):
                    blocks.append(parts)
    return blocks


# ---------------------------------------------------------------- Part A


def browser_cells(raw, blocks):
    cells = defaultdict(list)
    for parts in blocks:
        if parts[0] != "B":
            continue
        _, arm, phase, block = parts[:4]
        found = None
        for suffix in ("", "R"):
            path = os.path.join(raw, "browser", f"{block}{suffix}-{phase}-{arm}", "cells.jsonl")
            if os.path.exists(path) and os.path.getsize(path) > 0:
                found = path
        if found:
            for cell in jsonl(found):
                cells[(phase, arm)].append(cell)
    return cells


def part_a(cells):
    out = {}
    fs = cells.get(("a1", "FS"), [])
    f5 = cells.get(("a1", "F5"), [])
    out["A1"] = {
        "FS": {"n": len(fs), "race_forced": sum(c["race_forced"] for c in fs),
               "success_receipt_for_detached_node": sum(c["success_receipt_for_detached_node"] for c in fs),
               "gen0_events_cells": sum(1 for c in fs if c["gen0_file_events"] > 0),
               "gen0_change_events_total": sum(c["gen0_change_events"] for c in fs)},
        "F5": {"n": len(f5), "race_forced": sum(c["race_forced"] for c in f5),
               "success_receipts": sum(1 for c in f5 if c.get("first_status") == "ok"),
               "refused": sum(1 for c in f5 if c.get("first_result") == "refused"),
               "refused_post_check_unknown": sum(1 for c in f5 if c.get("first_result") == "refused"
                                                 and c.get("first_delivery_unknown") and c.get("first_retryable") is False),
               "refused_pre_check": sum(1 for c in f5 if c.get("first_result") == "refused"
                                        and not c.get("first_delivery_unknown")),
               "codes": sorted({str(c.get("first_code")) for c in f5}),
               "gen0_events_cells": sum(1 for c in f5 if c["gen0_file_events"] > 0),
               "gen0_change_events_total": sum(c["gen0_change_events"] for c in f5),
               "cells_with_zero_gen0_change": sum(1 for c in f5 if c["gen0_change_events"] == 0)},
    }
    a = out["A1"]
    a["positive_control_pass"] = a["FS"]["success_receipt_for_detached_node"] >= 18 and a["FS"]["n"] == 20
    a["gate_clause_no_success"] = a["F5"]["n"] == 20 and a["F5"]["success_receipts"] == 0
    a["gate_clause_all_refused_or_unknown"] = a["F5"]["n"] == 20 and a["F5"]["refused"] == 20
    a["gate_clause_zero_gen0_change"] = a["F5"]["n"] == 20 and a["F5"]["cells_with_zero_gen0_change"] == 20
    a["gate_pass"] = a["gate_clause_no_success"] and a["gate_clause_all_refused_or_unknown"] and a["gate_clause_zero_gen0_change"]
    out["A2"] = {arm: {"n": len(cells.get(("a1", arm), [])),
                       "rebind_verified": sum(c["rebind_verified"] for c in cells.get(("a1", arm), []))}
                 for arm in ("F5", "FS")}
    out["A2"]["gate_pass"] = out["A2"]["F5"]["n"] == 20 and out["A2"]["F5"]["rebind_verified"] == 20
    a3 = {}
    shapes = set()
    for arm in ("F5", "F"):
        cs = cells.get(("a3", arm), [])
        a3[arm] = {"n": len(cs), "verified": sum(c["a3_verified"] for c in cs),
                   "seam_markers": sum(c["seam_markers"] for c in cs)}
        for c in cs:
            shapes.add(json.dumps([c.get("first_receipt_keys"), c.get("first_receipt")], sort_keys=True))
    a3["receipt_shapes"] = sorted(shapes)
    a3["gate_pass"] = (all(a3[arm]["n"] == 20 and a3[arm]["verified"] == 20 and a3[arm]["seam_markers"] == 0
                           for arm in ("F5", "F")) and len(shapes) == 1)
    out["A3"] = a3
    out["timing_descriptive_ms"] = {
        f"{phase}-{arm}": sorted(c["wall_ms_informational"] for c in cs) for (phase, arm), cs in cells.items()}
    return out


# ---------------------------------------------------------------- Parts C, D


def native_records(raw, blocks):
    rows = defaultdict(lambda: {"attempts": [], "windows": {}, "xrecord": defaultdict(list)})
    for parts in blocks:
        if parts[0] != "N":
            continue
        _, arm, row, block = parts[:4]
        for suffix in ("", "R"):
            path = os.path.join(raw, "native", arm, row, f"b{block}{suffix}.jsonl")
            if not os.path.exists(path) and not os.path.exists(path + ".gz"):
                continue
            for rec in jsonl(path):
                key = (row, arm)
                if rec.get("kind") == "attempt":
                    rows[key]["attempts"].append(rec)
                elif rec.get("kind") == "windows":
                    rows[key]["windows"][(rec["block"], rec["attempt"])] = rec
                elif rec.get("kind") == "xrecord":
                    rows[key]["xrecord"][rec["block"]].append(rec["item"])
    return rows


def win_ids(wrec, key):
    xid = wrec["windows"][key]
    frames = wrec.get("frames") or {}
    ids = {int(xid)}
    ids.update(int(p) for p in (frames.get("parents") or {}).get(str(xid), []))
    ids.update(int(c) for c in (frames.get("children") or {}).get(str(xid), []))
    return ids


def activation_items(items, ids, t0, t1):
    hits = []
    for it in items:
        if not (t0 <= it.get("t_ns", 0) <= t1):
            continue
        w = it.get("window")
        if w not in ids:
            continue
        if it.get("op") == "SendEvent" and it.get("net_active_window"):
            hits.append("net_active_window")
        elif it.get("op") in ACT_OPS:
            hits.append(it["op"])
        elif it.get("op") == "ConfigureWindow" and it.get("stack_mode_set"):
            hits.append("raise")
    return hits


def wstate(state, key):
    return ((state or {}).get("P") or {}).get("windows", {}).get(key) or {}


def changed(call, key, field):
    return wstate(call["pre"], key).get(field) != wstate(call["post"], key).get(field)


def step(att, prefix):
    for call in att["calls"]:
        if call["step"].startswith(prefix):
            return call
    return None


def part_c_d(rows):
    out = {}
    e4 = defaultdict(lambda: defaultdict(int))
    for (row, arm), data in sorted(rows.items()):
        atts = data["attempts"]
        res = {"n": len(atts)}
        if row == "WR":
            c = defaultdict(int)
            for att in atts:
                wrec = data["windows"].get((att["block"], att["attempt"]))
                items = data["xrecord"].get(att["block"], [])
                # Deviation 3 (README): the X RECORD oracle is live for a block only if it recorded traffic
                # beyond its "ready" line; attempts of a dead-oracle block are excluded from the X RECORD
                # clauses (counted as oracle_unavailable) and kept for every state-oracle clause.
                live = any("op" in it for it in items)
                c["xrecord_live_attempts"] += int(live)
                c["xrecord_unavailable_attempts"] += int(not live)
                w1 = win_ids(wrec, "w1") if wrec else set()
                for name in ("s1", "s2", "s3"):
                    call = step(att, name)
                    mut_w1 = changed(call, "w1", "agreed")
                    mut_w2 = changed(call, "w2", "agreed")
                    side = activation_items(items, w1, call["t_send_ns"], call["t_settled_ns"]) if live else []
                    c[f"{name}_refused"] += int(bool(call["is_error"]))
                    c[f"{name}_code_{call['refusal_code']}"] += 1
                    c[f"{name}_mutation_w1"] += int(mut_w1)
                    c[f"{name}_mutation_w2"] += int(mut_w2)
                    c[f"{name}_w1_side_effect"] += int(bool(side))
                    if mut_w1:
                        e4[arm]["cross_session_mutation"] += 1
                    if side:
                        e4[arm]["cross_session_routing_side_effect"] += 1
                s4, s5, s6 = step(att, "s4"), step(att, "s5"), step(att, "s6")
                c["s4_B_own_verified"] += int(not s4["is_error"] and changed(s4, "w2", "agreed")
                                              and not changed(s4, "w1", "agreed"))
                c["s6_A_own_verified"] += int(not s6["is_error"] and changed(s6, "w1", "agreed")
                                              and not changed(s6, "w2", "agreed"))
                if live:
                    c["s5_w1_activation_observed"] += int(bool(activation_items(
                        items, w1, s5["t_send_ns"], s5["t_settled_ns"])))
            res.update(c)
            n = len(atts)
            live_n = res.get("xrecord_live_attempts", 0)
            res["gate_pass"] = (n >= 20 and all(res.get(f"{s}_refused", 0) == n and res.get(f"{s}_mutation_w1", 0) == 0
                                                and res.get(f"{s}_mutation_w2", 0) == 0 for s in ("s1", "s2", "s3"))
                                and live_n >= 20
                                and res.get("s1_w1_side_effect", 0) == 0 and res.get("s2_w1_side_effect", 0) == 0
                                and res.get("s3_w1_side_effect", 0) == 0
                                and res["s4_B_own_verified"] == n and res["s6_A_own_verified"] == n
                                and res.get("s5_w1_activation_observed", 0) >= 0.9 * live_n)
        elif row in ("WS", "WK"):
            field = "note_text" if row == "WS" else "agreed"
            c = defaultdict(int)
            for att in atts:
                b = step(att, "B-types" if row == "WS" else "B-presses")
                a = step(att, "A-types" if row == "WS" else "A-presses")
                b_w1, b_w2 = changed(b, "w1", field), changed(b, "w2", field)
                a_w1, a_w2 = changed(a, "w1", field), changed(a, "w2", field)
                c["B_own_window_verified"] += int(b_w2 and not b_w1)
                c["B_wrote_into_A_window"] += int(b_w1)
                c["A_own_window_verified"] += int(a_w1 and not a_w2)
                c["A_wrote_into_B_window"] += int(a_w2)
                c["B_effect_" + str((b.get("response") or {}).get("structuredContent", {}).get("effect"))] += 1
                e4[arm]["cross_session_mutation"] += int(b_w1) + int(a_w2)
                for call, wrong, own in ((b, b_w1, b_w2), (a, a_w2, a_w1)):
                    effect = (call.get("response") or {}).get("structuredContent", {}).get("effect")
                    if effect == "confirmed" and (wrong or not own):
                        e4[arm]["unverified_success"] += 1
                    c["confirmed_receipt_but_wrong_window"] += int(effect == "confirmed" and wrong)
            res.update(c)
            res["gate_pass"] = (len(atts) == 20 and res["B_own_window_verified"] == 20 and res["A_own_window_verified"] == 20
                                and res["B_wrote_into_A_window"] == 0 and res["A_wrote_into_B_window"] == 0)
        elif row in ("W2dX", "W2cX"):
            c = defaultdict(int)
            for att in atts:
                b = att["calls"][-2]
                tail = att["calls"][-1]
                landed = any(changed(b, k, "agreed") for k in ("w1", "w2"))
                c["B_landed"] += int(landed)
                c["B_refused"] += int(bool(b["is_error"]) and not landed)
                c["B_code_" + str(b["refusal_code"])] += 1
                c["tail_verified"] += int(not tail["is_error"] and changed(tail, "w2", "agreed"))
                if row == "W2dX":
                    c["w1_closed_confirmed"] += int(bool(att.get("w1_closed_confirmed")))
                e4[arm]["cross_session_mutation"] += int(landed)
            res.update(c)
        out[f"{row}-{arm}"] = res
    for row in ("W2dX", "W2cX"):
        u, f = out.get(f"{row}-U", {}), out.get(f"{row}-F5", {})
        out[f"{row}-discriminating"] = bool(u.get("n") == 20 and u.get("B_landed", 0) >= 18 and f.get("n") == 20
                                            and f.get("B_refused", 0) == 20 and f.get("tail_verified", 0) == 20)
    return out, e4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(HERE, "raw"))
    ap.add_argument("--plans", default=os.path.join(HERE, "plans"))
    ap.add_argument("--out", default=os.path.join(HERE, "summary.json"))
    args = ap.parse_args()
    blocks = plan_blocks(args.plans)
    cells = browser_cells(args.raw, blocks)
    a = part_a(cells)
    cd, e4 = part_c_d(native_records(args.raw, blocks))
    for arm in ("FS", "F5"):
        cs = cells.get(("a1", arm), [])
        e4[arm]["stale_dispatch_seam_forced_A1"] += sum(1 for c in cs if c["gen0_file_events"] > 0)
        e4[arm]["unverified_success"] += sum(1 for c in cs if c["success_receipt_for_detached_node"])
    summary = {"part_a": a, "part_c_d": cd, "e4": {arm: dict(v) for arm, v in sorted(e4.items())}}
    f5 = summary["e4"].get("F5", {})
    summary["e4_F5_excluding_seam_forced_residue"] = sum(v for k, v in f5.items() if k != "stale_dispatch_seam_forced_A1")
    summary["e4_F5_strict"] = sum(f5.values())
    with open(args.out, "w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=1, sort_keys=True)
        stream.write("\n")
    # Pre-registered disposition rules (PREREG.json "dispositions"); unit rows are read from the unit logs.
    a1 = a["A1"]
    if a1["gate_pass"] and a1["positive_control_pass"]:
        f4 = "KEEP"
    elif (a1["positive_control_pass"] and a1["gate_clause_no_success"] and a1["gate_clause_all_refused_or_unknown"]):
        f4 = "REVISE (IRREDUCIBLE-with-honest-unknown)"
    else:
        f4 = "REVISE"
    wr_ok = all(cd.get(f"WR-{arm}", {}).get("gate_pass") for arm in ("F", "F5"))
    side_ok = all(cd.get(f"{row}-F5", {}).get("gate_pass") for row in ("WS", "WK"))
    disp = {
        "F4": {"verdict": f4, "A1_positive_control": a1["positive_control_pass"], "A1_gate": a1["gate_pass"],
               "A1_clauses": {k: a1[k] for k in a1 if k.startswith("gate_clause")},
               "A2": a["A2"]["gate_pass"], "A3": a["A3"]["gate_pass"]},
        "C": {"verdict": "KEEP" if (wr_ok and side_ok) else "REVISE", "WR_F_and_F5": wr_ok, "WS_WK_F5": side_ok,
              "routing_fix_needed": not all(cd.get(f"WR-{arm}", {}).get(f"s{n}_w1_side_effect", 1) == 0
                                            for arm in ("F", "F5") for n in (1, 2))},
        "D": {row: ("discriminating KEEP" if cd.get(f"{row}-discriminating") else "non-gating")
              for row in ("W2dX", "W2cX")},
        "E4_F5": {"excluding_seam_forced_A1_residue": summary["e4_F5_excluding_seam_forced_residue"],
                  "strict": summary["e4_F5_strict"]},
    }
    with open(os.path.join(os.path.dirname(args.out), "dispositions.json"), "w", encoding="utf-8") as stream:
        json.dump(disp, stream, indent=1, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"A1_gate": a["A1"]["gate_pass"], "A1_pc": a["A1"]["positive_control_pass"],
                      "A2": a["A2"]["gate_pass"], "A3": a["A3"]["gate_pass"],
                      **{k: v.get("gate_pass") for k, v in cd.items() if isinstance(v, dict) and "gate_pass" in v},
                      "W2dX_disc": cd.get("W2dX-discriminating"), "W2cX_disc": cd.get("W2cX-discriminating"),
                      "e4_F5_excl": summary["e4_F5_excluding_seam_forced_residue"], "e4_F5_strict": summary["e4_F5_strict"]}))


if __name__ == "__main__":
    main()

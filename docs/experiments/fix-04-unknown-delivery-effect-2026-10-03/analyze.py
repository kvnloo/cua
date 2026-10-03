#!/usr/bin/env python3
"""FIX-04 analysis: every REAL row, gate and E4 counter from raw/ (stdlib only).

usage: python3 analyze.py            -> writes summary.json and dispositions.json next to this file

Row definitions are the ones pre-registered in PREREG.json (this file is committed with it, before the
first counted block). Every attempt / cell is kept; invalid ones stay in the denominator and are
counted separately.
"""

from __future__ import annotations

import glob
import gzip
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")


def jl(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def plans():
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "plans", "*.txt"))):
        for line in open(path, encoding="utf-8"):
            parts = line.split()
            if parts and not parts[0].startswith("#"):
                out.append(parts)
    return out


def w2(state):
    return ((state or {}).get("P") or {}).get("windows", {}).get("w2")


def call(rec, prefix):
    for item in rec.get("calls", []):
        if item["step"].startswith(prefix):
            return item
    return None


def changed_w2(item):
    return item is not None and w2(item["pre"]) != w2(item["post"])


def receipt(item):
    sc = (item or {}).get("response", {}).get("structuredContent") or {}
    refused = bool(item and (item["is_error"] or item.get("refusal_code")))
    return {"class": "refused" if refused else "accepted", "code": (item or {}).get("refusal_code"),
            "effect": sc.get("effect")}


def native_attempts(arm, row):
    recs = []
    for path in sorted(glob.glob(os.path.join(RAW, "native", arm, row, "b*.jsonl*"))):
        recs += [r for r in jl(path) if r.get("kind") == "attempt"]
    return recs


def row_c(arm, row):
    """CT / CF: A's own token for its closed window w1; cross-window = any w2 change during A's call."""
    a_prefix = "A-types-into-closed-w1" if row == "CT" else "A-presses-space-on-closed-w1"
    tail_prefix = "B-types-into-own-w2" if row == "CT" else "B-clicks-own-w2"
    recs = native_attempts(arm, row)
    out = {"attempts": len(recs), "cross_window": 0, "a_refused": 0, "a_accepted": 0, "valid": 0,
           "w1_closed": 0, "tail_verified": 0, "codes": {}, "effects": {}, "cross_window_attempts": []}
    for rec in recs:
        a, tail = call(rec, a_prefix), call(rec, tail_prefix)
        closed = rec.get("w1_closed_confirmed") is True
        tail_ok = changed_w2(tail)
        out["w1_closed"] += closed
        out["tail_verified"] += tail_ok
        out["valid"] += closed and tail_ok
        r = receipt(a)
        out["a_refused" if r["class"] == "refused" else "a_accepted"] += 1
        out["codes"][str(r["code"])] = out["codes"].get(str(r["code"]), 0) + 1
        out["effects"][str(r["effect"])] = out["effects"].get(str(r["effect"]), 0) + 1
        if changed_w2(a):
            out["cross_window"] += 1
            out["cross_window_attempts"].append(f"{rec['block']}#{rec['attempt']}")
    return out


def row_w2dx(arm):
    recs = native_attempts(arm, "W2dX")
    out = {"attempts": len(recs), "landed": 0, "refused": 0, "tail_verified": 0, "w1_closed": 0, "codes": {}}
    for rec in recs:
        b = call(rec, "B-uses-A-w2-token-after-w1-closed")
        tail = call(rec, "A-uses-own-w2-token-after-w1-closed")
        out["w1_closed"] += rec.get("w1_closed_confirmed") is True
        out["landed"] += changed_w2(b)
        r = receipt(b)
        out["refused"] += r["class"] == "refused"
        out["codes"][str(r["code"])] = out["codes"].get(str(r["code"]), 0) + 1
        out["tail_verified"] += changed_w2(tail)
    return out


def browser_cells(arm, phase):
    cells = []
    for path in sorted(glob.glob(os.path.join(RAW, "browser", f"*-{phase}-{arm}", "cells", "*.jsonl"))):
        rows = jl(path)
        cells += [r for r in rows if r.get("type") == "cell"]
    return cells


def row_d(arm):
    cells = browser_cells(arm, "a1")
    out = {"cells": len(cells), "race_forced": 0, "success_receipts": 0, "unknown_receipts": 0,
           "raw_effects": {}, "raw_status": {}, "gen0_change_reached_server": 0, "rebind_verified": 0,
           "runner_refused": 0, "runner_may_redispatch_true": 0, "gen0_dispatches_gt1": 0,
           "gen0_change_events_gt1": 0, "wall_ms": []}
    for cell in cells:
        first = (cell.get("steps") or [{}])[0]
        raw = first.get("raw") or {}
        out["race_forced"] += bool(cell.get("race_forced"))
        out["success_receipts"] += raw.get("status") == "ok"
        unknown = (raw.get("status") == "refused" and raw.get("effect") == "unverifiable"
                   and raw.get("delivery") == "unknown" and raw.get("retryable") is False)
        out["unknown_receipts"] += unknown
        out["raw_effects"][str(raw.get("effect"))] = out["raw_effects"].get(str(raw.get("effect")), 0) + 1
        out["raw_status"][str(raw.get("status"))] = out["raw_status"].get(str(raw.get("status")), 0) + 1
        out["gen0_change_reached_server"] += (cell.get("gen0_change_events") or 0) >= 1
        out["gen0_change_events_gt1"] += (cell.get("gen0_change_events") or 0) > 1
        out["rebind_verified"] += bool(cell.get("rebind_verified"))
        out["runner_refused"] += first.get("result") == "refused"
        out["runner_may_redispatch_true"] += first.get("runner_may_redispatch") is True
        gen0_calls = [s for s in cell.get("steps") or [] if s.get("label") == "gen0_ref"]
        out["gen0_dispatches_gt1"] += len(gen0_calls) > 1
        out["wall_ms"].append(cell.get("wall_ms_informational"))
    walls = [w for w in out.pop("wall_ms") if isinstance(w, (int, float))]
    out["median_cell_wall_ms_informational"] = round(statistics.median(walls), 1) if walls else None
    return out


def row_a3(arm):
    cells = browser_cells(arm, "a3")
    keys = {}
    out = {"cells": len(cells), "verified": 0, "status_ok": 0, "effect_key_present": 0}
    for cell in cells:
        first = (cell.get("steps") or [{}])[0]
        raw = first.get("raw") or {}
        out["verified"] += bool(cell.get("a3_verified"))
        out["status_ok"] += raw.get("status") == "ok"
        out["effect_key_present"] += "effect" in (raw.get("keys") or [])
        k = ",".join(raw.get("keys") or [])
        keys[k] = keys.get(k, 0) + 1
    out["receipt_key_sets"] = keys
    return out


def main():
    summary = {
        "C": {"CT": {arm: row_c(arm, "CT") for arm in ("F5", "F6", "U")},
              "CF": {arm: row_c(arm, "CF") for arm in ("F5", "F6")}},
        "D": {"a1_F6": row_d("F6"), "a3_F6": row_a3("F6"),
              "W2dX": {arm: row_w2dx(arm) for arm in ("U", "F6")}},
        "plans_blocks": len(plans()),
    }
    ledger = os.path.join(RAW, "lock-ledger.jsonl")
    summary["locks"] = {"counted_receipts": len(jl(ledger)) if os.path.exists(ledger) else 0}
    c = summary["C"]
    d = summary["D"]
    gates = {
        "C_CT": "KEEP" if c["CT"]["F6"]["attempts"] == 20 and c["CT"]["F6"]["cross_window"] == 0 else "FAIL",
        "C_CF": "KEEP" if c["CF"]["F6"]["attempts"] == 20 and c["CF"]["F6"]["cross_window"] == 0 else "FAIL",
        "C_CT_discriminating": c["CT"]["F5"]["cross_window"] >= 1,
        "C_CF_discriminating": c["CF"]["F5"]["cross_window"] >= 1,
        "D": "KEEP" if d["a1_F6"]["cells"] == 20 and d["a1_F6"]["success_receipts"] == 0
        and d["a1_F6"]["unknown_receipts"] == 20 else "FAIL",
        "D_W2dX_discriminating": d["W2dX"]["U"]["landed"] >= 1 and d["W2dX"]["F6"]["landed"] == 0,
        "E4_blind_replays": d["a1_F6"]["runner_may_redispatch_true"] + d["a1_F6"]["gen0_dispatches_gt1"]
        + d["a1_F6"]["gen0_change_events_gt1"],
    }
    summary["gates"] = gates
    with open(os.path.join(HERE, "summary.json"), "w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=1, sort_keys=True)
        stream.write("\n")
    with open(os.path.join(HERE, "dispositions.json"), "w", encoding="utf-8") as stream:
        json.dump(gates, stream, indent=1, sort_keys=True)
        stream.write("\n")
    print(json.dumps(gates, sort_keys=True))


if __name__ == "__main__":
    main()

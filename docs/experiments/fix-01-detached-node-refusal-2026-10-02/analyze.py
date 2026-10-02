#!/usr/bin/env python3
"""Recompute every FIX-01 row, gate and disposition from raw/ (stdlib only).

usage: python3 analyze.py [--write]   (prints the summary; --write updates fix01-summary.json)
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
MEASURED = RAW / "measured"
SEED, RESAMPLES = 20261002, 10000


def jl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def blocks() -> list[dict]:
    out = []
    for d in sorted(p for p in MEASURED.iterdir() if p.is_dir()):
        v = json.loads((d / "validity.json").read_text())
        cells = []
        for c in sorted((d / "cells").iterdir()) if (d / "cells").exists() else []:
            if c.is_file():
                recs = jl(c)
                cell = next(r for r in recs if r["type"] == "cell")
                cell["_journal"] = next((r["events"] for r in recs if r["type"] == "target_journal"), [])
                cell["_runner_events"] = next((r["events"] for r in recs if r["type"] == "runner_events"), [])
            else:  # subprocess cell directory (G2/G6)
                cell = json.loads((c / "cell.json").read_text())
                recs = jl(c / "trial.jsonl")
                cell["_receipts"] = [r for r in recs if r.get("type") == "receipt"]
                cell["_runner_events"] = [r["event"] for r in recs if r.get("type") == "runner_event"]
                cell["_journal"] = next((r["events"] for r in recs if r.get("type") == "target_journal"), [])
            cells.append(cell)
        out.append({"name": d.name, "validity": v, "cells": cells, "valid": bool(v.get("ok"))})
    return out


def journal_summary(events: list[dict]) -> dict:
    """Target-owned counts, recomputed from the raw journal (same rules as harness/fix01_fixture.py)."""
    page = [e for e in events if e.get("kind") == "page_event"]
    srcs = [e for e in events if e.get("kind") == "submit_src"]
    return {
        "page_events_old": sum(1 for e in page if e.get("node") == "old"),
        "page_events_fresh": sum(1 for e in page if e.get("node") == "fresh"),
        "page_events_same": sum(1 for e in page if e.get("node") == "same"),
        "submits_from_detached_handler": sum(1 for e in srcs if e.get("src") == "detached"),
        "applied": sum(1 for e in events if e.get("kind") == "applied"),
    }


def label_of(block: dict) -> str:
    return block["validity"]["driver_label"]


def by_phase(bs, phase, label=None, runner=None):
    cells = []
    for b in bs:
        if not b["valid"] or b["validity"]["phase"] != phase:
            continue
        if label is not None and label_of(b) != label:
            continue
        for c in b["cells"]:
            if runner is not None and c.get("runner") != runner:
                continue
            cells.append(c)
    return cells


def first_click(cell):
    clicks = [m for m in cell.get("mutations") or [] if m.get("action", m.get("tool")) == "browser_click"]
    return clicks[0] if clicks else {}


def routine_row(cells):
    c = Counter()
    for cell in cells:
        fc = first_click(cell)
        js = journal_summary(cell["_journal"])
        c["n"] += 1
        c[f"first_click_{fc.get('result')}" + (f"_{fc.get('code')}" if fc.get("code") else "")] += 1
        c["old_node_page_events_gt0"] += js["page_events_old"] > 0
        c["detached_handler_submits_gt0"] += js["submits_from_detached_handler"] > 0
        c["fresh_node_page_events_gt0"] += js["page_events_fresh"] > 0
        c["same_node_page_events_gt0"] += js["page_events_same"] > 0
        c[f"outcome_{cell['outcome']}"] += 1
        c["independently_verified"] += bool(cell["independently_verified"])
        c["duplicates"] += cell["duplicate_submits"]
        c["unverified_success"] += bool(cell["unverified_success"])
        c["not_fresh_dispatches"] += cell["mutations_dispatched_not_fresh"]
        c["refusals"] += sum(1 for m in cell["mutations"] if m.get("result") == "refused")
        clicks = [m for m in cell["mutations"] if m.get("action") == "browser_click"]
        c["click_dispatch_attempts"] += len(clicks)
        c["rebind_redispatch_after_refusal"] += sum(1 for m in clicks if m.get("attempt", 1) == 2)
        c["applied_total"] += cell["journal_applied"]
    return dict(c)


def ordinary_row(cells):
    c = Counter()
    for cell in cells:
        c["n"] += 1
        c["redispatches_after_unverified_accepted"] += cell["redispatches_after_unverified_accepted"]
        c["cells_with_redispatch"] += cell["redispatches_after_unverified_accepted"] > 0
        c["first_click_classified_refused"] += bool(cell["first_click_classified_refused"])
        c["first_click_refused_accepted_as_success"] += bool(cell["first_click_refused_accepted_as_success"])
        c["runner_action_refused_events"] += cell["runner_step_events_with_action_refused"]
        c["fresh_observation_between_clicks"] += bool(cell.get("observations_between_first_and_second_click"))
        c[f"click_dispatches_{cell['click_dispatches']}"] += 1
        fo = cell.get("final_outcome_event") or {}
        c[f"outcome_{cell['outcome']}" + (f"_phase_{fo.get('phase')}" if fo.get("phase") else "")] += 1
        c["independently_verified"] += bool(cell["independently_verified"])
        c["duplicates"] += cell["duplicate_submits"]
        c["unverified_success"] += bool(cell["unverified_success"])
        c["old_node_page_events_gt0"] += journal_summary(cell["_journal"])["page_events_old"] > 0
        c["refusals_seen"] += cell["refusals_seen"]
    return dict(c)


def direct_row(cells):
    c = Counter()
    for cell in cells:
        c["n"] += 1
        fc = cell["mutations"][[m["tool"] for m in cell["mutations"]].index("browser_click")] if any(
            m["tool"] == "browser_click" for m in cell["mutations"]) else {}
        c[f"first_click_{fc.get('result')}" + (f"_{fc.get('code')}" if fc.get("code") else "")] += 1
        js = journal_summary(cell["_journal"])
        c["old_node_page_events_gt0"] += js["page_events_old"] > 0
        c[f"first_pointerdown_on_{cell.get('page_first_down_node')}"] += 1
        c[f"outcome_{cell['outcome']}"] += 1
        c["independently_verified"] += bool(cell["independently_verified"])
        c["refusals"] += cell["refusals"]
        c["unverified_success"] += bool(cell["unverified_success"])
        c["duplicates"] += max(0, js["applied"] - 1)
    return dict(c)


def window_rows(cells):
    rows = []
    for cell in sorted(cells, key=lambda x: x["delay_ms"]):
        fc = first_click(cell)
        if fc.get("result") == "refused":
            cls = f"refused:{fc.get('code')}"
        elif fc.get("result") == "accepted":
            cls = f"accepted:landed_on_{cell.get('page_first_down_node')}"
        else:
            cls = f"other:{fc.get('result')}"
        rows.append({"delay_ms": cell["delay_ms"], "class": cls, "outcome": cell["outcome"],
                     "first_down_minus_rerender_ms": cell.get("page_first_down_minus_rerender_ms"),
                     "click_send_to_return_ms": round(fc["t_return_ms"] - fc["t_send_ms"], 3) if fc.get("t_send_ms") is not None else None,
                     "applied": cell["journal_applied"]})
    inside = [r["first_down_minus_rerender_ms"] for r in rows
              if r["class"] == "accepted:landed_on_fresh" and r["first_down_minus_rerender_ms"] is not None]
    return {"cells": rows, "accepted_landed_on_replacement": len(inside),
            "window_lower_bound_ms": max(inside) if inside else None,
            "classes": dict(Counter(r["class"] for r in rows))}


def receipts_fresh(cell) -> tuple[int, int]:
    """(fresh, total) mutations from launcher Driver-call receipts."""
    latest, latest_after, mutations, fresh, total = None, -1, 0, 0, 0
    for r in cell.get("_receipts", []):
        if r.get("kind") != "driver_call" or not r.get("ok"):
            continue
        if r.get("tool") == "get_browser_state" and r.get("snapshot_id"):
            latest, latest_after = r["snapshot_id"], mutations
        elif r.get("tool") in ("browser_type", "browser_click"):
            total += 1
            if latest and str(r.get("arg_ref", "")).split(":")[0] == latest and latest_after == mutations:
                fresh += 1
            mutations += 1
    return fresh, total


def bootstrap_median(diffs):
    rng = random.Random(SEED)
    meds = sorted(statistics.median(rng.choice(diffs) for _ in diffs) for _ in range(RESAMPLES))
    return [round(meds[int(0.025 * RESAMPLES)], 3), round(meds[int(0.975 * RESAMPLES) - 1], 3)]


def g6(bs):
    cells = by_phase(bs, "g6")
    pairs: dict[int, dict] = {}
    for c in cells:
        pairs.setdefault(c["round"], {})[c["arm"][1:]] = c
    diffs, rows = [], []
    for rnd in sorted(pairs):
        p = pairs[rnd]
        u, f = p.get("U"), p.get("F")
        ok = bool(u and f and u.get("independently_verified") and f.get("independently_verified")
                  and u.get("T_ms") is not None and f.get("T_ms") is not None)
        rows.append({"pair": rnd, "order": "UF" if rnd % 2 == 0 else "FU", "T_U": u and u.get("T_ms"),
                     "T_F": f and f.get("T_ms"), "load_U": u and u.get("loadavg_at_spawn", [None])[0],
                     "load_F": f and f.get("loadavg_at_spawn", [None])[0], "both_verified": ok})
        if ok:
            diffs.append(round(f["T_ms"] - u["T_ms"], 3))
    tu = [r["T_U"] for r in rows if r["both_verified"]]
    tf = [r["T_F"] for r in rows if r["both_verified"]]
    return {
        "pairs_total": len(rows), "pairs_both_verified": len(diffs),
        "cells_total": len(cells), "cells_verified": sum(bool(c.get("independently_verified")) for c in cells),
        "median_T_U_ms": round(statistics.median(tu), 3) if tu else None,
        "median_T_F_ms": round(statistics.median(tf), 3) if tf else None,
        "paired_median_F_minus_U_ms": round(statistics.median(diffs), 3) if diffs else None,
        "ci95": bootstrap_median(diffs) if diffs else None,
        "provider_http_attempts": sum(int(c.get("http_attempts") or 0) for c in cells),
        "fresh_from_receipts": [sum(receipts_fresh(c)[0] for c in cells if c["arm"][1:] == "F"),
                                sum(receipts_fresh(c)[1] for c in cells if c["arm"][1:] == "F")],
        "rows": rows,
    }


def g4(bs):
    out = {}
    cells = by_phase(bs, "g4")
    for row in sorted({c["row"] for c in cells}):
        rc = [c for c in cells if c["row"] == row]
        stale = sum(1 for c in rc if row == "N4a" and first_click(c).get("result") == "accepted")
        ambiguous = sum(1 for c in rc for m in c["mutations"] if m.get("unique_matches", 1) != 1)
        out[row] = {"n": len(rc), "outcomes": dict(Counter(c["outcome"] for c in rc)),
                    "dispatches_per_rep": [sum(1 for m in c["mutations"] if m.get("result") in ("accepted", "refused", "transport_failure")) for c in rc],
                    "journal_applied": [c["journal_applied"] for c in rc], "stale_dispatches": stale,
                    "ambiguous_dispatches": ambiguous, "duplicates": sum(c["duplicate_submits"] for c in rc),
                    "unverified_success": sum(bool(c["unverified_success"]) for c in rc),
                    "not_fresh": sum(c["mutations_dispatched_not_fresh"] for c in rc),
                    "first_click": dict(Counter(f"{first_click(c).get('result')}:{first_click(c).get('code')}" for c in rc if first_click(c)))}
    return out


def g5(bs):
    out = {}
    cells = by_phase(bs, "g5")
    for row in sorted({c["row"] for c in cells}):
        rc = [c for c in cells if c["row"] == row]
        after_unknown = 0
        for c in rc:
            seen_unknown = False
            for e in c.get("events") or []:
                if e.get("kind") == "mutation_unknown":
                    seen_unknown = True
                elif seen_unknown and e.get("kind") in ("dispatched", "dispatch_refused"):
                    after_unknown += 1
        out[row] = {"n": len(rc), "outcomes": dict(Counter(c["outcome"] for c in rc)),
                    "journal_received_applied": [[c["journal_received"], c["journal_applied"]] for c in rc],
                    "reconcile_reads": [len(c["reconcile_reads"]) for c in rc],
                    "duplicates": sum(c["duplicate_submits"] for c in rc), "dispatches_after_unknown": after_unknown,
                    "fault_fired": sum(bool(c.get("fault_fired")) for c in rc),
                    "unverified_success": sum(bool(c["unverified_success"]) for c in rc),
                    "not_fresh": sum(c["mutations_dispatched_not_fresh"] for c in rc)}
    return out


def main() -> int:
    bs = blocks()
    invalid = [b["name"] for b in bs if not b["valid"]]
    s: dict = {"blocks": len(bs), "invalid_blocks": invalid,
               "cells_total": sum(len(b["cells"]) for b in bs),
               "cells_in_valid_blocks": sum(len(b["cells"]) for b in bs if b["valid"])}
    drivers = {}
    for b in bs:
        for label, d in b["validity"]["drivers"].items():
            drivers.setdefault(label, set()).add((d["sha256"], d["version"]))
    s["drivers"] = {k: sorted(map(list, v)) for k, v in drivers.items()}
    s["displays"] = sorted({b["validity"]["display"] for b in bs})
    s["C1"] = {lab: routine_row(by_phase(bs, "c1", lab)) for lab in ("U", "F")}
    s["C2"] = {"U+old": ordinary_row(by_phase(bs, "c2", "U", "old")),
               "U+fixed": ordinary_row(by_phase(bs, "c2", "U", "fixed")),
               "F+fixed": ordinary_row(by_phase(bs, "c2", "F", "fixed"))}
    s["C3"] = {lab: routine_row(by_phase(bs, "c3", lab)) for lab in ("U", "F")}
    s["C4"] = {lab: direct_row(by_phase(bs, "c4", lab)) for lab in ("U", "F")}
    s["C4w"] = window_rows(by_phase(bs, "c4w", "F"))
    s["C5"] = {"F+fixed": ordinary_row(by_phase(bs, "c5", "F", "fixed")),
               "F+old": ordinary_row(by_phase(bs, "c5", "F", "old"))}
    s["C6"] = {"fill": ordinary_row(by_phase(bs, "c6fill", "F")),
               "toggle": direct_row(by_phase(bs, "c6toggle", "F")),
               "modal": direct_row(by_phase(bs, "c6modal", "F")),
               "reattach": routine_row(by_phase(bs, "c6reattach", "F"))}
    g2c = by_phase(bs, "g2")
    s["G2"] = {"n": len(g2c), "verified": sum(bool(c.get("independently_verified")) for c in g2c),
               "reported": [c.get("reported_outcome") for c in g2c], "T_ms": [c.get("T_ms") for c in g2c],
               "provider_http_attempts": sum(int(c.get("http_attempts") or 0) for c in g2c),
               "fresh_from_receipts": [sum(receipts_fresh(c)[0] for c in g2c), sum(receipts_fresh(c)[1] for c in g2c)]}
    s["G4"] = g4(bs)
    s["G5"] = g5(bs)
    s["G6"] = g6(bs)
    inproc = (by_phase(bs, "c1", "F") + by_phase(bs, "c3", "F") + by_phase(bs, "c6reattach", "F")
              + by_phase(bs, "g4") + by_phase(bs, "g5"))
    s["G3"] = {"independent_receipts_fresh_total": [s["G2"]["fresh_from_receipts"][0] + s["G6"]["fresh_from_receipts"][0],
                                                     s["G2"]["fresh_from_receipts"][1] + s["G6"]["fresh_from_receipts"][1]],
               "self_recorded_fresh_total": [sum(sum(1 for m in c["mutations"] if m.get("fresh")) for c in inproc),
                                             sum(len(c["mutations"]) for c in inproc)]}
    # provider: in-process socket guard counts and launcher receipts
    nonloop = 0
    for b in bs:
        end = (MEASURED / b["name"] / "end.json")
        if end.exists():
            nonloop += json.loads(end.read_text()).get("nonloopback_refused_in_process", 0)
        for c in b["cells"]:
            nonloop += sum(int(r.get("count") or 0) for r in c.get("_receipts", []) if r.get("kind") == "nonloopback_refused")
    s["provider"] = {"attempts": nonloop + s["G2"]["provider_http_attempts"] + s["G6"]["provider_http_attempts"],
                     "reached": 0, "nonloopback_connects_refused": nonloop}

    # gates and dispositions (PREREG)
    c1f, c3f = s["C1"]["F"], s["C3"]["F"]
    c6 = s["C6"]
    fix_rows = {
        "C1_F_refuses_20_of_20": c1f.get("n") == 20 and c1f.get("first_click_refused_browser_ref_stale") == 20
        and c1f.get("old_node_page_events_gt0", 0) == 0 and c1f.get("detached_handler_submits_gt0", 0) == 0,
        "C3_F_zero_detached_effects_10_of_10": c3f.get("n") == 10 and c3f.get("detached_handler_submits_gt0", 0) == 0
        and c3f.get("old_node_page_events_gt0", 0) == 0,
        "C6_zero_false_refusals": all(c6[k].get("refusals", c6[k].get("refusals_seen", 0)) == 0 for k in c6)
        and c6["fill"].get("n") == 20 and all(c6[k].get("n") == 10 for k in ("toggle", "modal", "reattach"))
        and all(c6[k].get("independently_verified") == c6[k].get("n") for k in c6),
        "C2_fixed_zero_redispatch": all(s["C2"][k].get("n") == 10 and s["C2"][k].get("redispatches_after_unverified_accepted", 0) == 0
                                        for k in ("U+fixed", "F+fixed")),
        "C5_fixed_classifies_refused_10_of_10": s["C5"]["F+fixed"].get("n") == 10
        and s["C5"]["F+fixed"].get("first_click_classified_refused") == 10,
    }
    s["fix_measured_rows"] = fix_rows
    g4ok = all(r["stale_dispatches"] == 0 and r["ambiguous_dispatches"] == 0 and r["duplicates"] == 0
               and r["unverified_success"] == 0 and r["not_fresh"] == 0 for r in s["G4"].values()) and bool(s["G4"])
    g4ok = g4ok and s["G4"].get("N8", {}).get("dispatches_per_rep", [1]) == [0] * s["G4"].get("N8", {}).get("n", -1)
    g4ok = g4ok and c1f.get("n") == 20 and c1f.get("duplicates", 1) == 0 and c1f.get("unverified_success", 1) == 0
    g5ok = bool(s["G5"]) and all(r["duplicates"] == 0 and r["dispatches_after_unknown"] == 0 and r["unverified_success"] == 0
                                 for r in s["G5"].values())
    g3 = s["G3"]
    s["r2_07b_gates"] = {
        "G2": s["G2"]["n"] >= 1 and s["G2"]["verified"] == s["G2"]["n"] and s["G2"]["provider_http_attempts"] == 0,
        "G3": g3["independent_receipts_fresh_total"][0] == g3["independent_receipts_fresh_total"][1] > 0
        and g3["self_recorded_fresh_total"][0] == g3["self_recorded_fresh_total"][1] > 0,
        "G4": g4ok, "G5": g5ok,
    }
    ci = s["G6"]["ci95"]
    s["G6"]["gate_triggered_ge_5ms"] = bool(ci and ci[0] >= 5.0)
    print(json.dumps(s, indent=1, sort_keys=True, default=str))
    if "--write" in sys.argv:
        (HERE / "fix01-summary.json").write_text(json.dumps(s, indent=1, sort_keys=True, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

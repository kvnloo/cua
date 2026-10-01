"""Recompute every R2-05 headline number from raw/ and check the packet.

    python verify_artifacts.py           # verify r2-05-summary.json + README against raw/
    python verify_artifacts.py --write   # (re)write r2-05-summary.json from raw/

Only the registered measured run (raw/measured) counts; raw/pilot is reported
separately and never enters a denominator. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "measured"
PRE_WRITE = {"ClosedResourceError", "BrokenResourceError"}
TYPED_ROWS = ["R0_control", "RA_pre_dispatch", "RA2_request_lost", "RB_ack_lost_applied",
              "RC_delayed_after_unchanged", "RD_delayed_withheld"]
FAULT_ROWS = TYPED_ROWS[1:]


def load_trials(directory: Path) -> list[dict]:
    trials = []
    for path in sorted(directory.glob("trial-*.jsonl")):
        lines = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        header = lines[0]
        header["_attempts"] = [x for x in lines if x.get("kind") == "attempt"]
        header["_journal"] = next(x for x in lines if x.get("kind") == "target_journal")["events"]
        header["_file"] = path.name
        trials.append(header)
    return trials


def seam(t: dict, n: int = 0) -> list[dict]:
    return t["_attempts"][n]["seam_events"] if len(t["_attempts"]) > n else []


def barrier_reached(t: dict) -> bool | None:
    hits = [e for e in seam(t) if e["kind"] == "target_barrier"]
    return hits[0]["reached"] if hits else None


def forwarded_tools(t: dict, n: int = 0) -> list[str]:
    return [e.get("tool") for e in seam(t, n) if e["kind"] == "forwarded_request"]


def driver_route(t: dict) -> str | None:
    for e in seam(t):
        if e["kind"] in {"driver_response_held", "delivered_response"} and e.get("for_tool") == "browser_click":
            return (e.get("structured") or {}).get("route")
    return None


def placement_ok(t: dict) -> bool:
    if t["fault"] == "none":
        return True
    if not t["fault_fired"]:
        return False
    if t["fault"] == "ack_lost":
        return barrier_reached(t) is True
    return True


def tools_list_requests(t: dict, n: int) -> list[dict]:
    return [e for e in seam(t, n) if e["kind"] == "forwarded_request" and e.get("method") == "tools/list"]


def ra_pre_write_scope(t: dict) -> tuple[bool, list[str]]:
    """Is RA's ClosedResourceError the Submit request's OWN write failing (the only scoped proof)?

    In mcp 1.30.0 call_tool can also raise ClosedResourceError after a successful write and
    response, from the list_tools() refresh inside _validate_tool_result when the tool name is
    not in the session's output-schema cache (extension/test_pre_write_scope.py, case A). The
    class name alone is therefore not a pre-write proof. Here we check from raw/ that RA is the
    scoped case: the startup tools/list completed before the fault, the write stream was closed
    before the next request, no browser_click reached the transport, and the error surfaced in
    the action phase of the guarded-completion click.
    """
    misses: list[str] = []
    events = seam(t, 0)
    kinds = [e["kind"] for e in events]
    lists = tools_list_requests(t, 0)
    closed = [i for i, k in enumerate(kinds) if k == "session_write_stream_closed_before_next_request"]
    list_ok = (len(lists) == 1 and closed and events.index(lists[0]) < closed[0]
               and any(e["kind"] == "delivered_response" and e.get("for_tool") == "tools/list"
                       for e in events[:closed[0]]))
    if not list_ok:
        misses.append("startup_tools_list_before_close")
    if not closed:
        misses.append("write_stream_closed_before_next_request")
    if "browser_click" in forwarded_tools(t, 0):
        misses.append("no_click_forwarded")
    if t["first_phase"] != "action" or t["first_decision_route"] != "guarded-completion":
        misses.append("action_phase_guarded_completion")
    if t["first_error_class"] not in PRE_WRITE:
        misses.append("pre_write_error_class")
    if t["journal_before_recovery"]["received"] != 0:
        misses.append("received0")
    return (not misses), misses


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> list[float]:
    """Exact two-sided (1-alpha) binomial interval, by bisection on the binomial CDF."""
    def cdf(k: int, p: float) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))

    def solve(f) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return (lo + hi) / 2

    lower = 0.0 if x == 0 else solve(lambda p: 1 - cdf(x - 1, p) < alpha / 2)
    upper = 1.0 if x == n else solve(lambda p: cdf(x, p) > alpha / 2)
    return [round(lower, 4), round(upper, 4)]


def typed_first_blocks(order: list) -> dict:
    out: dict[str, int] = {}
    for row in sorted({r for _, r, a in order if a == "naive"}):
        blocks = sorted({b for b, r, _ in order if r == row})
        count = 0
        for b in blocks:
            arms = [a for bb, r, a in order if bb == b and r == row]
            count += arms.index("typed") < arms.index("naive")
        out[row] = count
    return out


def extension_unit() -> dict:
    path = ROOT / "raw" / "unit" / "extension-pre-write-scope.txt"
    text = path.read_text()
    cases = dict(re.findall(r"^([ABC]) \S+ \S+: (error=\S+ effects_applied=\d+)$", text, re.M))
    return {"cases": cases, "rc": re.search(r"^rc=(\d+)$", text, re.M).group(1),
            "ok": cases == {"A": "error=ClosedResourceError effects_applied=1",
                            "B": "error=none effects_applied=1",
                            "C": "error=ClosedResourceError effects_applied=0"}}


def typed_predicate(t: dict) -> tuple[bool, list[str]]:
    row, rec, jb = t["row"], t["recovery"], t["journal_before_recovery"]
    reads = [r["effect_visible"] for r in rec["reads"]]
    misses: list[str] = []

    def need(cond: bool, label: str) -> None:
        if not cond:
            misses.append(label)

    if row == "R0_control":
        need(t["first_outcome"] == "verified", "first_verified")
        need(rec["classification"] == "none", "no_recovery")
    elif row == "RA_pre_dispatch":
        need(t["fault_fired"], "fault_fired")
        need(t["first_error_class"] in PRE_WRITE, "pre_write_error_class")
        need(rec["classification"] == "not_dispatched_proven", "not_dispatched_proven")
        need(jb["received"] == 0, "received0_before_recovery")
        need("browser_click" not in forwarded_tools(t, 0), "no_click_forwarded")
        need(t["final_outcome_reported"] == "verified", "final_verified")
    elif row == "RA2_request_lost":
        need(t["fault_fired"], "fault_fired")
        need(rec["classification"] == "unknown_effect", "unknown_effect")
        need(rec["dispatch_attempts_after_first"] == 0 and t["attempts"] == 1, "no_dispatch_after")
        need(t["final_outcome_reported"] == "unknown" and rec.get("resolution") == "unresolved_unknown",
             "unresolved_unknown")
        need(t["journal_received"] == 0 and t["journal_applied"] == 0, "nothing_received")
    else:
        need(t["fault_fired"], "fault_fired")
        need(barrier_reached(t) is True, "barrier_reached")
        need(rec["classification"] == "unknown_effect", "unknown_effect")
        need(rec["dispatch_attempts_after_first"] == 0 and t["attempts"] == 1, "no_dispatch_after")
        need(t["journal_received"] == jb["received"], "no_new_receipt_after_recovery_start")
        if row == "RB_ack_lost_applied":
            need(jb["applied"] == 1, "applied_before_recovery")
            need(rec.get("resolution") == "reconciled_applied" and t["final_outcome_reported"] == "verified",
                 "reconciled_applied")
        elif row == "RC_delayed_after_unchanged":
            need(jb["applied"] == 0, "not_applied_before_recovery")
            need(bool(reads) and reads[0] is False, "first_read_unchanged")
            need(rec.get("resolution") == "reconciled_applied" and t["final_outcome_reported"] == "verified",
                 "reconciled_applied")
        elif row == "RD_delayed_withheld":
            need(jb["applied"] == 0, "not_applied_before_recovery")
            need(bool(reads) and not any(reads), "all_reads_unchanged")
            need(rec.get("resolution") == "unresolved_unknown" and t["final_outcome_reported"] == "unknown",
                 "unresolved_unknown")
    if row != "RA2_request_lost":
        need(t["journal_applied"] == 1, "applied1_after_settle")
    need(t["duplicate_mutations"] == 0, "no_duplicate")
    return (not misses), misses


def kill_events(t: dict) -> list[str]:
    rec, jb, events = t["recovery"], t["journal_before_recovery"], []
    if t["duplicate_mutations"] > 0:
        events.append("duplicate_mutation")
    if rec["classification"] == "unknown_effect" and (
        rec["dispatch_attempts_after_first"] or t["attempts"] > 1 or t["journal_received"] > jb["received"]
    ):
        events.append("dispatch_after_unknown")
    if jb["applied"] >= 1 and (rec["classification"] == "not_dispatched_proven"
                               or t["final_outcome_reported"] == "refuted"):
        events.append("landed_effect_classified_failed")
    if t["row"] == "RA2_request_lost" and rec["classification"] == "not_dispatched_proven":
        events.append("false_pre_dispatch_inference")
    return events


def cell_summary(rows: list[dict]) -> dict:
    res_ms = [r["resolution_ms_informational"] for r in rows]
    return {
        "n": len(rows),
        "placement_ok": sum(placement_ok(r) for r in rows),
        "first_outcome": dict(Counter(r["first_outcome"] for r in rows)),
        "first_error_class": dict(Counter(str(r["first_error_class"]) for r in rows)),
        "first_decision_route": dict(Counter(str(r["first_decision_route"]) for r in rows)),
        "classification": dict(Counter(str(r["recovery"]["classification"]) for r in rows)),
        "resolution": dict(Counter(str(r["recovery"].get("resolution")) for r in rows)),
        "final_outcome": dict(Counter(r["final_outcome_reported"] for r in rows)),
        "attempts": dict(Counter(str(r["attempts"]) for r in rows)),
        "journal_received": dict(Counter(str(r["journal_received"]) for r in rows)),
        "journal_applied": dict(Counter(str(r["journal_applied"]) for r in rows)),
        "applied_before_recovery": dict(Counter(str(r["journal_before_recovery"]["applied"]) for r in rows)),
        "trials_with_duplicate": sum(r["duplicate_mutations"] > 0 for r in rows),
        "duplicate_mutations_total": sum(r["duplicate_mutations"] for r in rows),
        "reconcile_reads_median": (statistics.median([len(r["recovery"]["reads"]) for r in rows])
                                   if rows else None),
        "first_read_visible": dict(Counter(str(r["recovery"]["reads"][0]["effect_visible"])
                                           for r in rows if r["recovery"]["reads"])),
        "receipt_effect": dict(Counter(str((r["mutation_outcome_receipt"] or {}).get("effect")) for r in rows)),
        "receipt_attempted": dict(Counter(str((r["mutation_outcome_receipt"] or {}).get("attempted"))
                                          for r in rows)),
        "receipt_retry_disposition": dict(Counter(str((r["mutation_outcome_receipt"] or {}).get("retryDisposition"))
                                                  for r in rows)),
        "driver_click_route": dict(Counter(str(driver_route(r)) for r in rows)),
        "post_user_agent_chrome_all": all(e.get("user_agent_chrome") for r in rows for e in r["_journal"]
                                          if e["kind"] == "received"),
        "resolution_ms_informational_median": round(statistics.median(res_ms), 1) if res_ms else None,
        "loadavg1_start_range": [min(r["loadavg_start"][0] for r in rows), max(r["loadavg_start"][0] for r in rows)]
        if rows and all(r["loadavg_start"] for r in rows) else None,
    }


def build(trials: list[dict], order: list) -> dict:
    cells: dict[str, dict] = {}
    for key in sorted({(t["row"], t["arm"]) for t in trials}):
        rows = [t for t in trials if (t["row"], t["arm"]) == key]
        summary = cell_summary(rows)
        if key[1] == "typed":
            verdicts = [typed_predicate(t) for t in rows]
            summary["predicate_held"] = sum(ok for ok, _ in verdicts)
            summary["predicate_misses"] = dict(Counter(m for _, ms in verdicts for m in ms))
        cells[f"{key[0]}:{key[1]}"] = summary
    typed = [t for t in trials if t["arm"] == "typed" and t["row"] in TYPED_ROWS]
    typed_fault = [t for t in typed if t["row"] in FAULT_ROWS]
    kills = {t["trial"]: kill_events(t) for t in typed if kill_events(t)}
    held_by_cell = {r: cells.get(f"{r}:typed", {}).get("predicate_held", 0) for r in TYPED_ROWS}
    n_by_cell = {r: cells.get(f"{r}:typed", {}).get("n", 0) for r in TYPED_ROWS}
    rd_naive_dup = cells.get("RD_delayed_withheld:naive", {}).get("trials_with_duplicate", 0)
    re_cell = cells.get("RE_runner_loop_withheld:runner", {})
    naive = [t for t in trials if t["arm"] == "naive"]
    if kills:
        disposition = "KILL"
    elif (all(held_by_cell[r] >= 9 for r in TYPED_ROWS) and rd_naive_dup >= 1
          and re_cell.get("trials_with_duplicate", 0) == 0):
        disposition = "KEEP"
    else:
        disposition = "REVISE"
    fault_trials = [t for t in trials if t["fault"] != "none"]
    ack_lost = [t for t in trials if t["fault"] == "ack_lost"]
    ra = [t for t in trials if t["row"] == "RA_pre_dispatch"]
    ra_scope = {t["trial"]: ra_pre_write_scope(t)[1] for t in ra if not ra_pre_write_scope(t)[0]}
    all_attempts = [(t, n) for t in trials for n in range(len(t["_attempts"]))]
    totals = {
        "trials": len(trials),
        "typed_trials": len(typed),
        "typed_fault_trials": len(typed_fault),
        "typed_duplicate_mutations": sum(t["duplicate_mutations"] for t in typed),
        "typed_trials_with_duplicate": sum(t["duplicate_mutations"] > 0 for t in typed),
        "typed_predicate_held": sum(held_by_cell.values()),
        "typed_predicate_n": sum(n_by_cell.values()),
        "typed_kill_events": kills,
        "naive_trials": len(naive),
        "naive_trials_with_duplicate": sum(t["duplicate_mutations"] > 0 for t in naive),
        "naive_duplicate_mutations": sum(t["duplicate_mutations"] for t in naive),
        "rd_naive_trials_with_duplicate": rd_naive_dup,
        "runner_re_trials_with_duplicate": re_cell.get("trials_with_duplicate"),
        "placement_ok": sum(placement_ok(t) for t in trials),
        "fault_trials": len(fault_trials),
        "fault_placement_ok": sum(placement_ok(t) for t in fault_trials),
        "ack_lost_trials": len(ack_lost),
        "ack_lost_barrier_reached": sum(barrier_reached(t) is True for t in ack_lost),
        "ra_pre_write_scope_ok": len(ra) - len(ra_scope),
        "ra_pre_write_scope_misses": ra_scope,
        "attempts_total": len(all_attempts),
        "attempts_with_exactly_one_startup_tools_list": sum(len(tools_list_requests(t, n)) == 1
                                                            for t, n in all_attempts),
        "typed_first_blocks_by_row": typed_first_blocks(order),
        "extension_unit_pre_write_scope": extension_unit(),
        "receipts_ra_attempted_true_effect_unknown": sum(
            1 for t in trials if t["row"] == "RA_pre_dispatch"
            and (t["mutation_outcome_receipt"] or {}).get("attempted") is True
            and (t["mutation_outcome_receipt"] or {}).get("effect") == "unknown"),
        "receipts_ra_n": sum(1 for t in trials if t["row"] == "RA_pre_dispatch"),
        "loadavg1_start_range": [min(t["loadavg_start"][0] for t in trials),
                                 max(t["loadavg_start"][0] for t in trials)],
        "driver_sha256": sorted({t["driver_sha256"] for t in trials}),
    }
    typed_dup = totals["typed_trials_with_duplicate"]
    rd_n = cells.get("RD_delayed_withheld:naive", {}).get("n", 0)
    totals["uncertainty_95_clopper_pearson"] = {
        "typed_trials_with_duplicate": clopper_pearson(typed_dup, len(typed)),
        "per_typed_cell_0_of_10": clopper_pearson(0, 10),
        "rd_naive_trials_with_duplicate": clopper_pearson(rd_naive_dup, rd_n),
    }
    cp = totals["uncertainty_95_clopper_pearson"]
    headlines = [
        f"typed duplicates {totals['typed_duplicate_mutations']} in {totals['typed_trials']} typed trials",
        f"typed predicate held {totals['typed_predicate_held']}/{totals['typed_predicate_n']}",
        f"RD naive duplicate in {rd_naive_dup}/{cells.get('RD_delayed_withheld:naive', {}).get('n', 0)}",
        f"naive duplicates {totals['naive_duplicate_mutations']} in {totals['naive_trials']} naive trials",
        f"RA receipt attempted=true effect=unknown {totals['receipts_ra_attempted_true_effect_unknown']}/{totals['receipts_ra_n']}",
        f"fault placement ok {totals['fault_placement_ok']}/{totals['fault_trials']} fault trials "
        f"(ack_lost barrier {totals['ack_lost_barrier_reached']}/{totals['ack_lost_trials']})",
        f"RA pre-write scope held {totals['ra_pre_write_scope_ok']}/{len(ra)}",
        f"typed duplicate-trial rate 95% CI {cp['typed_trials_with_duplicate'][0]:.3f}-"
        f"{cp['typed_trials_with_duplicate'][1]:.3f}",
        f"RD naive duplicate rate 95% CI {cp['rd_naive_trials_with_duplicate'][0]:.3f}-"
        f"{cp['rd_naive_trials_with_duplicate'][1]:.3f}",
        f"RE runner-loop duplicates {re_cell.get('trials_with_duplicate')}/{re_cell.get('n')}",
    ]
    return {"schema": "cua.r2-05.summary.v2", "disposition_by_gates": disposition, "totals": totals,
            "cells": cells, "headlines": headlines}


def main() -> None:
    trials = load_trials(RAW)
    schedule = json.loads((RAW / "schedule.json").read_text())
    assert len(trials) == len(schedule["order"]) == 120, (len(trials), len(schedule["order"]))
    for t, (block, row, arm) in zip(trials, schedule["order"]):
        assert (t["block"], t["row"], t["arm"]) == (block, row, arm), t["_file"]
    summary = build(trials, schedule["order"])
    pilots = {p.name: len(load_trials(p)) for p in sorted((ROOT / "raw" / "pilot").iterdir()) if p.is_dir()}
    summary["pilot_trials_excluded"] = pilots
    out = ROOT / "r2-05-summary.json"
    if "--write" in sys.argv:
        out.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        print("wrote", out.name)
    stored = json.loads(out.read_text())
    assert stored == json.loads(json.dumps(summary, sort_keys=True)), "summary differs from raw recomputation"
    prereg = json.loads((ROOT / "PREREG.json").read_text())
    for name, digest in prereg["harness_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, f"harness changed: {name}"
    readme = (ROOT / "README.md").read_text() if (ROOT / "README.md").exists() else ""
    if "--write" not in sys.argv:
        for line in summary["headlines"]:
            assert line in readme, f"README missing headline: {line}"
        assert summary["disposition_by_gates"] in readme
        assert summary["totals"]["extension_unit_pre_write_scope"]["ok"], "extension unit result changed"
        assert summary["totals"]["ra_pre_write_scope_ok"] == summary["totals"]["receipts_ra_n"], "RA scope"
        for path in ROOT.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".txt", ".py", ".sh"}:
                text = path.read_text(errors="ignore")
                assert not re.search(r"/(home|mnt|tmp)/", text) or path.name in {"verify_artifacts.py"}, path
    print(json.dumps({"disposition_by_gates": summary["disposition_by_gates"], "headlines": summary["headlines"]},
                     indent=1))


if __name__ == "__main__":
    main()

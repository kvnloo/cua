#!/usr/bin/env python3
"""Recompute every OWN-105 count from raw/ and scan the packet for private data.

usage:
  python3 verify_artifacts.py            # recompute, compare with own-105-summary.json, privacy scan
  python3 verify_artifacts.py --write    # recompute and (re)write own-105-summary.json

Only the standard library is used. The target journal in each trial file is the
oracle; the runner's outcome and receipts are what is under test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
MEASURED = RAW / "measured"
SUMMARY = HERE / "own-105-summary.json"

RESOLUTIONS = {"verified", "refuted", "unresolved_unknown", "pre_write_failed"}
RECEIPT_KEYS = {"receiptKind", "mutationKey", "authorityScope", "attempted", "effect",
                "verification", "retryDisposition", "resolution"}
MAIN_ROWS = ["R0_control", "R1_ack_lost_applied", "R2_delayed_within_deadline", "R3_delayed_past_deadline",
             "R4_read_failure_after_unverified", "R5_replanned_completion", "R6_own_write_raised"]
CONTROL_ROW = "R6n_unproven_not_written"
EXPECTED = {  # fixed runner: (final outcome, receipt resolution, phase or None, reconsiderations)
    "R0_control": ("verified", "verified", None, 0),
    "R1_ack_lost_applied": ("verified", "verified", "action", 0),
    "R2_delayed_within_deadline": ("verified", "verified", "action", 0),
    "R3_delayed_past_deadline": ("unknown", "unresolved_unknown", "action", 0),
    "R4_read_failure_after_unverified": ("unknown", "unresolved_unknown", "observe", 0),
    "R5_replanned_completion": ("unknown", "unresolved_unknown", "completion_blocked", 0),
    "R6_own_write_raised": ("verified", "verified", None, 1),
    CONTROL_ROW: ("unknown", "unresolved_unknown", "action", 0),
}
FAULT_KINDS = {"ack_lost": "target_barrier", "read_error": "read_error_injected",
               "pre_dispatch": ("session_write_stream_closed_before_next_request", "write_closed_before_next_request"),
               "request_lost": "request_taken_not_forwarded",
               "closed_before_request": "transport_closed_before_next_request"}


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> list[float]:
    """Exact two-sided interval via bisection on the binomial CDF (stdlib only)."""
    if n == 0:
        return [0.0, 1.0]

    def cdf(x: int, p: float) -> float:
        return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, x + 1))

    def solve(f, lo=0.0, hi=1.0):
        for _ in range(100):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: 1 - cdf(k - 1, p) >= alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: cdf(k, p) <= alpha / 2)
    return [round(lower, 3), round(upper, 3)]


def load_trial(path: Path) -> dict:
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    record = dict(lines[0])
    for line in lines[1:]:
        record[line["kind"]] = line["events"]
    return record


def analyse(t: dict) -> dict:
    events = t["runner_events"]
    seam = t["seam_events"]
    journal = t["target_journal"]
    final = events[-1] if events else {}
    receipt = final.get("mutation_outcome") if final.get("event") == "outcome" else None
    reconsiders = [e for e in events if e.get("event") == "reconsider"]
    sessions = [i for i, e in enumerate(seam) if e["kind"] == "session_start"]
    clicks = [i for i, e in enumerate(seam) if e["kind"] == "forwarded_request" and e.get("tool") == "browser_click"]
    clicks_session1 = [i for i in clicks if len(sessions) < 2 or i < sessions[1]]
    if t["runtime"] == "py":
        crashed = t["child_rc"] is None or not str(t["py_outcome"]).startswith(("verified", "refuted", "unknown",
                                                                                   "abstained", "budget"))
    else:
        crashed = t["child_rc"] is None or t["ts_exit_code"] not in (0, 1) or final.get("event") != "outcome"
    outcome = final.get("outcome") if final.get("event") == "outcome" else None
    receipt_ok = (
        isinstance(receipt, dict)
        and receipt.get("receiptKind") == "mutation-outcome/v0"
        and receipt.get("resolution") in RESOLUTIONS
        and set(receipt) <= RECEIPT_KEYS
        and not t["token_in_runner_log"]
    )
    # Journal facts (the oracle).
    exit_n = t["journal_events_at_runner_exit"]
    received_seq = next((e["seq"] for e in journal if e["kind"] == "received"), None)
    applied_seq = next((e["seq"] for e in journal if e["kind"] == "applied"), None)
    reads_after_dispatch_before_exit = [
        e for e in journal[:exit_n] if e["kind"] == "state_read" and received_seq is not None and e["seq"] > received_seq]
    negative_read_before_apply = any(
        e["kind"] == "state_read" and not e["effect_visible"] and received_seq is not None and e["seq"] > received_seq
        and (applied_seq is None or e["seq"] < applied_seq) for e in journal)
    landed = t["journal_applied"] >= 1
    landed_as_failure = landed and (
        crashed or outcome not in {"verified", "unknown"}
        or (isinstance(receipt, dict) and receipt.get("resolution") == "pre_write_failed"))
    # Fault placement validity.
    kinds = FAULT_KINDS.get(t["fault"])
    kinds = kinds if isinstance(kinds, tuple) else (kinds,) if kinds else ()
    fault_events = [e for e in seam if e["kind"] in kinds]
    placement: bool | None = None
    if t["fault"] != "none":
        placement = bool(t["fault_fired"]) and bool(fault_events)
        probe = fault_events[0].get("journal") if fault_events else None
        if t["fault"] == "ack_lost":
            placement = placement and bool(fault_events[0].get("reached"))
            if t["barrier"] == "received":
                placement = placement and isinstance(probe, dict) and probe.get("applied") == 0
        if t["fault"] in {"read_error", "pre_dispatch", "request_lost", "closed_before_request"}:
            placement = placement and isinstance(probe, dict) and probe.get("applied") == 0
        if t["fault"] in {"pre_dispatch", "request_lost", "closed_before_request"}:
            placement = placement and not clicks_session1
    # The first submit (op 1) carries the row's placement; it must not land before the runner exits.
    held_during_run = not any(e["kind"] == "applied" and e.get("op") == 1 for e in journal[:exit_n])
    if t["row"] in {"R3_delayed_past_deadline", "R4_read_failure_after_unverified", "R5_replanned_completion"}:
        placement = (placement if placement is not None else True) and held_during_run
    if t["row"] == "R2_delayed_within_deadline":
        placement = placement and negative_read_before_apply
    expected = EXPECTED[t["row"]]
    matches_expected = (
        outcome == expected[0]
        and isinstance(receipt, dict) and receipt.get("resolution") == expected[1]
        and (expected[2] is None or final.get("phase") == expected[2])
        and len(reconsiders) == expected[3])
    reconsider_receipt_ok = all(
        (r.get("mutation_outcome") or {}).get("resolution") == "pre_write_failed"
        and r["mutation_outcome"].get("attempted") is False and r["mutation_outcome"].get("effect") == "none"
        and r["mutation_outcome"].get("retryDisposition") == "reconsider" for r in reconsiders)
    # Gap reproduction predicates for the unfixed base runner (pre-registered).
    gap = None
    if t["arm"] == "py_unfixed":
        no_resolution = isinstance(receipt, dict) and "resolution" not in receipt
        if t["row"] == "R1_ack_lost_applied":
            gap = outcome == "unknown" and no_resolution and t["journal_at_runner_exit"]["applied"] >= 1 \
                and not reads_after_dispatch_before_exit
        elif t["row"] == "R3_delayed_past_deadline":
            gap = outcome == "unknown" and no_resolution and not reads_after_dispatch_before_exit
        elif t["row"] == "R4_read_failure_after_unverified":
            gap = crashed and receipt is None
        elif t["row"] == "R5_replanned_completion":
            gap = t["journal_at_runner_exit"]["received"] >= 2
    return {
        "trial": t["trial"], "row": t["row"], "arm": t["arm"], "runtime": t["runtime"],
        "outcome": outcome, "phase": final.get("phase"), "error": final.get("error"),
        "resolution": receipt.get("resolution") if isinstance(receipt, dict) else None,
        "receipt_ok": receipt_ok, "crashed": crashed,
        "reconsiders": len(reconsiders), "reconsider_receipt_ok": reconsider_receipt_ok,
        "sessions": len(sessions), "submits_forwarded": len(clicks), "submits_forwarded_session1": len(clicks_session1),
        "received": t["journal_received"], "applied": t["journal_applied"],
        "duplicates": max(0, t["journal_applied"] - 1),
        "second_dispatches": max(0, t["journal_received"] - 1),
        "landed_as_failure": landed_as_failure,
        "restart_while_unresolved": len(sessions) >= 2 and bool(clicks_session1),
        "placement_ok": placement, "negative_read_before_apply": negative_read_before_apply,
        "post_dispatch_reads_before_exit": len(reads_after_dispatch_before_exit),
        "matches_expected": matches_expected, "gap_reproduced": gap,
        "quiescent": t["journal_quiescent"], "driver_sha256": t["driver_sha256"],
        "elapsed_ms": t["child_elapsed_ms_informational"], "loadavg_start": t["loadavg_start"],
    }


def summarise(rows: list[dict], schedule: dict) -> dict:
    fixed = [r for r in rows if r["arm"] in {"py_fixed", "ts_fixed"}]
    unfixed = [r for r in rows if r["arm"] == "py_unfixed"]
    cells: dict[str, dict] = {}
    grouped: dict[tuple, list] = defaultdict(list)
    for r in rows:
        grouped[(r["row"], r["arm"])].append(r)
    for (row, arm), group in sorted(grouped.items()):
        cells[f"{row}:{arm}"] = {
            "n": len(group),
            "outcomes": dict(Counter(str(r["outcome"]) for r in group)),
            "resolutions": dict(Counter(str(r["resolution"]) for r in group)),
            "receipt_ok": sum(r["receipt_ok"] for r in group),
            "matches_expected": sum(r["matches_expected"] for r in group) if arm != "py_unfixed" else None,
            "duplicates": sum(r["duplicates"] for r in group),
            "second_dispatches": sum(r["second_dispatches"] for r in group),
            "reconsiders": sum(r["reconsiders"] for r in group),
            "crashed": sum(r["crashed"] for r in group),
            "placement_ok": sum(bool(r["placement_ok"]) for r in group if r["placement_ok"] is not None),
            "placement_checked": sum(r["placement_ok"] is not None for r in group),
            "gap_reproduced": sum(bool(r["gap_reproduced"]) for r in group) if arm == "py_unfixed" else None,
            "median_elapsed_ms_informational": round(statistics.median(r["elapsed_ms"] for r in group), 1),
        }
    main_fixed = [r for r in fixed if r["row"] in MAIN_ROWS]
    r5 = [r for r in fixed if r["row"] == "R5_replanned_completion"]
    r6 = [r for r in fixed if r["row"] == "R6_own_write_raised"]
    r6n = [r for r in fixed if r["row"] == CONTROL_ROW]
    placement_checked = [r for r in rows if r["placement_ok"] is not None]
    totals = {
        "trials": len(rows), "fixed_trials": len(fixed), "fixed_main_trials": len(main_fixed),
        "unfixed_trials": len(unfixed),
        "fixed_duplicates": sum(r["duplicates"] for r in fixed),
        "fixed_trials_with_duplicate": sum(r["duplicates"] > 0 for r in fixed),
        "fixed_second_dispatches": sum(r["second_dispatches"] for r in fixed),
        "fixed_receipts_ok": sum(r["receipt_ok"] for r in fixed),
        "fixed_landed_as_failure": sum(r["landed_as_failure"] for r in fixed),
        "fixed_restart_while_unresolved": sum(r["restart_while_unresolved"] for r in fixed),
        "fixed_crashed": sum(r["crashed"] for r in fixed),
        "fixed_matches_expected": sum(r["matches_expected"] for r in fixed),
        "r5_trials": len(r5), "r5_second_dispatches": sum(r["second_dispatches"] for r in r5),
        "r5_submits_forwarded_total": sum(r["submits_forwarded"] for r in r5),
        "r5_completion_blocked": sum(r["phase"] == "completion_blocked" for r in r5),
        "r6_trials": len(r6), "r6_exactly_one_reconsideration": sum(r["reconsiders"] == 1 for r in r6),
        "r6_reconsider_receipt_ok": sum(r["reconsider_receipt_ok"] and r["reconsiders"] == 1 for r in r6),
        "r6_two_sessions_no_submit_in_first": sum(r["sessions"] == 2 and r["submits_forwarded_session1"] == 0
                                                  for r in r6),
        "r6n_trials": len(r6n), "r6n_reconsiderations": sum(r["reconsiders"] for r in r6n),
        "r6n_received": sum(r["received"] for r in r6n),
        "placement_ok": sum(bool(r["placement_ok"]) for r in placement_checked),
        "placement_checked": len(placement_checked),
        "unfixed_gap_reproduced": sum(bool(r["gap_reproduced"]) for r in unfixed),
        "unfixed_gap_by_row": {row: sum(bool(r["gap_reproduced"]) for r in unfixed if r["row"] == row)
                               for row in sorted({r["row"] for r in unfixed})},
        "unfixed_duplicates": sum(r["duplicates"] for r in unfixed),
        "journal_not_quiescent": sum(not r["quiescent"] for r in rows),
        "driver_sha256_values": sorted({r["driver_sha256"] for r in rows}),
        "loadavg_start_range": [min(r["loadavg_start"][0] for r in rows), max(r["loadavg_start"][0] for r in rows)],
    }
    totals["uncertainty_95_clopper_pearson"] = {
        "fixed_duplicate_trial_rate": clopper_pearson(totals["fixed_trials_with_duplicate"], len(fixed)),
        "fixed_missing_receipt_rate": clopper_pearson(len(fixed) - totals["fixed_receipts_ok"], len(fixed)),
        "fixed_landed_as_failure_rate": clopper_pearson(totals["fixed_landed_as_failure"], len(fixed)),
        "r5_second_dispatch_trial_rate": clopper_pearson(sum(r["second_dispatches"] > 0 for r in r5), len(r5)),
    }
    return {"cells": cells, "totals": totals, "schedule_trials": len(schedule.get("order", []))}


def suites_pass() -> bool | None:
    steps = RAW / "unit" / "fix-head-full" / "steps.txt"
    if not steps.exists():
        return None
    rcs = re.findall(r"rc=(\d+)", steps.read_text())
    return bool(rcs) and all(rc == "0" for rc in rcs)


def disposition(totals: dict, suites: bool | None) -> dict:
    kill = {
        "blind_second_effect": totals["fixed_duplicates"] + totals["fixed_second_dispatches"],
        "landed_as_failure": totals["fixed_landed_as_failure"],
        "restart_while_unresolved": totals["fixed_restart_while_unresolved"],
    }
    keep = {
        "zero_duplicates": totals["fixed_duplicates"] == 0,
        "all_receipts": totals["fixed_receipts_ok"] == totals["fixed_trials"],
        "zero_landed_as_failure": totals["fixed_landed_as_failure"] == 0,
        "r5_zero_second_dispatch": totals["r5_second_dispatches"] == 0 and totals["r5_trials"] > 0,
        "r6_exactly_one_reconsideration": totals["r6_exactly_one_reconsideration"] == totals["r6_trials"] > 0,
        "unfixed_reproduces_gap": totals["unfixed_gap_reproduced"] >= 1,
        "suites_pass": suites is True,
        "placement_valid": totals["placement_ok"] == totals["placement_checked"],
    }
    if any(kill.values()):
        verdict = "KILL"
    elif all(keep.values()):
        verdict = "KEEP"
    else:
        verdict = "REVISE"
    return {"verdict": verdict, "kill_events": kill, "keep_gates": keep}


PRIVATE = [
    (re.compile(r"/(?:mnt|tmp)/[A-Za-z0-9_.-]+/|/home/[a-z]|/Users/"), "absolute local path"),
    (re.compile(r"sk-[A-Za-z0-9]{16,}|TYPESAFE_API_KEY\s*=\s*\S|BEGIN [A-Z ]*PRIVATE KEY"), "secret-like value"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|anthropic\.com)[A-Za-z0-9.-]+\.[a-z]{2,}"),
     "e-mail address"),
]


def privacy_scan() -> list[str]:
    findings = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for pattern, label in PRIVATE:
            for match in pattern.finditer(text):
                if path.name == "verify_artifacts.py":
                    continue  # the patterns themselves
                findings.append(f"{path.relative_to(HERE)}: {label}: {match.group(0)[:40]}")
    return findings


def check_prereg() -> dict:
    prereg = json.loads((HERE / "PREREG.json").read_text())
    mismatches = []
    for rel, digest in prereg.get("frozen_file_sha256", {}).items():
        actual = hashlib.sha256((HERE / rel).read_bytes()).hexdigest()
        if actual != digest:
            mismatches.append(rel)
    return {"frozen_files": len(prereg.get("frozen_file_sha256", {})), "mismatches": mismatches}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    files = sorted(MEASURED.glob("trial-*.jsonl"))
    schedule = json.loads((MEASURED / "schedule.json").read_text())
    rows = [analyse(load_trial(path)) for path in files]
    expected_names = [f"trial-{i:03d}-{row}-{arm}.jsonl" for i, (row, arm) in enumerate(schedule["order"])]
    summary = summarise(rows, schedule)
    summary["schedule_files_match"] = [p.name for p in files] == expected_names
    summary["suites_pass_at_fix_head"] = suites_pass()
    summary["prereg"] = check_prereg()
    summary["disposition_by_gates"] = disposition(summary["totals"], summary["suites_pass_at_fix_head"])
    summary["per_trial"] = rows
    summary["schema"] = "own-105-summary.v1"
    privacy = privacy_scan()
    t = summary["totals"]
    print(f"trials {t['trials']} (fixed {t['fixed_trials']}, unfixed {t['unfixed_trials']}); schedule files match: "
          f"{summary['schedule_files_match']}")
    print(f"fixed duplicates {t['fixed_duplicates']} in {t['fixed_trials']} fixed trials; second dispatches "
          f"{t['fixed_second_dispatches']}")
    print(f"fixed receipts ok {t['fixed_receipts_ok']}/{t['fixed_trials']}; landed effects classified as failure "
          f"{t['fixed_landed_as_failure']}; restart while unresolved {t['fixed_restart_while_unresolved']}; "
          f"crashed {t['fixed_crashed']}")
    print(f"fixed matched expected row outcome {t['fixed_matches_expected']}/{t['fixed_trials']}")
    print(f"R5 second dispatches {t['r5_second_dispatches']} in {t['r5_trials']} (completion_blocked "
          f"{t['r5_completion_blocked']}/{t['r5_trials']})")
    print(f"R6 exactly one reconsideration {t['r6_exactly_one_reconsideration']}/{t['r6_trials']}; R6n "
          f"reconsiderations {t['r6n_reconsiderations']} in {t['r6n_trials']}")
    print(f"placement ok {t['placement_ok']}/{t['placement_checked']}")
    print(f"unfixed gap reproduced {t['unfixed_gap_reproduced']}/{t['unfixed_trials']} {t['unfixed_gap_by_row']}; "
          f"unfixed duplicates {t['unfixed_duplicates']}")
    print(f"suites pass at fix head: {summary['suites_pass_at_fix_head']}; PREREG frozen-file mismatches: "
          f"{summary['prereg']['mismatches']}")
    print(f"disposition by gates: {summary['disposition_by_gates']['verdict']}")
    print(f"privacy findings: {len(privacy)}")
    for finding in privacy:
        print("  " + finding)
    ok = not privacy and summary["schedule_files_match"] and not summary["prereg"]["mismatches"]
    if args.write:
        SUMMARY.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    elif SUMMARY.exists():
        stored = json.loads(SUMMARY.read_text())
        same = json.dumps(stored, sort_keys=True) == json.dumps(summary, sort_keys=True)
        print(f"summary file matches recomputation: {same}")
        ok = ok and same
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

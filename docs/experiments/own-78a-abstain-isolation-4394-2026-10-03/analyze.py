#!/usr/bin/env python3
"""OWN-78A analysis: recompute every result row from raw/ (standard library only).

usage: python3 analyze.py            # writes own78a-summary.json
       python3 analyze.py --check    # exits 1 if the committed summary differs
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
LIVE_BLOCKS = ("L1", "L2", "L3")
ARMS = ("A0", "A1", "A2", "A3")
KIND = {"type-verification-value": "type", "abstain": "abstain", "reobserve": "reobserve",
        "submit-form": "click", "submit-form-foreground": "click"}
MUTATING = {"browser_type", "browser_click", "click", "type_text", "press_key", "set_value"}


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def trial(path: Path, fixture_field: dict) -> dict:
    rows = jsonl(path)
    cell = next(r for r in rows if r["type"] == "cell")
    receipts = [r for r in rows if r["type"] == "receipt"]
    events = [r["event"] for r in rows if r["type"] == "runner_event"]
    journal = [r for r in rows if r["type"] == "journal"]
    responses = [r for r in receipts if r.get("kind") == "provider_response"]
    ok = [r for r in responses if r.get("ok")]
    requests = [r for r in receipts if r.get("kind") == "provider_request"]
    http = [r for r in receipts if r.get("kind") == "http_attempt" and not r.get("loopback")]
    choices = [r for r in receipts if r.get("kind") == "choice"]
    snapshots = [r for r in receipts if r.get("kind") == "driver_call" and r.get("ref_index") is not None]
    dispatched = [r for r in receipts if r.get("kind") == "driver_call" and r.get("tool") in MUTATING]
    refused = [r for r in receipts if r.get("kind") == "mutation_refused"]
    decision_events = [e for e in events if e.get("event") == "step" or
                       (e.get("event") == "outcome" and e.get("outcome") == "abstained")]
    failure_receipts = [e for e in events if e.get("event") == "outcome" and e.get("outcome") == "unknown"]

    first = ok[0] if ok else None
    kind = KIND.get(first["selected_id"], "other") if first else "failure"
    target_ok = False
    if first and kind == "type" and choices and snapshots:
        choice = choices[0]
        index = {r["ref"]: r for r in snapshots[0]["ref_index"]}
        entry = index.get(choice.get("arg_ref"))
        target_ok = (choice.get("candidate") == "type-verification-value" and choice.get("tool") == "browser_type"
                     and entry is not None and entry.get("role") == fixture_field["role"]
                     and entry.get("name") == fixture_field["aria_label"]
                     and sum(1 for r in snapshots[0]["ref_index"]
                             if r.get("role") == "textbox" and r.get("name") == fixture_field["aria_label"]) == 1)
    no_mutation = cell["input_events"] == 0 and cell["submits"] == 0 and cell["submitted_is_none"] and not dispatched

    records = []  # backend == responder per decision record
    for number, response in enumerate(ok):
        attempt = http[number] if number < len(http) else None
        event = decision_events[number] if number < len(decision_events) else None
        backend = event.get("backend") if event else None
        records.append({
            "backend_field": backend,
            "responder": response.get("responder"),
            "http_status": attempt.get("status") if attempt else None,
            "request_id_match": bool(attempt) and attempt.get("request_id_sha256_16") is not None
                                and attempt.get("request_id_sha256_16") == response.get("request_id_sha256_16"),
            "backend_equals_responder": backend == response.get("responder") if backend is not None else None,
        })
    return {
        "cell_id": cell["cell_id"], "arm": cell["arm"], "block": cell["block"], "rc": cell["rc"],
        "kind": kind, "selected_id": first["selected_id"] if first else None,
        "correct_type": kind == "type" and target_ok and no_mutation,
        "no_mutation": no_mutation, "mutation_refused": len(refused),
        "p_type": first["probabilities"].get("type-verification-value") if first else None,
        "p_abstain": first["probabilities"].get("abstain") if first else None,
        "p_reobserve": first["probabilities"].get("reobserve") if first else None,
        "input_tokens": first.get("input_tokens") if first else None,
        "output_tokens": first.get("output_tokens") if first else None,
        "model": first.get("model") if first else None,
        "decisions": len(ok), "decision_events": len(decision_events),
        "failure_receipts": len(failure_receipts),
        "http_attempts": len([r for r in http if not r.get("guard_refused")]),
        "http_reached": len([r for r in http if isinstance(r.get("status"), int)]),
        "records": records,
        "state_key_paths": requests[0]["state_key_paths"] if requests else None,
        "question_names": sorted(requests[0]["questions"]) if requests else None,
        "instructions_sha256_16": [q["instructions_sha256_16"] for q in requests[0]["questions"].values()] if requests else None,
        "input_events": len(journal), "submits": cell["submits"],
        "submitted_equals_token": cell["submitted_equals_token"],
        "runner_verified": any(e.get("event") == "outcome" and e.get("outcome") == "verified" for e in events),
        "loadavg_at_spawn": cell["loadavg_at_spawn"],
    }


def span(values: list) -> list:
    values = [v for v in values if v is not None]
    return [round(min(values), 4), round(max(values), 4)] if values else []


def arm_summary(trials: list[dict]) -> dict:
    records = [r for t in trials for r in t["records"]]
    with_backend = [r for r in records if r["backend_field"] is not None]
    return {
        "n": len(trials),
        "kinds": {k: sum(1 for t in trials if t["kind"] == k) for k in ("type", "abstain", "reobserve", "click", "failure", "other")},
        "correct_type": sum(t["correct_type"] for t in trials),
        "abstain": sum(t["kind"] == "abstain" for t in trials),
        "p_type_range": span([t["p_type"] for t in trials]),
        "p_abstain_range": span([t["p_abstain"] for t in trials]),
        "p_type_median": round(statistics.median([t["p_type"] for t in trials if t["p_type"] is not None]), 4),
        "input_tokens_median": statistics.median([t["input_tokens"] for t in trials if t["input_tokens"] is not None]),
        "input_tokens_range": span([t["input_tokens"] for t in trials]),
        "models": sorted({t["model"] for t in trials if t["model"]}),
        "decision_records": len(records),
        "responder_typesafe_http200_reqid_match": sum(1 for r in records if r["responder"] == "typesafe"
                                                       and r["http_status"] == 200 and r["request_id_match"]),
        "backend_equals_responder": f"{sum(1 for r in with_backend if r['backend_equals_responder'])}/{len(with_backend)}"
                                    if with_backend else "n/a (runner has no backend field)",
        "state_key_paths": sorted({p for t in trials for p in (t["state_key_paths"] or [])}),
        "state_key_paths_identical_across_trials": len({json.dumps(t["state_key_paths"]) for t in trials}) == 1,
        "question_names": sorted({q for t in trials for q in (t["question_names"] or [])}),
        "instructions_sha256_16": sorted({h for t in trials for h in (t["instructions_sha256_16"] or [])}),
        "e4": {
            "duplicate_mutation": sum(1 for t in trials if not t["no_mutation"]),
            "unverified_success": sum(1 for t in trials if t["runner_verified"] and not t["submitted_equals_token"]),
            "replay_after_partial_progress": 0 if all(t["no_mutation"] for t in trials) else None,
            "decisions_counted_from_failure_receipts": sum(t["failure_receipts"] for t in trials if t["decisions"] == 0 and t["kind"] != "failure"),
            "mutation_refused_backstop": sum(t["mutation_refused"] for t in trials),
            "failure_receipts": sum(t["failure_receipts"] for t in trials),
        },
        "cells": [t["cell_id"] for t in trials],
    }


def attribution(arms: dict) -> dict:
    a0, a1, a2, a3 = (arms[a] for a in ARMS)
    valid = a0["abstain"] >= 4 and a3["correct_type"] >= 4
    if not valid:
        verdict = "INVALID"
    elif a1["correct_type"] >= 4:
        verdict = "FORM_OMISSION_SUFFICIENT"
    elif a1["correct_type"] <= 1 and a2["correct_type"] >= 4:
        verdict = "PAGE_OUTLINE_ALSO_NEEDED"
    else:
        verdict = "INCONCLUSIVE"
    return {"valid": valid, "A0_abstain": f"{a0['abstain']}/5", "A3_correct_type": f"{a3['correct_type']}/5",
            "A1_correct_type": f"{a1['correct_type']}/5", "A2_correct_type": f"{a2['correct_type']}/5",
            "verdict": verdict}


def smoke() -> dict:
    validity = json.loads((RAW / "smoke" / "validity.json").read_text())
    out = {}
    for path in sorted((RAW / "smoke").glob("smoke-*.jsonl")):
        t = trial(path, validity["fixture_field"])
        stub = [r for r in jsonl(path) if r["type"] == "stub"]
        out[t["cell_id"]] = {"kind": t["kind"], "state_key_paths_sdk": t["state_key_paths"],
                             "state_key_paths_on_wire": stub[0]["state_key_paths"] if stub else None,
                             "question_names": t["question_names"], "http_reached": t["http_reached"],
                             "verified": t["submitted_equals_token"], "submits": t["submits"],
                             "input_events": t["input_events"]}
    return out


def unit() -> dict:
    out = {}
    for row in ("pr", "f", "red"):
        out[row] = json.loads((RAW / "unit" / row / "summary.json").read_text())
    out["unit_109_of_109_credential_free_on_F"] = (out["f"]["ts"] == {"tests": 109, "pass": 109, "fail": 0}
                                                   and out["f"]["python_status"].startswith("OK")
                                                   and out["f"]["typecheck_rc"] == 0)
    return out


def budget() -> dict:
    ledger = jsonl(RAW / "provider-ledger.jsonl")
    attempts = [r for r in ledger if not r.get("guard_refused") and not r.get("loopback")]
    reached = [r for r in attempts if isinstance(r.get("status"), int)]
    recorded = json.loads((RAW / "budget.json").read_text())
    return {"lane_cap_reached": 24, "lane_cap_attempts": 30, "attempts": len(attempts), "reached": len(reached),
            "guard_refused": sum(1 for r in ledger if r.get("guard_refused")),
            "hosts": sorted({r["host"] for r in attempts}), "statuses": sorted({r["status"] for r in reached}),
            "request_id_present": sum(1 for r in reached if r.get("request_id_present")),
            "budget_file_agrees": recorded["attempts"] == len(attempts) and recorded["reached"] == len(reached),
            "remaining_reached_after_part_b": 24 - len(reached),
            "part_c_precondition_met": 24 - len(reached) >= 6}


def analyse() -> dict:
    fixture_field = json.loads((RAW / "L1" / "validity.json").read_text())["fixture_field"]
    trials = [trial(p, fixture_field) for b in LIVE_BLOCKS for p in sorted((RAW / b).glob(f"{b}-*.jsonl"))]
    arms = {a: arm_summary([t for t in trials if t["arm"] == a]) for a in ARMS}
    units, money = unit(), budget()
    attr = attribution(arms)
    keep = {"unit_109_credential_free": units["unit_109_of_109_credential_free_on_F"],
            "A2_correct_type_ge_4_of_5": arms["A2"]["correct_type"] >= 4,
            "r1_lite_3_of_3": False}
    failing = [k for k, v in keep.items() if not v]
    return {
        "schema": "cua.r2.own78a.summary.v1",
        "trials": trials,
        "arms": arms,
        "attribution": attr,
        "smoke": smoke(),
        "unit": units,
        "budget": money,
        "r1_lite": {"status": "NOT_RUN", "class": "BLOCKED",
                    "reason": f"precondition (>= 6 reached left) not met: {money['remaining_reached_after_part_b']} left of the 24 lane cap after Part B"},
        "r4_live": "NOT_RUN (BLOCKED: budget)",
        "keep_conditions": keep,
        "disposition": "KEEP" if not failing else "REVISE",
        "failing_rows": failing,
    }


def main() -> int:
    summary = analyse()
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    target = HERE / "own78a-summary.json"
    if "--check" in sys.argv:
        return 0 if target.exists() and target.read_text() == text else 1
    target.write_text(text)
    print(json.dumps({"arms": {a: {k: v for k, v in s.items() if k in ("kinds", "correct_type", "p_type_range", "p_abstain_range", "input_tokens_median", "backend_equals_responder", "responder_typesafe_http200_reqid_match")} for a, s in summary["arms"].items()},
                      "attribution": summary["attribution"], "budget": summary["budget"],
                      "disposition": summary["disposition"], "failing": summary["failing_rows"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

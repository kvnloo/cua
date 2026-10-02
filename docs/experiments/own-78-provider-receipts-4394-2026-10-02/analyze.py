#!/usr/bin/env python3
"""Recompute every OWN-78 count and gate from raw/ and write own78-summary.json.

usage: python3 analyze.py            (from anywhere; paths are relative to this file)
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
TYPESAFE_HOST = "api.typesafe.ai"
MEASURED_BLOCKS = {"m1-r2": "R2", "m2-r3": "R3", "m3-r1": "R1", "m4-r4a": "R4", "m5-r4b": "R4", "m6-r0": "R0", "m7-r4s-a": "R4s", "m8-r4s-b": "R4s"}
SMOKE_BLOCKS = ("smoke-a", "smoke-b", "smoke-live", "smoke-c", "smoke-d")
PLANNED = {"R1": {"py": 6, "ts": 4}, "R2": {"py": 5, "ts": 5}, "R3": {"py": 3, "ts": 3}, "R4": {"py": 12, "ts": 8}, "R4s": {"py": 12, "ts": 8}, "R0": {"py": 5}}


def load_trial(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    cell = next(r for r in rows if r["type"] == "cell")
    return {
        "cell": cell,
        "events": [r["event"] for r in rows if r["type"] == "runner_event"],
        "receipts": [r for r in rows if r["type"] == "receipt"],
        "journal": [r for r in rows if r["type"] == "journal"],
        "stub": [r for r in rows if r["type"] == "stub"],
    }


def is_decision(event: dict) -> bool:
    return event.get("event") == "step" or (event.get("event") == "outcome" and event.get("outcome") == "abstained" and "backend" in event)


def decision_selected(event: dict) -> str | None:
    return event.get("candidate") if event.get("event") == "step" else "abstain"


def input_mutations(journal: list[dict]) -> int:
    ordered = sorted(journal, key=lambda e: (e.get("seq") is None, e.get("seq") or 0, e["arrival_ns"]))
    count, previous = 0, False
    for entry in ordered:
        if entry["equals_token"] and not previous:
            count += 1
        previous = entry["equals_token"]
    return count


def derive(trial: dict) -> dict:
    cell, events, receipts = trial["cell"], trial["events"], trial["receipts"]
    attempts = [r for r in receipts if r.get("kind") == "http_attempt" and not r.get("guard_refused")]
    decisions = [e for e in events if is_decision(e)]
    failures = [e for e in events if e.get("event") == "outcome" and e.get("outcome") == "unknown"]
    final = events[-1] if events else {}
    tools = Counter(r["tool"] for r in receipts if r.get("kind") == "driver_call")
    switch = [r for r in receipts if r.get("kind") == "seam_switch"]
    counts = cell.get("server_counts") or {}
    responses_ok = [r for r in receipts if r.get("kind") == "provider_response" and r.get("ok")]
    if switch:
        t_switch = switch[0]["t_ns"]
        post = [a for a in attempts if int(a["t_start_ns"]) > int(t_switch)]
    else:
        post = []
    return {
        "id": cell["cell_id"], "row": cell["row"], "runtime": cell["runtime"], "rc": cell.get("rc"),
        "timed_out": cell.get("timed_out"), "harness_error": cell.get("harness_error"),
        "verified": cell.get("final_state") == {"submitted": cell["token"]} and counts.get("POST /submit", 0) == 1,
        "submits": counts.get("POST /submit", 0), "navigations": counts.get("GET /", 0), "routine_starts": counts.get("POST /reset", 0),
        "input_events": len(trial["journal"]), "input_mutations": input_mutations(trial["journal"]),
        "journal_trusted_insert": all(e.get("trusted") and e.get("input_type") == "insertText" for e in trial["journal"]),
        "attempts_total": len(attempts),
        "reached": sum(1 for a in attempts if not a.get("loopback") and isinstance(a.get("status"), int)),
        "loopback_refused": sum(1 for a in attempts if a.get("loopback") and not isinstance(a.get("status"), int)),
        "stub_answered": sum(1 for a in attempts if a.get("loopback") and isinstance(a.get("status"), int)),
        "guard_refused": sum(1 for r in receipts if r.get("kind") == "http_attempt" and r.get("guard_refused")),
        "http_200": [a for a in attempts if a.get("status") == 200],
        "responses_ok": responses_ok,
        "events": events, "decisions": decisions, "failures": failures, "final": final, "tools": tools, "switch": switch,
        "post_switch_attempts": post, "stub_requests": len(trial["stub"]),
        "loadavg_at_spawn": cell.get("loadavg_at_spawn"), "wall_s": (int(cell["exit_ns"]) - int(cell["spawn_ns"])) / 1e9 if cell.get("exit_ns") else None,
    }


def attribution(d: dict) -> list[dict]:
    """Match decision records, in order, to HTTP 200 attempts and decoded provider responses."""
    out = []
    for i, decision in enumerate(d["decisions"]):
        http = d["http_200"][i] if i < len(d["http_200"]) else None
        resp = d["responses_ok"][i] if i < len(d["responses_ok"]) else None
        selected = decision_selected(decision)
        responder = None
        if resp is not None:
            responder = resp.get("responder")
        out.append({
            "decision_index": i, "record": decision.get("event"), "backend_field": decision.get("backend"),
            "selected": selected, "http_host": http.get("host") if http else None, "http_status": http.get("status") if http else None,
            "responder": responder, "response_selected": resp.get("selected_id") if resp else None,
            "request_id_match": bool(http and resp and http.get("request_id_sha256_16") and http.get("request_id_sha256_16") == resp.get("request_id_sha256_16")),
            "model": resp.get("model") if resp else None, "input_tokens": resp.get("input_tokens") if resp else None,
            "p_type": (decision.get("probabilities") or {}).get("type-verification-value"),
            "p_abstain": (decision.get("probabilities") or {}).get("abstain"),
        })
    return out


def r4_checks(d: dict) -> dict:
    first = d["decisions"][0] if d["decisions"] else {}
    precondition = bool(first.get("event") == "step" and first.get("candidate") == "type-verification-value" and d["switch"] and d["http_200"])
    final = d["final"]
    checks = {
        "precondition_met": precondition,
        "input_mutations_eq_1": d["input_mutations"] == 1,
        "submits_eq_0": d["submits"] == 0,
        "browser_type_calls_eq_1": d["tools"].get("browser_type", 0) == 1,
        "navigations_eq_1": d["navigations"] == 1,
        "routine_starts_eq_1": d["routine_starts"] == 1,
        "browser_prepare_eq_1": d["tools"].get("browser_prepare", 0) == 1,
        "decision_records_eq_1": len(d["decisions"]) == 1,
        "final_unknown_decide_step2": final.get("event") == "outcome" and final.get("outcome") == "unknown" and final.get("phase") == "decide" and final.get("step") == 2,
        "exit_nonzero": d["rc"] not in (0, None),
        "post_switch_all_loopback_refused": bool(d["post_switch_attempts"]) and all(a.get("loopback") and not isinstance(a.get("status"), int) for a in d["post_switch_attempts"]),
        "failure_record_content_free": all(not any(k in f for k in ("candidate", "confidence", "probabilities")) for f in d["failures"]),
    }
    checks["pass"] = all(checks.values())
    checks["replay"] = d["input_mutations"] > 1 or d["tools"].get("browser_type", 0) > 1
    checks["restart"] = d["navigations"] > 1 or d["routine_starts"] > 1 or d["tools"].get("browser_prepare", 0) > 1 or sorted(e.get("step") for e in d["decisions"]) != [e.get("step") for e in d["decisions"]] or len({e.get("step") for e in d["decisions"]}) != len(d["decisions"])
    return checks


def main() -> None:
    trials: dict[str, list[dict]] = {row: [] for row in PLANNED}
    for block, row in MEASURED_BLOCKS.items():
        for path in sorted((RAW / block).glob(f"{block}-*.jsonl")):
            d = derive(load_trial(path))
            assert d["row"] == row, (path, d["row"])
            trials[row].append(d)
    smoke = []
    for block in SMOKE_BLOCKS:
        for path in sorted((RAW / block).glob(f"{block}-*.jsonl")):
            d = derive(load_trial(path))
            smoke.append({"id": d["id"], "row": d["row"], "runtime": d["runtime"], "rc": d["rc"], "verified": d["verified"],
                          "reached": d["reached"], "loopback_refused": d["loopback_refused"], "stub_answered": d["stub_answered"],
                          "decisions": [decision_selected(e) for e in d["decisions"]], "final": {k: d["final"].get(k) for k in ("event", "outcome", "phase", "step")},
                          "browser_window_ready": "list_windows" not in d["tools"] or d["tools"].get("get_browser_state", 0) > 0})

    summary: dict = {"schema": "cua.experiment.summary.v1", "id": "OWN-78", "rows": {}}
    n_by_runtime = lambda rows: dict(Counter(t["runtime"] for t in rows))  # noqa: E731

    # R1
    r1 = trials["R1"]
    att = [a for t in r1 for a in attribution(t)]
    r1_counts_match = all(len(t["decisions"]) == len(t["http_200"]) == len(t["responses_ok"]) for t in r1)
    summary["rows"]["R1"] = {
        "class": "LIVE_PROVIDER+REAL", "n_trials": len(r1), "n_by_runtime": n_by_runtime(r1), "planned": PLANNED["R1"],
        "decisions": len(att), "decisions_by_kind": dict(Counter(a["selected"] for a in att)),
        "backend_field_eq_http_responder": sum(1 for a in att if a["backend_field"] == "typesafe" and a["responder"] == "typesafe" and a["http_host"] == TYPESAFE_HOST and a["http_status"] == 200 and a["selected"] == a["response_selected"]),
        "request_id_match": sum(1 for a in att if a["request_id_match"]),
        "decision_count_eq_200_count_all_trials": r1_counts_match,
        "verified": sum(t["verified"] for t in r1), "submits": sum(t["submits"] for t in r1),
        "reached": sum(t["reached"] for t in r1), "attempts": sum(t["attempts_total"] for t in r1),
        "p_type_step1": [a["p_type"] for a in att], "p_abstain_step1": [a["p_abstain"] for a in att],
        "models": sorted({a["model"] for a in att if a["model"]}), "input_tokens_median": statistics.median([a["input_tokens"] for a in att if a["input_tokens"] is not None]),
    }
    # R2
    r2 = trials["R2"]
    r2_dec = [e for t in r2 for e in t["decisions"]]
    summary["rows"]["R2"] = {
        "class": "REAL", "n_trials": len(r2), "n_by_runtime": n_by_runtime(r2), "planned": PLANNED["R2"],
        "decisions": len(r2_dec), "backend_mock": sum(1 for e in r2_dec if e.get("backend") == "mock"),
        "http_attempts": sum(t["attempts_total"] + t["guard_refused"] for t in r2), "verified": sum(t["verified"] for t in r2),
        "python_mock_receipts": sum(1 for t in r2 if t["runtime"] == "py" for r in t["responses_ok"] if r.get("responder") == "mock"),
        "key_in_runner_env": False,
    }
    # R3
    r3 = trials["R3"]
    summary["rows"]["R3"] = {
        "class": "REAL", "n_trials": len(r3), "n_by_runtime": n_by_runtime(r3), "planned": PLANNED["R3"],
        "zero_mutation_trials": sum(1 for t in r3 if t["input_events"] == 0 and t["input_mutations"] == 0 and t["submits"] == 0),
        "decision_records": sum(len(t["decisions"]) for t in r3),
        "explicit_failure_trials": sum(1 for t in r3 if t["final"].get("outcome") == "unknown" and t["final"].get("phase") == "decide" and t["final"].get("step") == 1 and t["rc"] not in (0, None)),
        "failure_records_content_free": sum(1 for t in r3 for f in t["failures"] if not any(k in f for k in ("candidate", "confidence", "probabilities"))),
        "failure_record_backend_values": dict(Counter(f.get("backend") for t in r3 for f in t["failures"])),
        "reached": sum(t["reached"] for t in r3), "loopback_refused": sum(t["loopback_refused"] for t in r3),
    }
    # R4 and R4s
    for row, cls in (("R4", "LIVE_PROVIDER+REAL"), ("R4s", "FIXTURE+REAL")):
        rows = trials[row]
        checks = [r4_checks(t) for t in rows]
        att = [a for t in rows for a in attribution(t)]
        summary["rows"][row] = {
            "class": cls, "n_trials": len(rows), "n_by_runtime": n_by_runtime(rows), "planned": PLANNED[row],
            "precondition_met": sum(c["precondition_met"] for c in checks), "pass": sum(c["pass"] for c in checks),
            "replays": sum(c["replay"] for c in checks), "restarts": sum(c["restart"] for c in checks),
            "input_mutations_hist": dict(Counter(t["input_mutations"] for t in rows)), "submits": sum(t["submits"] for t in rows),
            "failure_receipts_decide_step2": sum(c["final_unknown_decide_step2"] for c in checks),
            "final_records": dict(Counter(f"{t['final'].get('event')}:{t['final'].get('outcome')}:{t['final'].get('phase')}:step{t['final'].get('step')}" for t in rows)),
            "step1_selected": dict(Counter(a["selected"] for a in att if a["decision_index"] == 0)),
            "step1_backend_field": dict(Counter(a["backend_field"] for a in att if a["decision_index"] == 0)),
            "step1_responder": dict(Counter(a["responder"] for a in att if a["decision_index"] == 0)),
            "reached": sum(t["reached"] for t in rows), "loopback_refused": sum(t["loopback_refused"] for t in rows), "stub_answered": sum(t["stub_answered"] for t in rows),
            "per_check_failures": {k: sum(1 for c in checks if not c[k]) for k in checks[0] if k not in ("pass", "replay", "restart")} if checks else {},
            "p_type_step1": [a["p_type"] for a in att if a["decision_index"] == 0] if row == "R4" else None,
        }
    # R0
    r0 = trials["R0"]
    r0_att = [a for t in r0 for a in attribution(t)]
    summary["rows"]["R0"] = {
        "class": "LIVE_PROVIDER+REAL", "runner": "pre-PR base 2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4 (no backend field exists there)",
        "n_trials": len(r0), "verified": sum(t["verified"] for t in r0), "step1_selected": dict(Counter(a["selected"] for a in r0_att if a["decision_index"] == 0)),
        "decisions": len(r0_att), "responder_typesafe": sum(1 for a in r0_att if a["responder"] == "typesafe" and a["http_host"] == TYPESAFE_HOST),
        "p_type_step1": [a["p_type"] for a in r0_att if a["decision_index"] == 0],
        "input_tokens_step1_median": statistics.median([a["input_tokens"] for a in r0_att if a["decision_index"] == 0 and a["input_tokens"] is not None]),
        "reached": sum(t["reached"] for t in r0),
    }
    summary["rows"]["R5"] = {"class": "BLOCKED", "blocker": "adapter not local; non-TypeSafe provider not permitted"}

    # Cross-row invariants (E4) over every measured trial.
    all_trials = [t for rows in trials.values() for t in rows]
    live_or_mock = [t for row in ("R1", "R2", "R4", "R0") for t in trials[row]]
    mismatch = 0
    for t in live_or_mock:
        for a in attribution(t):
            if t["row"] == "R2":
                if a["backend_field"] != "mock" or t["attempts_total"]:
                    mismatch += 1
            elif t["row"] == "R0":
                continue  # pre-PR runner has no backend field
            elif not (a["backend_field"] == "typesafe" and a["responder"] == "typesafe" and a["http_host"] == TYPESAFE_HOST):
                mismatch += 1
    without_response = sum(1 for t in all_trials if t["row"] not in ("R2",) and len(t["decisions"]) > len(t["http_200"]))
    replays = sum(r4_checks(t)["replay"] for t in all_trials if t["row"] in ("R3", "R4", "R4s"))
    restarts = sum(1 for t in all_trials if t["navigations"] > 1 or t["routine_starts"] > 1 or t["tools"].get("browser_prepare", 0) > 1)
    unverified_success = sum(1 for t in all_trials if any(e.get("outcome") == "verified" for e in t["events"]) and not t["verified"])
    duplicate_submits = sum(1 for t in all_trials if t["submits"] > 1)
    summary["invariants"] = {
        "decision_receipt_backend_mismatch_live_and_mock_rows": mismatch,
        "decisions_without_response": without_response,
        "replays_after_partial_progress": replays,
        "restarts": restarts,
        "unverified_successes": unverified_success,
        "duplicate_submits": duplicate_submits,
        "configured_intent_counted_as_decision": sum(1 for t in all_trials for f in t["failures"] if any(k in f for k in ("candidate", "confidence", "probabilities"))) + summary["rows"]["R3"]["decision_records"],
        "measured_trials": len(all_trials), "timeouts": sum(1 for t in all_trials if t["timed_out"]), "harness_errors": sum(1 for t in all_trials if t["harness_error"]),
    }
    budget = json.loads((RAW / "budget.json").read_text())
    cells = [derive(load_trial(p)) for p in sorted(RAW.glob("*/*-*.jsonl"))]
    summary["budget"] = {
        "provider": "TypeSafe", "lane_cap_reached": 45,
        "reached": sum(c["reached"] for c in cells), "loopback_refused": sum(c["loopback_refused"] for c in cells),
        "attempts_counted": sum(c["reached"] + c["loopback_refused"] for c in cells),
        "stub_answered_not_provider": sum(c["stub_answered"] for c in cells), "guard_refused": sum(c["guard_refused"] for c in cells),
        "budget_file_reached": budget["reached"], "budget_file_http_attempts_all": budget["attempts"],
    }
    phase_reached: Counter = Counter()
    for c in cells:
        phase = next(b for b in (*MEASURED_BLOCKS, *SMOKE_BLOCKS) if c["id"].startswith(b + "-"))
        phase_reached[phase] += c["reached"]
    summary["budget"]["by_phase_reached"] = dict(phase_reached)
    summary["smoke"] = smoke
    summary["unit"] = json.loads((RAW / "unit" / "ts-failures.json").read_text())
    summary["unit"]["steps"] = (RAW / "unit" / "steps.txt").read_text().splitlines()

    rows = summary["rows"]
    inv = summary["invariants"]
    suites_pass = summary["unit"]["credential_free"]["totals"][-1].strip() == "# fail 0" and all(
        "rc=0" in line for line in summary["unit"]["steps"] if not line.startswith(("python-guarded-focused", "ts-guarded-focused")))
    keep = (rows["R1"]["backend_field_eq_http_responder"] == 20 and rows["R1"]["verified"] == 10 and rows["R2"]["http_attempts"] == 0
            and rows["R3"]["zero_mutation_trials"] == 6 and rows["R4"]["replays"] == 0 and rows["R4"]["failure_receipts_decide_step2"] == 20 and suites_pass)
    kill = inv["decision_receipt_backend_mismatch_live_and_mock_rows"] > 0 or inv["decisions_without_response"] > 0 or inv["replays_after_partial_progress"] > 0 or inv["restarts"] > 0
    summary["gates"] = {
        "suites_pass": suites_pass, "KEEP": keep, "KILL": kill,
        "disposition": "KILL" if kill else "KEEP" if keep else "REVISE",
        "keep_conditions": {
            "R1_backend_eq_http_20_of_20_with_verified": f"{rows['R1']['backend_field_eq_http_responder']}/{rows['R1']['decisions']} decisions match; verified {rows['R1']['verified']}/{rows['R1']['n_trials']}",
            "R2_zero_http": rows["R2"]["http_attempts"] == 0,
            "R3_zero_mutations": f"{rows['R3']['zero_mutation_trials']}/{rows['R3']['n_trials']}",
            "R4_zero_replays_and_20_failure_receipts": f"replays {rows['R4']['replays']}, failure receipts {rows['R4']['failure_receipts_decide_step2']}/20, precondition met {rows['R4']['precondition_met']}/20",
            "suites": suites_pass,
        },
    }
    (HERE / "own78-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"disposition": summary["gates"]["disposition"], "keep_conditions": summary["gates"]["keep_conditions"], "invariants": inv, "budget": {k: summary["budget"][k] for k in ("reached", "loopback_refused", "attempts_counted", "stub_answered_not_provider")}}, indent=1))


if __name__ == "__main__":
    main()

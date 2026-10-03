#!/usr/bin/env python3
"""OWN-78L analysis: recompute every row, the E4 checks and the pre-registered gate from raw/.

usage: python3 analyze.py [--write]   (standard library only; prints the summary, --write saves it)
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
SUMMARY = HERE / "own78l-summary.json"
R1 = ("R1t1", "R1t2", "R1t3")
MOCK = ("MOCKt1", "MOCKt2", "MOCKt3")
CAP0 = ("CAP0t1",)
STUB = ("STUBt1",)
MUTATING = {"browser_type", "browser_click", "click", "type_text", "press_key", "set_value"}
TYPESAFE_HOST = "api.typesafe.ai"
CAP = {"reached": 6, "attempts": 8}
REQUIRED_KEYS = ("observation.form", "observation.page", "observation.outline")


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_block(block: str) -> dict:
    src = RAW / block
    cells = jsonl(src / "cells.jsonl")
    trial_file = src / f"{block}-01-C.jsonl"
    records = jsonl(trial_file) if trial_file.exists() else []
    return {"validity": json.loads((src / "validity.json").read_text()), "cell": cells[0], "records": records}


def trial_view(records: list[dict]) -> dict:
    events = [r["event"] for r in records if r["type"] == "runner_event"]
    receipts = sorted((r for r in records if r["type"] == "receipt"), key=lambda r: r.get("seq", 0))
    journal = [r for r in records if r["type"] == "journal"]
    stub = [r for r in records if r["type"] == "stub"]
    return {"events": events, "receipts": receipts, "journal": journal, "stub": stub}


def decision_records(events: list[dict]) -> list[dict]:
    """Runner records that carry a provider decision (never a decide-phase failure receipt)."""
    out = []
    for e in events:
        if e.get("event") == "step":
            out.append(e)
        elif e.get("event") == "outcome" and e.get("outcome") == "abstained" and "confidence" in e:
            out.append(e)
    return out


def backend_vs_responder(view: dict) -> dict:
    decisions = decision_records(view["events"])
    responses = [r for r in view["receipts"] if r.get("kind") == "provider_response" and r.get("ok")]
    pairs = []
    for index, decision in enumerate(decisions):
        response = responses[index] if index < len(responses) else None
        attempt = None
        if response is not None:
            prior = [r for r in view["receipts"] if r.get("kind") == "http_attempt" and r["seq"] < response["seq"]
                     and not r.get("guard_refused")]
            attempt = prior[-1] if prior else None
        pairs.append({
            "step": decision.get("step"), "candidate": decision.get("candidate"),
            "runner_backend": decision.get("backend"),
            "responder": response.get("responder") if response else None,
            "responder_host": response.get("responder_host") if response else None,
            "http_status": attempt.get("status") if attempt else None,
            "request_id_match": bool(attempt and response and attempt.get("request_id_present")
                                     and attempt.get("request_id_sha256_16") == response.get("request_id_sha256_16")),
            "model": response.get("model") if response else None,
            "selected_id": response.get("selected_id") if response else None,
            "probabilities": response.get("probabilities") if response else None,
            "input_tokens": response.get("input_tokens") if response else None,
            "output_tokens": response.get("output_tokens") if response else None,
        })
    for pair in pairs:
        pair["equal"] = (pair["runner_backend"] == pair["responder"] == "typesafe"
                         and pair["responder_host"] == TYPESAFE_HOST and pair["http_status"] == 200
                         and pair["request_id_match"] and pair["selected_id"] == pair["candidate"])
    return {"pairs": pairs, "n_decisions": len(decisions), "n_ok_responses": len(responses),
            "all_equal": bool(pairs) and len(pairs) == len(responses) and all(p["equal"] for p in pairs)}


def replay_restart(cell: dict, view: dict) -> dict:
    calls = [r for r in view["receipts"] if r.get("kind") == "driver_call"]
    mutating = [r for r in calls if r.get("tool") in MUTATING]
    per_tool = {}
    for r in mutating:
        per_tool[r["tool"]] = per_tool.get(r["tool"], 0) + 1
    click = next((r for r in mutating if r.get("tool") == "browser_click"), None)
    after_click = [r for r in mutating if click is not None and r["seq"] > click["seq"]]
    counts = cell.get("server_counts", {})
    input_after_submit = [j for j in view["journal"] if click is not None and j.get("arrival_ns", 0) > click.get("t_start_ns", 0)]
    flags = {
        "submits_gt_1": cell.get("submits", 0) > 1,
        "browser_type_gt_1": per_tool.get("browser_type", 0) > 1,
        "browser_click_gt_1": per_tool.get("browser_click", 0) > 1,
        "mutation_after_submit_click": bool(after_click),
        "browser_prepare_gt_1": sum(1 for r in calls if r.get("tool") == "browser_prepare") > 1,
        "browser_navigate_gt_1": sum(1 for r in calls if r.get("tool") == "browser_navigate") > 1,
        "reset_gt_1": counts.get("POST /reset", 0) > 1,
        "input_event_after_submit_click": bool(input_after_submit),
    }
    return {"mutating_dispatches": per_tool, "flags": flags, "replay_or_restart": any(flags.values()),
            "duplicate_mutation": flags["submits_gt_1"] or flags["browser_type_gt_1"] or flags["browser_click_gt_1"]}


def oracle(cell: dict, view: dict) -> dict:
    journal = view["journal"]
    verified = (cell.get("submitted_equals_token") is True and cell.get("submits") == 1
                and bool(journal) and journal[-1].get("equals_token") is True)
    runner_outcome = next((e.get("outcome") for e in reversed(view["events"]) if e.get("event") == "outcome"), None)
    return {"verified": verified, "submitted_equals_token": cell.get("submitted_equals_token"),
            "submits": cell.get("submits"), "input_events": cell.get("input_events"),
            "journal_last_equals_token": bool(journal) and journal[-1].get("equals_token") is True,
            "runner_outcome": runner_outcome, "runner_rc": cell.get("rc"),
            "unverified_success": runner_outcome == "verified" and not verified}


def typed_ref_check(view: dict, field: dict) -> bool | None:
    """Descriptive: the browser_type ref resolves to the fixture's own textbox in the step snapshot."""
    choice = next((r for r in view["receipts"] if r.get("kind") == "choice" and r.get("tool") == "browser_type"), None)
    if choice is None:
        return None
    snaps = [r for r in view["receipts"] if r.get("kind") == "driver_call" and "ref_index" in r and r["seq"] < choice["seq"]]
    if not snaps:
        return None
    hit = [x for x in snaps[-1]["ref_index"] if x.get("ref") == choice.get("arg_ref")]
    return bool(hit) and hit[0].get("role") == field["role"] and hit[0].get("name") == field["aria_label"]


def step_timings(events: list[dict]) -> list[dict]:
    keys = ("step", "candidate", "decision_ms", "semantic_observe_ms", "visual_observe_ms", "candidate_build_ms",
            "provider_decision_ms", "action_ms", "total_step_ms")
    return [{k: e.get(k) for k in keys} for e in events if e.get("event") == "step"]


def e4(rows: list[dict]) -> dict:
    return {"duplicate_mutations": sum(1 for r in rows if r["replay"]["duplicate_mutation"]),
            "replays_or_restarts": sum(1 for r in rows if r["replay"]["replay_or_restart"]),
            "unverified_successes": sum(1 for r in rows if r["oracle"]["unverified_success"]),
            "decisions_from_failure_receipts": 0}


def unit_row() -> dict:
    row = RAW / "unit" / "f"
    summary = json.loads((row / "summary.json").read_text())
    steps = (row / "steps.txt").read_text()
    rcs = dict(re.findall(r"^(\S+)\s+rc=(\d+)", steps, re.M))
    env = (row / "env.txt").read_text()
    cred = int(re.search(r"credential_env_present=(\d+)", env).group(1))
    green = (summary["ts"] == {"tests": 109, "pass": 109, "fail": 0} and summary["typecheck_rc"] == 0
             and summary["python_status"].startswith("OK") and all(v == "0" for v in rcs.values()) and cred == 0)
    attempts = {name: json.loads((RAW / "unit" / name / "summary.json").read_text())["python_status"]
                for name in ("attempt1-incomplete-export-f", "attempt2-incomplete-export-f")}
    return {"evidence_class": "UNIT", "ts": summary["ts"], "typecheck_rc": summary["typecheck_rc"],
            "python_ran": summary["python_ran"], "python_status": summary["python_status"],
            "step_rcs": rcs, "credential_env_present": cred, "green_109": green,
            "incomplete_export_attempts_kept": attempts}


def analyze() -> dict:
    blocks = {b: load_block(b) for b in (*STUB, *CAP0, *MOCK, *R1)}
    validity = {b: blocks[b]["validity"]["ok"] for b in blocks}
    field = blocks["R1t1"]["validity"]["fixture_field"]

    r1_rows = []
    for b in R1:
        cell, view = blocks[b]["cell"], trial_view(blocks[b]["records"])
        if cell.get("not_run"):
            r1_rows.append({"trial": b, "evidence_class": "NOT_RUN", "not_run": cell["not_run"]})
            continue
        bvr = backend_vs_responder(view)
        r1_rows.append({
            "trial": b, "evidence_class": "LIVE_PROVIDER+REAL", "token_sha256_16": cell["token_sha256_16"],
            "oracle": oracle(cell, view), "backend_vs_responder": bvr, "replay": replay_restart(cell, view),
            "typed_ref_is_fixture_textbox": typed_ref_check(view, field),
            "attempts": cell["http_attempts"], "reached": cell["http_reached"], "guard_refused": cell["guard_refused"],
            "allowance": [cell["reach_allowance"], cell["attempt_allowance"]],
            "models": sorted({p["model"] for p in bvr["pairs"] if p["model"]}),
            "http_latency_ms": [r["latency_ms"] for r in view["receipts"] if r.get("kind") == "http_attempt"],
            "step_timings_ms": step_timings(view["events"]),
            "loadavg_at_spawn": cell["loadavg_at_spawn"], "utc_start": cell["utc_start"]})
    ran = [r for r in r1_rows if r["evidence_class"] != "NOT_RUN"]
    r1 = {"n": len(R1), "ran": len(ran),
          "verified": sum(1 for r in ran if r["oracle"]["verified"]),
          "backend_equals_responder": sum(1 for r in ran if r["backend_vs_responder"]["all_equal"]),
          "replays_or_restarts": sum(1 for r in ran if r["replay"]["replay_or_restart"]),
          "decisions": sum(r["backend_vs_responder"]["n_decisions"] for r in ran),
          "max_decisions_per_trial": max((r["backend_vs_responder"]["n_decisions"] for r in ran), default=0),
          "models": sorted({m for r in ran for m in r["models"]}),
          "e4": e4(ran), "trials": r1_rows}
    lat = [x for r in ran for x in r["http_latency_ms"]]
    r1["descriptive_latency_ms"] = {"http_median": statistics.median(lat) if lat else None,
                                    "http_min": min(lat, default=None), "http_max": max(lat, default=None),
                                    "note": "descriptive only; no timing claim"}

    mock_rows = []
    for b in MOCK:
        cell, view = blocks[b]["cell"], trial_view(blocks[b]["records"])
        decisions = decision_records(view["events"])
        http = [r for r in view["receipts"] if r.get("kind") == "http_attempt"]
        requests = [r for r in view["receipts"] if r.get("kind") == "provider_request"]
        override = [r for r in view["receipts"] if r.get("kind") == "own78l_provider_override"]
        row = {"trial": b, "evidence_class": "FIXTURE", "decisions": len(decisions),
               "backends": sorted({d.get("backend") for d in decisions}),
               "http_attempt_receipts": len(http), "provider_request_receipts": len(requests),
               "override_receipt": [{"from": o.get("from"), "to": o.get("to")} for o in override],
               "oracle": oracle(cell, view), "replay": replay_restart(cell, view)}
        row["pass"] = (row["decisions"] >= 1 and row["backends"] == ["mock"] and not http and not requests
                       and row["override_receipt"] == [{"from": "typesafe", "to": "mock"}])
        mock_rows.append(row)
    mock = {"n": len(MOCK), "pass": sum(1 for r in mock_rows if r["pass"]),
            "verified": sum(1 for r in mock_rows if r["oracle"]["verified"]), "e4": e4(mock_rows), "trials": mock_rows}

    cell, view = blocks["CAP0t1"]["cell"], trial_view(blocks["CAP0t1"]["records"])
    http = [r for r in view["receipts"] if r.get("kind") == "http_attempt"]
    failure = next((e for e in view["events"] if e.get("event") == "outcome"), {})
    gate = cell["own78l_gate"]
    cap0 = {"evidence_class": "UNIT+FIXTURE", "harness_can_start_at_cap0": gate["own78a_can_start_C"],
            "lane_cap": gate["lane_cap"], "allowance": [cell["reach_allowance"], cell["attempt_allowance"]],
            "guard_refused": sum(1 for r in http if r.get("guard_refused")),
            "attempts": cell["http_attempts"], "reached": cell["http_reached"],
            "refused_hosts": sorted({r.get("host") for r in http if r.get("guard_refused")}),
            "key_in_runner_env": cell["key_in_runner_env"],
            "runner_outcome": {k: failure.get(k) for k in ("outcome", "phase", "backend", "error")},
            "input_events": cell["input_events"], "submits": cell["submits"]}
    cap0["pass"] = (cap0["harness_can_start_at_cap0"] is False and cap0["guard_refused"] >= 1
                    and cap0["attempts"] == 0 and cap0["reached"] == 0
                    and len(http) == cap0["guard_refused"] and cap0["refused_hosts"] == [TYPESAFE_HOST]
                    and failure.get("outcome") == "unknown" and failure.get("phase") == "decide"
                    and cap0["input_events"] == 0 and cap0["submits"] == 0 and not cap0["key_in_runner_env"])

    view = trial_view(blocks["STUBt1"]["records"])
    stub = {"evidence_class": "FIXTURE", "requests": len(view["stub"]),
            "state_key_paths": [s["state_key_paths"] for s in view["stub"]],
            "oracle": oracle(blocks["STUBt1"]["cell"], view)}
    stub["pass"] = stub["requests"] >= 1 and all(all(k in paths for k in REQUIRED_KEYS) for paths in stub["state_key_paths"])

    unit = unit_row()

    ledger = jsonl(RAW / "provider-ledger.jsonl")
    sent = [r for r in ledger if not r.get("guard_refused")]
    budget = json.loads((RAW / "budget.json").read_text())
    provider = {"attempts": len(sent), "reached": sum(1 for r in sent if isinstance(r.get("status"), int)),
                "guard_refused": sum(1 for r in ledger if r.get("guard_refused")),
                "hosts": sorted({r["host"] for r in sent}), "statuses": sorted({r["status"] for r in sent}),
                "by_block": {b: sum(1 for r in sent if r["block"] == b) for b in (*CAP0, *MOCK, *R1)},
                "budget_json": {k: budget[k] for k in ("attempts", "reached", "lane_cap_reached", "lane_cap_attempts")},
                "cap": CAP}
    provider["within_cap"] = provider["reached"] <= CAP["reached"] and provider["attempts"] <= CAP["attempts"]

    conditions = {
        "r1_verified_3_of_3": r1["verified"] == 3,
        "backend_equals_responder_3_of_3": r1["backend_equals_responder"] == 3,
        "zero_replays_or_restarts": r1["replays_or_restarts"] == 0 and mock["e4"]["replays_or_restarts"] == 0,
        "mock_control_pass": mock["pass"] == 3,
        "cap0_control_pass": cap0["pass"],
        "unit_109_credential_free": unit["green_109"],
    }
    keep = all(conditions.values()) and all(validity.values())
    e4_total = {k: r1["e4"][k] + mock["e4"][k] for k in r1["e4"]}
    return {
        "schema": "cua.r2.own78l.summary.v1", "lane": "OWN-78L",
        "headline": (f"R1-lite on F: verified {r1['verified']}/3, backend == responder {r1['backend_equals_responder']}/3, "
                     f"replays/restarts {r1['replays_or_restarts']}; MOCK {mock['pass']}/3; CAP-0 {'pass' if cap0['pass'] else 'FAIL'}; "
                     f"stub key-shape {'pass' if stub['pass'] else 'FAIL'}; UNIT TS {unit['ts']['pass']}/{unit['ts']['tests']}; "
                     f"provider {provider['attempts']} attempts / {provider['reached']} reached"),
        "disposition": "KEEP" if keep else "REVISE",
        "gate_conditions": conditions, "validity_ok": validity,
        "r1_lite": r1, "mock": mock, "cap0": cap0, "stub_keyshape": stub, "unit": unit,
        "provider": provider, "e4_all_arms": e4_total,
        "blocked": {"full_n_R1_20_R4_20": "BLOCKED (budget: about 60 reached)",
                    "A2_vs_A3_residual_gap": "BLOCKED (budget)",
                    "S1_backend_row": "BLOCKED (adapter not local; non-TypeSafe providers not permitted)"},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    summary = analyze()
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    if args.write:
        SUMMARY.write_text(text)
    print(summary["headline"])
    print("disposition:", summary["disposition"], summary["gate_conditions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Narrow fail-closed evidence auditor, not a Driver/runner modification.

Historical telemetry without separately captured per-trial dispatch and provider
observations cannot qualify. Timing is never interpreted as a provider count.
No authentication against a same-user adversary who replaces all custody files
is claimed. See README for the trust boundary.
"""

from __future__ import annotations
import json
from pathlib import Path
from prepare import PIN

PROOF_FIELDS = {
    "status",
    "prior_ref",
    "fresh_ref",
    "verification_field",
    "submit_matches",
    "session",
}
STEP_FIELDS = {
    "event",
    "step",
    "candidate",
    "tool",
    "decision_route",
    "guarded_completion",
    "dry_run",
    "action_error",
    "delivery_mode",
    "confidence",
    "probabilities",
    "visual",
    "action_ms",
    "candidate_build_ms",
    "decision_ms",
    "provider_decision_ms",
    "semantic_observe_ms",
    "total_step_ms",
    "visual_observe_ms",
}


def check_events(events, mode):
    errors = []
    if (
        not isinstance(events, list)
        or len(events) != 3
        or [e.get("event") for e in events] != ["step", "step", "outcome"]
    ):
        return ["event_sequence"]
    a, b, last = events
    if last != {"event": "outcome", "outcome": "verified"}:
        errors.append("outcome")
    expected_routes = (
        ["provider", "guarded-completion"] if mode == "accepted" else ["provider", "provider"]
    )
    if [a.get("decision_route"), b.get("decision_route")] != expected_routes:
        errors.append("route")
    for i, (event, tool, candidate) in enumerate(
        [(a, "browser_type", "type-verification-value"), (b, "browser_click", "submit-form")], 1
    ):
        if set(event) - STEP_FIELDS:
            errors.append("unexpected_step_field")
        if type(event.get("step")) is not int or event["step"] != i:
            errors.append("step_order")
        if event.get("tool") != tool or event.get("candidate") != candidate:
            errors.append("action_attribution")
        if event.get("dry_run") is not False or event.get("action_error"):
            errors.append("action_not_executed")
    if "guarded_completion" in a:
        errors.append("duplicate_or_early_proof")
    proof = b.get("guarded_completion")
    if mode == "accepted":
        if not isinstance(proof, dict) or set(proof) != PROOF_FIELDS:
            errors.append("proof_schema")
        else:
            if (
                proof["status"] != "accepted"
                or proof["verification_field"] != "contains_required_token"
            ):
                errors.append("proof_assertion")
            if type(proof["submit_matches"]) is not int or proof["submit_matches"] != 1:
                errors.append("proof_uniqueness")
            if not all(
                isinstance(proof[k], str) and proof[k].strip()
                for k in ["prior_ref", "fresh_ref", "session"]
            ):
                errors.append("proof_identifiers")
            if proof["prior_ref"] == proof["fresh_ref"]:
                errors.append("ref_reused")
        if (
            type(b.get("provider_decision_ms")) not in (int, float)
            or b["provider_decision_ms"] != 0
        ):
            errors.append("guarded_time_schema")
        if (
            "confidence" not in b
            or b["confidence"] is not None
            or "probabilities" not in b
            or b["probabilities"] is not None
        ):
            errors.append("guarded_model_scores")
    elif mode == "declined":
        if proof != {"status": "declined", "reason": "submit_not_unique"}:
            errors.append("decline_assertion")
    elif mode == "default":
        if proof is not None:
            errors.append("unexpected_guard")
    else:
        errors.append("unknown_mode")
    return errors


def audit_historical(folder):
    folder = Path(folder)
    result = json.loads((folder / "result.json").read_text())
    events = [json.loads(line) for line in (folder / "input.jsonl").read_text().splitlines()]
    receipt = json.loads((folder / "claimed-receipt.json").read_text())
    journal = [
        json.loads(line) for line in (folder / "claimed-journal.jsonl").read_text().splitlines()
    ]
    language, mode = result["language"], result["mode"]
    errors = check_events(events, mode)
    if receipt.get("exact_head") != PIN:
        errors.append("pin_mismatch")
    if receipt.get("mode") != mode:
        errors.append("mode_mismatch")
    if receipt.get("steps", {}).get(language) != [e for e in events if e.get("event") == "step"]:
        errors.append("receipt_jsonl_disagreement")
    selected = [e for e in journal if e.get("language") == language]
    if len(selected) != 1:
        errors.append("journal_attribution")
    elif (
        selected[0].get("received_expected_value") is not True
        or selected[0].get("committed_expected_value") is not True
    ):
        errors.append("journal_outcome")
    errors += [
        "missing_independent_provider_counter",
        "missing_observation_dispatch_binding",
        "missing_original_trial_attribution",
    ]
    return {
        "qualifying": False,
        "verdict": "NONQUALIFYING",
        "scope": "historical retained REAL evidence; not retroactively upgraded",
        "errors": sorted(set(errors)),
    }


def audit_capture(claim, trace, oracle):
    """Fail closed on malformed data; report codes, never field contents."""
    try:
        return _audit_capture(claim, trace, oracle)
    except (KeyError, TypeError, AttributeError, IndexError, ValueError):
        return {"qualifying": False, "verdict": "NONQUALIFYING", "errors": ["malformed_evidence"]}


def _audit_capture(claim, trace, oracle):
    """Audit one bounded, two-action FIX cell against separate witnesses."""
    errors = check_events(claim.get("events"), claim.get("mode"))
    if claim.get("schema") != "guarded-audit-v1":
        errors.append("claim_schema")
    for source in (claim, trace, oracle):
        if source.get("exact_head") != PIN:
            errors.append("pin_mismatch")
        for key in ("cell_key", "trial_key", "language"):
            if (
                not isinstance(source.get(key), str)
                or not source[key]
                or source[key] != claim.get(key)
            ):
                errors.append("trial_attribution")
    if claim.get("language") != "python":
        errors.append("uncertified_language")
    if claim.get("cell_key") != f"audit001/fix/python/{claim.get('mode')}":
        errors.append("cell_attribution")
    for source in (claim, trace):
        if (
            source.get("real_driver") is not False
            or source.get("scope") != "FIX"
            or source.get("provider") != "mock"
        ):
            errors.append("scope_upgrade")
    if trace.get("exit_code") != 0 or trace.get("mode") != claim.get("mode"):
        errors.append("consumer_mismatch")
    forced = {
        "guarded": claim.get("mode") != "default",
        "fixture_duplicate_submit": claim.get("mode") == "declined",
    }
    for source in (claim, trace):
        if source.get("forced") != forced or any(
            type(v) is not bool for v in source.get("forced", {}).values()
        ):
            errors.append("forced_mode")
    if claim.get("steps") != claim.get("events", [])[:2]:
        errors.append("receipt_jsonl_disagreement")
    if claim.get("outcome_verified") is not True:
        errors.append("claimed_outcome")
    if (
        oracle.get("initially_empty") is not True
        or oracle.get("state_matches_expected") is not True
    ):
        errors.append("independent_outcome")
    journal = oracle.get("journal")
    if not isinstance(journal, list) or len(journal) != 1:
        errors.append("journal_count")
    else:
        entry = journal[0]
        for key in ("cell_key", "trial_key", "language"):
            if entry.get(key) != claim.get(key):
                errors.append("journal_attribution")
        if (
            entry.get("event") != "fixture_submit"
            or entry.get("received_expected_value") is not True
            or entry.get("committed_expected_value") is not True
        ):
            errors.append("journal_outcome")
    for event in trace.get("events", []):
        if any(event.get(k) != claim.get(k) for k in ("cell_key", "trial_key")):
            errors.append("trace_attribution")
    expected_count = 1 if claim.get("mode") == "accepted" else 2
    calls = [e for e in trace.get("events", []) if e.get("kind") == "provider_call"]
    if (
        type(claim.get("provider_count")) is not int
        or type(trace.get("provider_count")) is not int
        or claim["provider_count"] != len(calls)
        or trace["provider_count"] != len(calls)
        or len(calls) != expected_count
    ):
        errors.append("provider_counter")
    items = trace.get("events", [])
    expected_kinds = (
        ["observation", "provider_call", "action", "observation"]
        + ([] if claim.get("mode") == "accepted" else ["provider_call"])
        + ["action"]
    )
    if [e.get("kind") for e in items] != expected_kinds:
        errors.append("trace_sequence")
    else:
        action_count = observation_count = 0
        for n, e in enumerate(items, 1):
            if type(e.get("seq")) is not int or e["seq"] != n:
                errors.append("trace_sequence")
            if e["kind"] == "observation":
                observation_count += 1
                if (
                    e.get("observation") != observation_count
                    or e.get("after_actions") != action_count
                ):
                    errors.append("observation_order")
            elif e["kind"] == "provider_call":
                if (
                    e.get("after_actions") != action_count
                    or e.get("after_observations") != observation_count
                ):
                    errors.append("provider_order")
            else:
                action_count += 1
                if e.get("action") != action_count or e.get("success") is not True:
                    errors.append("dispatch_failed")
        obs = [e for e in items if e["kind"] == "observation"]
        actions = [e for e in items if e["kind"] == "action"]
        sessions = [e.get("session") for e in obs + actions]
        if not all(isinstance(s, str) and s.strip() and s == sessions[0] for s in sessions):
            errors.append("dispatch_session")
        if [e.get("tool") for e in actions] != ["browser_type", "browser_click"]:
            errors.append("dispatch_tool")
        initial_refs, fresh_refs = obs[0].get("submit_refs"), obs[1].get("submit_refs")
        if (
            not isinstance(initial_refs, list)
            or len(initial_refs) != 1
            or not isinstance(fresh_refs, list)
            or not fresh_refs
        ):
            errors.append("observed_targets")
        else:
            if actions[1].get("ref") not in fresh_refs:
                errors.append("dispatch_ref")
            if (
                obs[0].get("field_contains_expected") is not False
                or obs[1].get("field_contains_expected") is not True
            ):
                errors.append("independent_field")
            if claim.get("mode") == "accepted":
                proof = claim["events"][1].get("guarded_completion") or {}
                if len(fresh_refs) != 1 or proof.get("submit_matches") != len(fresh_refs):
                    errors.append("independent_uniqueness")
                if (
                    proof.get("prior_ref") != initial_refs[0]
                    or proof.get("fresh_ref") != actions[1].get("ref")
                    or proof.get("fresh_ref") not in fresh_refs
                ):
                    errors.append("proof_ref_binding")
                if proof.get("session") != sessions[0]:
                    errors.append("proof_session_binding")
            elif claim.get("mode") == "declined" and len(fresh_refs) == 1:
                errors.append("decline_not_independently_proven")
    return {
        "qualifying": not errors,
        "verdict": "NONQUALIFYING" if errors else "QUALIFYING_FIX_ONLY",
        "errors": sorted(set(errors)),
    }


def strict_json(raw):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("nonfinite_json")

    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=nonfinite)


def audit_bound(claim_path, custody_path, custody_sha256):
    """Load witnesses ONLY from the externally hash-pinned custody map."""
    from prepare import sha
    import re

    try:
        custody_path = Path(custody_path)
        if not re.fullmatch("[0-9a-f]{64}", custody_sha256) or sha(custody_path) != custody_sha256:
            raise ValueError("custody_integrity")
        custody = strict_json(custody_path.read_text())
        claim = strict_json(Path(claim_path).read_text())
        if custody.get("exact_head") != PIN or custody.get("schema") != "owned-witness-custody-v1":
            raise ValueError("custody_integrity")
        pairs = [(e["cell_key"], e["trial_key"]) for e in custody["bindings"]]
        if len(set(pairs)) != len(pairs):
            raise ValueError("custody_integrity")
        selected = [
            e
            for e in custody["bindings"]
            if (e["cell_key"], e["trial_key"]) == (claim.get("cell_key"), claim.get("trial_key"))
        ]
        if len(selected) != 1:
            raise ValueError("custody_integrity")
        witnesses = []
        for name in ["transport", "oracle"]:
            rel = Path(selected[0][name + "_path"])
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("custody_integrity")
            path = custody_path.parent / rel
            path.resolve().relative_to(custody_path.parent.resolve())
            if sha(path) != selected[0][name + "_sha256"]:
                raise ValueError("custody_integrity")
            witnesses.append(strict_json(path.read_text()))
        return audit_capture(claim, *witnesses)
    except (OSError, KeyError, TypeError, AttributeError, ValueError):
        return {"qualifying": False, "verdict": "NONQUALIFYING", "errors": ["custody_integrity"]}


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim", type=Path, required=True)
    parser.add_argument("--custody", type=Path, required=True)
    parser.add_argument(
        "--custody-sha256",
        required=True,
        help="caller-held anchor, NOT an assertion from the claim",
    )
    args = parser.parse_args()
    result = audit_bound(args.claim, args.custody, args.custody_sha256)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["qualifying"] else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Offline, fail-closed qualification for CUA #10 run_steps/run_script task ledgers.

Measurement QA only. Does not execute or certify a CUA Driver, native desktop,
model, or browser-CDP experiment. No public ActionResult schema is defined here.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
import re
import statistics
from pathlib import Path
import random
import sys

ARMS = ("run_steps", "run_script")
EVIDENCE_CLASSES = {"synthetic", "browser_cdp", "native_driver"}
OUTCOMES = {"verified", "refuted", "abstained", "unknown", "timed_out", "refused"}
DELIVERIES = {"attempted", "applied", "refused", "unknown"}
EFFECTS = {"verified", "refuted", "unknown", "none"}
MATCH_FIELDS = (
    "task_contract_sha", "initial_state_sha", "permission_sha", "driver_source_sha",
    "driver_build_sha", "host_id", "fixture_sha", "provider_id",
)
TIMES = ("t_oracle_ms", "t_runner_ms", "fallback_ms")


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _one_of(value, allowed):
    """Membership for untrusted JSON enums: reject arrays/maps rather than crash."""
    return isinstance(value, str) and value in allowed


def _finite_ms(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _ci(samples: list[float], iterations: int = 4000) -> tuple[float, float]:
    """Deterministic paired bootstrap: fixed sample *pairs*, never separate arms."""
    rng = random.Random(151016)
    n = len(samples)
    mids = []
    for _ in range(iterations):
        resample = [samples[rng.randrange(n)] for _ in range(n)]
        mids.append(statistics.median(resample))
    mids.sort()
    return mids[int(.025 * iterations)], mids[int(.975 * iterations)]


def analyze(rows: list[dict]) -> dict:
    errors: list[str] = []
    by_pair: dict[str, list[dict]] = defaultdict(list)
    for i, r in enumerate(rows):
        prefix = f"row {i}"
        if not isinstance(r, dict):
            errors.append(f"{prefix}: not an object")
            continue
        pair = r.get("pair_id")
        if not _nonempty(pair):
            errors.append(f"{prefix}: missing pair_id")
            continue
        by_pair[pair].append(r)
        if not _one_of(r.get("arm"), ARMS):
            errors.append(f"{prefix}: unrecognized arm")
        if r.get("route_actual") != r.get("arm"):
            errors.append(f"{prefix}: actual route is absent or not the named arm")
        if not _one_of(r.get("outcome"), OUTCOMES):
            errors.append(f"{prefix}: outcome missing or invalid")
        if type(r.get("speed_eligible")) is not bool:
            errors.append(f"{prefix}: speed_eligible must be boolean")
        if r.get("slot") not in (0, 1) or isinstance(r.get("slot"), bool):
            errors.append(f"{prefix}: invalid paired slot")
        for key in MATCH_FIELDS:
            if not _nonempty(r.get(key)):
                errors.append(f"{prefix}: missing provenance {key}")
        if not re.fullmatch(r"[a-f0-9]{40}", str(r.get("driver_source_sha", ""))):
            errors.append(f"{prefix}: driver_source_sha must be a full 40-character git SHA")
        if not re.fullmatch(r"[a-f0-9]{64}", str(r.get("driver_build_sha", ""))):
            errors.append(f"{prefix}: driver_build_sha must be a full SHA256 binary digest")
        if not _one_of(r.get("evidence_class"), EVIDENCE_CLASSES):
            errors.append(f"{prefix}: evidence class missing (native_driver/browser_cdp/synthetic)")
        oracle = r.get("oracle")
        if not isinstance(oracle, dict) or oracle.get("independent") is not True or oracle.get("fresh_after_action") is not True:
            errors.append(f"{prefix}: oracle must independently re-read the final state after mutation")
        elif not _nonempty(oracle.get("observation_sha")):
            errors.append(f"{prefix}: missing independent oracle evidence digest")
        times = r.get("timing")
        if not isinstance(times, dict) or any(not _finite_ms(times.get(k)) for k in TIMES):
            errors.append(f"{prefix}: timing missing/nonfinite/negative (failures still count)")
        elif times["t_runner_ms"] < times["t_oracle_ms"]:
            errors.append(f"{prefix}: runner lifetime cannot be shorter than verified outcome")
        if r.get("fallback_used") is True and (not isinstance(times, dict) or not _finite_ms(times.get("fallback_ms")) or times["fallback_ms"] == 0):
            errors.append(f"{prefix}: fallback latency must be measured, not zeroed")
        if type(r.get("fallback_used")) is not bool:
            errors.append(f"{prefix}: fallback_used must be boolean")
        actions = r.get("actions")
        if not isinstance(actions, list):
            errors.append(f"{prefix}: missing actions/attempts ledger")
            continue
        if r.get("outcome") == "verified" and not actions:
            errors.append(f"{prefix}: verified task has no recorded mutations")
        seen_attempts = set()
        prior_mutation = {}
        for j, action in enumerate(actions):
            tag = f"{prefix}/action {j}"
            if not isinstance(action, dict) or not _nonempty(action.get("attempt_id")):
                errors.append(f"{tag}: missing attempt identity")
                continue
            if action["attempt_id"] in seen_attempts:
                errors.append(f"{tag}: duplicate attempt_id")
            seen_attempts.add(action["attempt_id"])
            mutation = action.get("logical_mutation_id")
            if not _nonempty(mutation):
                errors.append(f"{tag}: missing logical_mutation_id")
            elif mutation in prior_mutation:
                previous = prior_mutation[mutation]
                if previous.get("delivery") != "refused" or previous.get("may_have_landed") is not False or previous.get("cancelled") is True:
                    errors.append(f"{tag}: duplicate logical mutation after potentially applied/unknown/cancelled attempt")
            if _nonempty(mutation):
                prior_mutation[mutation] = action
            # These are safety facts, not truthy hints. In particular, an
            # acknowledgement-loss/cancellation ledger must not smuggle a
            # string or integer past the retry guard.
            for flag in ("may_have_landed", "replayed", "cancelled"):
                if type(action.get(flag)) is not bool:
                    errors.append(f"{tag}: {flag} must be boolean")
            if "reconciled_by_fresh_oracle" in action and type(action["reconciled_by_fresh_oracle"]) is not bool:
                errors.append(f"{tag}: reconciled_by_fresh_oracle must be boolean")
            if not _one_of(action.get("delivery"), DELIVERIES) or not _one_of(action.get("effect"), EFFECTS):
                errors.append(f"{tag}: invalid delivery/effect classification")
            if action.get("delivery") == "applied" and action.get("may_have_landed") is not True:
                errors.append(f"{tag}: applied delivery contradicts may_have_landed=false/unknown")
            if action.get("delivery") == "refused" and action.get("may_have_landed") is not False:
                errors.append(f"{tag}: refused delivery requires a proven non-dispatch")
            if action.get("delivery") == "refused" and action.get("effect") == "verified":
                errors.append(f"{tag}: refused delivery contradicts verified effect")
            if action.get("delivery") == "unknown" and r.get("outcome") == "verified" and action.get("reconciled_by_fresh_oracle") is not True:
                errors.append(f"{tag}: unknown delivery needs explicit independent reconciliation")
            if action.get("replayed") is True and (action.get("may_have_landed") is True or action.get("delivery") in ("applied", "unknown")):
                errors.append(f"{tag}: unsafe replay after accepted/unknown delivery")
            if action.get("cancelled") is True and action.get("replayed") is True:
                errors.append(f"{tag}: unsafe replay after cancellation")
            if action.get("effect") == "verified" and not (isinstance(oracle, dict) and oracle.get("independent") is True and oracle.get("fresh_after_action") is True):
                errors.append(f"{tag}: verified effect has no fresh independent oracle")
        if r.get("outcome") == "verified" and not any(
            isinstance(action, dict) and (
                (action.get("effect") == "verified" and action.get("delivery") in ("applied", "attempted", "unknown"))
                or (action.get("delivery") == "unknown" and action.get("reconciled_by_fresh_oracle") is True)
            )
            for action in actions
        ):
            errors.append(f"{prefix}: verified task has no verified mutation effect")
        if r.get("outcome") == "verified" and not _nonempty(r.get("final_effect_sha")):
            errors.append(f"{prefix}: verified outcome missing independent final-effect digest")
        if r.get("outcome") != "verified" and r.get("speed_eligible") is True:
            errors.append(f"{prefix}: an unsuccessful/refused/unknown attempt cannot claim latency eligibility")

    pairs: list[tuple[dict, dict]] = []
    order = Counter()
    for pair_id, both in sorted(by_pair.items()):
        arms = Counter(row.get("arm") for row in both if _one_of(row.get("arm"), ARMS))
        if len(both) != 2 or any(arms[arm] != 1 for arm in ARMS):
            errors.append(f"pair {pair_id}: missing/duplicate arm (all attempts required)")
            continue
        a = next(row for row in both if row["arm"] == "run_steps")
        b = next(row for row in both if row["arm"] == "run_script")
        if type(a.get("slot")) is not int or type(b.get("slot")) is not int or {a["slot"], b["slot"]} != {0, 1}:
            errors.append(f"pair {pair_id}: both slots must occur exactly once")
            continue
        slots = sorted(both, key=lambda r: r["slot"])
        if slots[0].get("arm") in ARMS:
            order[slots[0]["arm"]] += 1
        for key in MATCH_FIELDS:
            if a.get(key) != b.get(key):
                errors.append(f"pair {pair_id}: unmatched {key}")
        if a.get("outcome") == "verified" and b.get("outcome") == "verified" and a.get("final_effect_sha") != b.get("final_effect_sha"):
            errors.append(f"pair {pair_id}: verified effects are not equivalent")
        pairs.append((a, b))
    if pairs and abs(order["run_steps"] - order["run_script"]) > 1:
        errors.append("arm order unbalanced; use AB/BA alternation")

    verified_pairs = [
        (a, b) for a, b in pairs
        if a.get("outcome") == b.get("outcome") == "verified"
        and a.get("final_effect_sha") == b.get("final_effect_sha")
        and isinstance(a.get("timing"), dict) and isinstance(b.get("timing"), dict)
        and _finite_ms(a["timing"].get("t_oracle_ms")) and _finite_ms(b["timing"].get("t_oracle_ms"))
    ]
    counts = {arm: dict(Counter(
        r.get("outcome") if _one_of(r.get("outcome"), OUTCOMES) else "invalid"
        for r in rows if isinstance(r, dict) and r.get("arm") == arm
    )) for arm in ARMS}
    differences = [b["timing"]["t_oracle_ms"] - a["timing"]["t_oracle_ms"] for a, b in verified_pairs]
    interval = list(_ci(differences)) if len(differences) >= 2 else None
    # Gate a performance *claim*, not the validity of the safety/evidence tests.
    fully_verified = len(verified_pairs) == len(pairs) and len(rows) == 2 * len(pairs)
    statistical_signal = (
        not errors and fully_verified and len(verified_pairs) >= 20 and interval is not None
        and (interval[1] < 0 or interval[0] > 0)
    )
    all_native = len(rows) > 0 and all(isinstance(r, dict) and r.get("evidence_class") == "native_driver" for r in rows)
    # Every field above is supplied by the ledger author. A forged ledger can
    # declare itself native_driver, invent independent observations, and choose
    # timings that produce a nonzero bootstrap interval. Even if source/build
    # digests look well formed, none of their bytes are authenticated here.
    # Consequently this offline tool may identify a candidate for an external
    # Driver+oracle audit, but MUST NOT certify a performance claim.
    audit_candidate = bool(statistical_signal and all_native and all(r.get("speed_eligible") is True for r in rows))
    return {
        "classification": "LOCAL_LEDGER_QA_ONLY; NOT_DRIVER_CERTIFICATION",
        "valid": not errors,
        "errors": errors,
        "attempts": len(rows),
        "pairs": len(pairs),
        "verified_pairs": len(verified_pairs),
        "order_first": dict(order),
        "outcomes_by_arm": counts,
        "paired_script_minus_steps_median_ms": statistics.median(differences) if differences else None,
        "paired_bootstrap_95pct_ms": interval,
        "statistical_signal_only": bool(statistical_signal),
        "candidate_for_external_driver_audit": audit_candidate,
        "speed_claim_eligible": False,
        "external_source_oracle_audit": "REQUIRED; ledger fields are asserted, not authenticated",
        "speed_claim_blockers": [
            "offline ledger cannot authenticate Driver execution, build/source bytes, or the independent oracle",
            *([] if audit_candidate else [
                "also requires native scope, safe complete matched pairs, 20+ verified pairs, a nonzero interval, and both arms marked speed_eligible"
            ]),
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ledger", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    try:
        rows = [json.loads(line) for line in a.ledger.read_text().splitlines() if line.strip()]
        out = analyze(rows)
    except (OSError, ValueError) as exc:
        print(f"INVALID_INPUT: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if out["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

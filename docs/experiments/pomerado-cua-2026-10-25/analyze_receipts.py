#!/usr/bin/env python3
"""Validate paired CUA/Pomerado site-tool receipts. Never infer unrun benchmarks."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics
import sys

SCHEMA = "cua.pomerado.trial.v1"
ORDERS = {"ABBA", "BAAB"}
ROUTES = {"cua-driver", "pomerado-mcp", "fallback-cua", "blocked"}
OUTCOMES = {"verified", "refuted", "unknown", "abstained"}
PINS = ("workflow", "variant", "input_fingerprint", "fixture_sha", "caller_sha",
        "driver_sha", "pomerado_sha")
REQUIRED = {
    "schema", "evidence_class", "run_id", "block_id", "position", "arm",
    "workflow", "variant", "input_fingerprint", "fixture_sha", "caller_sha",
    "driver_sha", "pomerado_sha", "browser_version", "route_observed",
    "route_evidence", "reset_verified", "oracle_outcome", "oracle_evidence",
    "elapsed_ms", "model_calls", "input_tokens", "output_tokens",
    "wrong_target", "unauthorized_effect", "duplicate_effect",
    "uncertain_effect", "fallback_count", "mint_ms",
}


class InvalidReceipts(ValueError):
    pass


def must(valid: bool, why: str) -> None:
    if not valid:
        raise InvalidReceipts(why)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def number(value: object, *, positive: bool) -> bool:
    return (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and (value > 0 if positive else value >= 0)
    )


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def validate(rows: list[dict]) -> dict[tuple[str, str], list[list[dict]]]:
    must(bool(rows), "no receipts: NOT_RUN, cannot evaluate")
    seen: set[str] = set()
    blocks: dict[str, list[dict]] = defaultdict(list)
    for line, row in enumerate(rows, 1):
        must(isinstance(row, dict), f"row {line}: expected JSON object")
        absent = REQUIRED - row.keys()
        must(not absent, f"row {line}: missing {sorted(absent)}")
        must(row["schema"] == SCHEMA, f"row {line}: wrong schema")
        must(row["evidence_class"] in {"REAL", "UNIT"}, f"row {line}: bad evidence class")
        for field in ("run_id", "block_id", *PINS, "browser_version",
                      "route_evidence", "oracle_evidence"):
            must(nonempty(row[field]), f"row {line}: missing {field}")
        must(row["run_id"] not in seen, f"row {line}: duplicate run_id")
        seen.add(row["run_id"])
        must(type(row["position"]) is int and 1 <= row["position"] <= 4,
             f"row {line}: invalid position")
        must(row["arm"] in {"A", "B"}, f"row {line}: invalid arm")
        must(row["route_observed"] in ROUTES, f"row {line}: invalid actual route")
        must(row["oracle_outcome"] in OUTCOMES, f"row {line}: invalid oracle outcome")
        must(row["reset_verified"] is True, f"row {line}: reset not independently verified")
        for field in ("wrong_target", "unauthorized_effect", "duplicate_effect",
                      "uncertain_effect"):
            must(type(row[field]) is bool, f"row {line}: {field} must be bool")
        must(number(row["elapsed_ms"], positive=True), f"row {line}: invalid elapsed_ms")
        must(number(row["mint_ms"], positive=False), f"row {line}: invalid mint_ms")
        for field in ("model_calls", "input_tokens", "output_tokens", "fallback_count"):
            must(type(row[field]) is int and row[field] >= 0,
                 f"row {line}: invalid {field}")
        blocks[row["block_id"]].append(row)

    cohorts: dict[tuple[str, str], list[list[dict]]] = defaultdict(list)
    for block_id, group in blocks.items():
        must(len(group) == 4, f"block {block_id}: expected exactly four trials")
        group.sort(key=lambda r: r["position"])
        must([r["position"] for r in group] == [1, 2, 3, 4],
             f"block {block_id}: positions incomplete or duplicated")
        order = "".join(r["arm"] for r in group)
        must(order in ORDERS, f"block {block_id}: not ABBA/BAAB")
        for field in PINS:
            must(len({r[field] for r in group}) == 1,
                 f"block {block_id}: mismatched {field}")
        cohorts[group[0]["workflow"], group[0]["variant"]].append(group)
    return cohorts


def summarize(rows: list[dict], minimum_blocks: int = 30) -> dict:
    cohorts = validate(rows)
    result: dict = {"schema": "cua.pomerado.analysis.v1", "attempts": len(rows), "cohorts": {}}
    for (workflow, variant), blocks in sorted(cohorts.items()):
        trials = [trial for block in blocks for trial in block]
        counts = Counter("".join(r["arm"] for r in block) for block in blocks)
        problems = []
        if len(blocks) < minimum_blocks or min(counts.get("ABBA", 0), counts.get("BAAB", 0)) < minimum_blocks // 2:
            problems.append("insufficient balanced paired blocks")
        if any(r["evidence_class"] != "REAL" for r in trials):
            problems.append("non-real/unit evidence present")
        if any(r["oracle_outcome"] != "verified" for r in trials):
            problems.append("unverified, refuted or incomplete outcomes")
        if any(r["wrong_target"] or r["unauthorized_effect"] or r["duplicate_effect"]
               or r["uncertain_effect"] for r in trials):
            problems.append("unsafe or uncertain side effect")
        if any(r["fallback_count"] for r in trials):
            problems.append("fallback present (retain attempted-arm accounting)")
        if any(r["route_observed"] != ("cua-driver" if r["arm"] == "A" else "pomerado-mcp")
               for r in trials):
            problems.append("requested route was not always exercised")
        if len({r["browser_version"] for r in trials}) != 1:
            problems.append("browser-version comparability confound")
        if not any(r["mint_ms"] > 0 for r in trials if r["arm"] == "B"):
            problems.append("mint preparation cost not measured")
        arms = {}
        for arm in ("A", "B"):
            subset = [r for r in trials if r["arm"] == arm]
            durations = [r["elapsed_ms"] for r in subset]
            arms[arm] = {
                "attempted": len(subset),
                "verified": sum(r["oracle_outcome"] == "verified" for r in subset),
                "p50_all_attempts_ms": statistics.median(durations),
                "p95_all_attempts_ms": percentile(durations, 0.95),
                "fallbacks": sum(r["fallback_count"] for r in subset),
                "wrong_targets": sum(r["wrong_target"] for r in subset),
                "unauthorized_effects": sum(r["unauthorized_effect"] for r in subset),
                "duplicates": sum(r["duplicate_effect"] for r in subset),
                "model_calls": sum(r["model_calls"] for r in subset),
                "input_tokens": sum(r["input_tokens"] for r in subset),
                "output_tokens": sum(r["output_tokens"] for r in subset),
                "mint_ms_total": sum(r["mint_ms"] for r in subset),
            }
        delta = None
        if not problems:
            per_block_deltas = [
                statistics.mean(r["elapsed_ms"] for r in block if r["arm"] == "B")
                - statistics.mean(r["elapsed_ms"] for r in block if r["arm"] == "A")
                for block in blocks
            ]
            delta = statistics.median(per_block_deltas)
        result["cohorts"][f"{workflow}/{variant}"] = {
            "status": "COMPARABLE_DESCRIPTIVE_ONLY" if not problems else "NOT_READY",
            "reasons": problems,
            "blocks": len(blocks),
            "orders": dict(counts),
            "arms": arms,
            "paired_median_B_minus_A_ms": delta,
            "note": "warm comparison does not include cold mint; show its measured cost separately",
        }
    return result


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise InvalidReceipts(f"line {n}: invalid JSON: {error}") from error
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, help="redacted REAL JSONL task receipts")
    args = parser.parse_args()
    try:
        output = summarize(load_jsonl(args.receipts))
    except (InvalidReceipts, OSError) as error:
        print(json.dumps({"status": "INVALID_OR_NOT_RUN", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify complete receipt coverage of a frozen ABBA/BAAB plan.

This checks assignment/receipt consistency ONLY. It cannot prove a tool ran,
that a route trace is authentic, or that the claimed oracle is independent.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

PLAN_SCHEMA = "cua.pomerado.assignment.v1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
ORDERS = {"ABBA", "BAAB"}


class CoverageError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise CoverageError(message)


def digest(obj: dict) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def verify(plan: dict, rows: list[dict], *, expected_head: str, prereg: dict,
           expected_manifest_sha256: str) -> dict:
    """Check exactly one receipt per planned attempt; no execution claim."""
    require(isinstance(plan, dict), "expected plan object")
    require(plan.get("schema") == PLAN_SCHEMA, "wrong plan schema")
    require(plan.get("evidence_class") == "PLAN_ONLY" and plan.get("status") == "NOT_RUN"
            and plan.get("actual_executions") == 0,
            "plan must remain an inert assignment, not a forged observation")
    require(isinstance(expected_head, str) and SHA40.fullmatch(expected_head) is not None,
            "expected head must be a full Git SHA")
    require(plan.get("candidate_head_sha") == expected_head,
            "plan HEAD does not match externally pinned commit")
    require(isinstance(prereg, dict) and prereg.get("schema") == "cua.pomerado.prereg.v1"
            and prereg.get("status") == "PREREGISTERED_NOT_RUN",
            "invalid source preregistration")
    require(plan.get("prereg_sha256") == digest(prereg),
            "plan prereg digest disagrees with exact source")
    design = prereg.get("design", {})
    require(plan.get("seed") == design.get("seed"), "seed disagrees with prereg")
    require(plan.get("blocks_per_variant") == design.get("blocks_per_workflow_variant")
            and plan.get("trials_per_block") == design.get("attempts_per_block"),
            "planned sample size disagrees with prereg")
    require(isinstance(expected_manifest_sha256, str) and
            SHA64.fullmatch(expected_manifest_sha256) is not None,
            "external manifest SHA256 pin must be exactly 64 lowercase hex characters")
    recorded = plan.get("manifest_sha256")
    require(isinstance(recorded, str) and SHA64.fullmatch(recorded) is not None,
            "missing manifest SHA")
    unsigned = dict(plan)
    unsigned.pop("manifest_sha256")
    require(digest(unsigned) == recorded, "plan manifest digest mismatch")
    require(recorded == expected_manifest_sha256,
            "external manifest SHA256 pin mismatch: assignments changed since preregistration")
    require(plan.get("phase") in {"read_only", "synthetic_write"}, "invalid phase")
    if plan["phase"] == "synthetic_write":
        proof = plan.get("read_only_proof_sha256")
        require(isinstance(proof, str) and SHA64.fullmatch(proof) is not None,
                "synthetic write phase lacks read-only proof digest")
    else:
        require(plan.get("read_only_proof_sha256") is None,
                "read-only phase unexpectedly carries a write proof")
    blocks = plan.get("blocks")
    require(isinstance(blocks, list) and len(blocks) > 0, "no planned blocks")
    require(type(plan.get("block_count")) is int and len(blocks) == plan["block_count"],
            "inconsistent planned block count")
    require(plan.get("planned_attempt_count") == 4 * len(blocks)
            and plan.get("trials_per_block") == 4,
            "inconsistent planned attempt count")
    require(type(plan.get("blocks_per_variant")) is int
            and plan["blocks_per_variant"] >= 2
            and plan["blocks_per_variant"] % 2 == 0,
            "invalid per-variant size")
    expectations: dict[tuple[str, int], tuple[str, dict]] = {}
    seen_blocks: set[str] = set()
    counts: Counter[tuple[str, str]] = Counter()
    variants: set[str] = set()
    for b in blocks:
        require(isinstance(b, dict), "malformed plan block")
        bid, variant, workflow, order = (b.get(k) for k in
                                         ("block_id", "variant", "workflow", "order"))
        require(all(isinstance(x, str) and x for x in (bid, variant, workflow, order)),
                "plan block has missing identity")
        require(bid not in seen_blocks, f"duplicate planned block {bid}")
        seen_blocks.add(bid)
        require(order in ORDERS, f"bad planned order for {bid}")
        attempts = b.get("attempts")
        require(isinstance(attempts, list) and len(attempts) == 4,
                f"block {bid}: not four planned attempts")
        require([a.get("position") for a in attempts if isinstance(a, dict)] == [1, 2, 3, 4],
                f"block {bid}: invalid planned positions")
        require("".join(a.get("arm_assigned", "?") for a in attempts) == order,
                f"block {bid}: planned arm order mismatch")
        for a in attempts:
            arm = a["arm_assigned"]
            require(a.get("effect_kind_planned") == ("read" if plan["phase"] == "read_only" else "write"),
                    f"block {bid}: phase/attempt effect mismatch")
            require(a.get("route_assigned_not_observed") ==
                    ("cua-driver" if arm == "A" else "pomerado-mcp"),
                    f"block {bid}: assigned route mismatch")
            require(a.get("status") == "NOT_RUN" and a.get("blind_retry") == "PROHIBITED",
                    f"block {bid}: plan mutated into an execution/retry instruction")
            expectations[bid, a["position"]] = (arm, b)
        counts[variant, order] += 1
        variants.add(variant)
    allowed = {"default", *design.get("negative_variants", [])}
    require(variants <= allowed, "plan introduced unregistered cohort")
    require(set(variants) == set(plan.get("cohort_orders", {})),
            "plan cohort summary is incomplete")
    require(all(b["workflow"] == design.get("first_fixture") for b in blocks),
            "plan target changed from preregistered fixture")
    for variant in variants:
        require(counts[variant, "ABBA"] == counts[variant, "BAAB"] ==
                plan["blocks_per_variant"] // 2,
                f"variant {variant}: invalid preregistered ABBA/BAAB balance")
    require(plan.get("cohort_orders") == {
        v: {"ABBA": counts[v, "ABBA"], "BAAB": counts[v, "BAAB"]}
        for v in variants}, "cohort-order summary mismatch")

    require(isinstance(rows, list), "receipts must be a list")
    observed: set[tuple[str, int]] = set()
    run_ids: set[str] = set()
    route_mismatches = 0
    for n, row in enumerate(rows, 1):
        require(isinstance(row, dict), f"receipt {n} is not an object")
        bid, pos, arm, run_id = (row.get(k) for k in
                                 ("block_id", "position", "arm", "run_id"))
        require(isinstance(bid, str) and bool(bid.strip()),
                f"receipt {n}: invalid block_id")
        require(type(pos) is int and 1 <= pos <= 4, f"receipt {n}: invalid position")
        key = (bid, pos)
        require(key in expectations, f"receipt {n}: not in frozen plan")
        require(key not in observed, f"receipt {n}: duplicate planned attempt {bid}/{pos}")
        observed.add(key)
        require(isinstance(run_id, str) and bool(run_id.strip()) and run_id not in run_ids,
                f"receipt {n}: blank or reused run_id")
        run_ids.add(run_id)
        expected_arm, b = expectations[key]
        require(arm == expected_arm and row.get("workflow") == b["workflow"]
                and row.get("variant") == b["variant"],
                f"receipt {n}: arm/workflow/variant disagrees with plan")
        require(row.get("effect_kind") == ("read" if plan["phase"] == "read_only" else "write"),
                f"receipt {n}: effect class disagrees with frozen phase")
        require(isinstance(row.get("route_observed"), str) and row["route_observed"] in
                {"cua-driver", "pomerado-mcp", "fallback-cua", "blocked"},
                f"receipt {n}: missing/invalid observed route")
        if row["route_observed"] != ("cua-driver" if arm == "A" else "pomerado-mcp"):
            route_mismatches += 1  # Attribution confounds stay visible, not silently dropped.
    missing = sorted(set(expectations) - observed)
    if missing:
        raise CoverageError(f"{len(missing)} planned attempts missing, first: {missing[0]}")
    return {
        "schema": "cua.pomerado.coverage.v1",
        "status": "COVERAGE_COMPLETE_NOT_AUTHENTICATED",
        "qualification": "ASSIGNMENT_TO_RECEIPT_CONSISTENCY_ONLY",
        "plan_sha256": recorded,
        "candidate_head_sha": expected_head,
        "planned_attempts": len(expectations),
        "received_attempts": len(rows),
        "blocks": len(blocks),
        "route_mismatches": route_mismatches,
        "cua_vs_pomerado_verified_trials": None,
        "warning": "Coverage cannot authenticate route/oracle/audit evidence or establish real execution.",
    }


def load_jsonl(path: Path) -> list[dict]:
    result = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CoverageError(f"invalid JSONL line {n}: {exc}") from exc
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True,
                        help="independently retained pre-execution canonical manifest digest")
    parser.add_argument("--prereg", type=Path, required=True)
    opts = parser.parse_args()
    try:
        result = verify(json.loads(opts.plan.read_text(encoding="utf-8")),
                        load_jsonl(opts.receipts), expected_head=opts.expected_head,
                        prereg=json.loads(opts.prereg.read_text(encoding="utf-8")),
                        expected_manifest_sha256=opts.expected_manifest_sha256)
    except (CoverageError, ValueError, OSError) as exc:
        parser.exit(2, json.dumps({"status": "COVERAGE_INVALID", "error": str(exc)}) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

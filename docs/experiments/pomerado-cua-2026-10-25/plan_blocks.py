#!/usr/bin/env python3
"""Deterministic, non-executing ABBA/BAAB assignment for the CUA pilot.

This file cannot launch CUA, Pomerado, Avrea, Boat or a browser. It emits a
PLAN_ONLY manifest, not observations, measurements, or grant of authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re

HERE = Path(__file__).resolve().parent
SCHEMA = "cua.pomerado.assignment.v1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
LABEL = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
# Arm C (opencli adapter over CDP) was added by exp/opencli-arm-20261026. Blocks stay
# four attempts and two arms each; a three-arm study is the pairwise set AB, AC, BC.
ARM_ROUTE = {"A": "cua-driver", "B": "pomerado-mcp", "C": "opencli-adapter-cdp"}


class PlanError(ValueError):
    """Invalid preregistration or insufficient write-planning gate."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise PlanError(why)


def digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def build_plan(prereg: dict, *, head_sha: str, phase: str = "read_only",
               read_only_proof_sha256: str | None = None,
               variants: list[str] | None = None,
               arms: tuple[str, ...] = ("A", "B")) -> dict:
    require(isinstance(arms, (tuple, list)) and 2 <= len(arms) <= 3
            and len(set(arms)) == len(arms) and all(a in ARM_ROUTE for a in arms)
            and list(arms) == sorted(arms),
            "arms must be a sorted subset of A, B, C with at least two arms")
    pairs = [(x, y) for i, x in enumerate(arms) for y in arms[i + 1:]]
    two_arm = list(arms) == ["A", "B"]
    require(isinstance(prereg, dict) and prereg.get("schema") == "cua.pomerado.prereg.v1",
            "not the pinned preregistration schema")
    require(prereg.get("status") == "PREREGISTERED_NOT_RUN",
            "registration changed; re-review before regenerating")
    ownership = prereg.get("ownership", {})
    require(ownership.get("default_off") is True
            and ownership.get("caller_side_only") is True
            and ownership.get("external_runtime_separate_authority") is True,
            "caller-side, default-off isolation gate is missing")
    require(isinstance(head_sha, str) and SHA40.fullmatch(head_sha) is not None,
            "head_sha must be an exact lowercase 40-hex Git commit SHA")
    require(phase in {"read_only", "synthetic_write"}, "unknown phase")
    if phase == "synthetic_write":
        require(isinstance(read_only_proof_sha256, str)
                and SHA64.fullmatch(read_only_proof_sha256) is not None,
                "synthetic write planning requires a read-only proof digest")
    design = prereg.get("design", {})
    total = design.get("blocks_per_workflow_variant")
    per_order = design.get("blocks_per_order")
    orders = design.get("orders")
    require(type(total) is int and type(per_order) is int
            and total == 2 * per_order and total >= 2
            and orders == ["ABBA", "BAAB"]
            and design.get("attempts_per_block") == 4,
            "ABBA/BAAB block contract has changed")
    seed = design.get("seed")
    require(type(seed) is int and seed >= 0, "invalid preregistered seed")
    workflow = design.get("first_fixture")
    allowed = ["default", *design.get("negative_variants", [])]
    require(isinstance(workflow, str) and LABEL.fullmatch(workflow) is not None,
            "unsafe workflow identifier")
    require(all(isinstance(v, str) and LABEL.fullmatch(v) for v in allowed)
            and len(allowed) == len(set(allowed)), "unsafe/duplicate cohort")
    chosen = allowed if variants is None else variants
    require(bool(chosen) and len(chosen) == len(set(chosen))
            and all(v in allowed for v in chosen), "unknown/duplicate cohort request")
    require(prereg.get("fixture", {}).get("reset") == "POST /reset"
            and prereg.get("fixture", {}).get("state") == "GET /state"
            and prereg.get("fixture", {}).get("write_oracle", "").startswith("GET /audit"),
            "independent reset, state, or mutation audit was changed")

    rng = random.Random(seed)
    blocks = []
    for variant in chosen:
        for x, y in pairs:
            orders = (x + y + y + x, y + x + x + y)
            order_list = [orders[0]] * per_order + [orders[1]] * per_order
            rng.shuffle(order_list)
            for n, order in enumerate(order_list, 1):
                pair_tag = "" if two_arm else f"{x}{y}:"
                block_id = f"{phase}:{workflow}:{variant}:{pair_tag}{n:03d}"
                block = {
                    "block_id": block_id,
                    "workflow": workflow,
                    "variant": variant,
                    "order": order,
                    "attempts": [{
                        "position": pos,
                        "arm_assigned": arm,
                        "route_assigned_not_observed": ARM_ROUTE[arm],
                        "status": "NOT_RUN",
                        "reset_before": "MUST_VERIFY_INDEPENDENTLY",
                        "state_oracle": "GET /state",
                        "mutation_oracle": "GET /audit",
                        "effect_kind_planned": "read" if phase == "read_only" else "write",
                        "blind_retry": "PROHIBITED",
                    } for pos, arm in enumerate(order, 1)],
                }
                if not two_arm:
                    block["arm_pair"] = x + y
                blocks.append(block)
    # Shuffle complete blocks, not trial order; interleave scenario cohorts.
    rng.shuffle(blocks)
    counts: dict[str, dict[str, int]] = {}
    for variant in chosen:
        for x, y in pairs:
            orders = (x + y + y + x, y + x + x + y)
            tally = Counter(b["order"] for b in blocks if b["variant"] == variant
                            and (two_arm or b["arm_pair"] == x + y))
            require(tally == Counter({orders[0]: per_order, orders[1]: per_order}),
                    f"lost paired balance for {variant}")
            key = variant if two_arm else f"{variant}/{x}{y}"
            counts[key] = dict(sorted(tally.items()))
    manifest = {
        "schema": SCHEMA,
        "evidence_class": "PLAN_ONLY",
        "status": "NOT_RUN",
        "actual_executions": 0,
        "authorization": "NONE; offline assignment cannot mint, execute, or spend",
        "phase": phase,
        "read_only_proof_sha256": read_only_proof_sha256 if phase == "synthetic_write" else None,
        "prereg_sha256": digest(prereg),
        "candidate_head_sha": head_sha,
        "seed": seed,
        "blocks_per_variant": total,
        "trials_per_block": 4,
        "cohort_orders": counts,
        "block_count": len(blocks),
        "planned_attempt_count": 4 * len(blocks),
        "blocks": blocks,
    }
    if not two_arm:
        manifest["arms"] = list(arms)
    manifest["manifest_sha256"] = digest(manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prereg", type=Path, default=HERE / "PREREG.json")
    parser.add_argument("--head-sha", required=True, help="exact 40-character PR head commit")
    parser.add_argument("--phase", choices=("read_only", "synthetic_write"), default="read_only")
    parser.add_argument("--read-only-proof-sha256")
    parser.add_argument("--variant", action="append", dest="variants", help="one cohort; repeatable")
    parser.add_argument("--arms", default="AB",
                        help="AB (default, original design) or ABC for pairwise AB, AC, BC blocks")
    parser.add_argument("--output", type=Path, help="write immutable plan JSON (default stdout)")
    args = parser.parse_args()
    try:
        prereg = json.loads(args.prereg.read_text(encoding="utf-8"))
        plan = build_plan(prereg, head_sha=args.head_sha, phase=args.phase,
                          read_only_proof_sha256=args.read_only_proof_sha256,
                          variants=args.variants, arms=tuple(args.arms))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    serialized = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

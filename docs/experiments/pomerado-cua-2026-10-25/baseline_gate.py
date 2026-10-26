#!/usr/bin/env python3
"""Fail-closed fairness gate for REAL CUA-vs-Pomerado A/B receipts.

Checks source-declared routes, not execution authenticity. Run alongside the
existing analyze_receipts.py and verify external traces independently.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

TOOLS = {"run_steps", "run_script"}
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}", re.ASCII)


class BaselineError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise BaselineError(reason)


def check(rows: list[dict], *, expected_driver_sha: str | None = None) -> dict:
    """Require an observed, current batch/script baseline, never legacy per-step.

    Output is syntactic/route-claim evidence only. The independently run Driver,
    tool traces, policy, executable SHA, reset and outcome remain external gates.
    """
    require(isinstance(rows, list) and bool(rows), "no rows")
    if expected_driver_sha is not None:
        require(isinstance(expected_driver_sha, str)
                and SHA.fullmatch(expected_driver_sha) is not None,
                "invalid expected_driver_sha")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    evidence_seen: set[str] = set()
    for i, row in enumerate(rows, 1):
        require(isinstance(row, dict), f"row {i}: not an object")
        require(row.get("evidence_class") == "REAL",
                f"row {i}: REAL receipts required; synthetic data cannot qualify")
        require(row.get("arm") in {"A", "B"}, f"row {i}: invalid arm")
        require(row.get("route_observed") == (
            "cua-driver" if row["arm"] == "A" else "pomerado-mcp"
        ), f"row {i}: route mismatch or fallback")
        tool = row.get("baseline_tool")
        require(isinstance(tool, str) and tool in TOOLS,
                f"row {i}: invalid/stale baseline_tool; require run_steps or run_script")
        driver_sha = row.get("driver_sha")
        require(isinstance(driver_sha, str) and SHA.fullmatch(driver_sha) is not None,
                f"row {i}: invalid driver_sha")
        if expected_driver_sha is not None:
            require(driver_sha == expected_driver_sha,
                    f"row {i}: driver_sha differs from attested build")
        workflow, variant = row.get("workflow"), row.get("variant")
        require(isinstance(workflow, str) and bool(workflow)
                and isinstance(variant, str) and bool(variant),
                f"row {i}: workflow/variant required")
        groups[workflow, variant].append(row)
        if row["arm"] == "A":
            advertised = row.get("advertised_driver_tools")
            observed = row.get("observed_driver_tools")
            require(isinstance(advertised, list) and all(isinstance(t, str) for t in advertised)
                    and tool in advertised,
                    f"row {i}: baseline tool not advertised by tools/list")
            require(isinstance(observed, list) and all(isinstance(t, str) for t in observed)
                    and tool in observed,
                    f"row {i}: declared baseline not observed in actual Driver calls")
            require("run_actions" not in observed,
                    f"row {i}: deprecated run_actions is not a current baseline")
            if tool == "run_script":
                require(row.get("run_script_operator_enabled") is True,
                        f"row {i}: script disabled or operator policy not proven")
            evidence = row.get("baseline_trace_evidence")
            require(isinstance(evidence, str) and bool(evidence.strip()),
                    f"row {i}: missing baseline trace reference")
            require(evidence not in evidence_seen,
                    f"row {i}: repeated baseline trace reference")
            evidence_seen.add(evidence)
    for (workflow, variant), group in groups.items():
        require(len({r["baseline_tool"] for r in group}) == 1,
                f"{workflow}/{variant}: mixed baseline_tool")
        require(len({r["driver_sha"] for r in group}) == 1,
                f"{workflow}/{variant}: mixed driver_sha")
        require(any(r["arm"] == "A" for r in group) and any(r["arm"] == "B" for r in group),
                f"{workflow}/{variant}: unpaired arms")
    return {
        "status": "RECEIPT_SHAPE_ONLY_NOT_RUNTIME_PROOF",
        "real_rows_checked": len(rows),
        "baseline_cohorts": {f"{w}/{v}": group[0]["baseline_tool"]
                             for (w, v), group in sorted(groups.items())},
        "warning": "Requires separate analyze_receipts/coverage gates and independent audit of actual Driver tool traces, policy and binary provenance. No speedup certified."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path)
    parser.add_argument("--expected-driver-sha", required=True,
                        help="Exact attested current binary/source SHA; never use a prose version")
    args = parser.parse_args()
    try:
        with args.receipts.open(encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        result = check(rows, expected_driver_sha=args.expected_driver_sha)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

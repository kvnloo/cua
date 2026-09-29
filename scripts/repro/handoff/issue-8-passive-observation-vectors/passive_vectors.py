#!/usr/bin/env python3
"""ACTIONABLE-DOMAIN PRECEDENCE vectors for the proposed passive native observation rule (#3903/#3904).

DATA + REFERENCE MODEL ONLY. Nothing here touches production; the reference evaluator encodes the proposed
rule so the vectors are executable and self-consistent, and so the production implementation can be pointed
at vectors.json later (feed `input`, compare to `expect`) without renegotiating cases.

Rule: if the existing selector matches >=1 actionable row, evaluate the actionable domain exactly as current
main does and ignore passive rows. Only when actionable matches == 0 may passive observations participate.
Passive rows can never mint action tokens/authority.

usage: python3 passive_vectors.py          # runs the self-check, exits non-zero on any mismatch
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def evaluate(case: dict) -> dict:
    """Reference evaluator of the proposed rule. Returns {status, reason, may_mint_action_token}."""
    actionable = case["actionable_matches"]
    passive = case["passive_matches"]
    want = case["predicate"]                     # {"property": str, "equals": any} or {"exists": true/false}
    if actionable >= 1:
        # unchanged current-main semantics: the actionable domain decides; passive rows are ignored
        return {"status": case["actionable_status_on_main"], "reason": "actionable_domain",
                "may_mint_action_token": True}
    complete = case["actionable_walk_complete"] and case["passive_walk_complete"]
    if not passive:
        if want.get("exists") is False:
            return {"status": "satisfied" if complete else "unknown",
                    "reason": "absent_complete" if complete else "incomplete_walk",
                    "may_mint_action_token": False}
        return {"status": "unsatisfied" if complete else "unknown",
                "reason": "no_match" if complete else "incomplete_walk", "may_mint_action_token": False}
    if len(passive) > 1:
        return {"status": "unknown", "reason": "multi_match", "may_mint_action_token": False}
    row = passive[0]
    if not row["trusted"]:
        return {"status": "unknown", "reason": "untrusted_source", "may_mint_action_token": False}
    if "exists" in want:
        return {"status": "satisfied" if want["exists"] else "unsatisfied", "reason": "passive_exists",
                "may_mint_action_token": False}
    prop = want["property"]
    if prop not in row["properties"]:
        return {"status": "unknown", "reason": "unsupported_predicate", "may_mint_action_token": False}
    ok = row["properties"][prop] == want["equals"]
    return {"status": "satisfied" if ok else "unsatisfied", "reason": "passive_property", "may_mint_action_token": False}


def main() -> int:
    vectors = json.loads((HERE / "vectors.json").read_text())
    bad = 0
    for case in vectors["cases"]:
        got = evaluate(case["input"])
        want = case["expect"]
        if got != want:
            bad += 1
            print("MISMATCH", case["id"], "got", got, "want", want)
    tokens = [c["id"] for c in vectors["cases"] if c["expect"]["may_mint_action_token"] and c["input"]["actionable_matches"] == 0]
    if tokens:
        bad += 1
        print("passive-only case may mint an action token:", tokens)
    print(json.dumps({"cases": len(vectors["cases"]), "mismatches": bad}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

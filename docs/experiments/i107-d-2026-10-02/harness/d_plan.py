"""Lane-D schedule (kvnloo/cua#107 CMP-D, CMP-D-K2, dependency controls).

Pure data: which trials run, in which order, in which block. Each block is one
``quiet-timed`` invocation (EXCLUSIVE quiet-lane lock taken before the first
MCP session of the block opens). Arms: ``A`` = jev-use run.py without
``--guarded-completion``; ``D`` = run.py ``--guarded-completion`` (trycua/cua
PR 4316), both on A's full fresh semantic_v2 reads (B is BLOCKED).
"""

from __future__ import annotations

import secrets
from typing import Any

ARMS = ("A", "D")
PAIRS_PER_BLOCK = 10
# W-quiet / W-churn block order, counterbalanced (QCCQQC) over the 60 primary pairs.
CMPD_BLOCK_ORDER = ("W-quiet", "W-churn", "W-churn", "W-quiet", "W-quiet", "W-churn")
VARIANT = {"W-quiet": "quiet", "W-churn": "churn"}
REPS_PER_CONTROL = 5
K2_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # disjoint from K1 (lowercase hex, digits, "-")

# Dependency controls run in lane D (PREREG dependency_controls, arms incl. A and D).
# point: after_type = right after the first browser_type returns (before the step-2
# snapshot); before_click = after the step-2 snapshot and decision, immediately
# before the first browser_click is sent (the check-to-dispatch interval).
CONTROLS: dict[str, dict[str, Any]] = {
    "DC01": {"op": "set_value", "args": {"value": "changed-by-page"}, "point": "after_type"},
    "DC03": {"op": "insert_competing", "point": "after_type"},
    "DC04": {"op": "remove_submit", "point": "after_type"},
    "DC05a": {"op": "rerender_submit", "point": "after_type"},
    "DC05b": {"op": "replace_submit_watch", "point": "before_click"},
    "DC06": {"op": "relocate_decoy", "point": "after_type"},
    "DC07": {"op": "replace_document", "point": "before_click", "settle": "control_open"},
    "DC10": {"probe": "session_replacement", "point": "before_click"},
    "DC12": {"op": "hide_submit", "point": "after_type"},
    "DC13": {"op": "offscreen_submit", "point": "after_type"},
    "DC14a": {"op": "overlay_submit", "point": "after_type"},
    "DC14b": {"op": "overlay_submit", "point": "before_click"},
    "DC15": {"op": "blur_field", "point": "after_type"},
    "DC16a": {"op": "fieldset_disable", "point": "after_type"},
    "DC16b": {"op": "aria_disable", "point": "after_type"},
    "DC17a": {"op": "set_value", "args": {"value": ""}, "point": "after_type"},
    "DC17b": {"op": "before_name", "point": "after_type"},
    "DC20a": {"fault": {"mode": "ack_lost", "barrier": "applied"}},
    "DC20b": {"submit_delay_ms": 300},
}
for _c in CONTROLS.values():
    _c.setdefault("variant", "control")


def make_token(cohort: str) -> str:
    """K1: run.py's own default token form. K2: 64 uppercase ASCII letters (disjoint from K1 characters)."""
    if cohort == "K1":
        return f"jev-{secrets.token_hex(5)}"
    if cohort == "K2":
        return "".join(secrets.choice(K2_ALPHABET) for _ in range(64))
    raise ValueError(cohort)


def _pair(prefix: str, pair: int, order: tuple[str, str], **common: Any) -> list[dict[str, Any]]:
    o = "".join(order)
    return [{"pair": f"{prefix}-p{pair:03d}", "order": o, "arm": arm, **common} for arm in order]


def _name(block: str, idx: int, t: dict[str, Any]) -> str:
    tag = (t.get("control") or t["condition"].replace("W-", "")).lower()
    return f"{block}-{idx:03d}-{tag}-{t['arm']}"


def _block(plan: str, block: str, trials: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    for i, t in enumerate(trials):
        t["name"] = _name(block, i, t)
        t["block"] = block
    return {"plan": plan, "block": block, "trials": trials, **extra}


def _measured_blocks(plan: str, prefix: str, conditions: list[str], comparison: str, cohort: str,
                     names: list[str], start_pair: int = 0, **extra: Any) -> list[dict[str, Any]]:
    blocks, p = [], start_pair
    for block_name, cond in zip(names, conditions):
        trials: list[dict[str, Any]] = []
        for _ in range(PAIRS_PER_BLOCK):
            order = ("A", "D") if p % 2 == 0 else ("D", "A")
            trials += _pair(prefix, p, order, condition=cond, variant=VARIANT[cond], cohort=cohort,
                            comparison=comparison, kind="measured", control=None)
            p += 1
        blocks.append(_block(plan, block_name, trials, **extra))
    return blocks


def schedule() -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    # Smoke (excluded): one A/D pair on W-quiet; checks the session, Driver, trace sink and fixture.
    smoke = _pair("smoke", 0, ("A", "D"), condition="W-quiet", variant="quiet", cohort="K1",
                  comparison="CMP-D", kind="measured", control=None)
    for t in smoke:
        t["excluded"] = "smoke"
    blocks.append(_block("smoke", "smoke", smoke))
    # Shakedown (excluded from every analysis): harness and control-path check only.
    shake: list[dict[str, Any]] = []
    shake += _pair("shake", 0, ("A", "D"), condition="W-quiet", variant="quiet", cohort="K1",
                   comparison="CMP-D", kind="measured", control=None)
    shake += _pair("shake", 1, ("D", "A"), condition="W-churn", variant="churn", cohort="K1",
                   comparison="CMP-D", kind="measured", control=None)
    for i, cid in enumerate(("DC01", "DC06", "DC07", "DC20a")):
        shake += _pair("shake", 2 + i, ("A", "D") if i % 2 == 0 else ("D", "A"), condition="W-quiet",
                       variant="control", cohort="K1", comparison="controls", kind="control", control=cid)
    for t in shake:
        t["excluded"] = "shakedown"
    blocks.append(_block("shakedown", "shake", shake))
    # CMP-D, K1, W-quiet and W-churn: 6 blocks x 10 pairs (QCCQQC).
    blocks += _measured_blocks("cmpd", "cmpd", list(CMPD_BLOCK_ORDER), "CMP-D", "K1",
                               [f"cmpd-b{i + 1}" for i in range(6)])
    # Continuation (PREREG continuation_rule): exactly one more 30-pair block per INCONCLUSIVE condition.
    blocks += _measured_blocks("cmpd-continuation", "cmpdxq", ["W-quiet"] * 3, "CMP-D", "K1",
                               ["cmpd-xq1", "cmpd-xq2", "cmpd-xq3"], run_if="continuation_rule")
    blocks += _measured_blocks("cmpd-continuation", "cmpdxc", ["W-churn"] * 3, "CMP-D", "K1",
                               ["cmpd-xc1", "cmpd-xc2", "cmpd-xc3"], run_if="continuation_rule")
    # CMP-D-K2 (secondary, after K1): 3 blocks x 10 pairs, W-quiet.
    blocks += _measured_blocks("k2", "k2", ["W-quiet"] * 3, "CMP-D-K2", "K2", ["k2-b1", "k2-b2", "k2-b3"])
    # Controls: 19 controls x 5 reps x 2 arms, ABBA, controls rotated per rep, blocks of <= 10 pairs.
    pairs: list[list[dict[str, Any]]] = []
    ids = list(CONTROLS)
    p = 0
    for rep in range(REPS_PER_CONTROL):
        rot = ids[rep * 4 % len(ids):] + ids[:rep * 4 % len(ids)]
        for cid in rot:
            order = ("A", "D") if p % 2 == 0 else ("D", "A")
            pairs.append(_pair("ctl", p, order, condition="W-quiet", variant="control", cohort="K1",
                               comparison="controls", kind="control", control=cid, rep=rep))
            p += 1
    for i in range(0, len(pairs), PAIRS_PER_BLOCK):
        trials = [t for pr in pairs[i:i + PAIRS_PER_BLOCK] for t in pr]
        blocks.append(_block("controls", f"ctl-b{i // PAIRS_PER_BLOCK + 1:02d}", trials))
    return blocks


def block_by_name(name: str) -> dict[str, Any]:
    for b in schedule():
        if b["block"] == name:
            return b
    raise KeyError(name)

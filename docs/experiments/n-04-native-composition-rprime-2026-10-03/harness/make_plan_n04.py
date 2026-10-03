#!/usr/bin/env python3
"""N-04 plan (deterministic). Writes plan.json (measured + control blocks) or pilot.json.

usage: make_plan_n04.py measured plan.json | make_plan_n04.py pilot pilot.json

Every measured block is ONE ROUND, so the load rule (a round starts only at 1-minute loadavg <= 4.0)
and the 10-minute cap per lock acquisition can end a chunk between rounds.

* k=1 (``k1-rNN``, NN = 0..23): both tasks per round (first task alternating by round), the four arms
  BASE, X, X+V, X+V+HCL in the order of Williams row (r mod 4) of a 4x4 Williams square (first-order
  carry-over balanced; 6 squares = 24 rounds per task, so 24 pairs per contrast per task). One fresh
  Driver and one fresh fixture per trial.
* k=5 (``k5-rNN``, NN = 0..11): X+V and X+V+HCL sessions of 5 tasks per Driver session and fixture.
  Per task the arm order is AB/BA by round: (r + task index) even -> X+V first. The task index is the
  task's FIXED index (checkbox 0, text 1), never its position in the round, so the order alternates
  across rounds for each task (N-03's Part B confounded order with element type through the
  position). 12 sessions per arm per task.
* S0 supplement (``s0-rNN``, NN = 0..23): BASE vs S0 (KEEP-only: post-action sleep 0, default
  cursor), AB/BA by round per task with the same fixed-index rule. 24 pairs per task.
Controls (SHARED lock, <= 20 trials per block): default-off smoke on R'n and on R' (``smk-rn``,
``smk-rp``: arm D, 5 per task), V control (``vctl``: 5 X+V rows and 5 X rows, AB/BA), focus steal on
X+V+HCL (``dec1``, ``dec2``: 10 rows each, tasks alternating; 20 rows).
The plan asserts its own balance (see ``check_balance``).
"""

from __future__ import annotations

import json
import sys
from collections import Counter

TASKS = ["checkbox", "text"]
ARMS = ["BASE", "X", "X+V", "X+V+HCL"]
K5_ARMS = ("X+V", "X+V+HCL")
S0_ARMS = ("BASE", "S0")


def williams4() -> list[list[int]]:
    first = [0, 1, 3, 2]
    return [[(x + i) % 4 for x in first] for i in range(4)]


def trial(block: str, n: int, **kw) -> dict:
    return {"id": f"{block}-{n:03d}", "block": block, **kw}


def ordered_tasks(r: int) -> list[str]:
    return TASKS if r % 2 == 0 else TASKS[::-1]


def pair_order(r: int, task: str, arms: tuple[str, str]) -> list[str]:
    return list(arms) if (r + TASKS.index(task)) % 2 == 0 else list(arms)[::-1]


def k1_round(r: int) -> dict:
    rows = williams4()
    trials = []
    for task in ordered_tasks(r):
        for j in rows[r % 4]:
            trials.append(trial(f"k1-r{r:02d}", len(trials) + 1, kind="main", task=task, arm=ARMS[j], round=r, k=1))
    return {"block": f"k1-r{r:02d}", "kind": "main", "lock": "exclusive", "round": r, "trials": trials}


def k5_round(r: int) -> dict:
    trials = []
    for task in ordered_tasks(r):
        for arm in pair_order(r, task, K5_ARMS):
            trials.append(trial(f"k5-r{r:02d}", len(trials) + 1, kind="session", task=task, arm=arm, round=r, k=5))
    return {"block": f"k5-r{r:02d}", "kind": "session", "lock": "exclusive", "round": r, "trials": trials}


def s0_round(r: int) -> dict:
    trials = []
    for task in ordered_tasks(r):
        for arm in pair_order(r, task, S0_ARMS):
            trials.append(trial(f"s0-r{r:02d}", len(trials) + 1, kind="main", task=task, arm=arm, round=r, k=1))
    return {"block": f"s0-r{r:02d}", "kind": "main", "lock": "exclusive", "round": r, "trials": trials}


def controls() -> list[dict]:
    blocks = []
    for b in ("smk-rn", "smk-rp"):
        blocks.append({"block": b, "kind": "smoke", "lock": "shared",
                       "trials": [trial(b, k + 1, kind="smoke", task=TASKS[k % 2], arm="D", round=k // 2)
                                  for k in range(10)]})
    vctl = []
    for p in range(5):
        for arm in (("X+V", "X") if p % 2 == 0 else ("X", "X+V")):
            vctl.append(trial("vctl", len(vctl) + 1, kind="vctl", task="checkbox", arm=arm, round=p))
    blocks.append({"block": "vctl", "kind": "vctl", "lock": "shared", "trials": vctl})
    for b, rounds in (("dec1", range(0, 10)), ("dec2", range(10, 20))):
        blocks.append({"block": b, "kind": "decoy", "lock": "shared",
                       "trials": [trial(b, len(list(range(rounds.start, p))) + 1, kind="decoy", task=TASKS[p % 2],
                                        arm="X+V+HCL", round=p, variant_ms=100) for p in rounds]})
    return blocks


def check_balance(plan: dict) -> dict:
    """Assert the design: Williams positions per arm per task, AB/BA counts per task per pair block."""
    out: dict = {}
    k1 = [t for b in plan["blocks"] if b["block"].startswith("k1-") for t in b["trials"]]
    for task in TASKS:
        pos = Counter()
        for r in range(24):
            arms = [t["arm"] for t in k1 if t["task"] == task and t["round"] == r]
            assert sorted(arms) == sorted(ARMS), (task, r, arms)
            for i, a in enumerate(arms):
                pos[(a, i)] += 1
            for a, b in zip(arms, arms[1:]):
                pos[("after", a, b)] += 1
        assert all(pos[(a, i)] == 6 for a in ARMS for i in range(4)), pos
        assert all(pos[("after", a, b)] == 6 for a in ARMS for b in ARMS if a != b), pos
        out[f"k1/{task}"] = "each arm 6x in each position; each ordered neighbour pair 6x"
    for prefix, arms, n in (("k5-", K5_ARMS, 12), ("s0-", S0_ARMS, 24)):
        rows = [t for b in plan["blocks"] if b["block"].startswith(prefix) for t in b["trials"]]
        for task in TASKS:
            first = Counter()
            for r in range(n):
                seq = [t["arm"] for t in rows if t["task"] == task and t["round"] == r]
                assert sorted(seq) == sorted(arms), (prefix, task, r, seq)
                first[seq[0]] += 1
            assert first[arms[0]] == first[arms[1]] == n // 2, (prefix, task, first)
            out[f"{prefix}/{task}"] = f"{arms[0]} first {first[arms[0]]}/{n}, {arms[1]} first {first[arms[1]]}/{n}"
    return out


def measured() -> dict:
    blocks = [k1_round(r) for r in range(24)] + [k5_round(r) for r in range(12)] + [s0_round(r) for r in range(24)]
    blocks += controls()
    plan = {"schema": "n04.plan.v1", "arms": ARMS, "tasks": TASKS, "k5_arms": list(K5_ARMS),
            "s0_arms": list(S0_ARMS), "williams4": williams4(), "blocks": blocks}
    plan["balance"] = check_balance(plan)
    return plan


def pilot() -> dict:
    a = []
    for task in TASKS:
        for arm in ARMS + ["S0"]:
            a.append(trial("pil", len(a) + 1, kind="main", task=task, arm=arm, round=0, k=1))
    a.append(trial("pil", len(a) + 1, kind="session", task="text", arm="X+V+HCL", round=0, k=5))
    a.append(trial("pil", len(a) + 1, kind="vctl", task="checkbox", arm="X+V", round=0))
    a.append(trial("pil", len(a) + 1, kind="smoke", task="checkbox", arm="D", round=0))
    a.append(trial("pil", len(a) + 1, kind="decoy", task="checkbox", arm="X+V+HCL", round=0, variant_ms=100))
    # the decoy window exists only in a block of kind "decoy" (N-03 harness), as in the measured dec1/dec2
    d = [trial("pil2", k + 1, kind="decoy", task=TASKS[k % 2], arm="X+V+HCL", round=k, variant_ms=100) for k in range(2)]
    return {"schema": "n04.pilot-plan.v1", "excluded": True,
            "blocks": [{"block": "pil", "kind": "pilot", "lock": "shared", "round": 0, "trials": a},
                       {"block": "pil2", "kind": "decoy", "lock": "shared", "round": 0, "trials": d}]}


def main() -> None:
    which, out = sys.argv[1], sys.argv[2]
    plan = measured() if which == "measured" else pilot()
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Write the N-02 trial plan (deterministic; stdlib only).

usage: make_plan.py measured|pilot <out.json>

Measured plan (pre-registered in PREREG.json):
* d01: default-off smoke, 4 trials, arm D (no CUA_DRIVER_EXP_* at all), shared lock.
* e01, e02: two EXCLUSIVE acquisitions (quiet-timed), 12 rounds each (24 rounds).
  Each round runs both tasks, the first task alternating by round; each task runs
  its 4 arms in Williams row (round mod 4) of the 4x4 Williams square:
  checkbox S0, S0+HC, S0+CL, S0+HC+CL; text X, X+HC, X+CL, X+HC+CL.
  n = 24 per arm per task (192 trials), paired within the round. Rounds 0 and 1
  also keep a full-result corpus for the offline HC equivalence control.
  Phase 1 attribution uses the S0 (checkbox) and X (text) cells of these rounds.
* c01..c12: CL safety controls, shared lock, 20 trials per block: per task, all 4
  arms x {decoy 100 ms, edge 205-215 ms, no steal} x 10, arms in Williams order.
"""

from __future__ import annotations

import json
import sys

ARMS = {"checkbox": ["S0", "S0+HC", "S0+CL", "S0+HC+CL"], "text": ["X", "X+HC", "X+CL", "X+HC+CL"]}
TASKS = ["checkbox", "text"]
ROUNDS = 24
EDGE_MS = [round(205 + i * 10 / 9, 1) for i in range(10)]


def williams(n: int) -> list[list[int]]:
    """Williams square for even n: first row 0,1,n-1,2,n-2,...; row i = row0 + i mod n."""
    first = [0]
    lo, hi = 1, n - 1
    take_lo = True
    while len(first) < n:
        if take_lo:
            first.append(lo)
            lo += 1
        else:
            first.append(hi)
            hi -= 1
        take_lo = not take_lo
    return [[(x + i) % n for x in first] for i in range(n)]


SQUARE = williams(4)


def trial(block: str, k: int, **fields) -> dict:
    return {"id": f"{block}-{k:03d}", "block": block, **fields}


def measured() -> list[dict]:
    blocks = []
    smoke = [trial("d01", k + 1, kind="smoke", task=task, arm="D", round=None)
             for k, task in enumerate(["checkbox", "text", "checkbox", "text"])]
    blocks.append({"block": "d01", "kind": "smoke", "lock": "shared", "trials": smoke})
    for e in range(2):
        name = f"e{e + 1:02d}"
        trials = []
        for r in range(e * 12, (e + 1) * 12):
            order = TASKS if r % 2 == 0 else TASKS[::-1]
            for task in order:
                for a in SQUARE[r % 4]:
                    trials.append(trial(name, len(trials) + 1, kind="main", task=task, arm=ARMS[task][a],
                                        round=r, corpus=r < 2))
        blocks.append({"block": name, "kind": "main", "lock": "exclusive", "trials": trials})
    n = 0
    for kind in ("decoy", "edge", "nosteal"):
        for task in TASKS:
            for half in range(2):
                n += 1
                name = f"c{n:02d}"
                trials = []
                for p in range(5):
                    rep = half * 5 + p
                    for a in SQUARE[rep % 4]:
                        variant = {"decoy": 100, "edge": EDGE_MS[rep], "nosteal": None}[kind]
                        trials.append(trial(name, len(trials) + 1, kind=kind, task=task, arm=ARMS[task][a],
                                            variant_ms=variant, round=rep))
                blocks.append({"block": name, "kind": kind, "lock": "shared", "trials": trials})
    return blocks


def pilot() -> list[dict]:
    main = [trial("p01", k + 1, kind="main", task=task, arm=ARMS[task][a], round=0, corpus=True)
            for k, (task, a) in enumerate([(t, a) for t in TASKS for a in SQUARE[0]])]
    edge = [trial("p02", k + 1, kind="edge", task=task, arm=arm, variant_ms=210.0, round=0)
            for k, (task, arm) in enumerate([("checkbox", "S0"), ("checkbox", "S0+CL"),
                                             ("text", "X"), ("text", "X+CL")])]
    nos = [trial("p03", k + 1, kind="nosteal", task=task, arm=arm, variant_ms=None, round=0)
           for k, (task, arm) in enumerate([("checkbox", "S0+CL"), ("text", "X+CL")])]
    return [
        {"block": "p01", "kind": "main", "lock": "shared", "trials": main},
        {"block": "p02", "kind": "edge", "lock": "shared", "trials": edge},
        {"block": "p03", "kind": "nosteal", "lock": "shared", "trials": nos},
    ]


def main() -> None:
    which, out = sys.argv[1], sys.argv[2]
    blocks = measured() if which == "measured" else pilot()
    plan = {"schema": "n02.plan.v1", "which": which, "arms": ARMS, "tasks": TASKS,
            "williams": SQUARE, "edge_ms": EDGE_MS, "blocks": blocks}
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

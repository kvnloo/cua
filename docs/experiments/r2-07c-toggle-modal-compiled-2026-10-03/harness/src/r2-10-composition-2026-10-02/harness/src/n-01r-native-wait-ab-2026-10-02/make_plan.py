#!/usr/bin/env python3
"""Write the N-01R trial plan (deterministic; stdlib only).

usage: make_plan.py measured|pilot <out.json>

Measured plan (pre-registered in PREREG.json):
* d01: default-off smoke, 5 trials, arm B (knobs unset).
* e01..e04: four exclusive acquisitions, each = 5 main rounds + 1 warm block + 1
  observation block (one isolated session each).
* m01..m20 (sub-blocks): one round each. Each round runs both tasks; the task that goes
  first alternates by round; each task runs the 6 arms in Williams row
  (round mod 6) of the 6x6 Williams square. n = 20 per arm per task, paired
  within the round.
* w01..w04 (supplementary H_C warm-cursor checkbox): 20 rounds of {B, C},
  AB/BA alternating by round, 10 trials per block.
* o01..o04 (supplementary observation modality inside the composed arm): 20
  rounds per task of {X2, X2o}, X2o = X2 with an accessibility-only task
  observation; AB/BA alternating; 20 trials per block.
* a01..a08 decoy focus steal (B vs F0; 100 ms and 20 ms; both tasks; 10 per
  arm per variant per task; AB/BA pairs), l01..l08 late effect (B vs S0; 30 ms
  and 80 ms; both tasks; same layout), s01..s03 stale token after fixture
  restart (5 per arm, 6 arms). Control blocks hold at most 10 trials.
"""

from __future__ import annotations

import json
import sys

ARMS = ["B", "C", "S0", "F0", "X", "X2"]
TASKS = ["checkbox", "text"]
ROUNDS = 20


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


def trial(block: str, k: int, **fields) -> dict:
    return {"id": f"{block}-{k:02d}", "block": block, **fields}


def measured() -> list[dict]:
    blocks = []
    smoke = [trial("d01", k + 1, kind="smoke", task=task, arm="B", round=None)
             for k, task in enumerate(["checkbox", "text", "checkbox", "text", "checkbox"])]
    blocks.append({"block": "d01", "kind": "smoke", "lock": "shared", "trials": smoke})
    square = williams(len(ARMS))
    main_blocks = []
    for r in range(ROUNDS):
        name = f"m{r + 1:02d}"
        order = TASKS if r % 2 == 0 else TASKS[::-1]
        trials = []
        for task in order:
            for a in square[r % len(ARMS)]:
                trials.append(trial(name, len(trials) + 1, kind="main", task=task, arm=ARMS[a], round=r))
        main_blocks.append({"block": name, "kind": "main", "lock": "exclusive", "trials": trials})
    warm_blocks = []
    for b in range(4):
        name = f"w{b + 1:02d}"
        trials = []
        for r in range(b * 5, b * 5 + 5):
            pair = ["B", "C"] if r % 2 == 0 else ["C", "B"]
            for arm in pair:
                trials.append(trial(name, len(trials) + 1, kind="warm", task="checkbox", arm=arm, round=r))
        warm_blocks.append({"block": name, "kind": "warm", "lock": "exclusive", "trials": trials})
    obs_blocks = []
    for b in range(4):
        name = f"o{b + 1:02d}"
        trials = []
        for r in range(b * 5, b * 5 + 5):
            for task in (TASKS if r % 2 == 0 else TASKS[::-1]):
                pair = ["X2", "X2o"] if (r + (task == "text")) % 2 == 0 else ["X2o", "X2"]
                for arm in pair:
                    trials.append(trial(name, len(trials) + 1, kind="obs", task=task, arm=arm, round=r))
        obs_blocks.append({"block": name, "kind": "obs", "lock": "exclusive", "trials": trials})
    # Four EXCLUSIVE acquisitions (one isolated session each): 5 main rounds, then one warm
    # block and one observation block. Trial ids keep their sub-block names (m01-01, ...).
    for e in range(4):
        trials = [t for mb in main_blocks[e * 5:(e + 1) * 5] for t in mb["trials"]]
        trials += warm_blocks[e]["trials"] + obs_blocks[e]["trials"]
        blocks.append({"block": f"e{e + 1:02d}", "kind": "measured", "lock": "exclusive", "trials": trials})
    controls = []

    def control(prefix: str, kind: str, arms: list[str], variants: list[int]) -> list[dict]:
        out = []
        cells = [(task, v) for v in variants for task in TASKS]
        n = 0
        for half in range(2):
            for task, v in cells:
                n += 1
                name = f"{prefix}{n:02d}"
                trials = []
                for p in range(5):
                    pair = arms if (p + half) % 2 == 0 else arms[::-1]
                    for arm in pair:
                        trials.append(trial(name, len(trials) + 1, kind=kind, task=task, arm=arm,
                                            variant_ms=v, round=half * 5 + p))
                out.append({"block": name, "kind": kind, "lock": "shared", "trials": trials})
        return out

    decoy = control("a", "decoy", ["B", "F0"], [100, 20])
    late = control("l", "late", ["B", "S0"], [30, 80])
    stale = []
    order = [a for _ in range(5) for a in ARMS]
    for b in range(3):
        name = f"s{b + 1:02d}"
        stale.append({"block": name, "kind": "stale", "lock": "shared",
                      "trials": [trial(name, k + 1, kind="stale", task="checkbox", arm=arm, round=None)
                                 for k, arm in enumerate(order[b * 10:(b + 1) * 10])]})
    for i in range(8):
        controls.append(decoy[i])
        controls.append(late[i])
        if i in (2, 5, 7):
            controls.append(stale[[2, 5, 7].index(i)])
    blocks.extend(controls)
    return blocks


def pilot() -> list[dict]:
    square = williams(len(ARMS))
    trials = [trial("p01", k + 1, kind="main", task=task, arm=ARMS[a], round=0)
              for k, (task, a) in enumerate([(t, a) for t in TASKS for a in square[0]])]
    return [
        {"block": "p01", "kind": "main", "lock": "exclusive", "trials": trials},
        {"block": "p02", "kind": "warm", "lock": "exclusive",
         "trials": [trial("p02", 1, kind="warm", task="checkbox", arm="B", round=0),
                    trial("p02", 2, kind="warm", task="checkbox", arm="C", round=0)]},
        {"block": "p03", "kind": "decoy", "lock": "shared",
         "trials": [trial("p03", k + 1, kind="decoy", task=task, arm=arm, variant_ms=100, round=0)
                    for k, (task, arm) in enumerate([("checkbox", "B"), ("checkbox", "F0"),
                                                     ("text", "B"), ("text", "F0")])]},
        {"block": "p04", "kind": "late", "lock": "shared",
         "trials": [trial("p04", k + 1, kind="late", task=task, arm=arm, variant_ms=80, round=0)
                    for k, (task, arm) in enumerate([("checkbox", "B"), ("checkbox", "S0"),
                                                     ("text", "B"), ("text", "S0")])]},
        {"block": "p06", "kind": "obs", "lock": "shared",
         "trials": [trial("p06", k + 1, kind="obs", task=task, arm=arm, round=0)
                    for k, (task, arm) in enumerate([("checkbox", "X2"), ("checkbox", "X2o"),
                                                     ("text", "X2o"), ("text", "X2")])]},
        {"block": "p05", "kind": "stale", "lock": "shared",
         "trials": [trial("p05", 1, kind="stale", task="checkbox", arm="B", round=None),
                    trial("p05", 2, kind="stale", task="checkbox", arm="X2", round=None)]},
    ]


def main() -> None:
    which, out = sys.argv[1], sys.argv[2]
    blocks = measured() if which == "measured" else pilot()
    plan = {"schema": "n01r.plan.v1", "which": which, "arms": ARMS, "tasks": TASKS,
            "williams": williams(len(ARMS)), "blocks": blocks}
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

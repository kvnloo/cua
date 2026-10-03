#!/usr/bin/env python3
"""N-03 plan (deterministic): writes plan.json (measured + control blocks) or pilot.json.

usage: make_plan.py measured plan.json | make_plan.py pilot pilot.json

Part A arms X, X+HCL, X+V, X+HCL+V in a 4x4 Williams square (first-order carry-over
balanced). k=1: 24 rounds per task, both tasks each round (first task alternating), arms in
row (round mod 4); two EXCLUSIVE blocks of 12 rounds (96 trials each). k=5: 12 rounds per task,
one session of 5 tasks per cell; two EXCLUSIVE blocks of 6 rounds (48 sessions each).
Part B: 20 AB/BA pairs per element type (check box, button), B = default 50 ms sleep, S0 =
sleep knob 0; one EXCLUSIVE block of 80 trials; family U (BU / S0U: the same with the
foreground window-change observation off) in a second EXCLUSIVE block of 80. Controls run
under the SHARED lock in blocks of at most 20 trials.
"""

from __future__ import annotations

import json
import sys

TASKS = ["checkbox", "text"]
ARMS = ["X", "X+HCL", "X+V", "X+HCL+V"]
ELEMENTS = ["checkbox", "button"]


def williams4() -> list[list[int]]:
    first = [0, 1, 3, 2]
    return [[(x + i) % 4 for x in first] for i in range(4)]


def trial(block: str, n: int, **kw) -> dict:
    return {"id": f"{block}-{n:03d}", "block": block, **kw}


def part_a_k1(name: str, rounds: range) -> dict:
    rows = williams4()
    trials = []
    for r in rounds:
        for task in (TASKS if r % 2 == 0 else TASKS[::-1]):
            for j in rows[r % 4]:
                trials.append(trial(name, len(trials) + 1, kind="main", task=task, arm=ARMS[j], round=r, k=1))
    return {"block": name, "kind": "main", "lock": "exclusive", "trials": trials}


def part_a_k5(name: str, rounds: range) -> dict:
    rows = williams4()
    trials = []
    for r in rounds:
        for task in (TASKS if r % 2 == 0 else TASKS[::-1]):
            for j in rows[(r + 1) % 4]:
                trials.append(trial(name, len(trials) + 1, kind="session", task=task, arm=ARMS[j], round=r, k=5))
    return {"block": name, "kind": "session", "lock": "exclusive", "trials": trials}


def part_b(name: str, rounds: range, kind: str = "axfg", lock: str = "exclusive", arms=("B", "S0"),
           variant_ms: int | None = None) -> dict:
    trials = []
    for r in rounds:
        for ei, element in enumerate(ELEMENTS if r % 2 == 0 else ELEMENTS[::-1]):
            order = list(arms) if (r + ei) % 2 == 0 else list(arms)[::-1]
            for arm in order:
                t = trial(name, len(trials) + 1, kind=kind, task=element, arm=arm, round=r)
                if variant_ms is not None:
                    t["variant_ms"] = variant_ms
                trials.append(t)
    return {"block": name, "kind": kind, "lock": lock, "trials": trials}


def decoy(name: str, rounds: range) -> dict:
    rows = williams4()
    trials = []
    for p in rounds:
        task = TASKS[p % 2]
        for j in rows[p % 4]:
            trials.append(trial(name, len(trials) + 1, kind="decoy", task=task, arm=ARMS[j], round=p,
                                variant_ms=100))
    return {"block": name, "kind": "decoy", "lock": "shared", "trials": trials}


def measured() -> dict:
    blocks = [
        part_a_k1("a1", range(0, 12)),
        part_a_k5("k1", range(0, 6)),
        part_b("b1", range(0, 20)),
        part_a_k1("a2", range(12, 24)),
        part_a_k5("k2", range(6, 12)),
        # Part B family U (supplementary): the same pairs with the foreground post-check's
        # window-change observation off in both arms.
        part_b("bu1", range(0, 20), arms=("BU", "S0U")),
    ]
    # Controls (SHARED lock, <= 20 trials each).
    # Focus steal ~100 ms after the app's state change: 5 per task per arm (40). Each control
    # block holds 5 rounds x 4 arms of one task pattern: rounds 0-4 (task alternating) and 5-9.
    blocks.append(decoy("cd1", range(0, 5)))
    blocks.append(decoy("cd2", range(5, 10)))
    vctl = []
    for p in range(5):
        for arm in (("X+V", "X") if p % 2 == 0 else ("X", "X+V")):
            vctl.append(trial("cv1", len(vctl) + 1, kind="vctl", task="checkbox", arm=arm, round=p))
    blocks.append({"block": "cv1", "kind": "vctl", "lock": "shared", "trials": vctl})
    for b in ("csn3", "csr"):
        blocks.append({"block": b, "kind": "smoke", "lock": "shared",
                       "trials": [trial(b, k + 1, kind="smoke", task=TASKS[k % 2], arm="D", round=k // 2)
                                  for k in range(10)]})
    # Positive control (injected 30 ms app-side delay): S0U must show "not visible at return";
    # BU (50 ms sleep) and S0 at default config (800 ms window-change observation) are its
    # contrasts.
    blocks.append(part_b("bd1", range(0, 5), kind="axfg_delay", lock="shared", arms=("S0U", "BU"), variant_ms=30))
    blocks.append(part_b("bd2", range(0, 5), kind="axfg_delay", lock="shared", arms=("S0",), variant_ms=30))
    blocks.append({"block": "bs1", "kind": "axfg_smoke", "lock": "shared",
                   "trials": [trial("bs1", k + 1, kind="axfg_smoke", task="checkbox", arm="B", round=k)
                              for k in range(2)]})
    return {"schema": "n03.plan.v1", "arms": ARMS, "tasks": TASKS, "elements": ELEMENTS,
            "williams4": williams4(), "blocks": blocks}


def pilot() -> dict:
    a = []
    for task in TASKS:
        for arm in ARMS:
            a.append(trial("ap1", len(a) + 1, kind="main", task=task, arm=arm, round=0, k=1))
    a.append(trial("ap1", len(a) + 1, kind="session", task="text", arm="X+HCL", round=0, k=5))
    a.append(trial("ap1", len(a) + 1, kind="vctl", task="checkbox", arm="X+V", round=0))
    a.append(trial("ap1", len(a) + 1, kind="vctl", task="checkbox", arm="X", round=0))
    a.append(trial("ap1", len(a) + 1, kind="smoke", task="checkbox", arm="D", round=0))
    blocks = [{"block": "ap1", "kind": "pilot", "lock": "shared", "trials": a},
              {"block": "ap2", "kind": "decoy", "lock": "shared",
               "trials": [trial("ap2", 1, kind="decoy", task="checkbox", arm="X", round=0, variant_ms=100),
                          trial("ap2", 2, kind="decoy", task="text", arm="X+HCL+V", round=0, variant_ms=100)]}]
    blocks.append(part_b("bp1", range(0, 2), kind="axfg", lock="shared"))
    blocks.append(part_b("bp2", range(0, 1), kind="axfg_delay", lock="shared", arms=("S0U", "BU"), variant_ms=30))
    blocks.append(part_b("bp4", range(0, 1), kind="axfg", lock="shared", arms=("BU", "S0U")))
    blocks.append(part_b("bp5", range(0, 1), kind="axfg_delay", lock="shared", arms=("S0",), variant_ms=30))
    blocks.append({"block": "bp3", "kind": "axfg_smoke", "lock": "shared",
                   "trials": [trial("bp3", 1, kind="axfg_smoke", task="checkbox", arm="B", round=0)]})
    return {"schema": "n03.pilot-plan.v1", "excluded": True, "blocks": blocks}


def main() -> None:
    which, out = sys.argv[1], sys.argv[2]
    plan = measured() if which == "measured" else pilot()
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

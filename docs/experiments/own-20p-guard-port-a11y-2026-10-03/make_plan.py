#!/usr/bin/env python3
"""Write the OWN-20P trial plan (deterministic; stdlib only).

usage: make_plan.py measured|pilot <out.json>

The harness (harness/, blob-identical to OWN-20G ce7544cc0) runs two binaries per block,
named "U" and "G" in each trial's ``bin``. Each block names the binary roles behind them
in ``bins``; every trial also carries its role as ``binary``. Every pair is AB/BA: pair k
runs (U, G) when k is even and (G, U) when k is odd. At most 10 trials per block (one
shared quiet-lane acquisition each).

Roles: U0 = clean upstream main cb685fad7; G0 = U0 + the guard port; U0m / G0m = U0 / G0
+ OWN-20G's three measurement-only picks (default off; the R1 harness keys its stall and
steal on their ``do_action_replied`` mark); GA = G0 + the AT-SPI reconnect fix.

* R1 (gated, c08-017 reproduction): ``replystall`` U0m vs G0m, checkbox arm S0 and text
  arm X, 20 per binary per task (blocks q1-q8). Control ``replyonly`` (proxy on, no hold,
  no steal) 5 per binary per task (qc1, qc2).
* Normal path (gated): ``nosteal`` U0 vs G0, arm D (no CUA_DRIVER_EXP_* at all: product
  defaults), 20 per binary per task (n1-n8). Attribution only: ``nosteal`` U0m vs G0m on
  the R1 arms, 10 per binary per task (m1-m4), for the settle length from the marks.
* R3 (gated): bus restart G0 vs GA, ``bus`` 20 per binary (r3a-r3d); controls
  ``registry``, ``noop``, ``noop_direct`` (discriminating) and ``bus_direct``, 5 per binary
  each (r3e-r3h).
"""

from __future__ import annotations

import json
import sys

TASK_ARM = {"checkbox": "S0", "text": "X"}
SIZE = 10


def pairs(a: dict, b: dict, k: int) -> list[dict]:
    return [a, b] if k % 2 == 0 else [b, a]


def pair(kind: str, k: int, bins: dict[str, str], **fields) -> list[dict]:
    a = {"kind": kind, "bin": "U", "binary": bins["U"], "pair": k, **fields}
    b = {"kind": kind, "bin": "G", "binary": bins["G"], "pair": k, **fields}
    return pairs(a, b, k)


def blocks_of(prefix: str, kind: str, trials: list[dict], bins: dict[str, str], row: str,
              harness: str | None = None) -> list[dict]:
    out = []
    for i in range(0, len(trials), SIZE):
        name = f"{prefix}{i // SIZE + 1}"
        part = [{"id": f"{name}-{j + 1:03d}", "block": name, "row": row, **t}
                for j, t in enumerate(trials[i:i + SIZE])]
        block = {"block": name, "kind": kind, "lock": "shared", "bins": bins, "row": row, "trials": part}
        if harness:
            block["harness"] = harness
        out.append(block)
    return out


def focus_trials(kind: str, n_pairs: int, bins: dict[str, str], arm_of: dict[str, str]) -> list[dict]:
    trials: list[dict] = []
    for task in ("checkbox", "text"):
        for k in range(n_pairs):
            trials += pair(kind, k, bins, task=task, arm=arm_of[task])
    return trials


def measured() -> list[dict]:
    marked = {"U": "U0m", "G": "G0m"}
    product = {"U": "U0", "G": "G0"}
    r3bins = {"U": "G0", "G": "GA"}
    blocks: list[dict] = []
    blocks += blocks_of("q", "replystall", focus_trials("replystall", 20, marked, TASK_ARM), marked, "R1")
    blocks += blocks_of("qc", "replyonly", focus_trials("replyonly", 5, marked, TASK_ARM), marked, "R1_control")
    blocks += blocks_of("n", "nosteal", focus_trials("nosteal", 20, product, {"checkbox": "D", "text": "D"}),
                        product, "normal")
    blocks += blocks_of("m", "nosteal", focus_trials("nosteal", 10, marked, TASK_ARM), marked, "normal_marked")
    bus: list[dict] = []
    for k in range(20):
        bus += pair("r3", k, r3bins, variant="bus")
    letters = "abcdefgh"
    r3 = blocks_of("r3", "r3", bus, r3bins, "R3", harness="r3_harness.py")
    ctl: list[dict] = []
    for k in range(20):
        ctl += pair("r3", k, r3bins, variant=("registry", "noop", "noop_direct", "bus_direct")[k // 5])
    r3 += blocks_of("r3c", "r3", ctl, r3bins, "R3_control", harness="r3_harness.py")
    for i, b in enumerate(r3):  # r3a-r3d (bus), r3e-r3h (controls)
        old = b["block"]
        b["block"] = f"r3{letters[i]}"
        for t in b["trials"]:
            t["block"] = b["block"]
            t["id"] = t["id"].replace(f"{old}-", f"{b['block']}-", 1)
    blocks += r3
    return blocks


def pilot() -> list[dict]:
    marked = {"U": "U0m", "G": "G0m"}
    product = {"U": "U0", "G": "G0"}
    r3bins = {"U": "G0", "G": "GA"}
    out = blocks_of("pq", "replystall", pair("replystall", 0, marked, task="checkbox", arm="S0"), marked, "pilot")
    out += blocks_of("pn", "nosteal", pair("nosteal", 0, product, task="checkbox", arm="D"), product, "pilot")
    out += blocks_of("pr", "r3", pair("r3", 0, r3bins, variant="bus"), r3bins, "pilot", harness="r3_harness.py")
    for b in out:
        b["block"] = b["block"].rstrip("1")
        for t in b["trials"]:
            t["block"] = b["block"]
            t["id"] = t["id"].replace(f"{b['block']}1-", f"{b['block']}-", 1)
    return out


def main() -> None:
    which, out = sys.argv[1], sys.argv[2]
    blocks = measured() if which == "measured" else pilot()
    names = [b["block"] for b in blocks]
    assert len(names) == len(set(names)), names
    assert all(len(b["trials"]) <= SIZE for b in blocks)
    plan = {"schema": "own20p.plan.v1", "which": which, "task_arm": TASK_ARM, "max_trials_per_block": SIZE,
            "roles": {"U0": "upstream main cb685fad7 (clean)", "G0": "U0 + guard port",
                      "U0m": "U0 + OWN-20G measurement picks", "G0m": "G0 + OWN-20G measurement picks",
                      "GA": "G0 + AT-SPI reconnect fix"},
            "blocks": blocks}
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

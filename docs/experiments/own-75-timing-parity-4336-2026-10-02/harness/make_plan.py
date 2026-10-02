#!/usr/bin/env python3
"""Write the pre-registered OWN-75 REAL trial plan (deterministic; stdlib only).

usage: make_plan.py <out-dir> [--pilot]

Measured plan: for repetition i in 0..19 and each cell (runner, task) in CELLS, one pair of trials
(head, m0); the pair order is head->m0 (AB) when i is even and m0->head (BA) when i is odd, so
every cell has 10 AB and 10 BA pairs. 160 trials in 16 blocks of 10 (one quiet-lane lock
acquisition and one private X11 session per block). The pilot plan is 4 trials, excluded from
results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CELLS = [
    ("python", "gtk3-choose-size"),
    ("typescript", "gtk3-choose-size"),
    ("python", "gtk3-save-note"),
    ("typescript", "gtk3-save-note"),
]
REPS = 20
BLOCK = 10


def measured() -> list[dict]:
    trials = []
    for i in range(REPS):
        order = ["head", "m0"] if i % 2 == 0 else ["m0", "head"]
        for runner, task in CELLS:
            for position, arm in enumerate(order):
                trials.append({
                    "trial_id": f"t{len(trials) + 1:03d}-{arm}-{runner[:2]}-{task.split('-', 1)[1]}",
                    "rep": i, "arm": arm, "runner": runner, "task": task,
                    "pair": f"{runner}:{task}:{i}", "pair_order": "AB" if i % 2 == 0 else "BA",
                    "pair_position": position,
                })
    return trials


def pilot() -> list[dict]:
    rows = [("head", "python", "gtk3-choose-size"), ("m0", "typescript", "gtk3-choose-size"),
            ("m0", "python", "gtk3-save-note"), ("head", "typescript", "gtk3-save-note")]
    return [{"trial_id": f"p{n + 1:02d}-{arm}-{runner[:2]}-{task.split('-', 1)[1]}", "rep": -1, "arm": arm,
             "runner": runner, "task": task, "pair": None, "pair_order": None, "pair_position": None}
            for n, (arm, runner, task) in enumerate(rows)]


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=False)
    trials = pilot() if "--pilot" in sys.argv else measured()
    for start in range(0, len(trials), BLOCK):
        name = f"block-{'p' if '--pilot' in sys.argv else 'm'}{start // BLOCK + 1:02d}.json"
        (out / name).write_text(json.dumps(trials[start:start + BLOCK], indent=1) + "\n")
    print(json.dumps({"trials": len(trials), "blocks": (len(trials) + BLOCK - 1) // BLOCK}))


if __name__ == "__main__":
    main()

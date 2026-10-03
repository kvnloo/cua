#!/usr/bin/env python3
"""OWN-20Q: the r3_carry supplement plan (plan-supp.json), committed before it runs.

In the counted r3_carry blocks the blob-identical r3_harness.py signalled the bus daemon in 14 of 20
trials: in r2-004 it did not see the new launcher's daemon within its 5 s wait, and in r2-005..010 it
found no daemon under that launcher and skipped the kill (OWN-20P deviation 2, same harness). Those
trials stay counted under the pre-registered rule. This supplement (one block, 10 GQ trials, same
harness and variant) only enters the post-hoc restart-happened view, never the gate cell.
"""

import json
from pathlib import Path

from make_plan import R3, blocks_for

plan = {"schema": "own20q.plan.v1", "supplement": True,
        "blocks": blocks_for("rs", "r3_carry_supp", "bus", {"U": "GQ", "G": "GQ"}, 5, 5, R3, {"variant": "bus"},
                             single="G")}
path = Path(__file__).resolve().parent / "plan-supp.json"
path.write_text(json.dumps(plan, indent=1, sort_keys=True) + "\n", encoding="utf-8")
print(path.name, sum(len(b["trials"]) for b in plan["blocks"]), "trials")

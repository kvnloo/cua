#!/usr/bin/env python3
"""Write the OWN-20P R3 supplement plan (deterministic; stdlib only). Committed before it runs.

usage: make_plan_supp.py <out.json>

Why: in the counted R3 block r3b, trial r3b-009 (GA) killed the a11y bus daemon but the harness
did not see the new launcher's daemon within its 5 s wait; the next trial, r3b-010 (G0), found no
daemon under that launcher and skipped the kill ("not this session's process"), so no restart
happened in r3b-010 and fixture A stayed on the old bus (truthful re-observation). Both trials stay
counted under the pre-registered rule. This supplement adds 5 bus pairs (G0 vs GA, AB/BA, one
shared acquisition, block r3s) so that each binary has >= 20 trials in which the daemon kill
actually happened. The supplement never enters the pre-registered gate cells; it is reported in
the post-hoc "restart happened" view (a daemon pid was signalled in the trial).
"""

from __future__ import annotations

import json
import sys

from make_plan import pair


def main() -> None:
    bins = {"U": "G0", "G": "GA"}
    trials = []
    for k in range(5):
        trials += pair("r3", k, bins, variant="bus")
    block = {"block": "r3s", "kind": "r3", "lock": "shared", "bins": bins, "row": "R3_supp",
             "harness": "r3_harness.py",
             "trials": [{"id": f"r3s-{j + 1:03d}", "block": "r3s", "row": "R3_supp", **t}
                        for j, t in enumerate(trials)]}
    plan = {"schema": "own20p.plan.v1", "which": "supplement", "blocks": [block]}
    with open(sys.argv[1], "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

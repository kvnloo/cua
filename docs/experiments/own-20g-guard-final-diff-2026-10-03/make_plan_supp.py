#!/usr/bin/env python3
"""OWN-20G R2 supplementary pairs (PREREG R2_cl.counts: "edge/d100: if < 20 valid per arm per
task, up to 10 supplementary pairs with the same delays"). Deterministic; stdlib only.

usage: make_plan_supp.py <out.json>

After the planned R2 blocks, two groups had fewer than 20 valid steals in an arm:
checkbox edge (S0+CL 18/21 valid) and text d100 (X+CL 19/20 valid). Each gets 10 supplementary
AB/BA pairs (G vs G+CL), continuing the plan's pair numbering and delay sequence:
* ecs: checkbox edge, pairs k = 21..30, delay 205 + (k mod 11) ms;
* dts: text d100, pairs k = 20..29, delay 100 ms.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
from make_plan import EDGE_MS, chunk, focus_pair  # noqa: E402


def main() -> None:
    edge = []
    for k in range(21, 31):
        edge += focus_pair("steal", "checkbox", k, "G", "S0", "G", "S0+CL", group="edge", delay_ms=EDGE_MS[k % 11])
    d100 = []
    for k in range(20, 30):
        d100 += focus_pair("steal", "text", k, "G", "X", "G", "X+CL", group="d100", delay_ms=100)
    blocks = chunk("ecs", "steal", edge) + chunk("dts", "steal", d100)
    plan = {"schema": "own20g.plan.v1", "which": "supplement", "blocks": blocks}
    with open(sys.argv[1], "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

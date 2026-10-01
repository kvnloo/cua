"""Write the R2-06 trial plans (deterministic; no randomness).

Arms (all ref-addressed browser_click on the jev-use fixture Submit, after an
ordinary browser_type of a per-trial token):
  T   trusted route, delivery_mode="foreground" (the only trusted browser_click
      path on Linux; background refuses by contract)
  D   dom_event route (positive control, same fixture/oracle)
Controls:
  N_bg     trusted route, default background delivery -> expected refusal
  N_blank  trusted click at viewport (8, 8), off any control -> no submit
  N_empty  trusted Submit click with no typing -> HTML validation, no submit
  N_stale  trusted click with a ref from before a re-navigation -> refusal
  T_plain / D_plain  same as T / D on the uninstrumented fixture page
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

T = {"arm": "T", "click_args": {"delivery_mode": "foreground"}}
D = {"arm": "D", "click_args": {"input_route": "dom_event"}}
CONTROLS = {
    "N_bg": {"arm": "N_bg", "click_args": {}},
    "N_blank": {"arm": "N_blank", "click_args": {"delivery_mode": "foreground"}, "coords": [8, 8]},
    "N_empty": {"arm": "N_empty", "click_args": {"delivery_mode": "foreground"}, "type": False},
    "N_stale": {"arm": "N_stale", "click_args": {"delivery_mode": "foreground"}, "stale_ref": True},
}


def blocks_ab(first_block: int, n_blocks: int, a: dict, b: dict, start_index: int, extra: dict | None = None) -> tuple[list, int]:
    blocks = []
    idx = start_index
    for k in range(n_blocks):
        pattern = "ABBAABBAAB" if k % 2 == 0 else "BAABBAABBA"
        trials = []
        for pos, ch in enumerate(pattern):
            spec = dict(a if ch == "A" else b)
            if extra:
                spec.update(extra)
            trials.append({**spec, "index": idx, "pos": pos})
            idx += 1
        blocks.append({"block": first_block + k, "trials": trials})
    return blocks, idx


def main_plan() -> dict:
    blocks, idx = blocks_ab(1, 6, T, D, 1)
    # Controls block (fresh Driver + browser): each control 3x, interleaved.
    order = ["N_bg", "N_blank", "N_empty", "N_stale"] * 3
    blocks.append({"block": 7, "trials": [{**CONTROLS[c], "index": idx + i, "pos": i} for i, c in enumerate(order)]})
    idx += len(order)
    # Instrumentation-off control block: plain fixture page, T/D ABBA.
    plain_t = {**T, "arm": "T_plain", "instrumented": False}
    plain_d = {**D, "arm": "D_plain", "instrumented": False}
    pattern = "ABBAABBAAB"
    blocks.append({"block": 8, "trials": [{**(plain_t if ch == "A" else plain_d), "index": idx + i, "pos": i} for i, ch in enumerate(pattern)]})
    return {"name": "r2-06-main", "blocks": blocks}


def pilot_plan() -> dict:
    return {"name": "r2-06-pilot-harness-check", "blocks": [{"block": 0, "trials": [{**T, "index": 900, "pos": 0}, {**D, "index": 901, "pos": 1}]}]}


if __name__ == "__main__":
    which, dest = sys.argv[1], Path(sys.argv[2])
    plan = {"main": main_plan, "pilot": pilot_plan}[which]()
    dest.write_text(json.dumps(plan, indent=1) + "\n")
    print(dest, sum(len(b["trials"]) for b in plan["blocks"]), "trials")

#!/usr/bin/env python3
"""Deterministic OWN-20 block schedule (pre-registered): round-robin over block types until each
type has its block count; the type order is reversed on every odd round (ABBA-style interleave)."""
import json
import sys

COUNTS = {
    "text_v1": 2, "text_v2": 2, "focus_v1": 2, "focus_v2": 2, "selection_v1": 2, "selection_v2": 2,
    "checkbox_v1": 2, "checkbox_v2": 2, "child_pts": 4, "child_stp": 4, "recreate": 2, "window": 4,
    "process_v1": 7, "process_v2": 7, "registry": 4, "noop": 2, "decoy": 2, "listener_cycle": 2,
}


def schedule():
    left = dict(COUNTS)
    order = list(COUNTS)
    out, rnd = [], 0
    while any(left.values()):
        for t in (order if rnd % 2 == 0 else order[::-1]):
            if left[t]:
                n = COUNTS[t] - left[t] + 1
                out.append({"seq": len(out) + 1, "block_id": f"b{len(out) + 1:02d}-{t}-{n}", "block_type": t})
                left[t] -= 1
        rnd += 1
    return out


if __name__ == "__main__":
    json.dump(schedule(), sys.stdout, indent=1)
    sys.stdout.write("\n")

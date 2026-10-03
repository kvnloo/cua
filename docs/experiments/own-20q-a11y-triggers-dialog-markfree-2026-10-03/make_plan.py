#!/usr/bin/env python3
"""OWN-20Q: write the frozen trial plan (plan.json) or the pilot plan (plan-pilot.json).

Deterministic (no randomness). Within every block the two slots alternate in ABBA order per pair
(pair k: AB when k is even, BA when odd). Blocks hold <= 10 trials (<= 8 for the slower A2 rows) so a
block holds the shared quiet-lane lock for well under 300 s.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OWN20Q = "own20q_harness.py"
R3Q = "r3q_harness.py"
R3 = "r3_harness.py"  # OWN-20G, blob-identical (carry-over row)


def abba(n_pairs: int, start: int = 0) -> list[str]:
    order: list[str] = []
    for k in range(start, start + n_pairs):
        order += ["U", "G"] if k % 2 == 0 else ["G", "U"]
    return order


def blocks_for(prefix: str, row: str, kind: str, bins: dict[str, str], n_pairs: int, per_block_pairs: int,
               harness: str, extra: dict, single: str | None = None) -> list[dict]:
    """``single``: run only that slot (n_pairs * 2 trials of it), e.g. the GQ-only rows."""
    out, pair = [], 0
    b = 0
    while pair < n_pairs:
        k = min(per_block_pairs, n_pairs - pair)
        slots = [single] * (2 * k) if single else abba(k, pair)
        b += 1
        name = f"{prefix}{b}"
        trials = []
        for i, slot in enumerate(slots):
            trials.append({"id": f"{name}-{i + 1:03d}", "row": row, "kind": kind, "bin": slot,
                           "binary": bins[slot], "pair": pair + i // 2, **extra})
        out.append({"block": name, "row": row, "kind": kind, "bins": bins, "harness": harness, "trials": trials})
        pair += k
    return out


def main_plan() -> dict:
    um = {"U": "U0m", "G": "G0m"}
    u0g0 = {"U": "U0", "G": "G0"}
    gagq = {"U": "GA", "G": "GQ"}
    gq = {"U": "GQ", "G": "GQ"}
    blocks: list[dict] = []
    blocks += blocks_for("c", "cal", "mfcal", um, 10, 5, OWN20Q, {"task": "checkbox", "arm": "P"})
    blocks += blocks_for("q", "r1m", "mfstall", u0g0, 20, 5, OWN20Q, {"task": "checkbox", "arm": "P"})
    blocks += blocks_for("qt", "r1m", "mfstall", u0g0, 20, 5, OWN20Q, {"task": "text", "arm": "PX"})
    blocks += blocks_for("qc", "r1m_control", "mfonly", u0g0, 5, 5, OWN20Q, {"task": "checkbox", "arm": "P"})
    blocks += blocks_for("qct", "r1m_control", "mfonly", u0g0, 5, 5, OWN20Q, {"task": "text", "arm": "PX"})
    blocks += blocks_for("d", "dlg", "dlgsteal", gagq, 20, 5, OWN20Q, {"task": "checkbox", "arm": "P"})
    blocks += blocks_for("dd", "dlg_control", "dlgdialog", gagq, 10, 5, OWN20Q, {"task": "dialog", "arm": "P"})
    blocks += blocks_for("n", "normal", "nosteal", gq, 10, 5, OWN20Q, {"task": "checkbox", "arm": "P"}, single="G")
    blocks += blocks_for("nt", "normal", "nosteal", gq, 10, 5, OWN20Q, {"task": "text", "arm": "P"}, single="G")
    blocks += blocks_for("k", "r3n", "launcher_keep", gagq, 20, 4, R3Q, {"variant": "launcher_keep"})
    blocks += blocks_for("s", "r3s", "slow", gagq, 20, 4, R3Q, {"variant": "slow"})
    blocks += blocks_for("w", "r3w", "launcher_wedge", gagq, 10, 2, R3Q, {"variant": "launcher_wedge"})
    blocks += blocks_for("r", "r3_carry", "bus", gq, 10, 5, R3, {"variant": "bus"}, single="G")
    return {"schema": "own20q.plan.v1", "blocks": blocks}


def pilot_plan() -> dict:
    blocks: list[dict] = []
    blocks += blocks_for("pc", "pilot", "mfcal", {"U": "U0m", "G": "G0m"}, 1, 1, OWN20Q, {"task": "checkbox", "arm": "P"})
    blocks += blocks_for("pq", "pilot", "mfstall", {"U": "U0", "G": "G0"}, 1, 1, OWN20Q, {"task": "checkbox", "arm": "P"})
    blocks += blocks_for("pqt", "pilot", "mfstall", {"U": "U0", "G": "G0"}, 1, 1, OWN20Q, {"task": "text", "arm": "PX"})
    blocks += blocks_for("pd", "pilot", "dlgsteal", {"U": "GA", "G": "GQ"}, 1, 1, OWN20Q, {"task": "checkbox", "arm": "P"})
    blocks += blocks_for("pdd", "pilot", "dlgdialog", {"U": "GA", "G": "GQ"}, 1, 1, OWN20Q, {"task": "dialog", "arm": "P"})
    blocks += blocks_for("pn", "pilot", "nosteal", {"U": "GA", "G": "GQ"}, 1, 1, OWN20Q, {"task": "text", "arm": "P"})
    blocks += blocks_for("pk", "pilot", "launcher_keep", {"U": "GA", "G": "GQ"}, 1, 1, R3Q, {"variant": "launcher_keep"})
    blocks += blocks_for("pw", "pilot", "launcher_wedge", {"U": "GA", "G": "GQ"}, 1, 1, R3Q, {"variant": "launcher_wedge"})
    blocks += blocks_for("ps", "pilot", "slow", {"U": "GA", "G": "GQ"}, 1, 1, R3Q, {"variant": "slow"})
    blocks += blocks_for("pr", "pilot", "bus", {"U": "GQ", "G": "GQ"}, 1, 1, R3, {"variant": "bus"}, single="G")
    return {"schema": "own20q.plan.v1", "pilot": True, "blocks": blocks}


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "main"
    plan = pilot_plan() if which == "pilot" else main_plan()
    path = Path(__file__).resolve().parent / ("plan-pilot.json" if which == "pilot" else "plan.json")
    path.write_text(json.dumps(plan, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(path.name, sum(len(b["trials"]) for b in plan["blocks"]), "trials", len(plan["blocks"]), "blocks")

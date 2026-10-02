#!/usr/bin/env python3
"""R2-09 measured plan (pre-registered with PREREG.json). stdlib only.

usage: make_plan.py <plan.json>

Families (each compared only within itself; one source, one binary W):
  M  T1 Chromium, background delivery, arms B / S0 / EW, tasks checkbox + submit
  F  T1 Chromium, background delivery, arms B_F0 / S0_F0 / EW_F0 (supplementary:
     focus-guard settle knob 0 on top, so the post-DoAction wait is the only
     post-action wait), tasks checkbox + submit
  G  T2 GTK3 canonical fixture, FOREGROUND delivery, arms B / S0 / EW, tasks
     checkbox + text
Each family: 20 rounds; round r runs both tasks (first task alternates with r)
and, per task, the three arms in Williams row r mod 6 (all 6 orders of 3 arms,
so every arm precedes every other equally often). One fresh Driver and one
fresh target per trial.
Controls (T1, EW arm, n = 10 each): a replace, b decoy, c reconnect, d noop,
and c2 bus drop (supplementary; one trial per session because the private
AT-SPI bus does not come back).
Default-off smoke: W with no knob, T1 checkbox B, n = 5.
Every block runs under bin/quiet-timed (exclusive quiet-lane lock) and is
sized to stay under 15 minutes.
"""

from __future__ import annotations

import json
import sys

WILLIAMS3 = [(0, 1, 2), (1, 2, 0), (2, 0, 1), (0, 2, 1), (1, 0, 2), (2, 1, 0)]
FAMILIES = {
    "M": {"target": "chrome", "delivery": "background", "arms": ["B", "S0", "EW"], "tasks": ["checkbox", "submit"]},
    "F": {"target": "chrome", "delivery": "background", "arms": ["B_F0", "S0_F0", "EW_F0"],
          "tasks": ["checkbox", "submit"]},
    "G": {"target": "gtk3", "delivery": "foreground", "arms": ["B", "S0", "EW"], "tasks": ["checkbox", "text"]},
}
ROUNDS = 20
ROUNDS_PER_BLOCK = {"M": 7, "F": 7, "G": 5}
CONTROLS = [("a", "replace", "checkbox"), ("b", "decoy", "checkbox"), ("c", "reconnect", "checkbox"),
            ("d", "noop", "noop")]


def family_trials(fam: str) -> list[dict]:
    spec = FAMILIES[fam]
    out = []
    for r in range(ROUNDS):
        tasks = spec["tasks"] if r % 2 == 0 else list(reversed(spec["tasks"]))
        for task in tasks:
            for slot, ai in enumerate(WILLIAMS3[r % 6]):
                arm = spec["arms"][ai]
                out.append({"id": f"{fam}-r{r:02d}-{task}-{arm}", "family": fam, "round": r, "slot": slot,
                            "target": spec["target"], "task": task, "arm": arm, "kind": "main",
                            "variant": "main", "delivery": spec["delivery"]})
    return out


def main() -> None:
    blocks = [{"block": "d01", "kind": "smoke", "lock": "exclusive", "trials": [
        {"id": f"D-{i}", "family": "D", "round": i, "slot": 0, "target": "chrome", "task": "checkbox",
         "arm": "B", "kind": "smoke", "variant": "main", "delivery": "background"} for i in range(5)]}]
    for fam in ("M", "F", "G"):
        trials = family_trials(fam)
        per = ROUNDS_PER_BLOCK[fam]
        n = 0
        for start in range(0, ROUNDS, per):
            n += 1
            chunk = [t for t in trials if start <= t["round"] < start + per]
            blocks.append({"block": f"{fam.lower()}{n:02d}", "kind": "main", "lock": "exclusive", "trials": chunk})
    for code, variant, task in CONTROLS:
        blocks.append({"block": f"c{code}", "kind": f"ctl_{code}", "lock": "exclusive", "trials": [
            {"id": f"C{code}-{i}", "family": f"C{code}", "round": i, "slot": 0, "target": "chrome", "task": task,
             "arm": "EW", "kind": f"ctl_{code}", "variant": variant, "delivery": "background"}
            for i in range(10)]})
    for i in range(10):
        blocks.append({"block": f"cc2-{i:02d}", "kind": "ctl_c2", "lock": "exclusive", "trials": [
            {"id": f"Cc2-{i}", "family": "Cc2", "round": i, "slot": 0, "target": "chrome", "task": "checkbox",
             "arm": "EW", "kind": "ctl_c2", "variant": "busdrop", "delivery": "background"}]})
    plan = {"schema": "r209.plan.v1", "williams3": WILLIAMS3, "families": FAMILIES, "rounds": ROUNDS,
            "blocks": blocks}
    with open(sys.argv[1], "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")
    print({b["block"]: len(b["trials"]) for b in blocks})


if __name__ == "__main__":
    main()

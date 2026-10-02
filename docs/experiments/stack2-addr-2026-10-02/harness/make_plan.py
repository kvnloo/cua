"""Write plan.json for stack2-addr (deterministic; seed 20261002).

measured: 12 pairs x {gtk3, browser} x {before, after} on cua-driver 0.32.0; arm order inside each (pair, task)
          drawn from random.Random(seed); tasks alternate gtk3 then browser inside each pair  -> 48 runs
legacy:   after-arm Hermes on the pinned cua-driver 0.21.0, 3 per task, run after the measured set  -> 6 runs
usage: make_plan.py <out plan.json>
"""
import json
import random
import sys

SEED = 20261002
rng = random.Random(SEED)
runs, n = [], 0
for pair in range(1, 13):
    for task in ("gtk3", "browser"):
        arms = ["before", "after"]
        rng.shuffle(arms)
        for arm in arms:
            n += 1
            runs.append({"run_id": f"m{n:03d}-{task}-{arm}-p{pair:02d}", "task": task, "arm": arm, "pair": pair,
                         "driver_key": "main_0_32_0", "set": "measured"})
for i, task in enumerate(["gtk3", "browser"] * 3, start=1):
    runs.append({"run_id": f"l{i:02d}-{task}-after-legacy", "task": task, "arm": "after", "pair": 100 + i,
                 "driver_key": "pinned_0_21_0", "set": "legacy"})
json.dump({"seed": SEED, "runs": runs}, open(sys.argv[1], "w"), indent=1)
print(len(runs), "runs")

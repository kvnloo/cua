#!/usr/bin/env python3
"""Write the OWN-20G trial plan (deterministic; stdlib only).

usage: make_plan.py measured|pilot <out.json>

Measured plan (pre-registered in PREREG.json). Arms: checkbox S0, text X (N-02's base
arms); binaries U (bdf33d9fe) and G (U + the fix commit). Every pair is AB/BA:
pair k runs (A, B) when k is even and (B, A) when k is odd.

* s01: default-off smoke, arm D (no CUA_DRIVER_EXP_*), U and G x checkbox and text x 2.
* R1, two stall rows, U vs G, n = 20 per binary per task, shared lock:
  - ``replystall`` (blocks r1qa-r1qd): the c08-017 reproduction. The reply to the guard's
    new-client read after its ~90 ms poll is held 2.0 s by xstall_proxy.py; the decoy
    steals at ~217 ms. Control ``replyonly`` (proxy on, no hold, no steal), 5 per binary
    per task (r1qe);
  - ``stall`` (blocks r1ga-r1gd): the planner's XGrabServer row (grab ~2.0 s from ~100 ms,
    steal issued at ~217 ms). Control ``stallonly`` (grab, no steal), r1ge.
* R2 (CL re-test; run only after UNIT and R1 pass): G vs G+CL (CL =
  CUA_DRIVER_EXP_FOCUS_GUARD_CLAMP=1, on G).
  - band: delays 216, 220, 225, 230, 235, 240, 245 ms after do_action_replied; one
    round = every delay once per arm per task (7 pairs, delay order rotated by the
    round); rounds 1-6 always (blocks b<task><r>); rounds 7-10 (blocks x<task><r>)
    run only under PREREG's band-extension rule;
  - edge: 205-215 ms (205 + k mod 11), 21 pairs per task;
  - d100: 100 ms, 20 pairs per task;
  - nosteal: decoy mapped, sampler on, no steal, 10 pairs per task.
* t01: timing block, EXCLUSIVE (quiet-timed): G vs G+CL, 24 AB/BA pairs per task,
  tasks alternating by pair, no decoy and no steal.
* R3 (bus restart): variant ``bus`` 20 per binary (blocks r3a, r3b); controls
  ``registry`` and ``noop`` 5 per binary each (r3c); ``noop_direct`` (the old token is
  clicked without a re-observation: the discriminating control) and ``bus_direct``
  (exploratory: restart, then the old token without a re-observation), 5 per binary
  each (r3d). Shared lock.
"""

from __future__ import annotations

import json
import sys

TASK_ARM = {"checkbox": "S0", "text": "X"}
BAND_MS = [216, 220, 225, 230, 235, 240, 245]
EDGE_MS = [205 + k for k in range(11)]
BAND_ROUNDS = 6
BAND_ROUNDS_MAX = 10


def pairs(a: dict, b: dict, k: int) -> list[dict]:
    return [a, b] if k % 2 == 0 else [b, a]


def chunk(name: str, kind: str, trials: list[dict], lock: str = "shared", size: int = 20,
          harness: str | None = None) -> list[dict]:
    blocks = []
    for i in range(0, len(trials), size):
        bname = name if len(trials) <= size else f"{name}{i // size + 1}"
        part = [{"id": f"{bname}-{j + 1:03d}", "block": bname, **t} for j, t in enumerate(trials[i:i + size])]
        block = {"block": bname, "kind": kind, "lock": lock, "trials": part}
        if harness:
            block["harness"] = harness
        blocks.append(block)
    return blocks


def focus_pair(kind: str, task: str, k: int, a_bin: str, a_arm: str, b_bin: str, b_arm: str,
               **extra) -> list[dict]:
    a = {"kind": kind, "task": task, "bin": a_bin, "arm": a_arm, "pair": k, **extra}
    b = {"kind": kind, "task": task, "bin": b_bin, "arm": b_arm, "pair": k, **extra}
    return pairs(a, b, k)


def measured() -> list[dict]:
    blocks: list[dict] = []
    smoke = []
    for k, task in enumerate(["checkbox", "text", "checkbox", "text"]):
        smoke += focus_pair("smoke", task, k, "U", "D", "G", "D")
    blocks += chunk("s01", "smoke", smoke)
    # R1: the c08-017 reproduction (reply-delay stall) and the XGrabServer row as specified
    for kind, ctl_kind, prefix in (("replystall", "replyonly", "q"), ("stall", "stallonly", "g")):
        for task, names in (("checkbox", ("a", "b")), ("text", ("c", "d"))):
            arm = TASK_ARM[task]
            for half, name in enumerate(names):
                trials = []
                for p in range(10):
                    k = half * 10 + p
                    trials += focus_pair(kind, task, k, "U", arm, "G", arm)
                blocks += chunk(f"r1{prefix}{name}", kind, trials)
        ctl = []
        for task in ("checkbox", "text"):
            for k in range(5):
                ctl += focus_pair(ctl_kind, task, k, "U", TASK_ARM[task], "G", TASK_ARM[task])
        blocks += chunk(f"r1{prefix}e", ctl_kind, ctl)
    # R2
    for task in ("checkbox", "text"):
        arm = TASK_ARM[task]
        cl = f"{arm}+CL"
        for r in range(BAND_ROUNDS_MAX):
            order = BAND_MS[r % 7:] + BAND_MS[:r % 7]
            trials = []
            for i, d in enumerate(order):
                trials += focus_pair("steal", task, r * 7 + i, "G", arm, "G", cl, group="band",
                                     delay_ms=d, round=r + 1)
            prefix = "b" if r < BAND_ROUNDS else "x"
            blocks += chunk(f"{prefix}{task[0]}{r + 1:02d}", "steal", trials)
        edge = []
        for k in range(21):
            edge += focus_pair("steal", task, k, "G", arm, "G", cl, group="edge", delay_ms=EDGE_MS[k % 11])
        blocks += chunk(f"e{task[0]}", "steal", edge, size=14)
        d100 = []
        for k in range(20):
            d100 += focus_pair("steal", task, k, "G", arm, "G", cl, group="d100", delay_ms=100)
        blocks += chunk(f"d{task[0]}", "steal", d100)
        nos = []
        for k in range(10):
            nos += focus_pair("nosteal", task, k, "G", arm, "G", cl, group="nosteal")
        blocks += chunk(f"n{task[0]}", "nosteal", nos)
    timing = []
    for k in range(48):
        task = ("checkbox", "text")[k % 2]
        arm = TASK_ARM[task]
        timing += focus_pair("timing", task, k // 2, "G", arm, "G", f"{arm}+CL")
    blocks += chunk("t01", "timing", timing, lock="exclusive", size=96)
    # R3
    bus = []
    for k in range(20):
        bus += pairs({"kind": "r3", "variant": "bus", "bin": "U", "pair": k},
                     {"kind": "r3", "variant": "bus", "bin": "G", "pair": k}, k)
    blocks += chunk("r3a", "r3", bus[:20], harness="r3_harness.py")
    blocks += chunk("r3b", "r3", bus[20:], harness="r3_harness.py")
    for name, variants in (("r3c", ("registry", "noop")), ("r3d", ("noop_direct", "bus_direct"))):
        ctl3 = []
        for k in range(10):
            variant = variants[k % 2]
            ctl3 += pairs({"kind": "r3", "variant": variant, "bin": "U", "pair": k},
                          {"kind": "r3", "variant": variant, "bin": "G", "pair": k}, k)
        blocks += chunk(name, "r3", ctl3, harness="r3_harness.py")
    return blocks


def pilot() -> list[dict]:
    trials = []
    trials += focus_pair("stall", "checkbox", 0, "U", "S0", "G", "S0")
    trials += focus_pair("stall", "text", 1, "U", "X", "G", "X")
    trials += focus_pair("steal", "checkbox", 0, "G", "S0", "G", "S0+CL", group="band", delay_ms=230)
    trials += [{"kind": "nosteal", "task": "checkbox", "bin": "G", "arm": "S0", "pair": 0, "group": "nosteal"}]
    trials += focus_pair("stallonly", "checkbox", 0, "U", "S0", "G", "S0")
    r3 = [{"kind": "r3", "variant": v, "bin": b, "pair": 0} for v, b in
          (("noop", "G"), ("registry", "G"), ("bus", "G"), ("bus", "U"))]
    return chunk("p01", "mixed", trials) + chunk("p02", "r3", r3, harness="r3_harness.py")


def main() -> None:
    which, out = sys.argv[1], sys.argv[2]
    blocks = measured() if which == "measured" else pilot()
    plan = {"schema": "own20g.plan.v1", "which": which, "task_arm": TASK_ARM, "band_ms": BAND_MS,
            "edge_ms": EDGE_MS, "band_rounds": BAND_ROUNDS, "band_rounds_max": BAND_ROUNDS_MAX,
            "blocks": blocks}
    with open(out, "w", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=1, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()

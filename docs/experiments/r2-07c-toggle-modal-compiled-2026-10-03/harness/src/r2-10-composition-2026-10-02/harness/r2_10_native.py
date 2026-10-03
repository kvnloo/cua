#!/usr/bin/env python3
"""R2-10 native arms on the canonical GTK3 fixture (measurement only).

Runs the accepted N-01R harness (harness/src/n-01r-native-wait-ab-2026-10-02/n01r_harness.py,
copied by path from 3bb4a7fc7, unchanged) with R2-10's arms and plan:

  BASE  defaults (N-01R arm B)
  S0    CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS=0 (N-01R arm S0)
  X     S0 + set_agent_cursor_motion {glide_duration_ms: 1} (R2-10 spec; N-01R's X also sent
        dwell_after_click_ms 0, which has no Linux runtime reader)

Changes are applied by monkeypatching module globals only:
* ``FAST_MOTION`` = {"glide_duration_ms": 1};
* arm ``BASE`` = N-01R arm ``B``;
* the Driver environment additionally carries DO_NOT_TRACK=1 (Driver telemetry is also disabled
  with CUA_DRIVER_RS_TELEMETRY_ENABLED=0 from the session);
* ``--no-trace`` (default-off smoke): the Driver is started WITHOUT CUA_DRIVER_PHASE_TRACE_FILE
  (the harness still pre-creates the empty per-trial file; the Driver must leave it empty).

usage (inside hostless + hostless-strict + cua-x11-session.sh with AT-SPI, via in_session.sh):
  r2_10_native.py --wt <wt> --driver <bin> --driver-sha256 <sha> --plan <plan.json> --block <b>
                  --label <label> --out <dir> --work <dir> [--no-trace]
  r2_10_native.py --make-plan <out.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
N01R = HERE / "src" / "n-01r-native-wait-ab-2026-10-02"
sys.path.insert(0, str(N01R))

TASKS = ["checkbox", "text"]
ARMS = ["BASE", "S0", "X"]
ROUNDS = 24


def williams3() -> list[list[int]]:
    """Williams design for 3 treatments: the 3x3 square plus its mirror (6 sequences)."""
    first, lo, hi, take_lo = [0], 1, 2, True
    while len(first) < 3:
        first.append(lo if take_lo else hi)
        lo, hi = (lo + 1, hi) if take_lo else (lo, hi - 1)
        take_lo = not take_lo
    rows = [[(x + i) % 3 for x in first] for i in range(3)]
    return rows + [list(reversed(r)) for r in rows]


def make_plan() -> dict:
    rows = williams3()
    blocks = []
    for half in range(2):
        trials = []
        name = f"nm{half + 1}"
        for r in range(half * 12, half * 12 + 12):
            order = TASKS if r % 2 == 0 else TASKS[::-1]
            for task in order:
                for j in rows[r % 6]:
                    trials.append({"id": f"{name}-{len(trials) + 1:03d}", "block": name, "kind": "main",
                                   "task": task, "arm": ARMS[j], "round": r})
        blocks.append({"block": name, "kind": "main", "lock": "exclusive", "trials": trials})
    decoy = []
    for p in range(5):
        for task in TASKS:
            for arm in (ARMS if p % 2 == 0 else ARMS[::-1]):
                decoy.append({"id": f"nd1-{len(decoy) + 1:03d}", "block": "nd1", "kind": "decoy", "task": task,
                              "arm": arm, "variant_ms": 100, "round": p})
    blocks.append({"block": "nd1", "kind": "decoy", "lock": "exclusive", "trials": decoy})
    for b in ("nsR", "nsC"):
        smoke = [{"id": f"{b}-{k + 1:02d}", "block": b, "kind": "smoke", "task": TASKS[k % 2], "arm": "BASE",
                  "round": k // 2} for k in range(10)]
        blocks.append({"block": b, "kind": "smoke", "lock": "exclusive", "trials": smoke})
    shake = [{"id": f"nk1-{k + 1:02d}", "block": "nk1", "kind": "main", "task": task, "arm": arm, "round": 0}
             for k, (task, arm) in enumerate([(t, a) for t in TASKS for a in ARMS])]
    blocks.append({"block": "nk1", "kind": "main", "lock": "exclusive", "trials": shake})
    blocks.append({"block": "nk2", "kind": "decoy", "lock": "exclusive",
                   "trials": [{"id": f"nk2-{k + 1:02d}", "block": "nk2", "kind": "decoy", "task": task, "arm": arm,
                               "variant_ms": 100, "round": 0}
                              for k, (task, arm) in enumerate([("checkbox", "BASE"), ("text", "S0"),
                                                               ("checkbox", "X")])]})
    return {"schema": "r2-10.native-plan.v1", "arms": ARMS, "tasks": TASKS, "williams3": rows, "blocks": blocks}


def main() -> None:
    if "--make-plan" in sys.argv:
        out = sys.argv[sys.argv.index("--make-plan") + 1]
        Path(out).write_text(json.dumps(make_plan(), indent=1, sort_keys=True) + "\n")
        return
    no_trace = "--no-trace" in sys.argv
    if no_trace:
        sys.argv.remove("--no-trace")
    wt = Path(sys.argv[sys.argv.index("--wt") + 1]).resolve()
    sys.path.insert(0, str(wt / "libs/cua-driver/examples/jev-use/python"))
    import n01r_harness as h  # noqa: E402
    import driver_env  # noqa: E402
    import mcp  # noqa: E402

    h.FAST_MOTION = {"glide_duration_ms": 1}
    h.ARMS["BASE"] = dict(h.ARMS["B"])
    base_env = driver_env.driver_environment

    def env_with_dnt(source=None):  # noqa: ANN001
        env = base_env() if source is None else base_env(source)
        env["DO_NOT_TRACK"] = "1"
        env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
        return env

    driver_env.driver_environment = env_with_dnt
    if no_trace:
        real = mcp.StdioServerParameters

        def params_without_trace(*args, **kwargs):  # noqa: ANN002, ANN003
            env = dict(kwargs.get("env") or {})
            env.pop("CUA_DRIVER_PHASE_TRACE_FILE", None)
            kwargs["env"] = env
            return real(*args, **kwargs)

        mcp.StdioServerParameters = params_without_trace
    h.main()


if __name__ == "__main__":
    main()

"""B-07 browser harness: R'-source transport residual attribution and causal A/B.

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``in_session.sh``; the cargo-build lock and the quiet-lane lock are taken OUTSIDE (run_chunk.sh).

Derived from B-05's ``b05_browser.py`` (harness/b05/). It reuses the R2-10R browser harness
unchanged, by path (harness/r2-10r/, byte-identical copies from c183b95e3): trial lifecycle (fresh
Driver, fresh isolated browser, fresh fixture state and token per trial), the COMP arm, the scripted
chooser, compiled replay on fill, the 2 ms independent oracle sampler, the recorder and the N4a
control. B-07 adds, caller side only:
* ``b07_stdio``: B-05's stamped stdio client plus the PREP_FAST / ROUTE_FAST variants and GC stamps;
* arms: COMP (phase trace ON = marks on), COMP_OFF (trace OFF) and the Phase B candidate arms named
  in PREREG-AMENDMENT-1.json;
* a per-round load gate: a round starts only at 1-minute loadavg <= 4.0; otherwise it waits up to
  60 s (2 s polls) and, if the load stays high, the chunk ends and resumes later at that round. Every
  gate attempt is logged in the run manifest.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "r2-10r")]

import r2_10_browser as r  # noqa: E402  (R2-10R harness, unchanged)
import b07_stdio as bs  # noqa: E402

rc = r.rc
rc.stdio_client = bs.stdio_client  # r2_10_browser and run_b02 resolve rc.stdio_client at call time
bs.install()
bs.STAMP["rec_fn"] = lambda: rc.CLIENT["rec"]

r.ARMS["COMP_OFF"] = {**r.ARMS["COMP"], "trace": False}
B_ARMS: dict[str, dict[str, Any]] = {}
CLASSES = r.CLASSES
LOAD_MAX = 4.0
LOAD_WAIT_S = 60.0
POST_FAST_ENV = "CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM"

_orig_env = r.driver_env_for


def driver_env_for(arm: dict[str, Any], cls: str, trace_path: Path | None) -> dict[str, str]:
    """R2-10 driver_env_for, with the marks switch: arms with trace False never set the trace file."""
    return _orig_env(arm, cls, None if arm.get("trace") is False else trace_path)


r.driver_env_for = driver_env_for

FRAMES: dict[str, Any] = {"cur": None}
_orig_run_trial = r.run_trial


async def run_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, store: Any,
                    trace_path: Path | None, rec: Any, result: dict[str, Any]) -> None:
    arm = r.ARMS[spec["arm"]]
    bs.STAMP["prep"] = arm.get("prep", "default")
    bs.STAMP["route"] = arm.get("route", "default")
    frames: list[Any] = []
    gcs: list[Any] = []
    FRAMES["cur"] = frames
    bs.STAMP["frames"] = frames
    bs.STAMP["gc"] = gcs
    before = dict(bs.COUNTS)
    result["caller_variant"] = {"prep": bs.STAMP["prep"], "route": bs.STAMP["route"]}
    try:
        await _orig_run_trial(spec, args, fixtures, store, trace_path, rec, result)
    finally:
        result["caller_variant_counts"] = {k: bs.COUNTS[k] - before[k] for k in bs.COUNTS}
        result["gc_events"] = [list(x) for x in gcs]
        bs.STAMP["frames"] = None
        bs.STAMP["gc"] = None
        bs.STAMP["prep"] = "default"
        bs.STAMP["route"] = "default"


r.run_trial = run_trial


def write_frames(out: Path, name: str, frames: list[Any] | None) -> None:
    """Raw request/response lines; result objects are hashed here, after the trial (never inside T)."""
    if not frames:
        return
    (out / "frames").mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "frames" / f"{name}.frames.jsonl.gz", "wt", encoding="utf-8") as f:
        for kind, item in frames:
            if kind == "resobj":
                sha = hashlib.sha256(bs.canonical(item).encode()).hexdigest()
                f.write(json.dumps({"k": kind, "sha": sha}) + "\n")
            else:
                f.write(json.dumps({"k": kind, "line": item}, ensure_ascii=False) + "\n")


def build_plan(kind: str, start: int, rounds: int, arms: list[str], layer: str) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    if kind == "A":
        for rd in range(start, start + rounds):
            for cls in CLASSES[rd % 3:] + CLASSES[:rd % 3]:
                trials.append({"cls": cls, "arm": "COMP", "kind": "measured", "layer": layer, "round": rd,
                               "order": "A", "block": "A"})
        return trials
    if kind in ("ovh", "B"):
        a, b = arms  # control first in AB rounds
        for rd in range(start, start + rounds):
            for cls in CLASSES[rd % 3:] + CLASSES[:rd % 3]:
                order = [a, b] if rd % 2 == 0 else [b, a]
                for arm in order:
                    trials.append({"cls": cls, "arm": arm, "kind": "measured", "layer": layer, "round": rd,
                                   "order": "AB" if rd % 2 == 0 else "BA", "block": kind})
        return trials
    if kind == "n4a":
        for k in range(start, start + rounds):
            for arm in arms:
                for cls in CLASSES:
                    trials.append({"cls": cls, "arm": arm, "kind": "n4a", "layer": layer, "round": k, "block": "N"})
        return trials
    if kind == "shake":
        for arm in arms:
            for cls in CLASSES:
                trials.append({"cls": cls, "arm": arm, "kind": "measured", "layer": layer, "round": start,
                               "block": "K"})
        return trials
    raise ValueError(kind)


def load_amendment_arms(path: Path) -> None:
    """Register the Phase B arms exactly as PREREG-AMENDMENT-1.json names them."""
    data = json.loads(path.read_text())
    for cand in data.get("candidates", []):
        base = r.ARMS[cand.get("control_arm", "COMP_OFF")]
        arm = {**base, **cand.get("arm_overrides", {})}
        arm["knobs"] = {**base["knobs"], **cand.get("driver_knobs", {})}
        r.ARMS[cand["arm"]] = arm
        B_ARMS[cand["arm"]] = arm


def load1() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


async def load_gate(rd: int) -> dict[str, Any]:
    t0 = time.monotonic()
    samples = [load1()]
    while samples[-1] > LOAD_MAX and time.monotonic() - t0 < LOAD_WAIT_S:
        await asyncio.sleep(2.0)
        samples.append(load1())
    return {"round": rd, "utc": r.utc(), "ok": samples[-1] <= LOAD_MAX, "waited_s": round(time.monotonic() - t0, 1),
            "first": samples[0], "last": samples[-1], "polls": len(samples)}


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    if args.plan in ("smoke", "toolslist"):
        await r.main_async(args)  # R2-10 plans, unchanged (instrumented client, identical behaviour)
        return
    arms = args.arms.split(",")
    store = r.RoutineStore(Path(args.routines) if args.routines else out)
    fixtures = rc.Fixtures()
    trials = build_plan(args.plan, args.start_round, args.rounds, arms, args.layer)
    for i, spec in enumerate(trials):
        spec["name"] = f"{args.prefix}{i:03d}-{spec['cls']}-{spec['arm']}-{spec['kind']}-r{spec['round']:02d}"
    manifest: dict[str, Any] = {"plan": args.plan, "arms": arms, "layer": args.layer, "start_round": args.start_round,
                                "rounds": args.rounds, "trials": [s["name"] for s in trials], "started_utc": r.utc(),
                                "loadavg_start": r.loadavg(), "display_set": bool(os.environ.get("DISPLAY")),
                                "arm_configs": {a: r.ARMS[a] for a in arms}, "load_gate": [], "completed": [],
                                "ended_on_load_gate": None}
    deadline = time.monotonic() + args.max_minutes * 60.0
    try:
        cur = None
        for spec in trials:
            if spec["round"] != cur:
                cur = spec["round"]
                if time.monotonic() > deadline:
                    manifest["ended_on_time_cap"] = cur
                    break
                g = await load_gate(cur)
                manifest["load_gate"].append(g)
                if not g["ok"]:
                    manifest["ended_on_load_gate"] = cur
                    break
            FRAMES["cur"] = None
            await r.one(spec, args, fixtures, store, out)
            write_frames(out, spec["name"], FRAMES["cur"])
            manifest["completed"].append(spec["name"])
    finally:
        manifest.update({"ended_utc": r.utc(), "loadavg_end": r.loadavg(), "network": dict(r.NET)})
        (out / f"run-manifest-{args.prefix}.json").write_text(json.dumps(manifest, indent=1, default=str))
        fixtures.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", required=True, choices=("A", "ovh", "B", "n4a", "shake", "smoke", "toolslist"))
    p.add_argument("--arms", default="COMP")
    p.add_argument("--layer", default="A")
    p.add_argument("--start-round", type=int, default=0)
    p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--prefix", required=True)
    p.add_argument("--routines")
    p.add_argument("--amendment", help="PREREG-AMENDMENT-1.json (Phase B arms)")
    p.add_argument("--max-minutes", type=float, default=9.0, help="no new round starts after this (cap < 10 min)")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or os.environ.get("R2_10_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless + cua-x11-session.sh (in_session.sh)")
    for name in (r.TRACE_ENV, r.SETTLE_ENV, r.E_ENV, r.V_ENV, "CUA_DRIVER_EXP_MCP_SINGLE_WRITE", POST_FAST_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    os.environ.pop("TYPESAFE_API_KEY", None)  # provider cap for this lane is 0
    if args.amendment:
        load_amendment_arms(Path(args.amendment))
    # R2-10 main_async fields used by its smoke/toolslist plans.
    args.provider_ledger, args.cap_reached, args.cap_attempts = None, 0, 0
    args.plan_kind = args.plan
    args.save_snapshots = False
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

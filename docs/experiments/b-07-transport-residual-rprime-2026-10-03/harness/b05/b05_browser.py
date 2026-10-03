"""B-05 browser harness: MCP transport / resolution / admission attribution and causal A/B.

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``in_session.sh``; the cargo-build lock and the quiet-lane lock are taken OUTSIDE (run_chunk.sh).

Reuses the R2-10 browser harness unchanged, by path (harness/r2-10/, copied from 030f6bdbf): the
trial lifecycle (fresh Driver, fresh isolated browser, fresh token), the COMP arm, the scripted
chooser, compiled replay on fill, the 2 ms independent oracle sampler, the recorder and the N4a
control. B-05 adds, caller side only:
* ``b05_stdio.stdio_client``: mcp 1.30 stdio_client plus CLOCK_MONOTONIC stamps and raw-frame capture;
* arms: COMP (Driver phase trace ON = marks on), COMP_OFF (same, trace OFF = marks off) and the
  Phase B candidate arms named in PREREG-AMENDMENT-1.json (registered in ``B_ARMS``);
* plans: A (attribution), ovh (marks on/off AB/BA), B (candidate AB/BA), n4a, smoke, toolslist.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "r2-10")]

import r2_10_browser as r  # noqa: E402  (R2-10 harness, unchanged)
import b05_stdio as bs  # noqa: E402

rc = r.rc
rc.stdio_client = bs.stdio_client  # r2_10_browser and run_b02 resolve rc.stdio_client at call time
bs.install()
bs.STAMP["rec_fn"] = lambda: rc.CLIENT["rec"]

r.ARMS["COMP_OFF"] = {**r.ARMS["COMP"], "trace": False}
# Phase B candidate arms (filled from PREREG-AMENDMENT-1.json before any Phase B trial).
B_ARMS: dict[str, dict[str, Any]] = {}
CLASSES = r.CLASSES

_orig_env = r.driver_env_for


def driver_env_for(arm: dict[str, Any], cls: str, trace_path: Path | None) -> dict[str, str]:
    """R2-10 driver_env_for, with the B-05 marks switch: arms with trace False never set the trace file."""
    return _orig_env(arm, cls, None if arm.get("trace") is False else trace_path)


r.driver_env_for = driver_env_for

_orig_compile = rc.compile_output_validators


def compile_output_validators(session: Any) -> int:
    """R2-10 compile (outside T), then the Phase B validator variant when the arm names one."""
    n = _orig_compile(session)
    if bs.STAMP.get("validator") == "fast":
        import b05_variants as bv

        schemas = {rc._schema_key(s): s for s in getattr(session, "_tool_output_schemas", {}).values() if s is not None}
        rc.CLIENT["compiled"], kept = bv.fast_validators(rc.CLIENT["compiled"], schemas)
        VARIANT_LOG["validators_kept_library"] = kept
    return n


rc.compile_output_validators = compile_output_validators
VARIANT_LOG: dict[str, Any] = {}

FRAMES: dict[str, Any] = {"cur": None}
_orig_run_trial = r.run_trial


async def run_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, store: Any,
                    trace_path: Path | None, rec: Any, result: dict[str, Any]) -> None:
    arm = r.ARMS[spec["arm"]]
    bs.STAMP["parser"] = arm.get("parser", "default")
    bs.STAMP["max_bytes"] = arm.get("max_bytes", 65536)
    bs.STAMP["validator"] = arm.get("validator", "default")
    VARIANT_LOG.clear()
    frames: list[Any] = []
    FRAMES["cur"] = frames
    bs.STAMP["frames"] = frames
    result["caller_variant"] = {"parser": bs.STAMP["parser"], "max_bytes": bs.STAMP["max_bytes"],
                                "validator": bs.STAMP["validator"]}
    try:
        await _orig_run_trial(spec, args, fixtures, store, trace_path, rec, result)
    finally:
        if VARIANT_LOG:
            result["caller_variant_log"] = dict(VARIANT_LOG)
        bs.STAMP["frames"] = None
        bs.STAMP["parser"] = "default"
        bs.STAMP["max_bytes"] = 65536
        bs.STAMP["validator"] = "default"


r.run_trial = run_trial


def write_frames(out: Path, name: str, frames: list[Any] | None) -> None:
    if not frames:
        return
    (out / "frames").mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "frames" / f"{name}.frames.jsonl.gz", "wt", encoding="utf-8") as f:
        for kind, line in frames:
            f.write(json.dumps({"k": kind, "line": line}, ensure_ascii=False) + "\n")


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
        for arm in arms:
            for k in range(start, start + rounds):
                for cls in CLASSES:
                    trials.append({"cls": cls, "arm": arm, "kind": "n4a", "layer": layer, "round": k, "block": "N"})
        return trials
    if kind == "shake":
        for arm in arms:
            for cls in CLASSES:
                trials.append({"cls": cls, "arm": arm, "kind": "measured", "layer": layer, "round": 0, "block": "K"})
        return trials
    raise ValueError(kind)


def load_amendment_arms(path: Path) -> None:
    """Register the Phase B arms exactly as PREREG-AMENDMENT-1.json names them."""
    import b05_variants  # noqa: F401  (registers caller-side parser variants in bs.PARSERS)

    data = json.loads(path.read_text())
    for cand in data.get("candidates", []):
        base = r.ARMS[cand.get("control_arm", "COMP_OFF")]
        arm = {**base, **cand.get("arm_overrides", {})}
        arm["knobs"] = {**base["knobs"], **cand.get("driver_knobs", {})}
        r.ARMS[cand["arm"]] = arm
        B_ARMS[cand["arm"]] = arm


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
                                "arm_configs": {a: r.ARMS[a] for a in arms}}
    try:
        for spec in trials:
            FRAMES["cur"] = None
            await r.one(spec, args, fixtures, store, out)
            write_frames(out, spec["name"], FRAMES["cur"])
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
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or os.environ.get("R2_10_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless + cua-x11-session.sh (in_session.sh)")
    for name in (r.TRACE_ENV, r.SETTLE_ENV, r.E_ENV, r.V_ENV, "CUA_DRIVER_EXP_MCP_SINGLE_WRITE"):
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

"""R2-07d runner: quiet-window Phase S timing block with a load ceiling, plus carry-over controls.

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``driver/run_chunk_d.sh`` -> ``driver/probe_then.sh`` -> the R2-07c ``harness/in_session.sh``. The
locks are taken OUTSIDE, before the session opens.

Everything that touches the Driver, Chromium, the fixture or the oracle is the R2-07c harness
(``../r2-07c-toggle-modal-compiled-2026-10-03/harness/``, blob-identical to 7f46edd16), imported and
called unchanged: ``r2_07c.build_plan("timing", ...)`` for the trial specs and their order,
``r2_07c.one_comp`` (R2-10 COMP) and ``r2_07c.one_c`` (COMP+CR, training + compile + admission) per
trial, ``rb10.nw2_one`` for N-W2 and ``rb10.one`` for the default smoke. New here, and only here:

* the pre-registered load gate: a unit (a training invocation, or one AB/BA pair = both arms of one
  class in one round) starts only when the 1-min loadavg is <= 3.0; otherwise the runner waits up
  to 60 s inside the acquisition, polling every 1 s, and if the load never comes down it ends the
  chunk (exit 75) so the caller releases the locks and resumes the SAME units later. Every gate
  attempt is logged to ``load-gate.jsonl``;
* the chunk budget: no new unit starts after ``--budget-s`` seconds in the acquisition (exit 76);
* resume bookkeeping (``progress.json``): a unit is marked started before its first trial and done
  after its last; a unit found started-but-not-done on resume is kept as interrupted and re-run
  under an attempt suffix, so no trial file is ever overwritten;
* the controls plan (carry-over smoke): 1 rep per G4 row per class, N-W2 1 per class, G5
  applied_ack_lost + withheld_unresolved 1 per class, and the default smoke (R2-10 BASE arm, no
  ``CUA_DRIVER_EXP_*`` knob, no phase trace) 5 per class.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
R207C = HERE.parent.parent / "r2-07c-toggle-modal-compiled-2026-10-03" / "harness"
sys.path.insert(0, str(R207C))

LOAD_CEILING = 3.0
WAIT_MAX_S = 60.0
POLL_S = 1.0
EXIT_LOAD = 75
EXIT_BUDGET = 76


def load1() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


def gate(read: Callable[[], float], sleep: Callable[[float], None], clock: Callable[[], float],
         ceiling: float = LOAD_CEILING, wait_max: float = WAIT_MAX_S, poll: float = POLL_S) -> dict[str, Any]:
    """The pre-registered load gate. Start iff a 1-min loadavg read is <= ceiling, waiting at most
    ``wait_max`` seconds (polling every ``poll`` s) for one; otherwise do not start."""
    t0 = clock()
    first = read()
    reads = 1
    if first <= ceiling:
        return {"start": True, "load_first": first, "load_at_start": first, "waited_s": 0.0, "reads": reads}
    last = first
    while clock() - t0 < wait_max:
        sleep(poll)
        last = read()
        reads += 1
        if last <= ceiling:
            return {"start": True, "load_first": first, "load_at_start": last, "waited_s": round(clock() - t0, 3),
                    "reads": reads}
    return {"start": False, "load_first": first, "load_last": last, "waited_s": round(clock() - t0, 3), "reads": reads}


def name_specs(trials: list[dict[str, Any]], prefix: str) -> None:
    """r2_07c.main_async's naming, applied to the FULL plan so names are stable across chunks."""
    for i, spec in enumerate(trials):
        spec.setdefault("arm", "COMP_CR")
        spec.setdefault("block", spec["layer"])
        page = f"-on-{spec['page_cls']}" if spec.get("page_cls") else ""
        extra = f"-{spec['g5_row']}" if spec.get("g5_row") else ""
        spec["name"] = f"{prefix}{i:03d}-{spec['cls']}{page}-{spec['arm']}-{spec['kind']}{extra}-r{spec['round']:02d}"


def units_of(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Training specs are single units; measured trials group into pairs by (round, class), in plan order."""
    units: list[dict[str, Any]] = []
    for spec in trials:
        if spec["kind"] == "train":
            units.append({"key": f"train-{spec['cls']}", "kind": "train", "cls": spec["cls"], "round": spec["round"],
                          "specs": [spec]})
            continue
        key = f"pair-r{spec['round']:02d}-{spec['cls']}"
        if units and units[-1]["key"] == key:
            units[-1]["specs"].append(spec)
        else:
            units.append({"key": key, "kind": "pair", "cls": spec["cls"], "round": spec["round"], "specs": [spec]})
    return units


def controls_plan() -> list[dict[str, Any]]:
    import r2_07c as c

    trials: list[dict[str, Any]] = [{"cls": cls, "kind": "train", "layer": "scripted", "round": 0, "block": "G"}
                                    for cls in c.CLASSES]
    for nk, variant in c.NEG_KINDS.items():
        for cls in c.CLASSES:
            trials.append({"cls": cls, "kind": nk, "variant": variant, "layer": "scripted", "store_layer": "scripted",
                           "round": 0, "block": "N"})
    for cls, page in c.OOD:
        trials.append({"cls": cls, "page_cls": page, "kind": "n8", "layer": "scripted", "store_layer": "scripted",
                       "round": 0, "block": "N"})
    for cls in c.CLASSES:
        trials.append({"cls": cls, "kind": "nw2", "layer": "scripted", "round": 0, "block": "W"})
    for row in ("applied_ack_lost", "withheld_unresolved"):
        g = c.G5_ROWS[row]
        for cls in c.CLASSES:
            trials.append({"cls": cls, "kind": "g5", "g5_row": row, "hold": g["hold"], "barrier": g["barrier"],
                           "layer": "scripted", "store_layer": "scripted", "round": 0, "block": "R"})
    for k in range(5):
        for cls in c.CLASSES:
            trials.append({"cls": cls, "arm": "BASE", "kind": "smoke", "layer": "smoke", "round": k, "block": "D"})
    return trials


async def run_spec(spec: dict[str, Any], args: argparse.Namespace, store: Any, out: Path) -> None:
    import r2_07c as c

    rb10 = c.rb10
    fixtures = c.fx.FixturesC()  # fresh loopback fixture servers per invocation (as r2_07c.main_async)
    try:
        if spec["kind"] == "nw2":
            fixtures.configure("normal", "immediate")
            await rb10.nw2_one({**spec, "arm": "K5"}, args, fixtures, out)
        elif spec["kind"] == "smoke":
            fixtures.configure("normal", "immediate")
            await rb10.one(spec, args, fixtures, rb10.RoutineStore(out / "unused-r210-store"), out)
        elif spec["arm"] == "COMP":
            await c.one_comp(spec, args, fixtures, out)
        else:
            await c.one_c(spec, args, fixtures, store, out)
    finally:
        fixtures.close()


def jdump(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def jappend(path: Path, obj: Any) -> None:
    with path.open("a") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")


async def main_timing(args: argparse.Namespace, out: Path) -> int:
    import r2_07c as c

    store = c.Store(out)
    trials = c.build_plan("timing", 0, args.rounds)
    name_specs(trials, args.prefix)
    units = units_of(trials)
    prog_path = out / "progress.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else {"started": {}, "done": [], "interrupted": []}
    gate_log = out / "load-gate.jsonl"
    t_acq = time.monotonic()
    manifest: dict[str, Any] = {"plan": "timing_q", "rounds": args.rounds, "chunk": args.chunk, "units_total": len(units),
                                "started_utc": c.utc(), "loadavg_start": c.loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": c.rb10.NET["provider_mode"], "units_run": [], "exit": None,
                                "load_ceiling": LOAD_CEILING, "wait_max_s": WAIT_MAX_S, "budget_s": args.budget_s,
                                **c.DRIVER_ID}
    rc = 0
    try:
        for unit in units:
            if unit["key"] in prog["done"]:
                continue
            if time.monotonic() - t_acq > args.budget_s:
                rc = EXIT_BUDGET
                break
            g = gate(load1, time.sleep, time.monotonic)
            jappend(gate_log, {"utc": c.utc(), "chunk": args.chunk, "unit": unit["key"], "kind": unit["kind"],
                               "cls": unit["cls"], "round": unit["round"], "loadavg": c.loadavg(),
                               "decision": "start" if g["start"] else "end_chunk", **g})
            if not g["start"]:
                rc = EXIT_LOAD
                break
            attempt = prog["started"].get(unit["key"], 0) + 1
            if attempt > 1:
                prog["interrupted"].append({"unit": unit["key"], "attempt": attempt - 1})
            prog["started"][unit["key"]] = attempt
            jdump(prog_path, prog)
            for spec in unit["specs"]:
                spec = dict(spec)
                if attempt > 1:
                    spec["name"] = f"{spec['name']}-a{attempt}"
                await run_spec(spec, args, store, out)
            prog["done"].append(unit["key"])
            jdump(prog_path, prog)
            manifest["units_run"].append({"unit": unit["key"], "attempt": attempt, "trials": [s["name"] for s in unit["specs"]],
                                          "load_at_start": g["load_at_start"], "waited_s": g["waited_s"]})
    finally:
        manifest.update({"ended_utc": c.utc(), "loadavg_end": c.loadavg(), "exit": rc,
                         "remaining_units": [u["key"] for u in units if u["key"] not in prog["done"]],
                         "acquisition_s": round(time.monotonic() - t_acq, 3)})
        jdump(out / f"run-manifest-{args.prefix}{args.chunk}.json", manifest)
    return rc


async def main_controls(args: argparse.Namespace, out: Path) -> int:
    import r2_07c as c

    store = c.Store(out)
    trials = controls_plan()
    name_specs(trials, args.prefix)
    sel = trials[args.offset: args.offset + args.count] if args.count else trials[args.offset:]
    manifest: dict[str, Any] = {"plan": "controls", "offset": args.offset, "count": args.count, "chunk": args.chunk,
                                "trials": [s["name"] for s in sel], "plan_size": len(trials), "started_utc": c.utc(),
                                "loadavg_start": c.loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": c.rb10.NET["provider_mode"], **c.DRIVER_ID}
    try:
        for spec in sel:
            if (out / "trials" / f"{spec['name']}.jsonl").exists():
                raise SystemExit(f"refusing: {spec['name']} already exists (never overwrite a trial)")
            await run_spec(spec, args, store, out)
    finally:
        manifest.update({"ended_utc": c.utc(), "loadavg_end": c.loadavg()})
        jdump(out / f"run-manifest-{args.prefix}{args.chunk}.json", manifest)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", required=True, choices=("timing_q", "controls"))
    p.add_argument("--rounds", type=int, default=40)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--prefix", required=True)
    p.add_argument("--chunk", required=True)
    p.add_argument("--budget-s", type=float, default=480.0)
    args = p.parse_args()
    import r2_07c as c

    rb10 = c.rb10
    # r2_07c.main's refusals and Driver identity, unchanged in substance.
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or os.environ.get("R2_07C_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless + cua-x11-session.sh (in_session.sh)")
    for name in (rb10.TRACE_ENV, rb10.SETTLE_ENV, rb10.E_ENV, rb10.V_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    if os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("refusing: Phase S and controls are scripted; the provider key must not be forwarded")
    digest = hashlib.sha256(Path(args.driver).read_bytes()).hexdigest()
    if digest != args.driver_sha256:
        raise SystemExit("refusing: Driver binary sha256 mismatch")
    version = subprocess.run([args.driver, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    c.DRIVER_ID.update({"driver_name": Path(args.driver).name, "driver_sha256": digest, "driver_version": version})
    args.plan_kind = args.plan
    args.save_snapshots = False
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    rc = asyncio.run(main_timing(args, out) if args.plan == "timing_q" else main_controls(args, out))
    sys.exit(rc)


if __name__ == "__main__":
    main()

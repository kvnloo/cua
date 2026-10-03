"""R2-07e runner: alpha-adjusted modal non-regression block (Part Q), carry-over controls (Part C) and
live TypeSafe Phase L per admitted class (Part L) for the compiled fresh-bound toggle/modal routine.

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``driver/run_chunk_e.sh`` -> the R2-07d ``driver/probe_then.sh`` -> the R2-07c ``harness/in_session.sh``.
The locks are taken OUTSIDE, before the session opens.

Everything that touches the Driver, Chromium, the fixture, the oracle or the provider is the R2-07c
harness (blob-identical to 7f46edd16) and the R2-07d runner (blob-identical to 79f6dd299), imported
and called unchanged:

* ``r2_07c.build_plan`` ("timing", "live") for the trial specs and their order;
* ``r2_07d.run_spec`` -> ``r2_07c.one_comp`` (R2-10 COMP), ``r2_07c.one_c`` (COMP+CR training +
  compile + clean-reset admission, warm replay, fallback), ``rb10.nw2_one``, ``rb10.one`` (smoke);
* ``r2_07d.gate`` / ``load1`` (the load gate), ``units_of``, ``name_specs``, ``controls_plan``;
* ``r2_07c.install_provider_ledger_c`` (hard lane cap, counted before sending),
  ``r2_07c.install_model_tap``, ``rb10.enable_live_network``.

New here, and only here:

* ``q_plan``: the R2-07c timing plan for 60 rounds, restricted to the modal class plus a 10-pair
  toggle carry-over sanity block in the same window (toggle kept on rounds TOGGLE_ROUNDS, whose
  parity alternates so the toggle arm order alternates AB/BA), relabelled into store ``timed-e``;
* ``controls_plan_e``: the R2-07d controls plan relabelled into store ``scripted-e``;
* ``live_plan``: the R2-07c live plan (30 rounds) restricted to the admitted classes, plus the
  pre-registered per-class fallback invocations (``FALLBACKS``);
* ``main_live``: r2_07c.main_async's live loop (budget stop with LIVE_RESERVE, one retrain then
  NOT_RUN no_admitted_routine) applied to that plan, with resume bookkeeping. Every invocation
  is kept, NOT_RUN entries stay in the denominators.
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
from typing import Any

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
R207C = EXP / "r2-07c-toggle-modal-compiled-2026-10-03" / "harness"
R207D = EXP / "r2-07d-quiet-timing-phase-l-2026-10-03" / "driver"
sys.path[:0] = [str(R207D), str(R207C)]

import r2_07d as d  # noqa: E402  (imports nothing heavy at module load)

Q_ROUNDS = 60
TOGGLE_ROUNDS = (5, 10, 17, 22, 29, 34, 41, 46, 53, 58)  # 10 pairs, parity alternates (BA, AB, ...)
LIVE_ROUNDS = 30
STORE_Q = "timed-e"
STORE_C = "scripted-e"
# Per-class fallback invocations after round 29 (pre-registered; see PREREG.json part_L.fallback):
#   LF  verdict-bearing forced fallback: precondition fails at the current state (n7_presat: the
#       checkbox starts checked / the dialog starts open), the routine dispatches nothing, the guarded
#       continuation finishes with live decisions; must verify with exactly 1 completion mutation.
#   LN  descriptive negative (the lane spec's literal role+name rename, n1_renamed): the routine refuses
#       at the failed precondition; the task's exact role+name candidate builder never offers the
#       renamed target, so the live continuation cannot verify by construction; must not report
#       success; run only if the budget guard allows it after LF.
FALLBACKS = (("n7", "n7_presat", 30, "LF"), ("n1", "n1_renamed", 31, "LN"))


def c_mod() -> Any:
    import r2_07c as c

    return c


def relabel(spec: dict[str, Any], frm: str, to: str) -> dict[str, Any]:
    for k in ("layer", "store_layer"):
        if spec.get(k) == frm:
            spec[k] = to
    return spec


def q_plan() -> list[dict[str, Any]]:
    """Training (+compile+admission) per class into ``timed-e``, then 60 modal AB/BA pairs and 10
    toggle AB/BA pairs on TOGGLE_ROUNDS, in r2_07c.build_plan('timing') order."""
    c = c_mod()
    out = []
    for spec in c.build_plan("timing", 0, Q_ROUNDS):
        if spec["cls"] == "toggle" and spec["kind"] != "train" and spec["round"] not in TOGGLE_ROUNDS:
            continue
        spec["block"] = "Q" if spec["cls"] == "modal" else "QT"
        out.append(relabel(spec, "timed", STORE_Q))
    return out


def controls_plan_e() -> list[dict[str, Any]]:
    return [relabel(s, "scripted", STORE_C) for s in d.controls_plan()]


def live_plan(classes: list[str], rounds: int = LIVE_ROUNDS) -> list[dict[str, Any]]:
    c = c_mod()
    trials = [s for s in c.build_plan("live", 0, rounds) if s["cls"] in classes]
    for i, (kind, variant, rnd, block) in enumerate(FALLBACKS):
        order = list(classes) if (rnd % 2 == 0) else list(classes)[::-1]
        for cls in order:
            trials.append({"cls": cls, "kind": kind, "variant": variant, "layer": "live", "store_layer": "live",
                           "round": rnd, "block": block})
    return trials


def jdump(path: Path, obj: Any) -> None:
    d.jdump(path, obj)


def jappend(path: Path, obj: Any) -> None:
    d.jappend(path, obj)


async def main_q(args: argparse.Namespace, out: Path) -> int:
    """r2_07d.main_timing with q_plan (load gate per unit, chunk budget, resume bookkeeping)."""
    c = c_mod()
    store = c.Store(out)
    trials = q_plan()
    d.name_specs(trials, args.prefix)
    units = d.units_of(trials)
    if args.max_units:
        units = units[: args.max_units]
    prog_path = out / "progress.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else {"started": {}, "done": [], "interrupted": []}
    gate_log = out / "load-gate.jsonl"
    t_acq = time.monotonic()
    manifest: dict[str, Any] = {"plan": "q", "rounds": Q_ROUNDS, "toggle_rounds": list(TOGGLE_ROUNDS),
                                "chunk": args.chunk, "units_total": len(units), "started_utc": c.utc(),
                                "loadavg_start": c.loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": c.rb10.NET["provider_mode"], "units_run": [], "exit": None,
                                "load_ceiling": d.LOAD_CEILING, "wait_max_s": d.WAIT_MAX_S, "budget_s": args.budget_s,
                                **c.DRIVER_ID}
    rc = 0
    try:
        for unit in units:
            if unit["key"] in prog["done"]:
                continue
            if time.monotonic() - t_acq > args.budget_s:
                rc = d.EXIT_BUDGET
                break
            g = d.gate(d.load1, time.sleep, time.monotonic)
            jappend(gate_log, {"utc": c.utc(), "chunk": args.chunk, "unit": unit["key"], "kind": unit["kind"],
                               "cls": unit["cls"], "round": unit["round"], "loadavg": c.loadavg(),
                               "decision": "start" if g["start"] else "end_chunk", **g})
            if not g["start"]:
                rc = d.EXIT_LOAD
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
                await d.run_spec(spec, args, store, out)
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
    c = c_mod()
    store = c.Store(out)
    trials = controls_plan_e()
    d.name_specs(trials, args.prefix)
    sel = trials[args.offset: args.offset + args.count] if args.count else trials[args.offset:]
    manifest: dict[str, Any] = {"plan": "controls", "offset": args.offset, "count": args.count, "chunk": args.chunk,
                                "trials": [s["name"] for s in sel], "plan_size": len(trials), "started_utc": c.utc(),
                                "loadavg_start": c.loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": c.rb10.NET["provider_mode"], **c.DRIVER_ID}
    try:
        for spec in sel:
            if (out / "trials" / f"{spec['name']}.jsonl").exists():
                raise SystemExit(f"refusing: {spec['name']} already exists (never overwrite a trial)")
            await d.run_spec(spec, args, store, out)
    finally:
        manifest.update({"ended_utc": c.utc(), "loadavg_end": c.loadavg()})
        jdump(out / f"run-manifest-{args.prefix}{args.chunk}.json", manifest)
    return 0


def live_step(spec: dict[str, Any], ledger: dict[str, Any], caps: tuple[int, int], store: Any,
              reserve: int) -> tuple[str, dict[str, Any] | None]:
    """r2_07c.main_async's per-invocation live rules, unchanged in substance:
    budget  -> stop if reached+reserve or attempts+reserve would exceed a cap (this and every later
               invocation NOT_RUN budget);
    warm    -> needs an admitted routine; without one the class retrains once (kind -> train,
               counted like the first), then the class stops (NOT_RUN no_admitted_routine).
    Fallback invocations (LF/LN) also need an admitted routine (else NOT_RUN no_admitted_routine).
    Returns (action, kind_change) with action in run | budget | no_admitted_routine."""
    if ledger["reached"] + reserve > caps[0] or ledger["attempts"] + reserve > caps[1]:
        return "budget", None
    state = store.get("live", spec["cls"])
    admitted = bool(state and state.get("admitted"))
    if spec["kind"] == "warm" and not admitted:
        trainings = int((state or {}).get("trainings", 0))
        if trainings < 2:
            return "run", {"trial": spec["name"], "to": "train", "trainings_before": trainings}
        return "no_admitted_routine", None
    if spec["kind"] not in ("train", "warm") and not admitted:
        return "no_admitted_routine", None
    return "run", None


async def main_live(args: argparse.Namespace, out: Path) -> int:
    c = c_mod()
    rb10 = c.rb10
    store = c.Store(out)
    classes = [x for x in args.classes.split(",") if x]
    trials = live_plan(classes)
    d.name_specs(trials, args.prefix)
    prog_path = out / "live-progress.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else {"started": {}, "done": [], "interrupted": [],
                                                                         "not_run": []}
    t_acq = time.monotonic()
    manifest: dict[str, Any] = {"plan": "live", "classes": classes, "rounds": LIVE_ROUNDS, "chunk": args.chunk,
                                "plan_size": len(trials), "trials": [s["name"] for s in trials], "started_utc": c.utc(),
                                "loadavg_start": c.loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": rb10.NET["provider_mode"],
                                "provider_caps": {"reached": args.cap_reached, "attempts": args.cap_attempts},
                                "ledger_start": {k: c.LEDGER[k] for k in ("attempts", "reached", "blocked")},
                                "kind_changes": [], "not_run": [], "invocations": [], **c.DRIVER_ID}
    models0 = dict(c.MODEL_IDS)
    rc = 0
    stopped: set[str] = set()
    try:
        for idx, spec in enumerate(trials):
            if spec["name"] in prog["done"] or spec["name"] in {x["trial"] for x in prog["not_run"]}:
                continue
            if time.monotonic() - t_acq > args.budget_s:
                rc = d.EXIT_BUDGET
                break
            if spec["cls"] in stopped:
                entry = {"trial": spec["name"], "reason": "no_admitted_routine"}
                prog["not_run"].append(entry)
                manifest["not_run"].append(entry)
                jdump(prog_path, prog)
                continue
            action, change = live_step(spec, c.LEDGER, (args.cap_reached, args.cap_attempts), store, c.LIVE_RESERVE)
            if action == "budget":
                rest = [s for s in trials[idx:] if s["name"] not in prog["done"]]
                entries = [{"trial": s["name"], "reason": "budget"} for s in rest]
                prog["not_run"] += entries
                manifest["not_run"] += entries
                manifest["stopped_for_budget"] = {"at": spec["name"],
                                                  "ledger": {k: c.LEDGER[k] for k in ("attempts", "reached")}}
                jdump(prog_path, prog)
                break
            if action == "no_admitted_routine":
                if spec["kind"] == "warm":
                    stopped.add(spec["cls"])
                entry = {"trial": spec["name"], "reason": "no_admitted_routine"}
                prog["not_run"].append(entry)
                manifest["not_run"].append(entry)
                jdump(prog_path, prog)
                continue
            spec = dict(spec)
            if change:
                manifest["kind_changes"].append(change)
                spec["kind"] = "train"
            attempt = prog["started"].get(spec["name"], 0) + 1
            if attempt > 1:
                prog["interrupted"].append({"trial": spec["name"], "attempt": attempt - 1})
            prog["started"][spec["name"]] = attempt
            jdump(prog_path, prog)
            base_name = spec["name"]
            if attempt > 1:
                spec["name"] = f"{base_name}-a{attempt}"
            await d.run_spec(spec, args, store, out)
            prog["done"].append(base_name)
            jdump(prog_path, prog)
            manifest["invocations"].append({"trial": spec["name"], "kind": spec["kind"], "cls": spec["cls"],
                                            "ledger": {k: c.LEDGER[k] for k in ("attempts", "reached")}})
    finally:
        manifest.update({"ended_utc": c.utc(), "loadavg_end": c.loadavg(), "exit": rc, "network": dict(rb10.NET),
                         "ledger_end": {k: c.LEDGER[k] for k in ("attempts", "reached", "blocked")},
                         "provider_models": {k: v - models0.get(k, 0) for k, v in c.MODEL_IDS.items()
                                             if v - models0.get(k, 0)},
                         "acquisition_s": round(time.monotonic() - t_acq, 3)})
        jdump(out / f"run-manifest-{args.prefix}{args.chunk}.json", manifest)
    return rc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", required=True, choices=("q", "controls", "live"))
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--max-units", type=int, default=0, help="shakedown only: run the first N Q units")
    p.add_argument("--prefix", required=True)
    p.add_argument("--chunk", required=True)
    p.add_argument("--budget-s", type=float, default=480.0)
    p.add_argument("--classes", default="", help="live: comma-separated admitted classes")
    p.add_argument("--provider-ledger")
    p.add_argument("--cap-reached", type=int, default=0)
    p.add_argument("--cap-attempts", type=int, default=0)
    args = p.parse_args()
    c = c_mod()
    rb10 = c.rb10
    # r2_07c.main's refusals and Driver identity, unchanged in substance.
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or os.environ.get("R2_07C_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless + cua-x11-session.sh (in_session.sh)")
    for name in (rb10.TRACE_ENV, rb10.SETTLE_ENV, rb10.E_ENV, rb10.V_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    digest = hashlib.sha256(Path(args.driver).read_bytes()).hexdigest()
    if digest != args.driver_sha256:
        raise SystemExit("refusing: Driver binary sha256 mismatch")
    version = subprocess.run([args.driver, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    c.DRIVER_ID.update({"driver_name": Path(args.driver).name, "driver_sha256": digest, "driver_version": version})
    if args.plan == "live":
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            raise SystemExit("blocked: provider key not forwarded into the session")
        if not args.provider_ledger or args.cap_reached <= 0 or args.cap_attempts <= 0 or not args.classes:
            raise SystemExit("refusing: live needs --provider-ledger, both caps and --classes")
        rb10.enable_live_network()
        c.install_provider_ledger_c(Path(args.provider_ledger), args.cap_reached, args.cap_attempts)
        c.install_model_tap()
    elif os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("refusing: Q and controls are scripted; the provider key must not be forwarded")
    args.plan_kind = args.plan
    args.save_snapshots = False
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    runner = {"q": main_q, "controls": main_controls, "live": main_live}[args.plan]
    sys.exit(asyncio.run(runner(args, out)))


if __name__ == "__main__":
    main()

"""R2-07g runner: quiet toggle non-regression block (Part T), carry-over controls (Part C) and the live
modal forced-fallback re-run plus the toggle literal-rename negative (Part L2) for the compiled
fresh-bound toggle/modal routine on binary R.

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``driver/run_chunk_g.sh`` -> the R2-07d ``driver/probe_then.sh`` -> the R2-07c ``harness/in_session.sh``.
The locks are taken OUTSIDE, before the session opens.

Everything that touches the Driver, Chromium, the fixture, the oracle or the provider is the R2-07c
harness (tree-identical to 7f46edd16), the R2-07d runner (blob-identical to 79f6dd299) and the R2-07e
runner (blob-identical to 67b99ddc6), imported and called unchanged:

* ``r2_07c.build_plan("timing")`` for the Part T trial specs and their order, ``r2_07c.NEG_KINDS`` /
  ``r2_07c.CLASSES`` for the control and fallback variants;
* ``r2_07d.run_spec`` -> ``r2_07c.one_comp`` (R2-10 COMP), ``r2_07c.one_c`` (COMP+CR training + compile +
  clean-reset admission, warm replay, fallback), ``rb10.one`` (default smoke);
* ``r2_07d.gate`` / ``load1`` (the load gate, here with the lane's round-start ceiling 4.0),
  ``units_of``, ``name_specs``, ``jdump``, ``jappend``;
* ``r2_07e.relabel``;
* ``r2_07c.install_provider_ledger_c`` (hard lane cap, counted before sending),
  ``r2_07c.install_model_tap``, ``rb10.enable_live_network``.

New here, and only here (the reviewed plan entry for this lane's specs):

* ``t_plan``: the R2-07c timing plan for 40 rounds restricted to toggle (one training + compile +
  clean-reset admission at round -1, then 40 AB/BA pairs: AB on even rounds, BA on odd), store
  ``timed-g``; ``main_t`` runs it unit by unit behind the round-start load gate (ceiling 4.0);
* ``controls_plan_g``: 1 training (+admission) per class into ``scripted-g``, N4a / N4b / N8 1 per
  class, default smoke 3 per class;
* ``l2_plan`` / ``main_l2``: per class one SCRIPTED training + compile + clean-reset admission into
  ``l2-scripted`` (layer does not start with "live", so the chooser is the scripted one and 0
  provider requests are possible), then modal LF x 3 (``n7_presat``, live continuation), then toggle
  LN x 1 (``n1_renamed``, live continuation); budget stop before an invocation if reached+4 > cap or
  attempts+4 > cap; an LF/LN invocation needs an admitted, authority-clean routine.
  ``--plan l2shake`` is the same plan with the live layer renamed so the chooser stays scripted
  (pre-PREREG plumbing shakedown; the provider key must not be forwarded).
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
R207E = EXP / "r2-07e-modal-gate-phase-l-2026-10-03" / "driver"
sys.path[:0] = [str(R207E)]

import r2_07e as e  # noqa: E402  (puts the R2-07d runner and the R2-07c harness on sys.path)

d = e.d

T_ROUNDS = 40
T_LOAD_CEILING = 4.0
STORE_T = "timed-g"
STORE_C = "scripted-g"
STORE_L = "l2-scripted"
LF_N = 3
CAP_REACHED_MAX = 16
CAP_ATTEMPTS_MAX = 20
N8_PAIRS = (("toggle", "modal"), ("modal", "toggle"))
SMOKE_PER_CLASS = 3


def c_mod() -> Any:
    return e.c_mod()


def t_plan() -> list[dict[str, Any]]:
    """r2_07c.build_plan('timing', 0, 40) restricted to toggle, relabelled into ``timed-g``."""
    c = c_mod()
    out = []
    for spec in c.build_plan("timing", 0, T_ROUNDS):
        if spec["cls"] != "toggle":
            continue
        spec["block"] = "T"
        out.append(e.relabel(spec, "timed", STORE_T))
    return out


def controls_plan_g() -> list[dict[str, Any]]:
    c = c_mod()
    trials: list[dict[str, Any]] = [{"cls": cls, "kind": "train", "layer": STORE_C, "round": 0, "block": "G"}
                                    for cls in c.CLASSES]
    for nk in ("n4a", "n4b"):
        for cls in c.CLASSES:
            trials.append({"cls": cls, "kind": nk, "variant": c.NEG_KINDS[nk], "layer": STORE_C, "store_layer": STORE_C,
                           "round": 0, "block": "N"})
    for cls, page in N8_PAIRS:
        trials.append({"cls": cls, "page_cls": page, "kind": "n8", "layer": STORE_C, "store_layer": STORE_C,
                       "round": 0, "block": "N"})
    for k in range(SMOKE_PER_CLASS):
        for cls in c.CLASSES:
            trials.append({"cls": cls, "arm": "BASE", "kind": "smoke", "layer": "smoke", "round": k, "block": "D"})
    return trials


def l2_plan(live_layer: str = "live") -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = [{"cls": cls, "kind": "train", "layer": STORE_L, "round": -1, "block": "L2T"}
                                    for cls in ("modal", "toggle")]
    for k in range(LF_N):
        trials.append({"cls": "modal", "kind": "n7", "variant": "n7_presat", "layer": live_layer, "store_layer": STORE_L,
                       "round": k, "block": "LF"})
    trials.append({"cls": "toggle", "kind": "n1", "variant": "n1_renamed", "layer": live_layer, "store_layer": STORE_L,
                   "round": LF_N, "block": "LN"})
    return trials


def routine_ready(store: Any, layer: str, cls: str) -> tuple[bool, list[Any] | None]:
    """An LF/LN invocation needs an admitted routine whose artifact passes the authority scan."""
    c = c_mod()
    state = store.get(layer, cls)
    if not (state and state.get("admitted") and state.get("artifact")):
        return False, None
    problems = c.crt.check_artifact_authority_tm(state["artifact"])
    return not problems, problems


def l2_step(spec: dict[str, Any], ledger: dict[str, Any], caps: tuple[int, int], store: Any, reserve: int,
            live: bool) -> str:
    """run | budget | no_admitted_routine. Scripted trainings never touch the provider and are not
    budget-checked; every live invocation is (reached+reserve or attempts+reserve above a cap -> stop)."""
    if spec["kind"] == "train":
        return "run"
    if live and (ledger["reached"] + reserve > caps[0] or ledger["attempts"] + reserve > caps[1]):
        return "budget"
    ok, _ = routine_ready(store, spec["store_layer"], spec["cls"])
    return "run" if ok else "no_admitted_routine"


async def main_t(args: argparse.Namespace, out: Path) -> int:
    """Part T: units in t_plan order behind the round-start load gate (ceiling 4.0); chunk budget and
    resume bookkeeping as r2_07d.main_timing / r2_07e.main_q."""
    c = c_mod()
    store = c.Store(out)
    trials = t_plan()
    d.name_specs(trials, args.prefix)
    units = d.units_of(trials)
    if args.max_units:
        units = units[: args.max_units]
    prog_path = out / "progress.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else {"started": {}, "done": [], "interrupted": []}
    gate_log = out / "load-gate.jsonl"
    t_acq = time.monotonic()
    manifest: dict[str, Any] = {"plan": "t", "rounds": T_ROUNDS, "chunk": args.chunk, "units_total": len(units),
                                "started_utc": c.utc(), "loadavg_start": c.loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": c.rb10.NET["provider_mode"], "units_run": [], "exit": None,
                                "load_ceiling": T_LOAD_CEILING, "wait_max_s": d.WAIT_MAX_S, "budget_s": args.budget_s,
                                **c.DRIVER_ID}
    rc = 0
    try:
        for unit in units:
            if unit["key"] in prog["done"]:
                continue
            if time.monotonic() - t_acq > args.budget_s:
                rc = d.EXIT_BUDGET
                break
            g = d.gate(d.load1, time.sleep, time.monotonic, ceiling=T_LOAD_CEILING)
            d.jappend(gate_log, {"utc": c.utc(), "chunk": args.chunk, "unit": unit["key"], "kind": unit["kind"],
                                 "cls": unit["cls"], "round": unit["round"], "loadavg": c.loadavg(),
                                 "decision": "start" if g["start"] else "end_chunk", **g})
            if not g["start"]:
                rc = d.EXIT_LOAD
                break
            attempt = prog["started"].get(unit["key"], 0) + 1
            if attempt > 1:
                prog["interrupted"].append({"unit": unit["key"], "attempt": attempt - 1})
            prog["started"][unit["key"]] = attempt
            d.jdump(prog_path, prog)
            for spec in unit["specs"]:
                spec = dict(spec)
                if attempt > 1:
                    spec["name"] = f"{spec['name']}-a{attempt}"
                await d.run_spec(spec, args, store, out)
            prog["done"].append(unit["key"])
            d.jdump(prog_path, prog)
            manifest["units_run"].append({"unit": unit["key"], "attempt": attempt, "trials": [s["name"] for s in unit["specs"]],
                                          "load_at_start": g["load_at_start"], "waited_s": g["waited_s"]})
    finally:
        manifest.update({"ended_utc": c.utc(), "loadavg_end": c.loadavg(), "exit": rc,
                         "remaining_units": [u["key"] for u in units if u["key"] not in prog["done"]],
                         "acquisition_s": round(time.monotonic() - t_acq, 3)})
        d.jdump(out / f"run-manifest-{args.prefix}{args.chunk}.json", manifest)
    return rc


async def main_controls(args: argparse.Namespace, out: Path) -> int:
    c = c_mod()
    store = c.Store(out)
    trials = controls_plan_g()
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
        d.jdump(out / f"run-manifest-{args.prefix}{args.chunk}.json", manifest)
    return 0


async def main_l2(args: argparse.Namespace, out: Path, live: bool) -> int:
    c = c_mod()
    rb10 = c.rb10
    store = c.Store(out)
    trials = l2_plan("live" if live else "shake-l2")
    d.name_specs(trials, args.prefix)
    prog_path = out / "live-progress.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else {"started": {}, "done": [], "interrupted": [],
                                                                         "not_run": []}
    t_acq = time.monotonic()
    caps = (args.cap_reached, args.cap_attempts)
    manifest: dict[str, Any] = {"plan": "l2" if live else "l2shake", "chunk": args.chunk, "plan_size": len(trials),
                                "trials": [s["name"] for s in trials], "started_utc": c.utc(),
                                "loadavg_start": c.loadavg(), "display": os.environ.get("DISPLAY"),
                                "provider_mode": rb10.NET["provider_mode"],
                                "provider_caps": {"reached": caps[0], "attempts": caps[1]}, "reserve": c.LIVE_RESERVE,
                                "ledger_start": {k: c.LEDGER[k] for k in ("attempts", "reached", "blocked")},
                                "retrains": [], "not_run": [], "invocations": [], "authority": {}, **c.DRIVER_ID}
    models0 = dict(c.MODEL_IDS)
    rc = 0
    try:
        for idx, spec in enumerate(trials):
            if spec["name"] in prog["done"] or spec["name"] in {x["trial"] for x in prog["not_run"]}:
                continue
            if time.monotonic() - t_acq > args.budget_s:
                rc = d.EXIT_BUDGET
                break
            action = l2_step(spec, c.LEDGER, caps, store, c.LIVE_RESERVE, live)
            if action == "budget":
                rest = [s for s in trials[idx:] if s["name"] not in prog["done"]]
                entries = [{"trial": s["name"], "reason": "budget"} for s in rest]
                prog["not_run"] += entries
                manifest["not_run"] += entries
                manifest["stopped_for_budget"] = {"at": spec["name"],
                                                  "ledger": {k: c.LEDGER[k] for k in ("attempts", "reached")}}
                d.jdump(prog_path, prog)
                break
            if action == "no_admitted_routine":
                ok, problems = routine_ready(store, spec["store_layer"], spec["cls"])
                entry = {"trial": spec["name"], "reason": "no_admitted_routine", "authority_problems": problems}
                prog["not_run"].append(entry)
                manifest["not_run"].append(entry)
                d.jdump(prog_path, prog)
                continue
            attempt = prog["started"].get(spec["name"], 0) + 1
            if attempt > 1:
                prog["interrupted"].append({"trial": spec["name"], "attempt": attempt - 1})
            prog["started"][spec["name"]] = attempt
            d.jdump(prog_path, prog)
            run = dict(spec)
            if attempt > 1:
                run["name"] = f"{spec['name']}-a{attempt}"
            await d.run_spec(run, args, store, out)
            if spec["kind"] == "train":
                ok, problems = routine_ready(store, STORE_L, spec["cls"])
                state = store.get(STORE_L, spec["cls"]) or {}
                if not ok and int(state.get("trainings", 0)) < 2:
                    # one scripted retrain (0 provider requests), kept under its own name
                    re_spec = dict(spec, name=f"{spec['name']}-retrain")
                    manifest["retrains"].append({"trial": spec["name"], "authority_problems": problems})
                    await d.run_spec(re_spec, args, store, out)
                    ok, problems = routine_ready(store, STORE_L, spec["cls"])
                manifest["authority"][spec["cls"]] = {"admitted_and_clean": ok, "problems": problems}
            prog["done"].append(spec["name"])
            d.jdump(prog_path, prog)
            manifest["invocations"].append({"trial": run["name"], "kind": spec["kind"], "cls": spec["cls"],
                                            "ledger": {k: c.LEDGER[k] for k in ("attempts", "reached")}})
    finally:
        manifest.update({"ended_utc": c.utc(), "loadavg_end": c.loadavg(), "exit": rc, "network": dict(rb10.NET),
                         "ledger_end": {k: c.LEDGER[k] for k in ("attempts", "reached", "blocked")},
                         "provider_models": {k: v - models0.get(k, 0) for k, v in c.MODEL_IDS.items()
                                             if v - models0.get(k, 0)},
                         "acquisition_s": round(time.monotonic() - t_acq, 3)})
        d.jdump(out / f"run-manifest-{args.prefix}{args.chunk}.json", manifest)
    return rc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", required=True, choices=("t", "controls", "l2", "l2shake"))
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=0)
    p.add_argument("--max-units", type=int, default=0, help="shakedown only: run the first N T units")
    p.add_argument("--prefix", required=True)
    p.add_argument("--chunk", required=True)
    p.add_argument("--budget-s", type=float, default=600.0)
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
    if args.plan == "l2":
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            raise SystemExit("blocked: provider key not forwarded into the session")
        if not args.provider_ledger or args.cap_reached <= 0 or args.cap_attempts <= 0:
            raise SystemExit("refusing: l2 needs --provider-ledger and both caps")
        if args.cap_reached > CAP_REACHED_MAX or args.cap_attempts > CAP_ATTEMPTS_MAX:
            raise SystemExit(f"refusing: lane caps are {CAP_REACHED_MAX} reached / {CAP_ATTEMPTS_MAX} attempts")
        rb10.enable_live_network()
        c.install_provider_ledger_c(Path(args.provider_ledger), args.cap_reached, args.cap_attempts)
        c.install_model_tap()
    elif os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("refusing: T, controls and l2shake are scripted; the provider key must not be forwarded")
    args.plan_kind = args.plan
    args.save_snapshots = False
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    if args.plan == "t":
        rc = asyncio.run(main_t(args, out))
    elif args.plan == "controls":
        rc = asyncio.run(main_controls(args, out))
    else:
        rc = asyncio.run(main_l2(args, out, live=args.plan == "l2"))
    sys.exit(rc)


if __name__ == "__main__":
    main()

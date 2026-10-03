"""R2-07f runner: compiled replay toggle/modal on binary B7, scripted BASE vs COMP vs COMP+CR in one
5-arm Williams design, with the B-07 stamped stdio client and the B7 phase marks, for the one-binary
decomposition of warm COMP+CR (E2) and the scripted BASE vs COMP+CR S (E3).

MEASUREMENT HARNESS ONLY (caller side). Run inside hostless + cua-x11-session.sh through
``driver/run_chunk_f.sh`` -> the R2-07d ``driver/probe_then.sh`` -> the R2-07c ``harness/in_session.sh``.
The locks are taken OUTSIDE, before the session opens.

Everything that touches the Driver, Chrome, the fixture or the oracle is the R2-07c harness
(``../r2-07c-toggle-modal-compiled-2026-10-03/harness/``, unchanged in this branch), imported and called
unchanged:

* ``r2_07c.one_comp`` (R2-10's own COMP trial, ``rb10.one``), ``r2_07c.one_c`` (COMP+CR: training +
  compile + clean-reset admission, warm replay with a fresh semantic_v2 observation per click and 0
  decisions, guarded continuation on a failed precondition), ``rb10.one`` (BASE arm and the default
  smoke), ``rb10.nw2_one`` (FIX-01 N-W2);
* the R2-07c control kinds (n1 renamed, n4a stale ref, n4b superseding snapshot, n5 session replaced,
  n7 precondition already satisfied, n8 wrong page) through ``one_c``.

New here, caller side only (no Driver change, no new service):

* the MCP stdio client is B-08's copy of B-07's stamped client (``b08/harness/b07/b07_stdio.py``,
  blob-identical from 49ae94590) in its default variant: it adds the caller stamps that B-05's sub-span
  decomposition needs and is identical in every arm (B-08 installs it the same way);
* the Driver identity (name, sha256, version) is written into EVERY trial record: ``one_c`` already
  does it through ``r2_07c.DRIVER_ID``; ``rb10.run_trial`` (BASE, COMP, smoke) and
  ``run_b02.control_trial`` (N-W2) are wrapped to add it to the trial result, which their records
  merge (the same wrapping B-08 uses for N-W2);
* the lane arm label and design position (``f_arm``, ``williams_seq``, ``pos_in_round``, ``attempt``,
  ``lock_mode``) are added to the trial result the same way (``rb10.run_trial`` / ``r2_07c.run_trial_c``
  wrappers); nothing else in a trial changes;
* arm PC = CRa plus a 15.0 ms CLOCK_MONOTONIC sleep INSIDE T right after snapshot1 returns (B-08's
  ``precise_sleep_ns``; ``PCRecDriver`` is used for PC trials only, by swapping ``r2_07c.RecDriverC``
  for the duration of the trial);
* the 5-arm Williams design (10 sequences = ``rc.williams(5)`` plus its row reversals), 40 rounds per
  class, class order alternating per round; the pre-registered load gate per round (1-min loadavg
  <= 4.0, wait <= 60 s, else end the chunk with exit 75); a chunk budget (exit 76); resume bookkeeping
  (a round started but not done is kept and re-run under an attempt suffix; no trial file is ever
  overwritten).

Plans: ``ident`` (Driver/Chrome identity in the session), ``pilot`` (<= 10 trials, SHARED, excluded),
``train`` (per class training + compile + clean-reset admission into the lane-local store, timed),
``main`` (the 40 measured rounds), ``fallback`` (n7_presat forced fallback, 3 per class),
``controls`` (N4a, N4b, N5, N8, N-W2, N1, default smoke).
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
PKT = HERE.parent
EXP = PKT.parent
R207C = EXP / "r2-07c-toggle-modal-compiled-2026-10-03" / "harness"
B07 = PKT / "b08" / "harness" / "b07"

CLASSES = ("toggle", "modal")
CLASS_INDEX = {"toggle": 0, "modal": 1}
ARMS = ("BASE", "COMP", "CRa", "CRb", "PC")
CR_ARMS = {"CRa", "CRb", "PC"}
ROUNDS = 40
STORE = "timed-f"
P_SLEEP_NS = 15_000_000
LOAD_MAX = 4.0
LOAD_WAIT_S = 60.0
EXIT_LOAD = 75
EXIT_BUDGET = 76
B7_NAME = "cua-driver-b07-231f6e8bb"
B7_SHA256 = "6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa"
B7_VERSION = "cua-driver 0.32.0"
FALLBACK_REPS = 3
CONTROL_REPS = 2
SMOKE_REPS = 5
OOD = (("toggle", "fill"), ("toggle", "modal"), ("modal", "toggle"))


def williams_rows(base: list[list[int]]) -> list[list[int]]:
    """Williams design for an odd number of treatments: the cyclic rows plus each row reversed
    (2n sequences; every ordered pair of distinct arms is adjacent equally often)."""
    return [list(r) for r in base] + [list(reversed(r)) for r in base]


def class_order(r: int) -> tuple[str, ...]:
    return CLASSES if r % 2 == 0 else CLASSES[::-1]


def round_specs(r: int, rows: list[list[int]], prefix: str = "M") -> list[dict[str, Any]]:
    """One measured round: per class (alternating order) one Williams sequence over the 5 arms,
    sequence index (r + class index) mod 10, so over 40 rounds every class runs every sequence 4 times."""
    out: list[dict[str, Any]] = []
    for cls in class_order(r):
        seq_i = (r + CLASS_INDEX[cls]) % len(rows)
        for pos, j in enumerate(rows[seq_i]):
            f_arm = ARMS[j]
            out.append({"cls": cls, "f_arm": f_arm, "round": r, "williams_seq": seq_i, "pos_in_round": pos,
                        "block": "M", "layer": STORE, "name": f"{prefix}-r{r:02d}-{cls}-{f_arm}"})
    return out


def train_specs(prefix: str = "T") -> list[dict[str, Any]]:
    return [{"cls": cls, "f_arm": "TRAIN", "kind": "train", "layer": STORE, "round": -1, "block": "T",
             "name": f"{prefix}-{cls}-train"} for cls in CLASSES]


def fallback_specs(prefix: str = "F") -> list[dict[str, Any]]:
    out = []
    for k in range(FALLBACK_REPS):
        for cls in (CLASSES if k % 2 == 0 else CLASSES[::-1]):
            out.append({"cls": cls, "f_arm": "FB", "kind": "n7", "variant": "n7_presat", "layer": STORE,
                        "store_layer": STORE, "round": k, "block": "F", "name": f"{prefix}-{k:02d}-{cls}-n7"})
    return out


def control_specs(prefix: str = "C") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    i = 0

    def add(spec: dict[str, Any]) -> None:
        nonlocal i
        page = f"-on-{spec['page_cls']}" if spec.get("page_cls") else ""
        spec["name"] = f"{prefix}-{i:03d}-{spec['cls']}{page}-{spec['kind']}"
        out.append(spec)
        i += 1

    variants = {"n4a": "normal", "n4b": "normal", "n5": "normal", "n1": "n1_renamed"}
    for k in range(CONTROL_REPS):
        for kind, variant in variants.items():
            for cls in CLASSES:
                add({"cls": cls, "f_arm": "CTL", "kind": kind, "variant": variant, "layer": STORE,
                     "store_layer": STORE, "round": k, "block": "C"})
        for cls, page in OOD:
            add({"cls": cls, "page_cls": page, "f_arm": "CTL", "kind": "n8", "layer": STORE, "store_layer": STORE,
                 "round": k, "block": "C"})
        for cls in CLASSES:
            add({"cls": cls, "f_arm": "NW2", "kind": "nw2", "layer": "scripted", "round": k, "block": "W"})
    for k in range(SMOKE_REPS):
        for cls in CLASSES:
            add({"cls": cls, "f_arm": "SMOKE", "arm": "BASE", "kind": "smoke", "layer": "smoke", "round": k,
                 "block": "D"})
    return out


def pilot_specs() -> list[dict[str, Any]]:
    """<= 10 trials under the SHARED lock, store 'pilot': harness compatibility of the R2-07c runner with
    B7 (training + admission per class, then BASE, COMP, CRa, PC on toggle). Excluded from results."""
    out = [{"cls": "toggle", "f_arm": "TRAIN", "kind": "train", "layer": "pilot", "round": -1, "block": "P",
            "name": "P-toggle-train"}]
    for f_arm in ("BASE", "COMP", "CRa", "PC"):
        out.append({"cls": "toggle", "f_arm": f_arm, "round": 0, "williams_seq": None, "pos_in_round": None,
                    "block": "P", "layer": "pilot", "name": f"P-r00-toggle-{f_arm}"})
    out.append({"cls": "modal", "f_arm": "TRAIN", "kind": "train", "layer": "pilot", "round": -1, "block": "P",
                "name": "P-modal-train"})
    out.append({"cls": "modal", "f_arm": "CRa", "round": 0, "williams_seq": None, "pos_in_round": None,
                "block": "P", "layer": "pilot", "name": "P-r00-modal-CRa"})
    return out  # 2 trainings x (training + admission) + 5 = 9 trial records


# ── everything below needs the jev-use environment (imported lazily so the plan code unit-tests
#    without it) ─────────────────────────────────────────────────────────────────────────────────

M: dict[str, Any] = {}
DRIVER_ID: dict[str, Any] = {}
TRIAL_META: dict[str, Any] = {}


async def precise_sleep_ns(ns: int) -> int:
    """Sleep ``ns`` on CLOCK_MONOTONIC (asyncio sleep to ~1 ms before, then a short spin); returns the
    actual slept ns (B-08 run_b08.precise_sleep_ns)."""
    t0 = time.monotonic_ns()
    target = t0 + ns
    coarse = (target - time.monotonic_ns() - 1_000_000) / 1e9
    if coarse > 0:
        await asyncio.sleep(coarse)
    while time.monotonic_ns() < target:
        pass
    return time.monotonic_ns() - t0


def meta_of(spec: dict[str, Any]) -> dict[str, Any]:
    return {"f_arm": spec.get("f_arm"), "williams_seq": spec.get("williams_seq"),
            "pos_in_round": spec.get("pos_in_round"), "f_round": spec.get("round"), **TRIAL_META}


def install() -> None:
    """Import the R2-07c harness and the B-07 stamped client; install the caller-side wrappers."""
    sys.path[:0] = [str(R207C), str(B07)]
    import r2_07c as c  # noqa: E402
    import b07_stdio as bs  # noqa: E402

    rb10, rc, rb = c.rb10, c.rc, c.rb
    rc.stdio_client = bs.stdio_client  # rb10.run_trial / r2_07c.run_trial_c / run_b02 resolve it at call time
    bs.install()
    bs.STAMP["rec_fn"] = lambda: rc.CLIENT["rec"]
    assert bs.STAMP["prep"] == "default" and bs.STAMP["route"] == "default"

    orig_rt = rb10.run_trial
    orig_rtc = c.run_trial_c
    orig_ct = rb.control_trial
    base_drv = c.RecDriverC

    class PCRecDriver(base_drv):  # type: ignore[misc, valid-type]
        """Arm PC: 15.0 ms CLOCK_MONOTONIC sleep inside T right after snapshot1 returns."""

        async def call(self, name: str, arguments: dict[str, Any], label: str | None = None) -> dict[str, Any]:
            first = (name == "get_browser_state" and arguments.get("snapshot_format") == "semantic_v2"
                     and label is None and self.n_snap == 0)
            data = await super().call(name, arguments, label)
            if first:
                self.rec.add("pc_sleep_start", target_ns=P_SLEEP_NS, placement="after_snapshot1")
                slept = await precise_sleep_ns(P_SLEEP_NS)
                self.rec.add("pc_sleep_end", slept_ns=slept)
            return data

    async def run_trial_wrapped(spec, args, fixtures, store, trace_path, rec, result):  # noqa: ANN001
        result.update({**DRIVER_ID, **meta_of(spec)})
        await orig_rt(spec, args, fixtures, store, trace_path, rec, result)

    async def run_trial_c_wrapped(spec, args, fixtures, store, trace_path, rec, result):  # noqa: ANN001
        result.update(meta_of(spec))
        pc = spec.get("f_arm") == "PC"
        if pc:
            c.RecDriverC = PCRecDriver
        try:
            await orig_rtc(spec, args, fixtures, store, trace_path, rec, result)
        finally:
            c.RecDriverC = base_drv

    async def control_trial_wrapped(spec, args, fixtures, trace_path, rec, result):  # noqa: ANN001
        result.update({**DRIVER_ID, **meta_of(spec)})
        await orig_ct(spec, args, fixtures, trace_path, rec, result)

    rb10.run_trial = run_trial_wrapped
    c.run_trial_c = run_trial_c_wrapped
    rb.control_trial = control_trial_wrapped
    M.update({"c": c, "rb10": rb10, "rc": rc, "rb": rb, "bs": bs, "PCRecDriver": PCRecDriver})


async def run_spec(spec: dict[str, Any], args: argparse.Namespace, store: Any, out: Path) -> None:
    """One trial with fresh loopback fixture servers (as r2_07c.main_async / r2_07d.run_spec)."""
    c, rb10 = M["c"], M["rb10"]
    if (out / "trials" / f"{spec['name']}.jsonl").exists():
        raise SystemExit(f"refusing: {spec['name']} already exists (never overwrite a trial)")
    fixtures = c.fx.FixturesC()
    f_arm = spec.get("f_arm")
    try:
        if spec.get("kind") == "nw2":
            fixtures.configure("normal", "immediate")
            await rb10.nw2_one({**spec, "arm": "K5"}, args, fixtures, out)
        elif spec.get("kind") == "smoke":
            fixtures.configure("normal", "immediate")
            await rb10.one({**spec, "arm": "BASE"}, args, fixtures, rb10.RoutineStore(out / "unused-r210-store"), out)
        elif f_arm == "BASE":
            fixtures.configure("normal", "immediate")
            await rb10.one({**spec, "arm": "BASE", "kind": "measured"}, args, fixtures,
                           rb10.RoutineStore(out / "unused-r210-store"), out)
        elif f_arm == "COMP":
            await c.one_comp({**spec, "arm": "COMP", "kind": "measured"}, args, fixtures, out)
        elif f_arm in CR_ARMS:
            await c.one_c({**spec, "arm": "COMP_CR", "kind": "warm", "store_layer": spec["layer"]}, args, fixtures,
                          store, out)
        else:  # TRAIN / FB / CTL: the R2-07c kinds through one_c
            await c.one_c({**spec, "arm": "COMP_CR"}, args, fixtures, store, out)
    finally:
        fixtures.close()


def load1() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


def load_gate(read=load1, sleep=time.sleep, clock=time.monotonic, ceiling: float = LOAD_MAX,  # noqa: ANN001
              wait_max: float = LOAD_WAIT_S, poll: float = 1.0) -> dict[str, Any]:
    """Start iff a 1-min loadavg read is <= ceiling, waiting at most wait_max s (1 s polls)."""
    t0 = clock()
    first = read()
    if first <= ceiling:
        return {"start": True, "load_first": first, "load_at_start": first, "waited_s": 0.0, "reads": 1}
    last, reads = first, 1
    while clock() - t0 < wait_max:
        sleep(poll)
        last = read()
        reads += 1
        if last <= ceiling:
            return {"start": True, "load_first": first, "load_at_start": last, "waited_s": round(clock() - t0, 3),
                    "reads": reads}
    return {"start": False, "load_first": first, "load_last": last, "waited_s": round(clock() - t0, 3), "reads": reads}


def jdump(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def jappend(path: Path, obj: Any) -> None:
    with path.open("a") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")


def units_for(plan: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    """A unit is gated and resumed as a whole: a measured round (10 trials), a training (training +
    admission), one fallback invocation, or one control trial."""
    if plan == "main":
        rows = williams_rows(M["rc"].williams(5)) if M else williams_rows(_williams(5))
        rounds = range(args.start_round, min(ROUNDS, args.start_round + args.rounds))
        return [{"key": f"round-{r:02d}", "specs": round_specs(r, rows)} for r in rounds]
    if plan == "train":
        return [{"key": s["name"], "specs": [s]} for s in train_specs()]
    if plan == "fallback":
        return [{"key": s["name"], "specs": [s]} for s in fallback_specs()]
    if plan == "controls":
        return [{"key": s["name"], "specs": [s]} for s in control_specs()]
    if plan == "pilot":
        return [{"key": s["name"], "specs": [s]} for s in pilot_specs()]
    raise ValueError(plan)


def _williams(n: int) -> list[list[int]]:
    """Same construction as run_critpath.williams (used only when the harness is not imported)."""
    first, lo, hi, take_lo = [0], 1, n - 1, True
    while len(first) < n:
        first.append(lo if take_lo else hi)
        lo, hi = (lo + 1, hi) if take_lo else (lo, hi - 1)
        take_lo = not take_lo
    return [[(x + i) % n for x in first] for i in range(n)]


async def main_units(args: argparse.Namespace, out: Path) -> int:
    c = M["c"]
    store = c.Store(Path(args.routines) if args.routines else out)
    units = units_for(args.plan, args)
    prog_path = out / f"progress-{args.plan}.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else {"started": {}, "done": [], "interrupted": []}
    gate_log = out / "load-gate.jsonl"
    t_acq = time.monotonic()
    manifest: dict[str, Any] = {"plan": args.plan, "chunk": args.chunk, "units_total": len(units),
                                "started_utc": c.utc(), "loadavg_start": c.loadavg(),
                                "display_set": bool(os.environ.get("DISPLAY")),
                                "provider_mode": c.rb10.NET["provider_mode"], "units_run": [], "exit": None,
                                "load_max": LOAD_MAX, "load_wait_s": LOAD_WAIT_S, "budget_s": args.budget_s,
                                "lock_mode": TRIAL_META.get("lock_mode"), "caller_variant":
                                {"prep": M["bs"].STAMP["prep"], "route": M["bs"].STAMP["route"]}, **DRIVER_ID}
    rc_exit = 0
    try:
        for unit in units:
            if unit["key"] in prog["done"]:
                continue
            if time.monotonic() - t_acq > args.budget_s:
                rc_exit = EXIT_BUDGET
                break
            g = load_gate()
            jappend(gate_log, {"utc": c.utc(), "chunk": args.chunk, "plan": args.plan, "unit": unit["key"],
                               "loadavg": c.loadavg(), "decision": "start" if g["start"] else "end_chunk", **g})
            if not g["start"]:
                rc_exit = EXIT_LOAD
                break
            attempt = prog["started"].get(unit["key"], 0) + 1
            if attempt > 1:
                prog["interrupted"].append({"unit": unit["key"], "attempt": attempt - 1})
            prog["started"][unit["key"]] = attempt
            jdump(prog_path, prog)
            TRIAL_META["attempt"] = attempt
            TRIAL_META["chunk"] = args.chunk
            for spec in unit["specs"]:
                spec = dict(spec)
                if attempt > 1:
                    spec["name"] = f"{spec['name']}-a{attempt}"
                await run_spec(spec, args, store, out)
            prog["done"].append(unit["key"])
            jdump(prog_path, prog)
            manifest["units_run"].append({"unit": unit["key"], "attempt": attempt,
                                          "trials": [s["name"] + (f"-a{attempt}" if attempt > 1 else "")
                                                     for s in unit["specs"]],
                                          "load_at_start": g["load_at_start"], "waited_s": g["waited_s"]})
    finally:
        manifest.update({"ended_utc": c.utc(), "loadavg_end": c.loadavg(), "exit": rc_exit,
                         "remaining_units": [u["key"] for u in units if u["key"] not in prog["done"]],
                         "network": dict(c.rb10.NET), "acquisition_s": round(time.monotonic() - t_acq, 3)})
        jdump(out / f"run-manifest-{args.plan}-{args.chunk}.json", manifest)
    return rc_exit


def driver_identity(path: str, want_sha: str) -> dict[str, Any]:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != want_sha:
        raise SystemExit("refusing: Driver binary sha256 mismatch")
    version = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    ident = {"driver_name": Path(path).name, "driver_sha256": digest, "driver_version": version}
    if (ident["driver_name"], ident["driver_sha256"], ident["driver_version"]) != (B7_NAME, B7_SHA256, B7_VERSION):
        raise SystemExit(f"refusing: not binary B7 ({ident})")
    return ident


def ident_plan(args: argparse.Namespace, out: Path) -> int:
    """In-session identity read: Driver name/sha256/version and the Driver-chosen Chrome's version."""
    chrome = {}
    for exe in ("/opt/google/chrome/chrome", "/usr/lib/chromium/chromium"):
        if Path(exe).exists():
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
            chrome[Path(exe).name] = (r.stdout or r.stderr).strip()
    doc = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "where": "in_session", **DRIVER_ID,
           "browsers": chrome, "loadavg": Path("/proc/loadavg").read_text().strip()}
    jdump(out / f"ident-{args.chunk}.json", doc)
    print(json.dumps(doc))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", required=True, choices=("ident", "pilot", "train", "main", "fallback", "controls"))
    p.add_argument("--chunk", required=True)
    p.add_argument("--start-round", type=int, default=0)
    p.add_argument("--rounds", type=int, default=ROUNDS)
    p.add_argument("--budget-s", type=float, default=700.0)
    p.add_argument("--routines", help="directory holding routines/ (defaults to --out)")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY") or os.environ.get("R2_07C_OUTER_HOSTLESS") != "1":
        raise SystemExit("refusing: run through hostless + cua-x11-session.sh (in_session.sh)")
    if os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("refusing: this lane is scripted (TypeSafe cap 0); the provider key must not be forwarded")
    lock = os.environ.get("R2_07F_LOCK")
    if args.plan in ("train", "main", "fallback") and lock != "exclusive":
        raise SystemExit("refusing: measured plans need R2_07F_LOCK=exclusive (quiet-timed + cargo lock)")
    if args.plan in ("pilot", "controls", "ident") and lock not in ("shared", "exclusive"):
        raise SystemExit("refusing: pilot/controls/ident need the quiet-lane lock (R2_07F_LOCK)")
    DRIVER_ID.update(driver_identity(args.driver, args.driver_sha256))
    TRIAL_META.update({"lock_mode": lock, "plan": args.plan})
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    if args.plan == "ident":
        sys.exit(ident_plan(args, out))
    install()
    c, rb10 = M["c"], M["rb10"]
    for name in (rb10.TRACE_ENV, rb10.SETTLE_ENV, rb10.E_ENV, rb10.V_ENV):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    c.DRIVER_ID.update(DRIVER_ID)
    os.environ.pop("TYPESAFE_API_KEY", None)
    args.plan_kind = args.plan
    args.save_snapshots = False
    sys.exit(asyncio.run(main_units(args, out)))


if __name__ == "__main__":
    main()

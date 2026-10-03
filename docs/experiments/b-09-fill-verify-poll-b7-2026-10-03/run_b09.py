"""B-09 runner: fill compiled-routine verify poll on binary B7 (measurement only). Derived from B-08's
run_b08.py (blob-identical copy in this lane's first commit; this file's git history shows every change).

Run inside hostless + cua-x11-session.sh with the jev-use virtualenv of this worktree:

    JEV_USE_DIR=<jev-use> <venv>/python run_b09.py --driver <bin> --driver-sha256 <hex> --out <dir> \
        --plan {main|pilot|ctl} --rounds 0-11 [--block m] [--attempt 1] [--budget-s 780]

The runner takes no lock itself. The caller takes the EXCLUSIVE quiet-lane lock (bin/quiet-timed, ledger
receipt) and, inside it, the cargo-build lock with ``flock -w 60`` OUTSIDE the session, and says so through
B09_LOCK=exclusive (forwarded into the session); a pilot runs under the SHARED lock
(lane-scripts/shared-locked.sh, B09_LOCK=shared) and is excluded from every analysis.

Everything trial-level is B-04's runner, imported unchanged from harness/b04/run_b04.py with its own
harness/ dependencies (blob-identical copies from 49ae94590, except harness/b04/harness/compiled_routine.py,
which gains B-09's env-gated, default-off verify-poll interval and stamps): fixtures with server
CLOCK_MONOTONIC journals, the 2 ms independent ``Sampler`` oracle, the ``ObsDriver`` call labels, R2-10's
step loop, R2-10's COMP / DEFAULT environments, ``rc.one`` bookkeeping. The compiled fill routine is R2-10R's
scripted COMP artifact (harness/r2-10r/scripted-COMP.json); its ``artifact`` must equal B-04's copy. The MCP
client is B-07's stamped stdio client in its default variant, as in B-08.

B-09 changes against run_b08.py (caller side only; no Driver change):

- fill only, every trial cold (the task document is the process's first; no warm-up);
- arms BASE / P10a / P10b / P1 / P0 / PC in one 6x6 Williams square (rc.williams(6)), round r runs row
  r mod 6, 36 rounds = 6 squares:
    BASE  R2-10 BASE = B-04 ``DEFAULT`` (feedback on, default glide, no guard, 100 ms poll, library
          validators, no CUA_DRIVER_EXP_*), step loop;
    P10a  R2-10 scripted COMP fill as B-08 C (compiled replay + guarded completion), verify poll unset
          (= the routine's 10 ms);
    P10b  identical to P10a, second label (A/A negative control);
    P1    P10a with CUA_LANE_EXP_ROUTINE_POLL_MS=1;
    P0    P10a with CUA_LANE_EXP_ROUTINE_POLL_MS=0 (a bare event-loop yield between reads);
    PC    P10a with CUA_LANE_EXP_PC_SLEEP_MS=15: a 15.0 ms CLOCK_MONOTONIC sleep inside T right after
          snapshot1 returns (positive control, as B-08 P2);
- the lane variables are set in this runner's own process for the trial only (the compiled routine and
  this runner read them; the Driver environment never carries CUA_LANE_EXP_*) and recorded per trial;
- the compiled routine's stamps (routine_read_send / routine_read_return around each routine oracle read,
  poll_sleep_start / poll_sleep_end around each verify-poll sleep) go to the trial recorder
  (``compiled_routine.STAMP = rec.add``, reset after the trial);
- plan ``ctl`` (after the measured rounds): 5 SMOKE (product default, no lane variable) and 3 FIX-01 N-W2
  detached-node refusal controls, fill;
- the Driver identity (name, sha256, version) is written into every trial record, every control record
  and every manifest; the runner refuses on a sha256 mismatch.

task_start = the return of the task ``browser_navigate`` (R2-10 rule). The load rule is applied before every
round: a round starts only when the 1-min loadavg is <= --load-max; otherwise the runner waits up to
--load-wait-s (1 s polls), and if it is still high it ends the chunk (exit 75). Output paths are relative
to --out.
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
sys.path.insert(0, str(HERE / "harness" / "b04"))
sys.path.insert(0, str(HERE / "harness" / "b07"))

import run_b04 as B4  # noqa: E402  (B-04 runner copy; imports its harness/ and jev-use)
import b07_stdio as bs  # noqa: E402  (blob-identical B-07 stamped stdio client, default variant)

rc, R2, cr = B4.rc, B4.R2, B4.cr
rc.stdio_client = bs.stdio_client  # b09_trial and run_b02.control_trial resolve rc.stdio_client at call time
bs.install()
bs.STAMP["rec_fn"] = lambda: rc.CLIENT["rec"]
assert bs.STAMP["prep"] == "default" and bs.STAMP["route"] == "default"

ROUTINE_DOC = json.loads((HERE / "harness" / "r2-10r" / "scripted-COMP.json").read_text())
ROUTINE = ROUTINE_DOC["artifact"]
assert ROUTINE == B4.ROUTINE, "R2-10R scripted COMP artifact differs from B-04's copy"
cr.require_clean(ROUTINE)
assert cr.Routine.VERIFY_INTERVAL_S == 0.010 and cr.Routine.VERIFY_DEADLINE_S == 2.0  # set by run_b04 (R2-10)

POLL_ENV = cr.POLL_ENV                       # CUA_LANE_EXP_ROUTINE_POLL_MS
PC_ENV = "CUA_LANE_EXP_PC_SLEEP_MS"
LANE_ENVS = (POLL_ENV, PC_ENV)
CONFIG = {"BASE": "DEFAULT", "P10a": "COMP", "P10b": "COMP", "P1": "COMP", "P0": "COMP", "PC": "COMP",
          "SMOKE": "DEFAULT"}
LANE_ENV = {"BASE": {}, "P10a": {}, "P10b": {}, "P1": {POLL_ENV: "1"}, "P0": {POLL_ENV: "0"},
            "PC": {PC_ENV: "15"}, "SMOKE": {}}
SQUARE_ARMS = ["BASE", "P10a", "P10b", "P1", "P0", "PC"]   # williams(6) index -> arm
CLS = "fill"
MAIN_ROUNDS = 36
CTL_ROUND = 36
SMOKE_N = 5
NW2_N = 3
TELEMETRY_ENV = "CUA_DRIVER_RS_TELEMETRY_ENABLED"
TELEMETRY_OFF = "false"
PREWARM_ENV = "CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM"
DRIVER_ID: dict[str, Any] = {}

_b4_driver_env_for = B4.driver_env_for


def driver_env_for(arm: dict[str, Any], cls: str, trace_path: Path | None) -> dict[str, str]:
    """B-04's driver_env_for (EXP_* stripped, arm knobs, trace file, settle 0 on fill) with telemetry 'false'."""
    env = _b4_driver_env_for(arm, cls, trace_path)
    env[TELEMETRY_ENV] = TELEMETRY_OFF
    env["DO_NOT_TRACK"] = "1"
    assert PREWARM_ENV not in env
    assert not any(k.startswith("CUA_LANE_EXP_") for k in env), "lane variables must not reach the Driver"
    return env


B4.driver_env_for = driver_env_for


def set_lane_env(values: dict[str, str]) -> dict[str, str | None]:
    """Set exactly ``values`` among LANE_ENVS in this process (others unset); returns what is now set."""
    for k in LANE_ENVS:
        os.environ.pop(k, None)
    os.environ.update(values)
    return {k: os.environ.get(k) for k in LANE_ENVS}


def pc_sleep_ns() -> int:
    raw = os.environ.get(PC_ENV)
    if raw is None or not raw.strip():
        return 0
    ms = float(raw)
    if not 0.0 < ms <= 100.0:
        raise ValueError(f"{PC_ENV}={raw!r} outside (0, 100]")
    return int(round(ms * 1_000_000))


# ── process identity (read-only /proc of this runner's own process tree) ──────────────────────

def proc_ident(pid: int | None) -> dict[str, Any] | None:
    if not pid:
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return {"pid": pid, "alive": False}
    rest = stat.rsplit(")", 1)[1].split()
    try:
        exe = os.path.basename(os.readlink(f"/proc/{pid}/exe"))
    except OSError as error:
        exe = f"unreadable:{type(error).__name__}"
    return {"pid": pid, "alive": rest[0] not in ("Z", "X"), "state": rest[0], "ppid": int(rest[1]),
            "starttime": int(rest[19]), "exe": exe}


def child_pids() -> list[int]:
    out: set[int] = set()
    try:
        for tid in os.listdir("/proc/self/task"):
            try:
                out |= {int(x) for x in Path(f"/proc/self/task/{tid}/children").read_text().split()}
            except OSError:
                continue
    except OSError:
        pass
    if not out:  # fallback: scan /proc for our children
        me = os.getpid()
        for d in os.listdir("/proc"):
            if d.isdigit():
                try:
                    if int(Path(f"/proc/{d}/stat").read_text().rsplit(")", 1)[1].split()[1]) == me:
                        out.add(int(d))
                except (OSError, IndexError, ValueError):
                    continue
    return sorted(out)


def find_driver_pid(driver_name: str) -> int | None:
    for pid in child_pids():
        ident = proc_ident(pid)
        if ident and ident.get("exe") == driver_name and ident.get("alive"):
            return pid
    return None


def pids_now(result: dict[str, Any]) -> dict[str, Any]:
    return {"driver": proc_ident(result.get("driver_pid")), "chrome": proc_ident(result.get("chrome_pid"))}


async def precise_sleep_ns(ns: int) -> int:
    """Sleep ``ns`` on CLOCK_MONOTONIC (asyncio sleep to ~1 ms before, then a short spin); returns the
    actual slept ns."""
    t0 = time.monotonic_ns()
    target = t0 + ns
    coarse = (target - time.monotonic_ns() - 1_000_000) / 1e9
    if coarse > 0:
        await asyncio.sleep(coarse)
    while time.monotonic_ns() < target:
        pass
    return time.monotonic_ns() - t0


class SleepAfterFirstObs(B4.ObsDriver):
    """Arm PC: a CUA_LANE_EXP_PC_SLEEP_MS CLOCK_MONOTONIC sleep INSIDE T, immediately after the first
    semantic_v2 observation (snapshot1) returns and before the next Driver call."""

    def __init__(self, *a: Any, result: dict[str, Any], sleep_ns: int, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.result = result
        self.sleep_ns = sleep_ns

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        first = (name == "get_browser_state" and arguments.get("snapshot_format") == "semantic_v2"
                 and not self.first_done)
        data = await super().call(name, arguments)
        if first:
            self.rec.add("pc_sleep_start", target_ns=self.sleep_ns, placement="after_snapshot1")
            slept = await precise_sleep_ns(self.sleep_ns)
            self.rec.add("pc_sleep_end", slept_ns=slept)
            self.result["pc_sleep_ns"] = slept
        return data


# ── trial ───────────────────────────────────────────────────────────────────────────────────

async def b09_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, trace_path: Path | None,
                    rec: Any, result: dict[str, Any]) -> None:
    cls, b09_arm = spec["cls"], spec["b09_arm"]
    cfg_name = CONFIG[b09_arm]
    arm = B4.ARMS[cfg_name]
    token = f"jev-{rc.uuid.uuid4().hex[:10]}"
    label = f"jev-b09-{rc.uuid.uuid4().hex[:8]}"
    task = rc.make_task(cls, token, fixtures)
    lane_env = set_lane_env(LANE_ENV[b09_arm])
    sleep_ns = pc_sleep_ns()
    result.update({"token_sha16": rc.sha16(token), "token_len": len(token), "session_label": label,
                   "outcome": "unknown", "routes": [], "tools": [], "input_routes": [], "candidates": [],
                   "probe": spec["plan"], "b09_arm": b09_arm, "P": "cold", "D": 0,
                   "variant": "task", "resnap": False, "inject_ms": 0, "inject_mode": None,
                   "attempt": spec["attempt"], "williams_row": spec.get("williams_row"),
                   "pos_in_round": spec.get("pos_in_round"), "lane_env": lane_env,
                   "verify_poll_interval_s": cr.verify_poll_interval_s(cr.Routine.VERIFY_INTERVAL_S),
                   "pc_sleep_target_ns": sleep_ns, **DRIVER_ID})
    task.reset()
    fixtures.state(cls).drain()
    poller = B4.Sampler(fixtures, cls, token, result)
    result["_poller"] = poller
    env = B4.driver_env_for(arm, cls, trace_path)
    result["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
    result["driver_env_trace_set"] = B4.TRACE_ENV in env
    result["driver_env_telemetry"] = env.get(TELEMETRY_ENV)
    result["driver_env_dnt"] = env.get("DO_NOT_TRACK")
    result["driver_env_lane"] = sorted(k for k in env if k.startswith("CUA_LANE_EXP_"))
    result["caller_variant"] = {"prep": bs.STAMP["prep"], "route": bs.STAMP["route"]}
    counts_before = dict(bs.COUNTS)
    mode = "replay" if (arm["replay"] and cls == "fill") else "step"
    result["mode"] = mode
    rec.add("trial_start", cls=cls, arm=cfg_name, b09_arm=b09_arm, mode=mode, lane_env=lane_env)
    rc.CLIENT["rec"] = rec
    rc.CLIENT["compiled"] = None
    cr.STAMP = rec.add
    params = rc.StdioServerParameters(command=args.driver, args=["mcp"], env=env)
    try:
        async with rc.stdio_client(params) as (read, write):
            async with rc.ClientSession(read, write) as session:
                await session.initialize()
                result["driver_pid"] = find_driver_pid(Path(args.driver).name)
                result["pids_init"] = {"driver": proc_ident(result["driver_pid"])}
                tools = (await session.list_tools()).tools
                if arm["compiled_validator"]:
                    rec.add("compile_validators_start")
                    result["compiled_validators"] = rc.compile_output_validators(session)
                    rec.add("compile_validators_end")
                available = {tool.name for tool in tools}
                capture_bound = rc.supports_capture_bound_click(tools)
                inner = rc.Driver(session, label)
                await rc.timed_call(rec, inner, "cursor_enabled", "set_agent_cursor_enabled", {"enabled": arm["cursor"]})
                motion = await rc.timed_call(rec, inner, "cursor_motion", "set_agent_cursor_motion", rc.DEFAULT_MOTION)
                result["motion_ack"] = {k: motion.get(k) for k in ("glide_duration_ms", "dwell_after_click_ms")
                                        if isinstance(motion, dict)}
                prepared = await rc.timed_call(rec, inner, "prepare", "browser_prepare",
                                               {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                pid = int(prepared["prepared_pid"])
                result["prepared_pid"] = pid  # rc.one pops this one (browser-exit wait)
                result["chrome_pid"] = pid
                result["pids_prepare"] = pids_now(result)
                result["browser_exe"] = (result["pids_prepare"]["chrome"] or {}).get("exe")
                window = await rc.wait_for_window(inner, pid)
                rec.add("window_ready")
                bound = await rc.timed_call(rec, inner, "bind", "get_browser_state",
                                            {"pid": pid, "window_id": window["window_id"]})
                tgt = {"target_id": bound["target_id"], "tab_id": rc.select_tab_id(bound["tabs"])}
                result["_tgt"] = tgt
                url = fixtures.page_url(cls)
                result["pids_pretask"] = pids_now(result)  # immediately before the task navigate (outside T)
                await rc.timed_call(rec, inner, "navigate", "browser_navigate", {**tgt, "url": url})
                nav_return = rc.now()
                rec.add("task_start", D=0)
                poller.start()
                if sleep_ns:
                    drv = SleepAfterFirstObs(inner, rec, nav_return_ns=nav_return, D=0, resnap=False, result=result,
                                             sleep_ns=sleep_ns)
                else:
                    drv = B4.ObsDriver(inner, rec, nav_return_ns=nav_return, D=0, resnap=False)
                loop_kw = dict(rec=rec, drv=drv, task=task, pid=pid, window=window, available=available,
                               capture_bound=capture_bound, guard=arm["guard"] and cls == "fill", poll_ms=arm["poll_ms"],
                               result=result)
                if mode == "replay":
                    async def fallback(ctx: Any, rrec: Any, index: int, reason: str) -> str:
                        rec.add("fallback_start", index=index, reason=reason)
                        result["fallback"] = {"index": index, "reason": reason}
                        out = await B4.step_loop(**loop_kw, prefix="fallback:")
                        return "fallback_verified" if out == "verified" else out

                    def read_oracle() -> dict[str, Any]:
                        rec.add("oracle_send", label="routine_read")
                        state = task.read_oracle()
                        rec.add("oracle_return", label="routine_read",
                                outcome="verified" if state.get("submitted") == token else "unknown")
                        return dict(state)

                    routine = cr.Routine(ROUTINE, fallback=fallback)
                    ctx = cr.ReplayContext(driver=drv, target_id=tgt["target_id"], tab_id=tgt["tab_id"], pid=pid,
                                           window_id=int(window["window_id"]), fixture_url=url, token=token,
                                           read_oracle=read_oracle, rebind=None)
                    rrec = cr.ReplayRecord()
                    rrec.t0_ns = rc.now()
                    await routine.replay(ctx, rrec)
                    if rrec.outcome == "stopped" and str(rrec.stop_reason or "") == "refused:browser_ref_stale" \
                            and not result.get("fallback"):
                        rrec.outcome = await fallback(ctx, rrec, -1, "refused:browser_ref_stale")
                    result["routine"] = {k: v for k, v in rrec.as_dict().items() if k != "events"}
                    result["routine_events"] = rrec.events
                    result["routes"] = ["compiled"] + result["routes"]
                    out = rrec.outcome
                    result["outcome"] = {"fallback_verified": "verified", "verified_by_reconcile": "verified"}.get(out, out)
                else:
                    result["outcome"] = await B4.step_loop(**loop_kw)
    finally:
        cr.STAMP = None
        set_lane_env({})
        result["caller_variant_counts"] = {k: bs.COUNTS[k] - counts_before[k] for k in bs.COUNTS}
    result.pop("_tgt", None)


rc.run_trial = b09_trial  # rc.one looks run_trial up at call time

# ── N-W2 (FIX-01 detached-node refusal carry-over): B-02 run_b02.control_one / control_trial, unchanged,
#    with the COMP admission knob and telemetry off in the Driver environment (R2-10R nw2_one rule) ──────

_orig_control_trial = R2.control_trial


async def nw2_control_trial(spec: dict[str, Any], args: argparse.Namespace, fixtures: Any, trace_path: Path,
                            rec: Any, result: dict[str, Any]) -> None:
    result.update({"b09_arm": "NW2", "probe": spec.get("plan"), "attempt": spec.get("attempt"),
                   "lane_env": set_lane_env({}), **DRIVER_ID})
    R2.CURRENT["knobs"] = {R2.V_ENV: "1", TELEMETRY_ENV: TELEMETRY_OFF, "DO_NOT_TRACK": "1"}
    env = rc.driver_environment()
    result["driver_env_exp"] = {k: v for k, v in env.items() if k.startswith("CUA_DRIVER_EXP_")}
    result["driver_env_telemetry"] = env.get(TELEMETRY_ENV)
    try:
        await _orig_control_trial(spec, args, fixtures, trace_path, rec, result)
    finally:
        R2.CURRENT["knobs"] = {}


R2.control_trial = nw2_control_trial  # control_one looks control_trial up at call time


# ── plan ────────────────────────────────────────────────────────────────────────────────────

def S(b09_arm: str, plan: str, kind: str = "measured", **kw: Any) -> dict[str, Any]:
    return {"cls": CLS, "b09_arm": b09_arm, "arm": CONFIG.get(b09_arm, "K5"), "kind": kind, "plan": plan, **kw}


def main_round(r: int, plan: str = "main") -> list[dict[str, Any]]:
    """One measured round: row (r mod 6) of the 6x6 Williams square over BASE/P10a/P10b/P1/P0/PC (fill)."""
    w = rc.williams(6)
    row_i = r % 6
    return [S(SQUARE_ARMS[j], plan, williams_row=row_i, pos_in_round=pos) for pos, j in enumerate(w[row_i])]


def ctl_round(plan: str = "ctl") -> list[dict[str, Any]]:
    """After the measured rounds: 5 SMOKE (product default, no lane variable) and 3 N-W2 controls (fill)."""
    return ([S("SMOKE", plan, kind="smoke", williams_row=None, pos_in_round=None) for _ in range(SMOKE_N)]
            + [S("NW2", plan, kind="nw2", williams_row=None, pos_in_round=None) for _ in range(NW2_N)])


def parse_rounds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def load1() -> float:
    return float(rc.loadavg().split()[0])


def driver_identity(path: str, want_sha: str) -> dict[str, Any]:
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    del data
    if sha != want_sha:
        raise SystemExit(f"refusing: driver sha256 {sha} != expected {want_sha}")
    ver = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
    version = (ver.stdout or ver.stderr).strip().splitlines()[0] if (ver.stdout or ver.stderr).strip() else ""
    return {"driver_name": Path(path).name, "driver_sha256": sha, "driver_version": version}


async def main_async(args: argparse.Namespace) -> int:
    out = Path(args.out)
    (out / "trials").mkdir(parents=True, exist_ok=True)
    rounds = [CTL_ROUND] if args.plan_kind == "ctl" else parse_rounds(args.rounds)
    lock = os.environ.get("B09_LOCK")
    if args.plan_kind in ("main", "ctl") and lock != "exclusive":
        raise SystemExit("refusing: measured / control plan needs B09_LOCK=exclusive (quiet-timed + cargo lock)")
    if args.plan_kind == "pilot" and lock not in ("shared", "exclusive"):
        raise SystemExit("refusing: pilot needs B09_LOCK (run under shared-locked.sh)")
    DRIVER_ID.update(driver_identity(args.driver, args.driver_sha256))
    tag = f"{args.plan_kind}-{args.block}-a{args.attempt}-r{rounds[0]:02d}-{rounds[-1]:02d}"
    manifest: dict[str, Any] = {"plan_kind": args.plan_kind, "block": args.block, "attempt": args.attempt,
                                "rounds_requested": rounds, "rounds_completed": [], "rounds_cut": [],
                                "rounds_not_started": [], "stop_reason": None, "load_checks": [],
                                "budget_s": args.budget_s, "load_max": args.load_max, "load_wait_s": args.load_wait_s,
                                "started_mono_ns": rc.now(), "started_utc": B4.utc(), "loadavg_start": rc.loadavg(),
                                "lock_mode": lock, "lock_label": os.environ.get("B09_LOCK_LABEL"),
                                "hostless": os.environ.get("B09_HOSTLESS"), "provider": "mock",
                                "display": os.environ.get("DISPLAY"), **DRIVER_ID,
                                "runner_env_telemetry": os.environ.get(TELEMETRY_ENV),
                                "runner_env_lane_at_start": {k: os.environ.get(k) for k in LANE_ENVS},
                                "routine_id": ROUTINE.get("routine_id"), "trials": []}
    args.save_snapshots = False
    t_begin = time.monotonic()
    max_round_s = 0.0
    rc_exit = 0
    seq = 0
    try:
        for idx, r in enumerate(rounds):
            elapsed = time.monotonic() - t_begin
            if elapsed + max(max_round_s * 1.3, 30.0) > args.budget_s:
                manifest["stop_reason"] = f"time_budget (elapsed {elapsed:.1f} s)"
                manifest["rounds_not_started"] = rounds[idx:]
                rc_exit = 75
                break
            # pre-registered load rule: start a round only at 1-min loadavg <= load_max; wait <= load_wait_s
            t_wait = time.monotonic()
            la = load1()
            manifest["load_checks"].append({"round": r, "utc": B4.utc(), "load1": la, "waited_s": 0.0})
            while la > args.load_max and time.monotonic() - t_wait < args.load_wait_s:
                await asyncio.sleep(1.0)
                la = load1()
                manifest["load_checks"].append({"round": r, "utc": B4.utc(), "load1": la,
                                                "waited_s": round(time.monotonic() - t_wait, 2)})
            if la > args.load_max:
                manifest["stop_reason"] = f"load_high (round {r}: load1 {la} after {args.load_wait_s} s)"
                manifest["rounds_not_started"] = rounds[idx:]
                rc_exit = 75
                break
            t_round = time.monotonic()
            specs = ctl_round() if args.plan_kind == "ctl" else main_round(r, args.plan_kind)
            for k, spec in enumerate(specs):
                spec.update({"block": args.block, "round": r, "attempt": args.attempt, "lock_mode": lock,
                             "driver_sha256": DRIVER_ID["driver_sha256"]})
                suffix = f"-{k}" if args.plan_kind == "ctl" else ""
                spec["name"] = f"{args.block}-a{args.attempt}-r{r:02d}-{spec['cls']}-{spec['b09_arm']}{suffix}"
                spec["seq"] = seq
                seq += 1
                manifest["trials"].append(spec["name"])
                fixtures = B4.B04Fixtures(0, "hdr")
                try:
                    if spec["kind"] == "nw2":
                        await R2.control_one({**spec, "arm": "K5"}, args, fixtures, out)
                    else:
                        await rc.one(spec, args, fixtures, out)
                finally:
                    fixtures.close()
            manifest["rounds_completed"].append(r)
            max_round_s = max(max_round_s, time.monotonic() - t_round)
    except BaseException as error:  # a cut round (timeout signal, crash): keep what ran
        manifest["stop_reason"] = f"exception: {type(error).__name__}"
        done_rounds = set(manifest["rounds_completed"])
        manifest["rounds_cut"] = [r for r in rounds if r not in done_rounds][:1]
        rc_exit = 1
        raise
    finally:
        manifest["ended_mono_ns"] = rc.now()
        manifest["ended_utc"] = B4.utc()
        manifest["loadavg_end"] = rc.loadavg()
        manifest["network"] = dict(rc.NETWORK)
        manifest["max_round_s"] = round(max_round_s, 2)
        (out / f"run-manifest-{tag}.json").write_text(json.dumps(manifest, indent=1, default=str))
    return rc_exit


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--plan", choices=("main", "pilot", "ctl"), required=True)
    p.add_argument("--rounds", default="36", help="e.g. 0-11 or 3,5,9 (ignored for ctl)")
    p.add_argument("--block", default="m")
    p.add_argument("--attempt", type=int, default=1)
    p.add_argument("--budget-s", type=float, default=780.0)
    p.add_argument("--load-max", type=float, default=4.0)
    p.add_argument("--load-wait-s", type=float, default=60.0)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND") for k in os.environ):
        raise SystemExit("refusing: not inside the isolated X11 session")
    if not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: no DISPLAY (run inside cua-x11-session.sh)")
    for name in (B4.TRACE_ENV, B4.SETTLE_ENV, PREWARM_ENV, *R2.KNOB_ENVS, *LANE_ENVS):
        if name in os.environ:
            raise SystemExit(f"refusing: {name} must not be set in the runner environment")
    if os.environ.get("TYPESAFE_API_KEY") or os.environ.get("CUA_SESSION_FORWARD_SECRETS"):
        raise SystemExit("refusing: provider key forwarded (provider cap for this lane is 0)")
    args.plan_kind, args.plan = args.plan, f"b09-{args.plan}"
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

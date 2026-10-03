#!/usr/bin/env python3
"""R2-07 harness: compiled fresh-bound fill->submit routine vs ordinary (A) and guarded (B) callers.

Run ONLY inside cua-x11-session.sh (refuses otherwise). Phases:
  smoke        mock: 1 round A,B (receipts) + compile of the mock A trace + C replay (excluded from analysis)
  learn        P1 one ordinary LIVE run (arm A config, trace kept) -> P2 compile (timed) -> P3 admission
               (clean fixture reset, fresh Driver/Chrome, compiled replay with fresh binding, NO fallback)
  warm         P4 rounds of A (run.py --provider live), B (+ --guarded-completion), C (compiled replay)
               in rotating Latin-square order; fresh Driver, Chrome, fixture and token per trial
  negatives    P5 gate-4 rows (in-process, mock fallback), 3 reps per row, untimed
  reconcile    P6 gate-5 ack loss on the compiled Submit (in-process seam), untimed
  livefallback P7 N1 (Submit renamed) with the LIVE chooser as fallback, timed subprocess cells

usage: r2_07_harness.py --phase <p> --examples <wt>/libs/cua-driver/examples/jev-use --driver <bin>
         --driver-sha256 <sha> --tested-sha <sha> --out <dir> --budget-file <json> [--rounds N] [--rows ...]
         [--artifact <json>]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "r2_07_launcher.py"
PROVIDER_CAP_REACHED = 80
CELL_RESERVE = {"A": 4, "B": 3, "C": 0, "C_live": 3}
FEEDBACK_SINK: list[dict] = []
LATIN = ["ABC", "BCA", "CAB", "ACB", "CBA", "BAC"]
FORBIDDEN_ENV = ("CUA_DRIVER_PERMISSION_MODE", "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
                 "CUA_E2E_BROWSER_NO_SANDBOX", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE")
NEG_ROWS = {
    "N1": {"variant": "n1_renamed"},
    "N2": {"variant": "n2_missing"},
    "N3": {"variant": "n3_duplicate"},
    "N4a": {"variant": "rerender_on_signal", "hook": "rerender_before_submit"},
    "N4b": {"variant": "normal", "hook": "supersede_before_submit"},
    "N5": {"variant": "normal", "hook": "replace_session_between_steps"},
    "N6": {"variant": "n6_modal"},
    "N7": {"variant": "n7_prefilled"},
    "N8": {"variant": "n8_toggle"},
    # comparator (not a routine row): the same re-render injection before the unmodified run.py's
    # Submit dispatch (mock provider), to attribute N4a's outcome to the Driver, not the routine.
    "N4a_ord": {"variant": "rerender_on_signal", "hook": "rerender_before_click", "ordinary": True},
}
P6_ROWS = {
    "applied_ack_lost": {"fault": "ack_lost", "barrier": "applied", "mode": "immediate"},
    "delayed_after_first_unchanged_read": {"fault": "ack_lost", "barrier": "received", "mode": "after_unchanged:1"},
    # extra pre-registered control: the effect is withheld until the caller has finished, so the
    # bounded reconcile cannot resolve it; the routine must stay unknown and never re-dispatch.
    "withheld_unresolved": {"fault": "ack_lost", "barrier": "received", "mode": "withheld"},
}


def now() -> int:
    return time.monotonic_ns()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def loadavg() -> list[str]:
    return Path("/proc/loadavg").read_text().split()[:3]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"unparsed": True})
    return out


def session_pids(xdg_runtime: str) -> dict[int, str]:
    needle = f"XDG_RUNTIME_DIR={xdg_runtime}".encode()
    found: dict[int, str] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            if needle in Path(f"/proc/{entry}/environ").read_bytes().split(b"\0"):
                found[int(entry)] = Path(f"/proc/{entry}/comm").read_text().strip()
        except OSError:
            continue
    return found


def reap_cell_leftovers(before: dict[int, str]) -> tuple[list[str], list[str]]:
    """Kill only browser/Driver/python processes that appeared during THIS cell (started by it)."""
    time.sleep(0.5)
    xdg = os.environ["XDG_RUNTIME_DIR"]
    leftovers = {pid: comm for pid, comm in session_pids(xdg).items() if pid not in before and pid != os.getpid()}
    killed = []
    for pid, comm in leftovers.items():
        if comm.startswith(("chrome", "cua-driver", "python")):
            try:
                os.kill(pid, 9)
                killed.append(comm)
            except OSError:
                pass
    return sorted(leftovers.values()), sorted(killed)


class Budget:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {
            "cap_reached": PROVIDER_CAP_REACHED, "attempts": 0, "reached": 0, "by_cell": {}}

    @property
    def reached(self) -> int:
        return int(self.data["reached"])

    def can_start(self, reserve: int) -> bool:
        return self.reached + reserve <= PROVIDER_CAP_REACHED

    def add(self, cell_id: str, attempts: int, reached: int) -> None:
        self.data["attempts"] = int(self.data["attempts"]) + attempts
        self.data["reached"] = self.reached + reached
        self.data["by_cell"][cell_id] = {"attempts": attempts, "reached": reached}
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")


# ------------------------------------------------------------------ subprocess cells (A, B, C)


def start_fixture(examples: Path):
    sys.path.insert(0, str(examples))
    sys.path.insert(0, str(examples / "python"))
    sys.path.insert(0, str(HERE))
    from fixture import JournalFixture

    fixture = JournalFixture()
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    return fixture


def oracle_read(url: str) -> dict:
    req = Request(url + "state", headers={"X-R207-Oracle": "1"})
    with urlopen(req, timeout=1) as response:
        return json.load(response)


def run_subprocess_cell(args, out: Path, *, phase: str, rnd: int, pos: int, arm: str, provider: str,
                        variant: str = "normal", artifact: Path | None = None, fallback: str = "none",
                        keep_trace_as: Path | None = None) -> dict:
    cell_id = f"{phase}-r{rnd:03d}-{pos}-{arm}"
    token = f"r207-{uuid.uuid4().hex[:12]}"
    cdir = out / "cells" / cell_id
    cdir.mkdir(parents=True, exist_ok=False)
    log_path, receipts_path = cdir / "runner.jsonl", cdir / "receipts.jsonl"
    fixture = start_fixture(args.examples)
    fixture.configure(cell_id, token, variant=variant)
    url = fixture.url
    py = str(args.examples / ".venv/bin/python")
    if arm in ("A", "B"):
        flags = ["--guarded-completion"] if arm == "B" else []
        cmd = [py, str(LAUNCHER), str(args.examples), "run", "--provider", provider, "--fixture-url", url,
               "--token", token, "--max-steps", "4", "--log", str(log_path), *flags]
    else:
        flags = [f"--fallback={fallback}"]
        cmd = [py, str(LAUNCHER), str(args.examples), "compiled", "--artifact", str(artifact), "--fixture-url", url,
               "--token", token, "--fallback", fallback, "--log", str(log_path)]
    env = dict(os.environ)
    env["CUA_DRIVER_BIN"] = str(args.driver)
    env["R2_07_RECEIPT_LOG"] = str(receipts_path)
    if provider != "live" and fallback != "live":
        env.pop("TYPESAFE_API_KEY", None)

    oracle = {"seen_ns": None, "polls": 0}
    stop = threading.Event()

    def poll_oracle() -> None:
        while not stop.is_set():
            try:
                state = oracle_read(url)
                oracle["polls"] += 1
                if state.get("submitted") == token:
                    oracle["seen_ns"] = now()
                    return
            except Exception:
                pass
            time.sleep(0.004)

    xdg = os.environ["XDG_RUNTIME_DIR"]
    before = session_pids(xdg)
    cell = {"cell_id": cell_id, "phase": phase, "round": rnd, "position": pos, "arm": arm, "variant": variant,
            "provider_configured": provider, "fallback": fallback, "flags": flags, "loadavg_at_spawn": loadavg()}
    poller = threading.Thread(target=poll_oracle, daemon=True)
    with (cdir / "stdout.txt").open("wb") as so, (cdir / "stderr.txt").open("wb") as se:
        spawn_ns = now()
        proc = subprocess.Popen(cmd, cwd=args.examples, env=env, stdout=so, stderr=se, start_new_session=True)
        poller.start()
        timed_out = False
        try:
            rc = proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, 15)
            try:
                rc = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, 9)
                rc = proc.wait()
        exit_ns = now()
    time.sleep(0.05)
    stop.set()
    poller.join(timeout=2)
    fixture.journal.release_all("harness_release_after_exit")
    fixture.journal.wait_quiescent(5)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = reap_cell_leftovers(before)

    receipts = read_jsonl(receipts_path)
    events = read_jsonl(log_path)
    attempts = [r for r in receipts if r.get("kind") == "http_attempt"]
    reached = [r for r in attempts if r.get("reached")]
    sem = [r for r in receipts if r.get("kind") == "driver_call" and r.get("arg_snapshot_format") == "semantic_v2"]
    first_sem_ns = sem[0]["t_start_ns"] if sem else None
    mutations = [r for r in receipts if r.get("kind") == "driver_call" and r.get("tool") in ("browser_type", "browser_click")]
    decisions = [r for r in receipts if r.get("kind") == "provider_response"]
    reported = None
    if arm in ("A", "B"):
        outs = [e for e in events if e.get("event") == "outcome"]
        reported = outs[-1].get("outcome") if outs else None
    else:
        reps = [e for e in events if e.get("event") == "compiled_replay"]
        reported = reps[-1].get("outcome") if reps else None
    verified_independent = journal["applied"] == 1 and journal["state_matches_token"]
    cell.update({
        "rc": rc, "timed_out": timed_out, "spawn_ns": spawn_ns, "exit_ns": exit_ns,
        "process_wall_ms": round((exit_ns - spawn_ns) / 1e6, 3),
        "first_semantic_send_ns": first_sem_ns, "oracle_seen_ns": oracle["seen_ns"], "oracle_polls": oracle["polls"],
        "T_ms": round((oracle["seen_ns"] - first_sem_ns) / 1e6, 3) if oracle["seen_ns"] and first_sem_ns else None,
        "T_target_ms": round((journal["first_visible_ns"] - first_sem_ns) / 1e6, 3) if journal["first_visible_ns"] and first_sem_ns else None,
        "journal_received": journal["received"], "journal_applied": journal["applied"],
        "journal_toggle_events": journal["toggle_events"], "journal_other_value": journal["submitted_other_value"],
        "duplicate_submits": max(0, journal["applied"] - 1),
        "independently_verified": verified_independent, "reported_outcome": reported,
        "unverified_success": reported in ("verified", "fallback_verified", "verified_by_reconcile") and not verified_independent,
        "http_attempts": len(attempts), "http_reached": len(reached),
        "provider_responses": [{k: d.get(k) for k in ("backend", "ok", "model", "input_tokens", "output_tokens", "selected_id", "request_id_sha256_16", "error")} for d in decisions],
        "provider_decisions_live": sum(1 for d in decisions if d.get("backend") == "typesafe"),
        "decision_routes": [e.get("decision_route") for e in events if e.get("event") == "step"],
        "mutation_calls": len(mutations), "semantic_observations": len(sem),
        "feedback_off": [r for r in receipts if r.get("kind") == "feedback_off"],
        "loadavg_at_exit": loadavg(), "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    })
    (cdir / "cell.json").write_text(json.dumps(cell, indent=1, sort_keys=True) + "\n")
    with (cdir / "trial.jsonl").open("w", encoding="utf-8") as raw:
        raw.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        for e in events:
            raw.write(json.dumps({"type": "runner_event", "event": e}, sort_keys=True) + "\n")
        for r in receipts:
            raw.write(json.dumps({"type": "receipt", **r}, sort_keys=True) + "\n")
        raw.write(json.dumps({"type": "target_journal", "events": journal["events"]}, sort_keys=True) + "\n")
    if keep_trace_as is not None:
        keep_trace_as.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in receipts))
    return cell


def validity(args) -> dict:
    ex_rel = "libs/cua-driver/examples/jev-use"
    worktree = args.examples.parents[2]
    git = lambda *a: subprocess.run(["git", "-C", str(worktree), *a], capture_output=True, text=True).stdout.strip()
    result = {
        "head": git("rev-parse", "HEAD"),
        "tested_sha": args.tested_sha,
        "examples_identical_to_tested_sha": git("diff", "--name-only", args.tested_sha, "--", ex_rel) == ""
        and git("ls-files", "--others", "--exclude-standard", "--", ex_rel) == "",
        "rust_identical_to_229b65b28": subprocess.run(["git", "-C", str(worktree), "diff", "--quiet",
                                                         "229b65b2849c3a595ddbc85200d7181b18bd2e47", args.tested_sha,
                                                         "--", "libs/cua-driver/rust"]).returncode == 0,
        "driver_sha256": sha256_file(args.driver), "driver_sha256_expected": args.driver_sha256,
        "driver_version": subprocess.run([str(args.driver), "--version"], capture_output=True, text=True).stdout.strip(),
        "forbidden_env_present": [n for n in FORBIDDEN_ENV if n in os.environ],
        "display_set": bool(os.environ.get("DISPLAY")),
        "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
        "harness_files_sha256": {p.name: sha256_file(p) for p in sorted(HERE.glob("*.py"))},
        "run_py_sha256": sha256_file(args.examples / "python/run.py"),
        "python": sys.version.split()[0],
    }
    result["ok"] = (result["examples_identical_to_tested_sha"] and result["rust_identical_to_229b65b28"]
                    and result["driver_sha256"] == args.driver_sha256 and not result["forbidden_env_present"]
                    and result["display_set"])
    return result


# ------------------------------------------------------------------ in-process routine trials (P5, P6)


async def inprocess_trial(args, fixture, *, token: str, row: str, hook_kind: str | None, fault: dict | None,
                          fallback_provider: str = "mock", artifact: dict) -> dict:
    import run as runner
    import compiled_routine as cr
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment
    from tasks import FixtureFormTask, fixture_state
    import fault_transport as ft

    import r2_07_launcher

    rec = cr.ReplayRecord()
    hook_log: list[dict] = []
    feedback: list[dict] = []
    FEEDBACK_SINK[:] = []
    r2_07_launcher.install_feedback_off(runner, emit=FEEDBACK_SINK.append)
    plan = None
    if fault:
        plan = ft.FaultPlan(mode=fault["fault"], barrier_kind=fault.get("barrier"), barrier_wait=fixture.journal.wait_for)
    os.environ["CUA_DRIVER_BIN"] = str(args.driver)
    params = StdioServerParameters(command=str(args.driver), args=["mcp"], env=driver_environment())
    transport = (lambda p: ft.fault_stdio_client(p, plan)) if plan else stdio_client
    fallback = cr.make_chooser_fallback(runner=runner, task_factory=lambda t, u: FixtureFormTask(t, u),
                                        provider=fallback_provider, max_decisions=2)
    url = fixture.url

    async def hook(where: str, index: int, ctx: cr.ReplayContext, r: cr.ReplayRecord) -> None:
        if hook_kind == "rerender_before_submit" and where == "before_dispatch" and index == 1:
            fixture.trigger_rerender()
            ok = await asyncio.to_thread(fixture.wait_rerendered, 5.0)
            hook_log.append({"hook": hook_kind, "rerender_acked": ok, "t_ms": round((now() - r.t0_ns) / 1e6, 3)})
        elif hook_kind == "supersede_before_submit" and where == "before_dispatch" and index == 1 and not hook_log:
            snap = await ctx.driver.call("get_browser_state", {"target_id": ctx.target_id, "tab_id": ctx.tab_id,
                                                                "snapshot_format": "semantic_v2"})
            hook_log.append({"hook": hook_kind, "superseding_snapshot": (snap.get("snapshot") or {}).get("id"),
                             "t_ms": round((now() - r.t0_ns) / 1e6, 3)})
        elif hook_kind == "replace_session_between_steps" and where == "before_step" and index == 1:
            old_target, old_tab = ctx.target_id, ctx.tab_id
            ctx.driver = runner.Driver(ctx.driver.session, f"jev-python-{uuid.uuid4().hex[:8]}")
            ctx.target_id = ctx.tab_id = None
            probe = {"hook": hook_kind, "session_replaced": True}
            try:  # discriminating control: the OLD target capability must not resolve in the new session
                await ctx.driver.call("get_browser_state", {"target_id": old_target, "tab_id": old_tab,
                                                             "snapshot_format": "semantic_v2"})
                probe["old_target_in_new_session"] = "accepted"
            except Exception as error:  # noqa: BLE001
                probe["old_target_in_new_session"] = "refused"
                probe["old_target_refusal_code"] = getattr(error, "code", None)
            hook_log.append(probe)

    async def rebind(ctx: cr.ReplayContext) -> None:
        await ctx.driver.call("browser_prepare", {"pid": ctx.pid})
        bound = await ctx.driver.call("get_browser_state", {"pid": ctx.pid, "window_id": ctx.window_id})
        ctx.target_id, ctx.tab_id = bound["target_id"], runner.select_tab_id(bound["tabs"])

    routine = cr.Routine(artifact, fallback=fallback, hook=hook)
    started = now()
    try:
        async with transport(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                driver = runner.Driver(session, f"jev-python-{uuid.uuid4().hex[:8]}")
                prepared = await driver.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
                pid = int(prepared["prepared_pid"])
                window = await runner.wait_for_window(driver, pid)
                bound = await driver.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
                target_id, tab_id = bound["target_id"], runner.select_tab_id(bound["tabs"])
                await driver.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": url})
                ctx = cr.ReplayContext(driver=driver, target_id=target_id, tab_id=tab_id, pid=pid,
                                       window_id=int(window["window_id"]), fixture_url=url, token=token,
                                       read_oracle=lambda: fixture_state(url), rebind=rebind)
                rec.t0_ns = now()
                await routine.replay(ctx, rec)
                rec.log("replay_end")
    except BaseException as error:  # noqa: BLE001
        if isinstance(error, KeyboardInterrupt):
            raise
        leaves, stack = [], [error]
        while stack:
            item = stack.pop()
            if isinstance(item, BaseExceptionGroup):
                stack.extend(item.exceptions)
            else:
                leaves.append(type(item).__name__)
        rec.log("context_exit_exception", leaves=sorted(leaves))
        if rec.outcome == "running":
            rec.outcome, rec.stop_reason = "error", ",".join(sorted(leaves))
    feedback.extend(FEEDBACK_SINK)
    return {"record": rec.as_dict(), "hook_log": hook_log, "wall_ms": round((now() - started) / 1e6, 3),
            "feedback_off": feedback,
            "seam_events": plan.events if plan else None, "fault_fired": plan.fired if plan else None}


async def inprocess_ordinary_trial(args, fixture, *, token: str) -> dict:
    """Unmodified run.py (mock provider) in process; re-render injected before its first browser_click."""
    import run as runner
    import r2_07_launcher

    FEEDBACK_SINK[:] = []
    r2_07_launcher.install_feedback_off(runner, emit=FEEDBACK_SINK.append)
    os.environ["CUA_DRIVER_BIN"] = str(args.driver)
    hook_log: list[dict] = []
    calls: list[dict] = []
    inner = runner.Driver.call

    async def call(self, name, arguments):
        if name == "browser_click" and not hook_log:
            fixture.trigger_rerender()
            ok = await asyncio.to_thread(fixture.wait_rerendered, 5.0)
            hook_log.append({"hook": "rerender_before_click", "rerender_acked": ok})
        entry = {"tool": name, "ref_snapshot": str(arguments.get("ref", "")).split(":")[0] or None}
        try:
            data = await inner(self, name, arguments)
            entry.update({"ok": True, "effect": data.get("effect") if isinstance(data, dict) else None})
            return data
        except Exception as error:
            entry.update({"ok": False, "code": getattr(error, "code", None)})
            raise
        finally:
            calls.append(entry)

    runner.Driver.call = call
    log = Path(os.environ["TMPDIR"]) / f"r207-ord-{uuid.uuid4().hex[:8]}.jsonl"
    ns = argparse.Namespace(provider="mock", fixture_url=fixture.url, token=token, max_steps=4, dry_run=False,
                            guarded_completion=False, log=str(log), visual_observation="auto")
    started = now()
    try:
        outcome = await runner.run(ns)
    except BaseException as error:  # noqa: BLE001
        if isinstance(error, KeyboardInterrupt):
            raise
        outcome = f"exception:{type(error).__name__}"
    finally:
        runner.Driver.call = inner
    events = read_jsonl(log)
    log.unlink(missing_ok=True)
    return {"outcome": outcome, "hook_log": hook_log, "driver_calls": calls, "runner_events": events,
            "wall_ms": round((now() - started) / 1e6, 3), "feedback_off": list(FEEDBACK_SINK)}


def run_ordinary_cell(args, out: Path, *, row: str, rep: int, variant: str) -> dict:
    cell_id = f"neg-{row}-rep{rep}"
    token = f"r207-{uuid.uuid4().hex[:12]}"
    fixture = start_fixture(args.examples)
    fixture.configure(cell_id, token, variant=variant)
    before = session_pids(os.environ["XDG_RUNTIME_DIR"])
    la = loadavg()
    result = asyncio.run(inprocess_ordinary_trial(args, fixture, token=token))
    fixture.journal.release_all("harness_release_after_caller_finished")
    fixture.journal.wait_quiescent(15)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = reap_cell_leftovers(before)
    clicks = [c for c in result["driver_calls"] if c["tool"] == "browser_click"]
    cell = {
        "cell_id": cell_id, "phase": "neg", "row": row, "rep": rep, "variant": variant, "caller": "run.py (unmodified, mock)",
        "loadavg_start": la, "loadavg_end": loadavg(), "outcome": result["outcome"], "hook_log": result["hook_log"],
        "driver_calls": result["driver_calls"], "runner_events": result["runner_events"],
        "wall_ms_informational": result["wall_ms"], "feedback_off": result["feedback_off"],
        "clicks_dispatched": len(clicks), "first_click_accepted_after_rerender": bool(clicks and clicks[0].get("ok") and result["hook_log"]),
        "journal_received": journal["received"], "journal_applied": journal["applied"],
        "duplicate_submits": max(0, journal["applied"] - 1),
        "independently_verified": journal["applied"] == 1 and journal["state_matches_token"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    path = out / "cells" / f"{cell_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        stream.write(json.dumps({"type": "target_journal", "events": journal["events"]}, sort_keys=True) + "\n")
    return cell


def run_inprocess_cell(args, out: Path, *, phase: str, row: str, rep: int, artifact: dict, hook_kind=None,
                       variant="normal", fault=None, mode="immediate", fallback_provider="mock") -> dict:
    cell_id = f"{phase}-{row}-rep{rep}"
    token = f"r207-{uuid.uuid4().hex[:12]}"
    fixture = start_fixture(args.examples)
    fixture.configure(cell_id, token, variant=variant, mode=mode)
    xdg = os.environ["XDG_RUNTIME_DIR"]
    before = session_pids(xdg)
    la = loadavg()
    result = asyncio.run(inprocess_trial(args, fixture, token=token, row=row, hook_kind=hook_kind, fault=fault,
                                         fallback_provider=fallback_provider, artifact=artifact))
    journal_before_release = {k: v for k, v in fixture.journal.snapshot().items() if k != "events"}
    fixture.journal.release_all("harness_release_after_caller_finished")
    quiescent = fixture.journal.wait_quiescent(15)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = reap_cell_leftovers(before)
    rec = result["record"]
    accepted = [m for m in rec["mutations"] if m.get("result") == "accepted"]
    rerender_t = [e["t_ms"] for e in journal["events"] if e["kind"] == "page_rerendered"]
    cell = {
        "cell_id": cell_id, "phase": phase, "row": row, "rep": rep, "variant": variant, "hook": hook_kind,
        "fault": fault, "fixture_mode": mode, "fallback_provider": fallback_provider, "loadavg_start": la,
        "loadavg_end": loadavg(), "outcome": rec["outcome"], "stop_reason": rec["stop_reason"], "route": rec["route"],
        "wall_ms_informational": result["wall_ms"],
        "mutations": rec["mutations"], "observations": rec["observations"], "events": rec["events"],
        "reconcile_reads": rec["reconcile_reads"], "fallback_decisions": rec["fallback_decisions"],
        "provider_decisions": rec["provider_decisions"], "hook_log": result["hook_log"],
        "seam_events": result["seam_events"], "fault_fired": result["fault_fired"],
        "feedback_off": result["feedback_off"],
        "mutations_accepted": len(accepted),
        "mutations_dispatched_not_fresh": sum(1 for m in rec["mutations"] if not m.get("fresh")),
        "accepted_after_rerender": sum(1 for m in accepted if m.get("step") == 1 and rerender_t),
        "journal_before_release": journal_before_release, "journal_quiescent": quiescent,
        "journal_received": journal["received"], "journal_applied": journal["applied"],
        "journal_toggle_events": journal["toggle_events"], "journal_other_value": journal["submitted_other_value"],
        "duplicate_submits": max(0, journal["applied"] - 1),
        "independently_verified": journal["applied"] == 1 and journal["state_matches_token"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    cell["unverified_success"] = cell["outcome"] in ("verified", "fallback_verified", "verified_by_reconcile") and not cell["independently_verified"]
    path = out / "cells" / f"{cell_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        stream.write(json.dumps({"type": "target_journal", "events": journal["events"]}, sort_keys=True) + "\n")
    return cell


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=("smoke", "learn", "warm", "negatives", "reconcile", "livefallback"))
    ap.add_argument("--examples", type=Path, required=True)
    ap.add_argument("--driver", type=Path, required=True)
    ap.add_argument("--driver-sha256", required=True)
    ap.add_argument("--tested-sha", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--budget-file", type=Path, required=True)
    ap.add_argument("--artifact", type=Path)
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--start-round", type=int, default=0)
    ap.add_argument("--rows", default="")
    ap.add_argument("--reps", type=int, default=3)
    args = ap.parse_args()
    args.examples = args.examples.resolve()
    sys.path.insert(0, str(args.examples))
    sys.path.insert(0, str(args.examples / "python"))
    sys.path.insert(0, str(HERE))
    import tasks
    import compiled_routine as cr

    assert tasks.FIELD_NAME == cr.FIELD_NAME and tasks.SUBMIT_NAME == "Submit"
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    check = validity(args)
    check.update({"phase": args.phase, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "loadavg_at_start": loadavg()})
    (out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "key_present": check["typesafe_key_present"]}), flush=True)
    if not check["ok"]:
        return 2
    budget = Budget(args.budget_file)
    cells_out = (out / "cells.jsonl").open("a", encoding="utf-8")
    stopped = None

    def emit(cell: dict) -> None:
        cells_out.write(json.dumps({k: v for k, v in cell.items() if k not in ("events", "runner_events")}, sort_keys=True) + "\n")
        cells_out.flush()
        print(json.dumps({"event": "cell", "id": cell["cell_id"], "verified": cell.get("independently_verified"),
                          "outcome": cell.get("reported_outcome", cell.get("outcome")), "T_ms": cell.get("T_ms"),
                          "reached": cell.get("http_reached"), "budget_reached": budget.reached,
                          "dup": cell.get("duplicate_submits")}), flush=True)

    live_needed = args.phase in ("learn", "warm", "livefallback")
    if live_needed and not check["typesafe_key_present"]:
        print(json.dumps({"event": "blocked", "reason": "TYPESAFE_API_KEY absent in session"}), flush=True)
        return 3

    if args.phase in ("smoke", "learn"):
        provider = "mock" if args.phase == "smoke" else "live"
        if provider == "live" and not budget.can_start(CELL_RESERVE["A"]):
            print(json.dumps({"event": "budget_stop"}), flush=True)
            return 4
        trace_path = out / "learning-trace.jsonl"
        p1 = run_subprocess_cell(args, out, phase=f"{args.phase}-P1", rnd=0, pos=1, arm="A", provider=provider,
                                 keep_trace_as=trace_path)
        budget.add(p1["cell_id"], p1["http_attempts"], p1["http_reached"])
        emit(p1)
        g1 = bool(p1["independently_verified"] and p1["reported_outcome"] == "verified"
                  and (provider == "mock" or p1["provider_decisions_live"] == 2))
        receipts = read_jsonl(trace_path)
        c0 = time.perf_counter()
        try:
            artifact = cr.compile_trace(receipts, learning_verified=g1, routine_id="r2-07-fill-submit-v1")
            compile_error = None
        except Exception as error:  # noqa: BLE001
            artifact, compile_error = None, f"{type(error).__name__}: {error}"
        compile_ms = round((time.perf_counter() - c0) * 1000, 3)
        art_path = out / "artifact.json"
        if artifact is not None:
            art_path.write_text(cr.dumps(artifact))
        p2 = {"phase": "P2-compile", "compile_ms": compile_ms, "compile_error": compile_error,
              "authority_problems": cr.check_artifact_authority(artifact) if artifact else None, "g1": g1}
        (out / "compile.json").write_text(json.dumps(p2, indent=1, sort_keys=True) + "\n")
        print(json.dumps({"event": "compile", **p2}), flush=True)
        if artifact is None:
            return 5
        p3 = run_subprocess_cell(args, out, phase=f"{args.phase}-P3", rnd=0, pos=1, arm="C", provider="none",
                                 artifact=art_path, fallback="none")
        emit(p3)
        admitted = bool(p3["independently_verified"] and p3["reported_outcome"] == "verified" and p3["http_attempts"] == 0)
        (out / "admission.json").write_text(json.dumps({"admitted": admitted, "cell_id": p3["cell_id"]}, indent=1) + "\n")
        print(json.dumps({"event": "admission", "admitted": admitted}), flush=True)
        if args.phase == "smoke":
            for pos, arm in enumerate("B", start=2):
                emit(run_subprocess_cell(args, out, phase="smoke", rnd=0, pos=pos, arm=arm, provider="mock"))
        return 0 if admitted else 6

    if args.phase in ("warm", "livefallback"):
        artifact_path = args.artifact.resolve()
        cr.require_clean(json.loads(artifact_path.read_text()))
        if args.phase == "warm":
            plan = []
            for rnd in range(args.start_round, args.start_round + args.rounds):
                order = LATIN[rnd % len(LATIN)]
                plan += [(rnd, pos, arm) for pos, arm in enumerate(order, start=1)]
        else:
            plan = [(rnd, 1, "C") for rnd in range(args.rounds)]
        for rnd, pos, arm in plan:
            reserve = CELL_RESERVE["C_live"] if args.phase == "livefallback" else CELL_RESERVE[arm]
            if not budget.can_start(reserve):
                stopped = f"provider budget: reached {budget.reached} of {PROVIDER_CAP_REACHED}"
                break
            try:
                if args.phase == "warm":
                    cell = run_subprocess_cell(args, out, phase="warm", rnd=rnd, pos=pos, arm=arm,
                                               provider="live" if arm in "AB" else "none",
                                               artifact=artifact_path if arm == "C" else None)
                else:
                    cell = run_subprocess_cell(args, out, phase="livefallback", rnd=rnd, pos=pos, arm="C",
                                               provider="none", variant="n1_renamed", artifact=artifact_path,
                                               fallback="live")
            except Exception as error:  # noqa: BLE001
                cell = {"cell_id": f"{args.phase}-r{rnd:03d}-{pos}-{arm}", "phase": args.phase, "round": rnd,
                        "position": pos, "arm": arm, "harness_error": f"{type(error).__name__}: {error}",
                        "http_attempts": 0, "http_reached": 0}
            budget.add(cell["cell_id"], int(cell.get("http_attempts") or 0), int(cell.get("http_reached") or 0))
            emit(cell)
            time.sleep(0.3)

    if args.phase == "negatives":
        artifact = json.loads(args.artifact.resolve().read_text())
        for row in [r for r in args.rows.split(",") if r]:
            spec = NEG_ROWS[row]
            for rep in range(1, args.reps + 1):
                if spec.get("ordinary"):
                    cell = run_ordinary_cell(args, out, row=row, rep=rep, variant=spec["variant"])
                else:
                    cell = run_inprocess_cell(args, out, phase="neg", row=row, rep=rep, artifact=artifact,
                                              hook_kind=spec.get("hook"), variant=spec["variant"])
                emit(cell)

    if args.phase == "reconcile":
        artifact = json.loads(args.artifact.resolve().read_text())
        wanted = [r for r in args.rows.split(",") if r] or list(P6_ROWS)
        for rep in range(1, args.reps + 1):
            for row, spec in [(r, P6_ROWS[r]) for r in wanted]:
                cell = run_inprocess_cell(args, out, phase="p6", row=row, rep=rep, artifact=artifact,
                                          fault={"fault": spec["fault"], "barrier": spec["barrier"]}, mode=spec["mode"])
                emit(cell)

    (out / "end.json").write_text(json.dumps({"ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                              "stopped_early": stopped, "budget_reached_after": budget.reached,
                                              "budget_attempts_after": budget.data["attempts"],
                                              "loadavg_at_end": loadavg()}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

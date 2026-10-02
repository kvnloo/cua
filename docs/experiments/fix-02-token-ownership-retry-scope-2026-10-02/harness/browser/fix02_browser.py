#!/usr/bin/env python3
"""FIX-02 browser rows: F3 (runner re-dispatch scope) and F4 (set_input_files on a detached input).

MEASUREMENT HARNESS ONLY. Run ONLY inside cua-x11-session.sh (refuses otherwise), under hostless,
with the quiet-lane lock taken OUTSIDE (locked.sh shared). Reuses, unchanged and copied by path:
``harness/r2-07`` (2d71548b4: fault seam, journaled fixture, launcher feedback-off, cell helpers) and
``harness/fix-01`` (4a301d32a: journaled fixture with page-event beacons). Provider cap 0: every
chooser is the mock and a socket guard refuses and counts any non-loopback connect.

usage: fix02_browser.py --phase f3|f3ctl|f4 --examples <wt>/libs/cua-driver/examples/jev-use
         --driver <bin> --arm U|F --out <dir> [--code stale|trust_unknown|not_retryable]
         [--reps N] [--start-rep K]
  f3     jev-use run.py (mock) on the spa_submit page; the first Submit click gets the injected
         refusal --code at the stdio seam. --arm U loads run.py from U (git blob at U_HEAD),
         --arm F imports the worktree's run.py.
  f3ctl  no injection, unchanged page, worktree run.py (C6-style no-refusal control).
  f4     direct caller on the file_rerender page: bind the file input, re-render, set files with
         the OLD ref, then one fresh observation, bind and set files on the fresh ref.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "fix-01", HERE.parent / "r2-07"):
    sys.path.insert(0, str(_p))
if "--examples" in sys.argv:
    _ex = Path(sys.argv[sys.argv.index("--examples") + 1]).resolve()
    sys.path[:0] = [str(_ex), str(_ex / "python")]

U_HEAD = "bd0cc9de764369b6afa31aca1fc348a1e05a0abf"  # 989cc76ce + FIX-01 8cfa8c1db, 6eb9319fe
U_RUN_PY = "libs/cua-driver/examples/jev-use/python/run.py"
FORBIDDEN_ENV = ("CUA_DRIVER_PERMISSION_MODE", "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
                 "CUA_E2E_BROWSER_NO_SANDBOX", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
                 "TYPESAFE_API_KEY", "CUA_DRIVER_CAPABILITY_MANIFEST_APPROVED",
                 "CUA_DRIVER_SESSION_POLICY_APPROVED")
NONLOOPBACK = {"refused": 0}


def _loopback(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return True
    host = str(address[0])
    return host.startswith("127.") or host in ("::1", "localhost")


def install_socket_guard() -> None:
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex

    def guarded(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address):
            NONLOOPBACK["refused"] += 1
            raise ConnectionRefusedError("FIX-02: non-loopback connect refused (provider cap 0)")
        return connect(self, address)

    def guarded_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address):
            NONLOOPBACK["refused"] += 1
            return 111
        return connect_ex(self, address)

    socket.socket.connect, socket.socket.connect_ex = guarded, guarded_ex


install_socket_guard()

import fault_transport as ft  # noqa: E402
import fix02_fixture  # noqa: E402
import r2_07_harness as base  # noqa: E402  (cell helpers: session_pids, reap, read_jsonl)
import refusal_seam  # noqa: E402


def now() -> int:
    return time.monotonic_ns()


def loadavg() -> list[str]:
    return Path("/proc/loadavg").read_text().split()[:3]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(wt: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(wt), *a], capture_output=True, text=True).stdout.strip()


def start_fixture():
    fixture = fix02_fixture.JournalFixture()
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    return fixture


def validity(args) -> dict:
    wt = args.examples.parents[2]
    session_dir = Path(os.environ.get("TMPDIR", "/nonexistent")).parent
    openbox_log = session_dir / "openbox.log"
    obx = openbox_log.read_text(errors="replace") if openbox_log.exists() else ""
    result = {
        "phase": args.phase, "arm": args.arm, "code": args.code,
        "head": git(wt, "rev-parse", "HEAD"),
        "rust_tree_at_head": git(wt, "rev-parse", "HEAD:libs/cua-driver/rust"),
        "worktree_dirty": git(wt, "status", "--porcelain", "--", "libs/cua-driver"),
        "run_py_sha256": sha256_file(args.examples / "python/run.py"),
        "driver": {"path_name": args.driver.name, "sha256": sha256_file(args.driver),
                   "version": subprocess.run([str(args.driver), "--version"], capture_output=True,
                                             text=True).stdout.strip()},
        "forbidden_env_present": [n for n in FORBIDDEN_ENV if os.environ.get(n)],
        "display": os.environ.get("DISPLAY"),
        "xdg_runtime_private": bool(os.environ.get("XDG_RUNTIME_DIR"))
        and Path(os.environ["XDG_RUNTIME_DIR"]).parent == session_dir,
        "openbox_wm_conflict": "already running" in obx.lower(),
        "harness_files_sha256": {f"{p.parent.name}/{p.name}": sha256_file(p)
                                 for d in (HERE, HERE.parent / "fix-01", HERE.parent / "r2-07")
                                 for p in sorted(d.glob("*.py"))},
        "python": sys.version.split()[0],
        "loadavg_at_start": loadavg(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    result["ok"] = bool(result["display"] and result["xdg_runtime_private"]
                        and not result["forbidden_env_present"] and not result["worktree_dirty"]
                        and not result["openbox_wm_conflict"])
    return result


# ------------------------------------------------------------------ F3: runner rows


def load_runner(args, arm: str):
    if arm == "F":
        import run as runner

        return runner
    path = Path(os.environ["TMPDIR"]) / "fix02_u_run" / "run_u.py"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(["git", "-C", str(args.examples.parents[2]), "show", f"{U_HEAD}:{U_RUN_PY}"],
                              capture_output=True, check=True).stdout
        path.write_bytes(blob)
    if "run_u" in sys.modules:
        return sys.modules["run_u"]
    spec = importlib.util.spec_from_file_location("run_u", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_u"] = module
    spec.loader.exec_module(module)
    return module


async def runner_trial(args, fixture, *, token: str, runner, injection: str | None) -> dict:
    import r2_07_launcher

    base.FEEDBACK_SINK[:] = []
    r2_07_launcher.install_feedback_off(runner, emit=base.FEEDBACK_SINK.append)
    os.environ["CUA_DRIVER_BIN"] = str(args.driver)
    plan = ft.FaultPlan(mode="refusal_injection")
    calls: list[dict] = []
    inner = runner.Driver.call
    original_transport = runner.stdio_client
    t0 = now()

    async def call(self, name, arguments):
        entry = {"tool": name, "ref_snapshot": str(arguments.get("ref", "")).split(":")[0] or None,
                 "t_ms": round((now() - t0) / 1e6, 3)}
        if name == "get_browser_state" and arguments.get("snapshot_format"):
            entry["observation"] = True
        try:
            data = await inner(self, name, arguments)
            entry.update({"ok": True, "effect": data.get("effect") if isinstance(data, dict) else None})
            entry["journal_received_at_return"] = fixture.journal.snapshot()["received"]
            return data
        except Exception as error:
            entry.update({"ok": False, "code": getattr(error, "code", None),
                          "refused": getattr(error, "refused", None),
                          "retryable": getattr(error, "retryable", "absent"), "error": type(error).__name__})
            raise
        finally:
            calls.append(entry)

    runner.Driver.call = call
    runner.stdio_client = lambda params: refusal_seam.refusal_stdio_client(params, plan, injection)
    log = Path(os.environ["TMPDIR"]) / f"fix02-run-{uuid.uuid4().hex[:8]}.jsonl"
    ns = argparse.Namespace(provider="mock", fixture_url=fixture.url, token=token, max_steps=4, dry_run=False,
                            guarded_completion=False, log=str(log), visual_observation="auto")
    started = now()
    try:
        outcome = await runner.run(ns)
    except BaseException as error:  # noqa: BLE001 - every failure stays in the denominator
        if isinstance(error, KeyboardInterrupt):
            raise
        outcome = f"exception:{type(error).__name__}"
    finally:
        runner.Driver.call = inner
        runner.stdio_client = original_transport
    events = base.read_jsonl(log)
    log.unlink(missing_ok=True)
    return {"outcome": outcome, "driver_calls": calls, "runner_events": events, "seam_events": plan.events,
            "injected": plan.fired, "wall_ms": round((now() - started) / 1e6, 3),
            "feedback_off": list(base.FEEDBACK_SINK)}


def runner_cell(args, out: Path, *, phase: str, rep: int, injection: str | None, variant: str) -> dict:
    cell_id = f"{phase}-{injection or 'none'}-{args.arm}-rep{rep:02d}"
    token = f"fix02-{uuid.uuid4().hex[:12]}"
    runner = load_runner(args, args.arm if phase == "f3" else "F")
    fixture = start_fixture()
    fixture.configure(cell_id, token, variant=variant)
    before = base.session_pids(os.environ["XDG_RUNTIME_DIR"])
    la = loadavg()
    result = asyncio.run(runner_trial(args, fixture, token=token, runner=runner, injection=injection))
    fixture.journal.release_all("harness_release_after_caller_finished")
    fixture.journal.wait_quiescent(15)
    time.sleep(0.5)  # late page effects still reach the journal
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = base.reap_cell_leftovers(before)
    calls = result["driver_calls"]
    clicks = [i for i, c in enumerate(calls) if c["tool"] == "browser_click"]
    seam = result["seam_events"]
    observations_between = (sum(1 for c in calls[clicks[0] + 1:clicks[1]] if c.get("observation"))
                            if len(clicks) >= 2 else None)
    outcome_events = [e for e in result["runner_events"] if e.get("event") == "outcome"]
    summary = fix02_fixture.journal_summary(journal["events"])
    cell = {
        "cell_id": cell_id, "phase": phase, "rep": rep, "arm": args.arm, "injection": injection,
        "variant": variant, "loadavg_start": la, "loadavg_end": loadavg(),
        "outcome": result["outcome"], "final_outcome_event": outcome_events[-1] if outcome_events else None,
        "injected": result["injected"],
        "click_dispatches_by_caller": len(clicks),
        "clicks_forwarded_to_driver": sum(1 for e in seam if e.get("kind") == "forwarded_request"
                                          and e.get("tool") == "browser_click"),
        "first_click": calls[clicks[0]] if clicks else None,
        "redispatches_after_refusal": max(0, len(clicks) - 1) if clicks and not calls[clicks[0]].get("ok") else 0,
        "observations_between_first_and_second_click": observations_between,
        "refusals_seen": sum(1 for c in calls if not c.get("ok") and c.get("refused")),
        "journal_received": journal["received"], "journal_applied": journal["applied"],
        "duplicate_submits": max(0, journal["applied"] - 1),
        "state_matches_token": journal["state_matches_token"],
        "independently_verified": journal["applied"] == 1 and journal["state_matches_token"],
        "journal_summary": summary, "driver_calls": calls, "seam_events": seam,
        "feedback_off": result["feedback_off"], "wall_ms_informational": result["wall_ms"],
        "nonloopback_refused_total": NONLOOPBACK["refused"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    cell["unverified_success"] = cell["outcome"] == "verified" and not cell["independently_verified"]
    write_cell(out, cell, result["runner_events"], journal["events"])
    return cell


# ------------------------------------------------------------------ F4: set_input_files rows


async def file_trial(args, fixture, *, upload: Path) -> dict:
    import run as runner
    import r2_07_launcher
    from driver_env import driver_environment
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    base.FEEDBACK_SINK[:] = []
    r2_07_launcher.install_feedback_off(runner, emit=base.FEEDBACK_SINK.append)
    params = StdioServerParameters(command=str(args.driver), args=["mcp"], env=driver_environment())
    rec: dict = {"steps": [], "observations": 0, "hook": [], "outcome": "running"}
    t0 = now()

    def ms() -> float:
        return round((now() - t0) / 1e6, 3)

    async def observe(driver, target_id, tab_id) -> dict:
        rec["observations"] += 1
        return await driver.call("get_browser_state", {"target_id": target_id, "tab_id": tab_id,
                                                       "snapshot_format": "semantic_v2"})

    def bind(snap) -> dict | None:
        refs = [r for r in snap.get("refs") or [] if r.get("name") == "attachment"]
        return refs[0] if len(refs) == 1 else None

    async def set_files(driver, base_args, ref, label) -> dict:
        entry = {"label": label, "ref_snapshot": ref["ref"].split(":")[0], "role": ref.get("role"),
                 "actions": ref.get("actions"), "t_send_ms": ms()}
        try:
            data = await driver.call("browser_set_input_files", {**base_args, "ref": ref["ref"],
                                                                 "files": [str(upload)]})
            entry.update({"result": "accepted", "status": data.get("status"), "file_count": data.get("file_count")})
        except Exception as error:  # noqa: BLE001
            entry.update({"result": "refused" if getattr(error, "refused", False) else "error",
                          "code": getattr(error, "code", None), "error": type(error).__name__,
                          "message_head": str(error)[:160]})
        entry["t_return_ms"] = ms()
        rec["steps"].append(entry)
        return entry

    async def bounded(predicate, deadline_s=3.0) -> bool:
        started = time.monotonic()
        while time.monotonic() - started < deadline_s:
            if predicate(fix02_fixture.journal_summary(fixture.journal.snapshot()["events"])):
                return True
            await asyncio.sleep(0.02)
        return False

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            driver = runner.Driver(session, f"jev-python-{uuid.uuid4().hex[:8]}")
            prepared = await driver.call("browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            window = await runner.wait_for_window(driver, pid)
            bound = await driver.call("get_browser_state", {"pid": pid, "window_id": window["window_id"]})
            target_id, tab_id = bound["target_id"], runner.select_tab_id(bound["tabs"])
            await driver.call("browser_navigate", {"target_id": target_id, "tab_id": tab_id, "url": fixture.url})
            base_args = {"target_id": target_id, "tab_id": tab_id}
            snap = await observe(driver, target_id, tab_id)
            old = bind(snap)
            if old is None:
                rec["outcome"] = "stopped:file_input_not_unique"
                return rec
            fixture.trigger_rerender()
            acked = await asyncio.to_thread(fixture.wait_rerendered, 5.0)
            rec["hook"].append({"rerender": "before_dispatch", "acked": acked, "t_ms": ms()})
            await set_files(driver, base_args, old, "old_ref")
            await asyncio.sleep(1.0)  # let any old-node event or the old-node files poll reach the journal
            snap = await observe(driver, target_id, tab_id)
            fresh = bind(snap)
            if fresh is None:
                rec["outcome"] = "stopped:fresh_file_input_not_unique"
                return rec
            second = await set_files(driver, base_args, fresh, "fresh_ref")
            landed = second["result"] == "accepted" and await bounded(lambda s: s["fresh_change_with_file"] >= 1)
            rec["outcome"] = "verified" if landed else "unknown"
    rec["feedback_off"] = list(base.FEEDBACK_SINK)
    return rec


def file_cell(args, out: Path, *, rep: int) -> dict:
    cell_id = f"f4-file-{args.arm}-rep{rep:02d}"
    token = f"fix02-{uuid.uuid4().hex[:12]}"
    upload = Path(os.environ["TMPDIR"]) / "fix02-upload.txt"
    upload.write_text("FIX-02 upload fixture (no secret content)\n")
    fixture = start_fixture()
    fixture.configure(cell_id, token, variant="file_rerender")
    before = base.session_pids(os.environ["XDG_RUNTIME_DIR"])
    la = loadavg()
    started = now()
    try:
        rec = asyncio.run(file_trial(args, fixture, upload=upload))
    except BaseException as error:  # noqa: BLE001
        if isinstance(error, KeyboardInterrupt):
            raise
        rec = {"outcome": f"error:{type(error).__name__}:{str(error)[:160]}", "steps": [], "observations": 0,
               "hook": []}
    wall = round((now() - started) / 1e6, 3)
    time.sleep(0.5)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = base.reap_cell_leftovers(before)
    summary = fix02_fixture.journal_summary(journal["events"])
    first = rec["steps"][0] if rec["steps"] else {}
    cell = {
        "cell_id": cell_id, "phase": "f4", "rep": rep, "arm": args.arm, "variant": "file_rerender",
        "loadavg_start": la, "loadavg_end": loadavg(), "outcome": rec["outcome"], "steps": rec["steps"],
        "hook": rec["hook"], "observations": rec["observations"], "feedback_off": rec.get("feedback_off"),
        "wall_ms_informational": wall,
        "old_ref_result": first.get("result"), "old_ref_code": first.get("code"),
        "old_node_events": summary["old_file_events"],
        "fresh_change_with_file": summary["fresh_change_with_file"],
        "rebind_verified": rec["outcome"] == "verified" and summary["fresh_change_with_file"] >= 1,
        "journal_summary": summary,
        "nonloopback_refused_total": NONLOOPBACK["refused"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    write_cell(out, cell, [], journal["events"])
    return cell


# ------------------------------------------------------------------ main


def write_cell(out: Path, cell: dict, runner_events: list, journal_events: list) -> None:
    path = out / "cells" / f"{cell['cell_id']}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write(json.dumps({"type": "cell", **cell}, sort_keys=True, default=str) + "\n")
        stream.write(json.dumps({"type": "runner_events", "events": runner_events}, sort_keys=True) + "\n")
        stream.write(json.dumps({"type": "target_journal", "events": journal_events}, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=("f3", "f3ctl", "f4"))
    ap.add_argument("--examples", type=Path, required=True)
    ap.add_argument("--driver", type=Path, required=True)
    ap.add_argument("--arm", required=True, choices=("U", "F"))
    ap.add_argument("--code", default=None, choices=(None, *refusal_seam.INJECTIONS))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--start-rep", type=int, default=1)
    args = ap.parse_args()
    args.examples = args.examples.resolve()
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        print("refusing: not inside the private X11 session", file=sys.stderr)
        return 97
    args.out.mkdir(parents=True, exist_ok=False)
    check = validity(args)
    (args.out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "display": check["display"]}), flush=True)
    if not check["ok"]:
        return 2
    cells_out = (args.out / "cells.jsonl").open("a", encoding="utf-8")
    for rep in range(args.start_rep, args.start_rep + args.reps):
        if args.phase == "f3":
            cell = runner_cell(args, args.out, phase="f3", rep=rep, injection=args.code, variant="spa_submit")
        elif args.phase == "f3ctl":
            cell = runner_cell(args, args.out, phase="f3ctl", rep=rep, injection=None, variant="normal")
        else:
            cell = file_cell(args, args.out, rep=rep)
        slim = {k: v for k, v in cell.items()
                if k not in ("driver_calls", "seam_events", "steps", "journal_summary", "feedback_off")}
        cells_out.write(json.dumps(slim, sort_keys=True, default=str) + "\n")
        cells_out.flush()
        print(json.dumps({"event": "cell", "id": cell["cell_id"], "outcome": cell.get("outcome"),
                          "clicks": cell.get("click_dispatches_by_caller"), "applied": cell.get("journal_applied"),
                          "old": cell.get("old_ref_result"), "code": cell.get("old_ref_code"),
                          "old_events": cell.get("old_node_events")}), flush=True)
    (args.out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "loadavg_at_end": loadavg(),
        "nonloopback_refused_in_process": NONLOOPBACK["refused"]}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

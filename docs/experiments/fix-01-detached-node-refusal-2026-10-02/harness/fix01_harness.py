#!/usr/bin/env python3
"""FIX-01 harness: detached-node refusal (Part C) and R2-07b compiled-replay re-qualification (Part D).

MEASUREMENT HARNESS ONLY. Run ONLY inside cua-x11-session.sh (refuses otherwise), under hostless,
with the quiet-lane lock taken OUTSIDE (locked.sh shared for correctness blocks, quiet-timed
exclusive for the G6 timing block). Reuses the R2-07 harness modules unchanged
(``docs/experiments/r2-07-2026-10-02/harness``): the compiled routine, its in-process trial and
P6 fault seam, the subprocess cell runner and the measurement-only launcher. The R2-07 fixture is
extended (not edited) by ``fix01_fixture.py``.

Provider cap for this lane is 0: no key is forwarded into the session, every chooser is the mock,
and a socket guard in this process (and in every launcher subprocess) refuses and counts any
non-loopback connect.

usage: fix01_harness.py --phase <phase> --examples <wt>/libs/cua-driver/examples/jev-use
         --driver <bin> --driver-label U|F --out <dir> [--reps N] [--runner old|fixed] [--rows ...]
         [--driver-u <bin> --driver-f <bin>]   (g6 only)
phases: c1 c2 c3 c4 c4w c5 c6fill c6toggle c6modal c6reattach g2 g4 g5 g6
"""

from __future__ import annotations

import argparse
import asyncio
import copy
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
R207 = HERE.parents[1] / "r2-07-2026-10-02" / "harness"
sys.path.insert(0, str(R207))
sys.path.insert(0, str(HERE))
if "--examples" in sys.argv:  # the R2-07 fixture imports the jev-use fixture_server page
    _ex = Path(sys.argv[sys.argv.index("--examples") + 1]).resolve()
    sys.path[:0] = [str(_ex), str(_ex / "python")]

BASE_SHA = "2d71548b46114cd1a1bc58ccdef323ce185c9965"
FIX_A = "8cfa8c1dbd281da84f9acf8745dc8bea73da96e3"
FIX_A_RUST_TREE = "e24808eff03761bacd52240a702180c2f45c83b2"
BASE_RUST_TREE = "ceadcc0e60ba811ba6ff926f63834561be3c9e30"
OLD_RUN_PY_BLOB = "462554e695250cf84f8469751f69965afb9a50e0"
ARTIFACT_BLOB = "4ffbe21d7d105f0ca77ec623c0e53f0180d866b7"
ARTIFACT_PATH = HERE.parents[1] / "r2-07-2026-10-02" / "raw" / "learn" / "artifact.json"
BINARIES = {
    "U": "8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3",
}
FORBIDDEN_ENV = ("CUA_DRIVER_PERMISSION_MODE", "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
                 "CUA_E2E_BROWSER_NO_SANDBOX", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE",
                 "TYPESAFE_API_KEY")
NONLOOPBACK = {"refused": 0}


# ------------------------------------------------------------------ provider cap 0: socket guard


def _loopback(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return True  # AF_UNIX path
    host = str(address[0])
    return host.startswith("127.") or host in ("::1", "localhost")


def install_socket_guard() -> None:
    if getattr(socket.socket.connect, "_fix01_guard", False):
        return
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex

    def guarded(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address):
            NONLOOPBACK["refused"] += 1
            raise ConnectionRefusedError("FIX-01: non-loopback connect refused (provider cap 0)")
        return connect(self, address)

    def guarded_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address):
            NONLOOPBACK["refused"] += 1
            return 111
        return connect_ex(self, address)

    guarded._fix01_guard = True
    socket.socket.connect, socket.socket.connect_ex = guarded, guarded_ex


install_socket_guard()

import r2_07_harness as base  # noqa: E402  (unchanged R2-07 harness)
import fix01_fixture  # noqa: E402

base.LAUNCHER = HERE / "fix01_launcher.py"  # same launcher, plus the socket guard


def start_fixture(examples: Path):
    for p in (str(examples), str(examples / "python")):
        if p not in sys.path:
            sys.path.insert(0, p)
    fixture = fix01_fixture.JournalFixture()
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    return fixture


base.start_fixture = start_fixture


def now() -> int:
    return time.monotonic_ns()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def loadavg() -> list[str]:
    return Path("/proc/loadavg").read_text().split()[:3]


def git(wt: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(wt), *a], capture_output=True, text=True).stdout.strip()


def validity(args) -> dict:
    wt = args.examples.parents[2]
    session_dir = Path(os.environ.get("TMPDIR", "/nonexistent")).parent
    openbox_log = session_dir / "openbox.log"
    obx = openbox_log.read_text(errors="replace") if openbox_log.exists() else ""
    drivers = {args.driver_label: args.driver} if args.phase != "g6" else {"U": args.driver_u, "F": args.driver_f}
    result = {
        "phase": args.phase, "driver_label": args.driver_label,
        "head": git(wt, "rev-parse", "HEAD"),
        "rust_tree_at_head": git(wt, "rev-parse", "HEAD:libs/cua-driver/rust"),
        "rust_tree_fix_a": FIX_A_RUST_TREE, "rust_tree_base": BASE_RUST_TREE,
        "examples_dirty": git(wt, "status", "--porcelain", "--", "libs/cua-driver/examples/jev-use"),
        "rust_dirty": git(wt, "status", "--porcelain", "--", "libs/cua-driver/rust"),
        "run_py_sha256": sha256_file(args.examples / "python/run.py"),
        "drivers": {label: {"path_name": Path(p).name, "sha256": sha256_file(Path(p)),
                            "version": subprocess.run([str(p), "--version"], capture_output=True, text=True).stdout.strip()}
                    for label, p in drivers.items()},
        "artifact_blob_sha1_ok": hashlib.sha1(b"blob %d\0" % len(ARTIFACT_PATH.read_bytes()) + ARTIFACT_PATH.read_bytes()).hexdigest() == ARTIFACT_BLOB,
        "forbidden_env_present": [n for n in FORBIDDEN_ENV if os.environ.get(n)],
        "display": os.environ.get("DISPLAY"),
        "xdg_runtime_private": bool(os.environ.get("XDG_RUNTIME_DIR"))
        and Path(os.environ["XDG_RUNTIME_DIR"]).parent == session_dir,
        "openbox_wm_conflict": "already running" in obx.lower(),
        "harness_files_sha256": {p.name: sha256_file(p) for p in sorted(HERE.glob("*.py"))},
        "python": sys.version.split()[0],
        "loadavg_at_start": loadavg(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    expected_u = BINARIES["U"]
    ok_drivers = all((label != "U" or d["sha256"] == expected_u) for label, d in result["drivers"].items())
    result["ok"] = bool(result["display"] and result["xdg_runtime_private"] and not result["forbidden_env_present"]
                        and not result["rust_dirty"] and not result["examples_dirty"] and ok_drivers
                        and result["rust_tree_at_head"] == FIX_A_RUST_TREE and result["artifact_blob_sha1_ok"]
                        and not result["openbox_wm_conflict"])
    return result


def load_artifact() -> dict:
    import compiled_routine as cr

    artifact = json.loads(ARTIFACT_PATH.read_text())
    cr.require_clean(artifact)  # logical identity only: no refs/tokens/captures/epochs/coordinates
    return artifact


def read_cell_journal(out: Path, cell_id: str) -> list[dict]:
    for line in (out / "cells" / f"{cell_id}.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "target_journal":
            return rec["events"]
    return []


# ------------------------------------------------------------------ routine rows (C1, C3, C6 reattach, G4, G5)


def routine_cell(args, out: Path, *, phase: str, row: str, rep: int, variant: str, hook: str | None,
                 fault=None, mode="immediate") -> dict:
    cell = base.run_inprocess_cell(args, out, phase=phase, row=row, rep=rep, artifact=args.artifact_obj,
                                   hook_kind=hook, variant=variant, fault=fault, mode=mode)
    events = read_cell_journal(out, cell["cell_id"])
    summary = fix01_fixture.journal_summary(events)
    clicks = [m for m in cell["mutations"] if m.get("action") == "browser_click"]
    first_click = clicks[0] if clicks else {}
    cell.update({
        "driver_label": args.driver_label, "journal_summary": summary,
        "first_click_result": first_click.get("result"), "first_click_code": first_click.get("code"),
        "first_click_effect": first_click.get("effect"),
        "click_dispatches": len(clicks),
        "refusals": sum(1 for m in cell["mutations"] if m.get("result") == "refused"),
        "rebinds_after_refusal": sum(1 for m in clicks if m.get("attempt", 1) > 1),
        "nonloopback_refused_total": NONLOOPBACK["refused"],
    })
    return cell


# ------------------------------------------------------------------ ordinary run.py rows (C2, C5, C6 fill)


def load_runner(args, which: str):
    if which == "fixed":
        import run as runner

        return runner
    path = Path(os.environ["TMPDIR"]) / "fix01_old_run" / "run_old.py"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(["git", "-C", str(args.examples.parents[2]), "cat-file", "blob", OLD_RUN_PY_BLOB],
                              capture_output=True, check=True).stdout
        path.write_bytes(blob)
    if "run_old" in sys.modules:
        return sys.modules["run_old"]
    spec = importlib.util.spec_from_file_location("run_old", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_old"] = module
    spec.loader.exec_module(module)
    assert hashlib.sha1(b"blob %d\0" % len(path.read_bytes()) + path.read_bytes()).hexdigest() == OLD_RUN_PY_BLOB
    return module


async def ordinary_trial(args, fixture, *, token: str, runner, hook: str | None) -> dict:
    import r2_07_launcher

    base.FEEDBACK_SINK[:] = []
    r2_07_launcher.install_feedback_off(runner, emit=base.FEEDBACK_SINK.append)
    os.environ["CUA_DRIVER_BIN"] = str(args.driver)
    hook_log: list[dict] = []
    calls: list[dict] = []
    inner = runner.Driver.call
    t0 = now()

    async def call(self, name, arguments):
        if name == "browser_click" and not hook_log and hook == "rerender_before_click":
            fixture.trigger_rerender()
            ok = await asyncio.to_thread(fixture.wait_rerendered, 5.0)
            hook_log.append({"hook": hook, "rerender_acked": ok, "t_ms": round((now() - t0) / 1e6, 3)})
        elif name == "browser_click" and not hook_log and hook == "supersede_before_click":
            snap = await inner(self, "get_browser_state", {"target_id": arguments["target_id"],
                                                           "tab_id": arguments["tab_id"],
                                                           "snapshot_format": "semantic_v2"})
            hook_log.append({"hook": hook, "superseding_snapshot": (snap.get("snapshot") or {}).get("id"),
                             "t_ms": round((now() - t0) / 1e6, 3)})
        entry = {"tool": name, "ref_snapshot": str(arguments.get("ref", "")).split(":")[0] or None,
                 "t_ms": round((now() - t0) / 1e6, 3)}
        if name == "get_browser_state" and arguments.get("snapshot_format"):
            entry["observation"] = True
        try:
            data = await inner(self, name, arguments)
            entry.update({"ok": True, "effect": data.get("effect") if isinstance(data, dict) else None,
                          "route": data.get("route") if isinstance(data, dict) else None})
            if name == "get_browser_state" and isinstance(data, dict):
                entry["snapshot_id"] = (data.get("snapshot") or {}).get("id")
            entry["journal_applied_at_return"] = fixture.journal.snapshot()["applied"]
            return data
        except Exception as error:
            entry.update({"ok": False, "code": getattr(error, "code", None),
                          "refused": getattr(error, "refused", None), "error": type(error).__name__})
            raise
        finally:
            calls.append(entry)

    runner.Driver.call = call
    log = Path(os.environ["TMPDIR"]) / f"fix01-ord-{uuid.uuid4().hex[:8]}.jsonl"
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
    events = base.read_jsonl(log)
    log.unlink(missing_ok=True)
    return {"outcome": outcome, "hook_log": hook_log, "driver_calls": calls, "runner_events": events,
            "wall_ms": round((now() - started) / 1e6, 3), "feedback_off": list(base.FEEDBACK_SINK)}


def ordinary_cell(args, out: Path, *, phase: str, row: str, rep: int, runner_which: str, variant: str,
                  hook: str | None) -> dict:
    cell_id = f"{phase}-{row}-{args.driver_label}-{runner_which}-rep{rep}"
    token = f"fix01-{uuid.uuid4().hex[:12]}"
    runner = load_runner(args, runner_which)
    fixture = start_fixture(args.examples)
    fixture.configure(cell_id, token, variant=variant)
    before = base.session_pids(os.environ["XDG_RUNTIME_DIR"])
    la = loadavg()
    result = asyncio.run(ordinary_trial(args, fixture, token=token, runner=runner, hook=hook))
    journal_before_release = {k: v for k, v in fixture.journal.snapshot().items() if k != "events"}
    fixture.journal.release_all("harness_release_after_caller_finished")
    fixture.journal.wait_quiescent(15)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = base.reap_cell_leftovers(before)
    calls = result["driver_calls"]
    clicks = [i for i, c in enumerate(calls) if c["tool"] == "browser_click"]
    # Oracle for C2: re-dispatches after an accepted click whose effect the target had not applied.
    first_unverified_accepted = next((i for i in clicks if calls[i].get("ok") and calls[i].get("effect") != "refused"
                                      and calls[i].get("journal_applied_at_return") == 0), None)
    redispatches = 0 if first_unverified_accepted is None else sum(1 for i in clicks if i > first_unverified_accepted)
    refused_calls = [c for c in calls if (not c.get("ok") and c.get("refused")) or c.get("effect") == "refused"]
    first_click = calls[clicks[0]] if clicks else {}
    classified_refused = bool(first_click) and not first_click.get("ok") and bool(first_click.get("refused"))
    accepted_as_success = bool(first_click) and bool(first_click.get("ok")) and first_click.get("effect") == "refused"
    observations_between = (sum(1 for c in calls[clicks[0] + 1:clicks[1]] if c.get("observation"))
                            if len(clicks) >= 2 else None)
    summary = fix01_fixture.journal_summary(journal["events"])
    outcome_events = [e for e in result["runner_events"] if e.get("event") == "outcome"]
    cell = {
        "cell_id": cell_id, "phase": phase, "row": row, "rep": rep, "driver_label": args.driver_label,
        "runner": runner_which, "variant": variant, "hook": hook, "loadavg_start": la, "loadavg_end": loadavg(),
        "outcome": result["outcome"], "final_outcome_event": outcome_events[-1] if outcome_events else None,
        "hook_log": result["hook_log"], "driver_calls": calls, "feedback_off": result["feedback_off"],
        "wall_ms_informational": result["wall_ms"],
        "click_dispatches": len(clicks), "redispatches_after_unverified_accepted": redispatches,
        "first_click_classified_refused": classified_refused,
        "first_click_refused_accepted_as_success": accepted_as_success,
        "first_click_code": first_click.get("code"), "first_click_effect": first_click.get("effect"),
        "refusals_seen": len(refused_calls), "observations_between_first_and_second_click": observations_between,
        "runner_step_events_with_action_refused": sum(1 for e in result["runner_events"] if e.get("action_refused")),
        "journal_before_release": journal_before_release, "journal_summary": summary,
        "journal_received": journal["received"], "journal_applied": journal["applied"],
        "duplicate_submits": max(0, journal["applied"] - 1),
        "independently_verified": journal["applied"] == 1 and journal["state_matches_token"],
        "nonloopback_refused_total": NONLOOPBACK["refused"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    cell["unverified_success"] = cell["outcome"] == "verified" and not cell["independently_verified"]
    path = out / "cells" / f"{cell_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        stream.write(json.dumps({"type": "runner_events", "events": result["runner_events"]}, sort_keys=True) + "\n")
        stream.write(json.dumps({"type": "target_journal", "events": journal["events"]}, sort_keys=True) + "\n")
    return cell


# ------------------------------------------------------------------ direct rows (C4, C4w, C6 toggle/modal)


async def direct_trial(args, fixture, *, token: str, kind: str, delay_ms: float | None = None) -> dict:
    """Fresh-bound two-step caller without a provider. kind: trusted_before | trusted_during | toggle | modal."""
    import run as runner
    import r2_07_launcher
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment

    base.FEEDBACK_SINK[:] = []
    r2_07_launcher.install_feedback_off(runner, emit=base.FEEDBACK_SINK.append)
    os.environ["CUA_DRIVER_BIN"] = str(args.driver)
    params = StdioServerParameters(command=str(args.driver), args=["mcp"], env=driver_environment())
    rec: dict = {"mutations": [], "observations": 0, "hook": [], "outcome": "running"}
    t0 = now()

    def ms() -> float:
        return round((now() - t0) / 1e6, 3)

    async def observe(driver, target_id, tab_id) -> dict:
        rec["observations"] += 1
        return await driver.call("get_browser_state", {"target_id": target_id, "tab_id": tab_id,
                                                       "snapshot_format": "semantic_v2"})

    def bind(snap, role, name):
        refs = [r for r in snap.get("refs") or [] if r.get("role") == role and r.get("name") == name]
        return refs[0] if len(refs) == 1 else None

    async def mutate(driver, tool, arguments, label):
        entry = {"label": label, "tool": tool, "ref_snapshot": str(arguments.get("ref", "")).split(":")[0],
                 "t_send_ms": ms(), "args": {k: v for k, v in arguments.items() if k in ("input_route", "delivery_mode", "replace")}}
        try:
            data = await driver.call(tool, arguments)
            entry.update({"result": "accepted", "effect": data.get("effect"), "route": data.get("route")})
        except Exception as error:  # noqa: BLE001
            code = getattr(error, "code", None)
            entry.update({"result": "refused" if getattr(error, "refused", False) else "error", "code": code,
                          "error": type(error).__name__})
        entry["t_return_ms"] = ms()
        rec["mutations"].append(entry)
        return entry

    async def bounded(predicate, deadline_s=3.0):
        started = time.monotonic()
        while time.monotonic() - started < deadline_s:
            if predicate(fix01_fixture.journal_summary(fixture.journal.snapshot()["events"])):
                return True
            await asyncio.sleep(0.01)
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
            t0 = now()
            if kind.startswith("trusted"):
                snap = await observe(driver, target_id, tab_id)
                field = bind(snap, "textbox", "verification value")
                await mutate(driver, "browser_type", {**base_args, "ref": field["ref"], "text": token, "replace": True}, "type")
                for attempt in (1, 2):
                    snap = await observe(driver, target_id, tab_id)
                    submit = bind(snap, "button", "Submit")
                    if submit is None:
                        rec["outcome"] = "stopped:submit_not_unique"
                        break
                    click = {**base_args, "ref": submit["ref"], "input_route": "trusted", "delivery_mode": "foreground"}
                    if attempt == 1 and kind == "trusted_before":
                        fixture.trigger_rerender()
                        acked = await asyncio.to_thread(fixture.wait_rerendered, 5.0)
                        rec["hook"].append({"rerender": "before_dispatch", "acked": acked, "t_ms": ms()})
                    if attempt == 1 and kind == "trusted_during":
                        async def later():
                            await asyncio.sleep(delay_ms / 1000.0)
                            fixture.trigger_rerender()
                            rec["hook"].append({"rerender": "during_dispatch", "delay_ms": delay_ms, "t_ms": ms()})
                        task = asyncio.create_task(later())
                        entry = await mutate(driver, "browser_click", click, f"click{attempt}")
                        await task
                        await asyncio.to_thread(fixture.wait_rerendered, 5.0)
                    else:
                        entry = await mutate(driver, "browser_click", click, f"click{attempt}")
                    if entry["result"] == "accepted":
                        landed = await bounded(lambda s: s["applied"] >= 1)
                        rec["outcome"] = "verified" if landed else "unknown"
                        break
                    if entry["result"] == "refused" and entry.get("code") == "browser_ref_stale" and attempt == 1:
                        continue  # exactly one fresh observation and one fresh dispatch
                    rec["outcome"] = f"stopped:{entry['result']}:{entry.get('code')}"
                    break
            elif kind == "toggle":
                snap = await observe(driver, target_id, tab_id)
                box = bind(snap, "checkbox", "feature")
                e1 = await mutate(driver, "browser_click", {**base_args, "ref": box["ref"], "input_route": "dom_event"}, "toggle")
                snap = await observe(driver, target_id, tab_id)
                go = bind(snap, "button", "Confirm")
                e2 = await mutate(driver, "browser_click", {**base_args, "ref": go["ref"], "input_route": "dom_event"}, "confirm")
                ok = e1["result"] == e2["result"] == "accepted" and await bounded(lambda s: s["toggle_events_checked"] >= 1)
                rec["outcome"] = "verified" if ok else "unknown"
            elif kind == "modal":
                snap = await observe(driver, target_id, tab_id)
                opener = bind(snap, "button", "Open dialog")
                e1 = await mutate(driver, "browser_click", {**base_args, "ref": opener["ref"], "input_route": "dom_event"}, "open")
                await bounded(lambda s: s["opened_events"] >= 1, 2.0)
                snap = await observe(driver, target_id, tab_id)
                act = bind(snap, "button", "Confirm choice")
                e2 = await mutate(driver, "browser_click", {**base_args, "ref": act["ref"], "input_route": "dom_event"}, "act")
                ok = e1["result"] == e2["result"] == "accepted" and await bounded(
                    lambda s: s["opened_events"] >= 1 and s["modal_events"] >= 1)
                rec["outcome"] = "verified" if ok else "unknown"
    rec["feedback_off"] = list(base.FEEDBACK_SINK)
    return rec


def direct_cell(args, out: Path, *, phase: str, row: str, rep: int, variant: str, kind: str,
                delay_ms: float | None = None) -> dict:
    cell_id = f"{phase}-{row}-{args.driver_label}-rep{rep}" + (f"-d{delay_ms:g}" if delay_ms is not None else "")
    token = f"fix01-{uuid.uuid4().hex[:12]}"
    fixture = start_fixture(args.examples)
    fixture.configure(cell_id, token, variant=variant)
    before = base.session_pids(os.environ["XDG_RUNTIME_DIR"])
    la = loadavg()
    started = now()
    try:
        rec = asyncio.run(direct_trial(args, fixture, token=token, kind=kind, delay_ms=delay_ms))
    except BaseException as error:  # noqa: BLE001
        if isinstance(error, KeyboardInterrupt):
            raise
        rec = {"outcome": f"error:{type(error).__name__}", "mutations": [], "observations": 0, "hook": []}
    wall = round((now() - started) / 1e6, 3)
    fixture.journal.release_all("harness_release_after_caller_finished")
    fixture.journal.wait_quiescent(15)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = base.reap_cell_leftovers(before)
    summary = fix01_fixture.journal_summary(journal["events"])
    page = [e for e in journal["events"] if e.get("kind") == "page_event"]
    t_rerender = next((e["page_t_ms"] for e in page if e.get("node") == "page"), None)
    first_down = next((e for e in page if e.get("event") in ("pointerdown", "mousedown")), None)
    clicks = [m for m in rec["mutations"] if m["tool"] == "browser_click"]
    cell = {
        "cell_id": cell_id, "phase": phase, "row": row, "rep": rep, "driver_label": args.driver_label,
        "variant": variant, "kind": kind, "delay_ms": delay_ms, "loadavg_start": la, "loadavg_end": loadavg(),
        "outcome": rec["outcome"], "mutations": rec["mutations"], "hook": rec["hook"],
        "observations": rec["observations"], "feedback_off": rec.get("feedback_off"), "wall_ms_informational": wall,
        "first_click_result": clicks[0]["result"] if clicks else None,
        "first_click_code": clicks[0].get("code") if clicks else None,
        "click_dispatches": len(clicks), "refusals": sum(1 for m in rec["mutations"] if m["result"] == "refused"),
        "journal_summary": summary, "journal_applied": journal["applied"],
        "independently_verified": (journal["applied"] == 1 and journal["state_matches_token"]) if kind.startswith("trusted")
        else (summary["toggle_events_checked"] >= 1 if kind == "toggle" else summary["opened_events"] >= 1 and summary["modal_events"] >= 1),
        "page_t_rerender_ms": t_rerender,
        "page_first_down_node": first_down.get("node") if first_down else None,
        "page_first_down_minus_rerender_ms": (round(first_down["page_t_ms"] - t_rerender, 3)
                                              if first_down and t_rerender is not None else None),
        "nonloopback_refused_total": NONLOOPBACK["refused"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    cell["unverified_success"] = cell["outcome"] == "verified" and not cell["independently_verified"]
    path = out / "cells" / f"{cell_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        stream.write(json.dumps({"type": "target_journal", "events": journal["events"]}, sort_keys=True) + "\n")
    return cell


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--examples", type=Path, required=True)
    ap.add_argument("--driver", type=Path)
    ap.add_argument("--driver-label", default="F")
    ap.add_argument("--driver-u", type=Path)
    ap.add_argument("--driver-f", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--start-rep", type=int, default=1)
    ap.add_argument("--runner", default="fixed", choices=("old", "fixed"))
    ap.add_argument("--rows", default="")
    ap.add_argument("--delays", default="")
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--start-pair", type=int, default=0)
    args = ap.parse_args()
    args.examples = args.examples.resolve()
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        print("refusing: not inside the private X11 session", file=sys.stderr)
        return 97
    for p in (str(args.examples), str(args.examples / "python")):
        sys.path.insert(0, p)
    args.out.mkdir(parents=True, exist_ok=False)
    if args.phase == "g6":
        args.driver = args.driver_f
        args.driver_label = "UF"
    check = validity(args)
    (args.out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "display": check["display"]}), flush=True)
    if not check["ok"]:
        return 2
    args.artifact_obj = load_artifact()
    cells_out = (args.out / "cells.jsonl").open("a", encoding="utf-8")

    def emit(cell: dict) -> None:
        slim = {k: v for k, v in cell.items() if k not in ("events", "runner_events", "driver_calls", "observations")
                or not isinstance(v, list)}
        cells_out.write(json.dumps(slim, sort_keys=True, default=str) + "\n")
        cells_out.flush()
        print(json.dumps({"event": "cell", "id": cell["cell_id"], "outcome": cell.get("outcome", cell.get("reported_outcome")),
                          "verified": cell.get("independently_verified"), "first": cell.get("first_click_result"),
                          "code": cell.get("first_click_code"), "dup": cell.get("duplicate_submits")}), flush=True)

    reps = range(args.start_rep, args.start_rep + args.reps)
    ph = args.phase
    if ph in ("c1", "c3", "c6reattach"):
        variant = {"c1": "n4a_instr", "c3": "n4a_handler", "c6reattach": "reattach"}[ph]
        for rep in reps:
            emit(routine_cell(args, args.out, phase=ph, row=f"{ph}-{args.driver_label}", rep=rep, variant=variant,
                              hook="rerender_before_submit"))
    elif ph == "c2":
        for rep in reps:
            emit(ordinary_cell(args, args.out, phase=ph, row="N4a_ord", rep=rep, runner_which=args.runner,
                               variant="n4a_instr", hook="rerender_before_click"))
    elif ph == "c5":
        for rep in reps:
            emit(ordinary_cell(args, args.out, phase=ph, row="N4b_ord", rep=rep, runner_which=args.runner,
                               variant="normal", hook="supersede_before_click"))
    elif ph == "c6fill":
        for rep in reps:
            emit(ordinary_cell(args, args.out, phase=ph, row="fill", rep=rep, runner_which="fixed",
                               variant="normal", hook=None))
    elif ph == "c4":
        for rep in reps:
            emit(direct_cell(args, args.out, phase=ph, row="trusted_n4a", rep=rep, variant="trusted_probe",
                             kind="trusted_before"))
    elif ph == "c4w":
        for i, d in enumerate(float(x) for x in args.delays.split(",") if x):
            emit(direct_cell(args, args.out, phase=ph, row="trusted_window", rep=i + 1, variant="trusted_probe",
                             kind="trusted_during", delay_ms=d))
    elif ph in ("c6toggle", "c6modal"):
        for rep in reps:
            emit(direct_cell(args, args.out, phase=ph, row=ph[2:], rep=rep,
                             variant="n8_toggle" if ph == "c6toggle" else "modal_act",
                             kind="toggle" if ph == "c6toggle" else "modal"))
    elif ph == "g4":
        for row in [r for r in args.rows.split(",") if r]:
            spec = base.NEG_ROWS[row]
            for rep in reps:
                emit(routine_cell(args, args.out, phase="g4", row=row, rep=rep, variant=spec["variant"],
                                  hook=spec.get("hook")))
    elif ph == "g5":
        for row in [r for r in args.rows.split(",") if r]:
            spec = base.P6_ROWS[row]
            for rep in reps:
                emit(routine_cell(args, args.out, phase="g5", row=row, rep=rep, variant="normal", hook=None,
                                  fault={"fault": spec["fault"], "barrier": spec["barrier"]}, mode=spec["mode"]))
    elif ph in ("g2", "g6"):
        budget = base.Budget(args.out / "budget.json")
        art = args.out / "artifact.json"
        art.write_text(ARTIFACT_PATH.read_text())
        if ph == "g2":
            plan = [(0, 1, "F")]
        else:
            plan = []
            for pair in range(args.start_pair, args.start_pair + args.pairs):
                order = "UF" if pair % 2 == 0 else "FU"
                plan += [(pair, pos, label) for pos, label in enumerate(order, start=1)]
        for rnd, pos, label in plan:
            cell_args = copy.copy(args)
            cell_args.driver = args.driver_u if label == "U" else (args.driver_f or args.driver)
            try:
                cell = base.run_subprocess_cell(cell_args, args.out, phase=ph, rnd=rnd, pos=pos, arm=f"C{label}",
                                                provider="none", artifact=art, fallback="none")
            except Exception as error:  # noqa: BLE001 - every failure stays in the denominator
                cell = {"cell_id": f"{ph}-r{rnd:03d}-{pos}-C{label}", "harness_error": f"{type(error).__name__}: {error}",
                        "http_attempts": 0, "http_reached": 0}
            cell["driver_label"] = label
            budget.add(cell["cell_id"], int(cell.get("http_attempts") or 0), int(cell.get("http_reached") or 0))
            emit(cell)
            time.sleep(0.3)
    else:
        print(f"unknown phase {ph}", file=sys.stderr)
        return 64
    (args.out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "loadavg_at_end": loadavg(),
        "nonloopback_refused_in_process": NONLOOPBACK["refused"]}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

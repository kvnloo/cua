#!/usr/bin/env python3
"""FIX-04 Part D browser rows (copy of FIX-03 harness/browser/fix03_browser.py; diff in
fix04_browser.fix03.diff): the F4 check-to-assignment (TOCTOU) window of browser_set_input_files,
re-run on F6. Additions: every set_input_files call also records the RAW structuredContent fields
(status, effect, refusal code, detail delivery / retryable) from the MCP result, and the jev-use
runner's own view of that same result object (run.Driver classification + run.may_redispatch_after),
without a second dispatch. Arms F6 / F5 / U.

Original FIX-03 docstring:
FIX-03 Part A browser rows: the F4 check-to-assignment (TOCTOU) window of browser_set_input_files.

MEASUREMENT HARNESS ONLY. Run ONLY inside cua-x11-session.sh (refuses otherwise), under hostless,
with the shared quiet-lane lock taken OUTSIDE (harness/a3/qlock.sh). Reuses, imported unchanged:
harness/fix02-w3/browser/fix02_fixture.py (the wave-3 ``file_rerender`` page: an
``<input type=file aria-label="attachment">`` whose node-level input/change listeners beacon every
event with the node's generation, ``old`` = generation 0, ``fresh`` = generation 1, plus a poll of the
OLD node's ``files``) and its fix-01 / r2-07 helpers. Provider cap 0: no chooser, no model; a socket
guard refuses and counts any non-loopback connect.

usage: fix03_browser.py --phase a1|a3 --examples <wt>/libs/cua-driver/examples/jev-use
         --driver <bin> --arm FS|F5|F --out <dir> [--reps N] [--start-rep K] [--gap-ms 50]
  a1  forced race. The Driver runs with CUA_DRIVER_EXP_SET_FILES_GAP_MS=<gap>. The harness reads the
      Driver's stderr; when the seam marker ``set_files_gap_begin`` appears (the connectedness check
      has passed and the assignment has not been sent), it releases the page's re-render, which
      replaces the input (generation 0 -> 1) inside the gap. Then A2 (rebind): one fresh observation,
      bind the fresh ref, set the files on the live node.
  a3  default path. No seam variable, no re-render: bind the input and set the files once.
Every cell is a fresh Driver process, a fresh Chrome (browser_prepare isolated_new) and a fresh
fixture server. The target-owned oracle is the fixture's journal (page beacons keyed by node
generation, the re-render ack), never the Driver's receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
W3 = HERE.parents[2] / "fix-03-toctou-session-routing-2026-10-03" / "harness" / "fix02-w3"
for _p in (W3 / "browser", W3 / "fix-01", W3 / "r2-07"):
    sys.path.insert(0, str(_p))
if "--examples" in sys.argv:
    _ex = Path(sys.argv[sys.argv.index("--examples") + 1]).resolve()
    sys.path[:0] = [str(_ex), str(_ex / "python")]

SEAM_ENV = "CUA_DRIVER_EXP_SET_FILES_GAP_MS"
SEAM_MARKER = "[cua-exp] set_files_gap_begin"
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
            raise ConnectionRefusedError("FIX-03: non-loopback connect refused (provider cap 0)")
        return connect(self, address)

    def guarded_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address):
            NONLOOPBACK["refused"] += 1
            return 111
        return connect_ex(self, address)

    socket.socket.connect, socket.socket.connect_ex = guarded, guarded_ex


install_socket_guard()

import fix02_fixture  # noqa: E402  (unchanged wave-3 copy)
import r2_07_harness as base  # noqa: E402  (session_pids, reap_cell_leftovers, FEEDBACK_SINK)


def now() -> int:
    return time.monotonic_ns()


def loadavg() -> list[str]:
    return Path("/proc/loadavg").read_text().split()[:3]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(wt: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(wt), *a], capture_output=True, text=True).stdout.strip()


def validity(args) -> dict:
    wt = args.examples.parents[2]
    session_dir = Path(os.environ.get("TMPDIR", "/nonexistent")).parent
    result = {
        "phase": args.phase, "arm": args.arm, "gap_ms": args.gap_ms if args.phase == "a1" else None,
        "harness_head": git(wt, "rev-parse", "HEAD"),
        "driver": {"path_name": args.driver.name, "sha256": sha256_file(args.driver),
                   "version": subprocess.run([str(args.driver), "--version"], capture_output=True,
                                             text=True).stdout.strip()},
        "forbidden_env_present": [n for n in FORBIDDEN_ENV if os.environ.get(n)],
        "seam_env_in_harness_env": os.environ.get(SEAM_ENV),
        "display": os.environ.get("DISPLAY"),
        "xdg_runtime_private": bool(os.environ.get("XDG_RUNTIME_DIR"))
        and Path(os.environ["XDG_RUNTIME_DIR"]).parent == session_dir,
        "harness_files_sha256": {f"{p.parent.name}/{p.name}": sha256_file(p)
                                 for d in (HERE, W3 / "browser", W3 / "fix-01", W3 / "r2-07")
                                 for p in sorted(d.glob("*.py"))},
        "python": sys.version.split()[0],
        "loadavg_at_start": loadavg(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    result["ok"] = bool(result["display"] and result["xdg_runtime_private"]
                        and not result["forbidden_env_present"] and not result["seam_env_in_harness_env"])
    return result


class StderrWatch:
    """Reads the Driver's stderr; on the seam marker, releases the page re-render exactly once."""

    def __init__(self, fixture, t0: int, arm_release: bool) -> None:
        self.fixture = fixture
        self.t0 = t0
        self.arm_release = arm_release
        self.marker_ms: float | None = None
        self.release_ms: float | None = None
        self.markers = 0
        read_fd, write_fd = os.pipe()
        self.errlog = os.fdopen(write_fd, "w")
        self._read = os.fdopen(read_fd, "r", errors="replace")
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        for line in self._read:
            if SEAM_MARKER in line:
                self.markers += 1
                if self.marker_ms is None:
                    self.marker_ms = round((now() - self.t0) / 1e6, 3)
                    if self.arm_release:
                        self.fixture.trigger_rerender()
                        self.release_ms = round((now() - self.t0) / 1e6, 3)

    def close(self) -> None:
        try:
            self.errlog.close()
        except OSError:
            pass
        self.thread.join(timeout=5)


async def file_trial(args, fixture, *, upload: Path, t0: int, watch: StderrWatch) -> dict:
    import run as runner
    import r2_07_launcher
    from driver_env import driver_environment
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    base.FEEDBACK_SINK[:] = []
    r2_07_launcher.install_feedback_off(runner, emit=base.FEEDBACK_SINK.append)
    env = driver_environment()
    env.pop(SEAM_ENV, None)
    if args.phase == "a1":
        env[SEAM_ENV] = str(args.gap_ms)
    params = StdioServerParameters(command=str(args.driver), args=["mcp"], env=env)
    rec: dict = {"steps": [], "observations": 0, "outcome": "running",
                 "seam_env": env.get(SEAM_ENV)}

    def ms() -> float:
        return round((now() - t0) / 1e6, 3)

    async def observe(driver, target_id, tab_id) -> dict:
        rec["observations"] += 1
        return await driver.call("get_browser_state", {"target_id": target_id, "tab_id": tab_id,
                                                       "snapshot_format": "semantic_v2"})

    def bind(snap) -> dict | None:
        refs = [r for r in snap.get("refs") or [] if r.get("name") == "attachment"]
        return refs[0] if len(refs) == 1 else None

    class OneResult:
        """Replays one recorded MCP result to run.Driver (the runner's classification, no dispatch)."""

        def __init__(self, result) -> None:
            self.result = result

        async def call_tool(self, _name, _args):
            return self.result

    async def set_files(driver, base_args, ref, label) -> dict:
        entry = {"label": label, "ref_snapshot": ref["ref"].split(":")[0], "role": ref.get("role"),
                 "t_send_ms": ms()}
        arguments = {**base_args, "ref": ref["ref"], "files": [str(upload)]}
        raw = await driver.session.call_tool("browser_set_input_files", {**arguments, "session": driver.label})
        rec["set_input_files_dispatches"] = rec.get("set_input_files_dispatches", 0) + 1
        sc = raw.structuredContent if isinstance(raw.structuredContent, dict) else {}
        refusal = sc.get("refusal") if isinstance(sc.get("refusal"), dict) else {}
        detail = refusal.get("detail") if isinstance(refusal.get("detail"), dict) else {}
        entry["raw"] = {"is_error": bool(raw.isError), "status": sc.get("status"), "effect": sc.get("effect"),
                        "keys": sorted(sc), "refusal_code": refusal.get("code"),
                        "delivery": detail.get("delivery"), "retryable": detail.get("retryable", "absent")}
        # The replay Driver shares the real Driver's session label, whose cursor feedback the
        # launcher already held OFF; mark it so the feedback-off wrapper does not re-send through
        # the replay (which would answer every tool with this one result).
        replay = runner.Driver(OneResult(raw), driver.label)
        replay._r207_feedback_label = driver.label
        try:
            data = await replay.call("browser_set_input_files", arguments)
            entry.update({"result": "accepted", "status": data.get("status"),
                          "receipt_keys": sorted(data), "receipt": {k: data.get(k) for k in
                                                                    ("status", "frame", "file_count")}})
        except Exception as error:  # noqa: BLE001 - every outcome stays in the record
            entry.update({"result": "refused" if getattr(error, "refused", False) else "error",
                          "code": getattr(error, "code", None),
                          "retryable": getattr(error, "retryable", "absent"),
                          "delivery_unknown": "'delivery': 'unknown'" in str(error),
                          "runner_may_redispatch": (runner.may_redispatch_after(error)
                                                    if getattr(error, "refused", False) else None),
                          "error": type(error).__name__, "message_head": str(error)[:240]})
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

    async with stdio_client(params, errlog=watch.errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            driver = runner.Driver(session, f"jev-python-{uuid.uuid4().hex[:8]}")
            prepared = await driver.call("browser_prepare", {"allow_launch": True,
                                                             "profile": {"mode": "isolated_new"}})
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
            first = await set_files(driver, base_args, old, "gen0_ref")
            if args.phase == "a3":
                landed = first["result"] == "accepted" and await bounded(
                    lambda s: any(k == "old:change1" for k in s["page_event_kinds"]))
                rec["outcome"] = "verified" if landed else "unknown"
                return rec
            rec["rerender_acked"] = await asyncio.to_thread(fixture.wait_rerendered, 5.0)
            await asyncio.sleep(1.0)  # late old-node events and the old-node files poll reach the journal
            snap = await observe(driver, target_id, tab_id)
            fresh = bind(snap)
            if fresh is None:
                rec["outcome"] = "stopped:fresh_file_input_not_unique"
                return rec
            second = await set_files(driver, base_args, fresh, "gen1_ref_rebind")
            landed = second["result"] == "accepted" and await bounded(lambda s: s["fresh_change_with_file"] >= 1)
            rec["outcome"] = "verified" if landed else "unknown"
    return rec


def page_order(events: list[dict]) -> dict:
    """Page-clock order of the re-render and the first generation-0 file event (both page beacons)."""
    page = [e for e in events if e.get("kind") == "page_event"]
    rerender = [e.get("page_t_ms") for e in page if e.get("node") == "page" and e.get("event") == "rerendered"]
    old_input = [e.get("page_t_ms") for e in page if e.get("node") == "old"
                 and str(e.get("event", "")).startswith(("input", "change"))]
    return {"rerender_page_ms": rerender[0] if rerender else None,
            "first_gen0_event_page_ms": min(old_input) if old_input else None,
            "detached_before_assignment": bool(rerender and old_input and rerender[0] < min(old_input))}


def file_cell(args, out: Path, *, rep: int) -> dict:
    cell_id = f"{args.phase}-{args.arm}-rep{rep:02d}"
    token = f"fix03-{uuid.uuid4().hex[:12]}"
    upload = Path(os.environ["TMPDIR"]) / "fix03-upload.txt"
    upload.write_text("FIX-03 upload fixture (no secret content)\n")
    fixture = fix02_fixture.JournalFixture()
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    fixture.configure(cell_id, token, variant="file_rerender")
    before = base.session_pids(os.environ["XDG_RUNTIME_DIR"])
    la = loadavg()
    t0 = now()
    watch = StderrWatch(fixture, t0, arm_release=(args.phase == "a1"))
    try:
        rec = asyncio.run(file_trial(args, fixture, upload=upload, t0=t0, watch=watch))
    except BaseException as error:  # noqa: BLE001 - every failure stays in the denominator
        if isinstance(error, KeyboardInterrupt):
            raise
        rec = {"outcome": f"error:{type(error).__name__}:{str(error)[:200]}", "steps": [], "observations": 0}
    watch.close()
    wall = round((now() - t0) / 1e6, 3)
    time.sleep(0.5)
    journal = fixture.journal.snapshot()
    fixture.shutdown()
    fixture.server_close()
    leftovers, killed = base.reap_cell_leftovers(before)
    summary = fix02_fixture.journal_summary(journal["events"])
    order = page_order(journal["events"])
    first = rec["steps"][0] if rec["steps"] else {}
    second = rec["steps"][1] if len(rec["steps"]) > 1 else {}
    gen0_file_events = summary["old_file_events"]
    cell = {
        "cell_id": cell_id, "phase": args.phase, "rep": rep, "arm": args.arm, "gap_ms": rec.get("seam_env"),
        "loadavg_start": la, "loadavg_end": loadavg(), "wall_ms_informational": wall,
        "outcome": rec["outcome"], "steps": rec["steps"], "observations": rec["observations"],
        "seam_markers": watch.markers, "seam_marker_ms": watch.marker_ms, "rerender_release_ms": watch.release_ms,
        "rerender_acked": rec.get("rerender_acked"), "page_rerendered_events": summary["page_rerendered"],
        **order,
        "first_result": first.get("result"), "first_status": first.get("status"), "first_code": first.get("code"),
        "first_retryable": first.get("retryable"), "first_delivery_unknown": first.get("delivery_unknown"),
        "first_receipt_keys": first.get("receipt_keys"), "first_receipt": first.get("receipt"),
        "gen0_file_events": gen0_file_events,
        "gen0_change_events": sum(1 for k in summary["page_event_kinds"] if k.startswith("old:change")),
        "gen1_change_with_file": summary["fresh_change_with_file"],
        "rebind_result": second.get("result"),
        "rebind_verified": args.phase == "a1" and rec["outcome"] == "verified"
        and summary["fresh_change_with_file"] >= 1,
        "page_event_kinds": summary["page_event_kinds"],
        "nonloopback_refused_total": NONLOOPBACK["refused"],
        "new_session_processes_after_exit": leftovers, "leftover_processes_killed": killed,
    }
    # Race validity (a1): the first seam marker (the first call's gap; the A2 rebind call passes the seam
    # too, so a second marker is expected) fired before the first call returned, the re-render was
    # released on it, and on the page clock the re-render preceded every generation-0 file event (or no
    # generation-0 event happened).
    first_return = first.get("t_return_ms")
    cell["first_marker_inside_first_call"] = bool(watch.marker_ms is not None and first_return is not None
                                                  and first.get("t_send_ms", 0) <= watch.marker_ms <= first_return)
    cell["race_forced"] = bool(args.phase == "a1" and cell["first_marker_inside_first_call"]
                               and watch.release_ms is not None and rec.get("rerender_acked")
                               and (order["detached_before_assignment"] or gen0_file_events == 0))
    cell["success_receipt_for_detached_node"] = bool(args.phase == "a1" and cell["race_forced"]
                                                     and first.get("status") == "ok")
    cell["refused_or_unknown"] = first.get("result") == "refused"
    cell["a3_verified"] = bool(args.phase == "a3" and rec["outcome"] == "verified"
                               and summary["page_rerendered"] == 0 and watch.markers == 0)
    path = out / "cells" / f"{cell_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        stream.write(json.dumps({"type": "cell", **cell}, sort_keys=True, default=str) + "\n")
        stream.write(json.dumps({"type": "target_journal", "events": journal["events"]}, sort_keys=True) + "\n")
    return cell


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=("a1", "a3"))
    ap.add_argument("--examples", type=Path, required=True)
    ap.add_argument("--driver", type=Path, required=True)
    ap.add_argument("--arm", required=True, choices=("F6", "F5", "U"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--start-rep", type=int, default=1)
    ap.add_argument("--gap-ms", type=int, default=50)
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
        cell = file_cell(args, args.out, rep=rep)
        slim = {k: v for k, v in cell.items() if k not in ("steps", "page_event_kinds")}
        cells_out.write(json.dumps(slim, sort_keys=True, default=str) + "\n")
        cells_out.flush()
        print(json.dumps({"event": "cell", "id": cell["cell_id"], "outcome": cell["outcome"],
                          "first": cell["first_result"], "status": cell["first_status"],
                          "code": cell["first_code"], "race": cell["race_forced"],
                          "gen0_events": cell["gen0_file_events"], "rebind": cell["rebind_verified"]}), flush=True)
    (args.out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "loadavg_at_end": loadavg(),
        "nonloopback_refused_in_process": NONLOOPBACK["refused"]}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

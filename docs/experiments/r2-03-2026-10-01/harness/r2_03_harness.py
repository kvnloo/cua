#!/usr/bin/env python3
"""R2-03 AB/BA harness: real Driver + real Chromium + live provider, independent fixture oracle.

Adapted from the local #10 lane harness (scripts/repro/handoff/issue-10-4316-ab/ab_harness.py on
the local evidence lane). Differences: both arms use ONE source tree and ONE Driver binary (only the
--guarded-completion flag differs); default Driver safety settings (no sandbox/permission/approval
overrides, no wrapper); strict AB/BA alternation; per-trial loadavg; responder receipts via
receipt_launcher.py; a provider-request budget; leftover detection limited to processes this cell
started; fixture submit counter; CLOCK_MONOTONIC timestamps shared with the runner process.

Run only inside cua-x11-session.sh. Phases:
  smoke        1 AB pair, --provider mock (harness check; excluded from analysis)
  main         N AB/BA pairs, --provider live (run under the quiet-lane lock)
  decline      guarded arm on the DUPLICATE_SUBMIT_ON_INPUT fixture, --provider live
  unreachable  one cell per arm, TYPESAFE_BASE_URL -> closed loopback port

usage: r2_03_harness.py --phase main --pairs 40 --examples <wt>/libs/cua-driver/examples/jev-use \
         --driver <bin> --tested-sha <sha> --driver-sha256 <sha256> --out <dir> --budget-file <json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "receipt_launcher.py"
REQUEST_CAP = 300
MAX_ATTEMPTS_PER_CELL = 12
FORBIDDEN_ENV = (
    "CUA_DRIVER_PERMISSION_MODE",
    "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS",
    "CUA_E2E_BROWSER_NO_SANDBOX",
    "WAYLAND_DISPLAY",
    "HYPRLAND_INSTANCE_SIGNATURE",
)


def now() -> int:
    return time.monotonic_ns()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def loadavg() -> list[str]:
    return Path("/proc/loadavg").read_text().split()[:3]


def session_pids(xdg_runtime: str) -> dict[int, str]:
    """Live processes carrying this isolated session's XDG_RUNTIME_DIR (all started in this session)."""
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


def closed_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class Budget:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"http_attempts": 0, "by_cell": {}}

    @property
    def used(self) -> int:
        return int(self.data["http_attempts"])

    def can_start(self) -> bool:
        return self.used + MAX_ATTEMPTS_PER_CELL <= REQUEST_CAP

    def add(self, cell_id: str, attempts: int) -> None:
        self.data["http_attempts"] = self.used + attempts
        self.data["by_cell"][cell_id] = attempts
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")


def run_cell(args, out: Path, *, phase: str, pair: int, order: int, arm: str, provider: str) -> dict:
    sys.path.insert(0, str(args.examples))
    import fixture_server
    from fixture_server import FixtureServer

    cell_id = f"{phase}-p{pair:03d}-{order}-{arm}"
    token = f"r2-03-{phase}-{pair:03d}-{arm}"
    cdir = out / "cells" / cell_id
    cdir.mkdir(parents=True, exist_ok=False)
    log_path, receipts_path = cdir / "runner.jsonl", cdir / "receipts.jsonl"

    original_page = fixture_server.PAGE
    if phase == "decline":
        from verify_setup import DUPLICATE_SUBMIT_ON_INPUT

        fixture_server.PAGE = original_page + DUPLICATE_SUBMIT_ON_INPUT
    server = FixtureServer(("127.0.0.1", 0))
    submits: list[int] = []
    original_submit = server.state.submit

    def counted_submit(value: str) -> None:
        submits.append(now())
        original_submit(value)

    server.state.submit = counted_submit  # type: ignore[method-assign]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"

    flags = ["--guarded-completion"] if arm == "guarded" else []
    cmd = [
        str(args.examples / ".venv/bin/python"), str(LAUNCHER), str(args.examples),
        "--provider", provider, "--fixture-url", url, "--token", token, "--max-steps", "4",
        "--log", str(log_path), *flags,
    ]
    env = dict(os.environ)
    env["CUA_DRIVER_BIN"] = str(args.driver)
    env["R2_03_RECEIPT_LOG"] = str(receipts_path)
    if phase == "unreachable":
        env["TYPESAFE_BASE_URL"] = f"http://127.0.0.1:{closed_loopback_port()}"
    if provider != "live":
        env.pop("TYPESAFE_API_KEY", None)

    oracle = {"seen_ns": None, "polls": 0}
    arrivals: list[tuple[int, dict]] = []
    stop = threading.Event()

    def poll_oracle() -> None:
        while not stop.is_set():
            try:
                with urlopen(url + "state", timeout=1) as response:
                    state = json.load(response)
                oracle["polls"] += 1
                if state.get("submitted") == token:
                    oracle["seen_ns"] = now()
                    return
            except Exception:
                pass
            time.sleep(0.004)

    def tail_log() -> None:
        pos, buf = 0, b""
        while not stop.is_set():
            try:
                size = log_path.stat().st_size
            except FileNotFoundError:
                time.sleep(0.002)
                continue
            if size > pos:
                with log_path.open("rb") as handle:
                    handle.seek(pos)
                    chunk = handle.read()
                pos += len(chunk)
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        try:
                            arrivals.append((now(), json.loads(line)))
                        except ValueError:
                            arrivals.append((now(), {"unparsed": True}))
            time.sleep(0.002)

    xdg = os.environ["XDG_RUNTIME_DIR"]
    before = session_pids(xdg)
    cell = {
        "cell_id": cell_id, "phase": phase, "pair": pair, "order": order, "arm": arm,
        "provider_configured": provider, "flags": flags, "token": token,
        "loadavg_at_spawn": loadavg(),
    }
    threads = [threading.Thread(target=poll_oracle, daemon=True), threading.Thread(target=tail_log, daemon=True)]
    with (cdir / "stdout.txt").open("wb") as stdout_f, (cdir / "stderr.txt").open("wb") as stderr_f:
        spawn_ns = now()
        proc = subprocess.Popen(cmd, cwd=args.examples, env=env, stdout=stdout_f, stderr=stderr_f, start_new_session=True)
        for thread in threads:
            thread.start()
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
    for thread in threads:
        thread.join(timeout=2)
    final_state = None
    try:
        with urlopen(url + "state", timeout=2) as response:
            final_state = json.load(response)
    except Exception as error:
        cell["final_state_error"] = type(error).__name__
    server.shutdown()
    server.server_close()
    fixture_server.PAGE = original_page

    time.sleep(0.5)
    leftovers = {pid: comm for pid, comm in session_pids(xdg).items() if pid not in before and pid != os.getpid()}
    killed = []
    for pid, comm in leftovers.items():  # started by this cell only; only browser/Driver leftovers are killed
        if not comm.startswith(("chrome", "cua-driver", "python")):
            continue
        try:
            os.kill(pid, 9)
            killed.append(comm)
        except OSError:
            pass
    cell["new_session_processes_after_exit"] = sorted(leftovers.values())

    receipts = read_jsonl(receipts_path)
    attempts = [r for r in receipts if r.get("kind") == "http_attempt"]
    cell.update(
        {
            "rc": rc, "timed_out": timed_out, "spawn_ns": spawn_ns, "exit_ns": exit_ns,
            "oracle_seen_ns": oracle["seen_ns"], "oracle_polls": oracle["polls"],
            "submit_ns": submits, "submit_count": len(submits), "final_state": final_state,
            "independently_verified": final_state == {"submitted": token} and len(submits) == 1,
            "loadavg_at_exit": loadavg(), "leftover_processes_killed": sorted(killed),
            "http_attempts": len(attempts),
        }
    )
    (cdir / "cell.json").write_text(json.dumps(cell, indent=1, sort_keys=True) + "\n")
    with (cdir / "trial.jsonl").open("w", encoding="utf-8") as raw:
        raw.write(json.dumps({"type": "cell", **cell}, sort_keys=True) + "\n")
        for arrival_ns, event in arrivals:
            raw.write(json.dumps({"type": "runner_event", "arrival_ns": arrival_ns, "event": event}, sort_keys=True) + "\n")
        for receipt in receipts:
            raw.write(json.dumps({"type": "receipt", **receipt}, sort_keys=True) + "\n")
    return cell


def validity(args) -> dict:
    examples_rel = "libs/cua-driver/examples/jev-use"
    worktree = args.examples.parents[2]
    diff = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--name-only", args.tested_sha, "--", examples_rel],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    untracked = subprocess.run(
        ["git", "-C", str(worktree), "ls-files", "--others", "--exclude-standard", "--", examples_rel],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    result = {
        "head": subprocess.run(["git", "-C", str(worktree), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "tested_sha": args.tested_sha,
        "examples_identical_to_tested_sha": diff == "" and untracked == "",
        "driver_sha256": sha256_file(args.driver),
        "driver_sha256_expected": args.driver_sha256,
        "forbidden_env_present": [name for name in FORBIDDEN_ENV if name in os.environ],
        "display_set": bool(os.environ.get("DISPLAY")),
        "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
        "launcher_sha256": sha256_file(LAUNCHER),
        "harness_sha256": sha256_file(Path(__file__)),
        "fixture_server_sha256": sha256_file(args.examples / "fixture_server.py"),
        "run_py_sha256": sha256_file(args.examples / "python/run.py"),
        "python": sys.version.split()[0],
    }
    result["ok"] = (
        result["examples_identical_to_tested_sha"]
        and result["driver_sha256"] == args.driver_sha256
        and not result["forbidden_env_present"]
        and result["display_set"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("smoke", "main", "decline", "unreachable"), required=True)
    parser.add_argument("--pairs", type=int, default=1)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget-file", type=Path, required=True)
    args = parser.parse_args()
    args.examples = args.examples.resolve()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)

    check = validity(args)
    check["phase"] = args.phase
    check["started_monotonic_ns"] = now()
    check["started_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    check["loadavg_at_start"] = loadavg()
    (out / "validity.json").write_text(json.dumps(check, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "validity", "ok": check["ok"], "key_present": check["typesafe_key_present"]}), flush=True)
    if not check["ok"]:
        return 2
    provider = "mock" if args.phase == "smoke" else "live"
    if provider == "live" and not check["typesafe_key_present"]:
        print(json.dumps({"event": "blocked", "reason": "TYPESAFE_API_KEY absent in session"}), flush=True)
        return 3

    if args.phase in ("smoke", "main"):
        plan = []
        for pair in range(1, args.pairs + 1):
            arms = ("baseline", "guarded") if pair % 2 == 1 else ("guarded", "baseline")
            plan += [(pair, order, arm) for order, arm in enumerate(arms, start=1)]
    elif args.phase == "decline":
        plan = [(pair, 1, "guarded") for pair in range(1, args.pairs + 1)]
    else:
        plan = [(1, 1, "baseline"), (1, 2, "guarded")]

    budget = Budget(args.budget_file)
    cells = (out / "cells.jsonl").open("a", encoding="utf-8")
    stopped = None
    for pair, order, arm in plan:
        if provider == "live" and not budget.can_start():
            stopped = f"request budget: {budget.used} used of {REQUEST_CAP}"
            break
        started = time.monotonic()
        try:
            cell = run_cell(args, out, phase=args.phase, pair=pair, order=order, arm=arm, provider=provider)
        except Exception as error:  # a broken cell is data
            cell = {"cell_id": f"{args.phase}-p{pair:03d}-{order}-{arm}", "phase": args.phase, "pair": pair,
                    "order": order, "arm": arm, "harness_error": f"{type(error).__name__}: {error}"}
        if provider == "live":
            budget.add(cell["cell_id"], int(cell.get("http_attempts") or 0))
        cells.write(json.dumps(cell, sort_keys=True) + "\n")
        cells.flush()
        print(json.dumps({
            "event": "cell", "id": cell["cell_id"], "verified": cell.get("independently_verified"),
            "rc": cell.get("rc"), "http_attempts": cell.get("http_attempts"), "budget_used": budget.used,
            "wall_s": round(time.monotonic() - started, 1), "error": cell.get("harness_error"),
        }), flush=True)
        time.sleep(0.3)
    (out / "end.json").write_text(json.dumps({
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stopped_early": stopped,
        "budget_used_after": budget.used, "loadavg_at_end": loadavg(),
    }, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

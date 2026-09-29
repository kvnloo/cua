#!/usr/bin/env python3
"""Interleaved A/B harness for jev-use guarded completion (trycua/cua#4316).

Runs the *real* jev-use runners (Python + TypeScript) against a real ``cua-driver mcp`` process and a
real Driver-launched isolated Chromium, inside an isolated X11 session (see cua-x11-session.sh).
It measures, independently of the runners, when the fixture's ``/state`` endpoint first says the task
outcome is verified, how long the runner process lives, and how long teardown takes afterwards.

Per cell (arm x language) it records
  * the runner's own JSONL events (phase timings, decision routes) with harness arrival times,
  * the independent oracle timeline (server-side mutation instant and first HTTP /state observation),
  * runner lifetime and cleanup-after-outcome,
  * optionally (traced cells) the full MCP conversation via ``mcp_trace_proxy.py``.

Arms/blocks are interleaved: each block contains every (arm, language) cell once, in a seeded random
order. Nothing is dropped; failures are recorded as cells with ``error``.

usage (inside the isolated session):
    ab_harness.py --config config.json --out OUTDIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
EXAMPLES_REL = Path("libs/cua-driver/examples/jev-use")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(worktree: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True, check=True).stdout.strip()


def descendants(root_pid: int) -> list[int]:
    children: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(int(entry))
    out, stack = [], [root_pid]
    while stack:
        pid = stack.pop()
        for child in children.get(pid, []):
            out.append(child)
            stack.append(child)
    return out


def marked_processes(marker: str) -> list[tuple[int, str]]:
    """Processes whose environment carries the per-cell marker (survives re-parenting)."""
    found = []
    needle = f"CUA_LANE_CELL={marker}".encode()
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            environ = Path(f"/proc/{entry}/environ").read_bytes()
        except OSError:
            continue
        if needle in environ.split(b"\0"):
            try:
                comm = Path(f"/proc/{entry}/comm").read_text().strip()
            except OSError:
                comm = "?"
            found.append((int(entry), comm))
    return found


def kill_marked(marker: str) -> list[dict]:
    leftovers = marked_processes(marker)
    killed = []
    for pid, comm in leftovers:
        try:
            os.kill(pid, signal.SIGKILL)
            killed.append({"pid": pid, "comm": comm})
        except OSError:
            pass
    return killed


class CellTimeline:
    """Thread-safe recorder for harness-side observations."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.log_arrivals: list[tuple[float, dict]] = []
        self.oracle_seen: float | None = None
        self.oracle_polls = 0
        self.state_changed: float | None = None


def run_cell(cfg: dict, out: Path, arm: dict, language: str, block: int, position: int, traced: bool, mode: str) -> dict:
    sys.path.insert(0, str(Path(cfg["fixture_examples_dir"])))
    from fixture_server import FixtureServer  # identical in every arm; asserted in the manifest

    provider = cfg["provider"]
    token = f"jev-guide-{provider}"
    cell_id = f"{mode}-b{block:02d}-p{position}-{arm['name']}-{language}"
    cdir = out / "cells" / cell_id
    cdir.mkdir(parents=True, exist_ok=False)
    examples = Path(arm["worktree"]) / EXAMPLES_REL
    log_path = cdir / "runner.jsonl"
    trace_path = cdir / "mcp-trace.jsonl"

    cell: dict = {
        "cell_id": cell_id,
        "mode": mode,
        "block": block,
        "position": position,
        "arm": arm["name"],
        "arm_head": arm["head"],
        "language": language,
        "provider": provider,
        "flags": arm.get("flags", []),
        "traced": traced,
        "driver_real": cfg["driver_real"],
        "error": None,
    }

    server = FixtureServer(("127.0.0.1", 0))
    timeline = CellTimeline()
    original_submit = server.state.submit

    def timed_submit(value: str) -> None:
        original_submit(value)
        with timeline.lock:
            if timeline.state_changed is None:
                timeline.state_changed = time.perf_counter()

    server.state.submit = timed_submit  # type: ignore[method-assign]
    serve = threading.Thread(target=server.serve_forever, daemon=True)
    serve.start()
    url = f"http://127.0.0.1:{server.server_port}/"

    wrapper = cdir / "driver.sh"
    exec_line = f'exec "{cfg["driver_real"]}" "$@"'
    if traced:
        exec_line = (
            f'exec /usr/bin/python3 "{HERE / "mcp_trace_proxy.py"}" --real "{cfg["driver_real"]}" '
            f'--trace "{trace_path}" -- "$@"'
        )
    wrapper.write_text(
        "#!/bin/bash\n"
        "# CI-equivalent Driver wrapper: restores the browser test hooks the runners do not forward.\n"
        "export CUA_E2E_BROWSER_NO_SANDBOX=1\nexport CUA_E2E_BROWSER_STDERR=1\n" + exec_line + "\n"
    )
    wrapper.chmod(0o700)

    common = [
        "--provider", provider, "--fixture-url", url, "--token", token,
        "--max-steps", str(cfg.get("max_steps", 4)), "--log", str(log_path),
    ] + list(arm.get("flags", []))
    if language == "python":
        cmd = [str(examples / ".venv/bin/python"), "python/run.py", *common]
    else:
        cmd = ["node", "--import", "tsx", "typescript/run.ts", *common]
    cell["cmd"] = [c if not c.startswith(str(out)) else "<out>/" + os.path.relpath(c, out) for c in cmd]

    env = dict(os.environ)
    env.update(
        {
            "CUA_DRIVER_BIN": str(wrapper),
            "CUA_DRIVER_PERMISSION_MODE": "unrestricted",
            "CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS": "1",
            "CUA_LANE_CELL": cell_id,
        }
    )

    stop = threading.Event()

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
                            event = json.loads(line)
                        except ValueError:
                            event = {"unparsed": line.decode("utf-8", "replace")}
                        with timeline.lock:
                            timeline.log_arrivals.append((time.perf_counter(), event))
            time.sleep(0.002)

    def poll_oracle() -> None:
        while not stop.is_set():
            try:
                with urlopen(url + "state", timeout=1) as response:
                    state = json.load(response)
                timeline.oracle_polls += 1
                if state.get("submitted") == token:
                    with timeline.lock:
                        timeline.oracle_seen = time.perf_counter()
                    return
            except Exception:
                pass
            time.sleep(0.004)

    threads = [threading.Thread(target=tail_log, daemon=True), threading.Thread(target=poll_oracle, daemon=True)]
    stdout_f = (cdir / "stdout.txt").open("wb")
    stderr_f = (cdir / "stderr.txt").open("wb")
    cell["loadavg_at_spawn"] = Path("/proc/loadavg").read_text().split()[:3]
    t_spawn = time.perf_counter()
    mono_spawn_ns = time.perf_counter_ns()
    proc = subprocess.Popen(cmd, cwd=examples, env=env, stdout=stdout_f, stderr=stderr_f, start_new_session=True)
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        rc = proc.wait(timeout=cfg.get("cell_timeout_s", 180))
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            rc = proc.wait()
    t_exit = time.perf_counter()
    time.sleep(0.05)
    stop.set()
    for thread in threads:
        thread.join(timeout=2)
    stdout_f.close()
    stderr_f.close()

    final_state = None
    try:
        with urlopen(url + "state", timeout=2) as response:
            final_state = json.load(response)
    except Exception as error:  # recorded, never hidden
        cell["error"] = f"final /state read failed: {type(error).__name__}"
    server.shutdown()
    server.server_close()

    ms = lambda t: None if t is None else round((t - t_spawn) * 1000, 2)  # noqa: E731
    events = [event for _, event in timeline.log_arrivals]
    steps = [e for e in events if e.get("event") == "step"]
    outcomes = [e for e in events if e.get("event") == "outcome"]
    abstain_with_decision = [e for e in outcomes if e.get("outcome") == "abstained" and "confidence" in e]
    provider_steps = [s for s in steps if s.get("decision_route") in (None, "provider")]
    guarded_steps = [s for s in steps if s.get("decision_route") == "guarded-completion"]
    visual_attempts = [
        s for s in steps if isinstance(s.get("visual"), dict) and s["visual"].get("status") not in ("skipped", None)
    ]
    action_steps = [s for s in steps if s.get("tool") and not s.get("action_error") and not s.get("dry_run")]
    verified = final_state == {"submitted": token}
    step_rows = []
    for s in steps:
        step_rows.append(
            {
                "step": s.get("step"),
                "candidate": s.get("candidate"),
                "decision_route": s.get("decision_route"),
                "tool": s.get("tool"),
                "visual_status": (s.get("visual") or {}).get("status"),
                "action_error": s.get("action_error"),
                **{
                    key: s.get(key)
                    for key in (
                        "semantic_observe_ms", "visual_observe_ms", "candidate_build_ms", "provider_decision_ms",
                        "decision_ms", "action_ms", "total_step_ms",
                    )
                },
            }
        )
    named = 0.0
    for s in steps:
        named += sum(float(s.get(k) or 0) for k in (
            "semantic_observe_ms", "visual_observe_ms", "candidate_build_ms", "provider_decision_ms", "action_ms"))

    cell.update(
        {
            "rc": rc,
            "timed_out": timed_out,
            "final_state": final_state,
            "independently_verified": verified,
            "runner_outcome": (outcomes[-1].get("outcome") if outcomes else None),
            "timeline_ms": {
                "state_changed_ms": ms(timeline.state_changed),
                "oracle_seen_ms": ms(timeline.oracle_seen),
                "step_event_arrival_ms": [ms(t) for t, e in timeline.log_arrivals if e.get("event") == "step"],
                "outcome_event_arrival_ms": [ms(t) for t, e in timeline.log_arrivals if e.get("event") == "outcome"],
                "exit_ms": ms(t_exit),
            },
            "verified_outcome_ms": ms(timeline.oracle_seen),
            "runner_lifetime_ms": ms(t_exit),
            "cleanup_after_outcome_ms": (
                None if timeline.oracle_seen is None else round((t_exit - timeline.oracle_seen) * 1000, 2)
            ),
            "oracle_polls": timeline.oracle_polls,
            "decision_routes": [s.get("decision_route") for s in steps],
            "counts": {
                "provider_decisions": len(provider_steps) + len(abstain_with_decision),
                "guarded_decisions": len(guarded_steps),
                "semantic_observations": len(steps) + len(abstain_with_decision),
                "visual_observations": len(visual_attempts),
                "driver_actions": len(action_steps),
                "action_errors_or_refusals": len([s for s in steps if s.get("action_error")]),
                "abstentions": len([o for o in outcomes if o.get("outcome") == "abstained"]),
                "reobserves": len([s for s in steps if s.get("candidate") == "reobserve"]),
            },
            "steps": step_rows,
            "named_step_span_sum_ms": round(named, 2),
            "mono_spawn_ns": mono_spawn_ns,
        }
    )
    if traced:
        cell["trace_file"] = str(trace_path.relative_to(out))
    leftovers = kill_marked(cell_id)
    cell["leftover_processes_killed"] = leftovers
    if rc != 0 and cell["error"] is None:
        cell["error"] = f"runner exit code {rc}"
    (cdir / "cell.json").write_text(json.dumps(cell, indent=1, sort_keys=True) + "\n")
    return cell


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only-mode", choices=("clean", "traced"), help="run just one phase")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=False)

    arms = cfg["arms"]
    for arm in arms:
        wt = Path(arm["worktree"])
        arm["head"] = git(wt, "rev-parse", "HEAD")
        arm["dirty"] = bool(git(wt, "status", "--porcelain", "--", str(EXAMPLES_REL)))
    fixture_hashes = {
        arm["name"]: sha256_file(Path(arm["worktree"]) / EXAMPLES_REL / "fixture_server.py") for arm in arms
    }
    manifest = {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uname": " ".join(platform.uname()),
        "display": os.environ.get("DISPLAY"),
        "env_wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        "env_hyprland_sig_present": "HYPRLAND_INSTANCE_SIGNATURE" in os.environ,
        "python": sys.version.split()[0],
        "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
        "driver_real": cfg["driver_real"],
        "driver_sha256": sha256_file(Path(cfg["driver_real"])),
        "driver_version": subprocess.run([cfg["driver_real"], "--version"], capture_output=True, text=True).stdout.strip(),
        "arms": [{k: v for k, v in arm.items()} for arm in arms],
        "fixture_server_sha256_by_arm": fixture_hashes,
        "fixture_server_identical_across_arms": len(set(fixture_hashes.values())) == 1,
        "config": cfg,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"event": "manifest", "arms": [(a["name"], a["head"][:9]) for a in arms],
                      "driver_sha256": manifest["driver_sha256"][:16],
                      "fixture_identical": manifest["fixture_server_identical_across_arms"]}), flush=True)
    if not manifest["fixture_server_identical_across_arms"]:
        print("fixture_server.py differs across arms; refusing to run", file=sys.stderr)
        return 2

    rng = random.Random(cfg["seed"])
    order = []
    phases = []
    if args.only_mode in (None, "clean"):
        phases.append(("clean", cfg["blocks"], False))
    if args.only_mode in (None, "traced"):
        phases.append(("traced", cfg["traced_blocks"], True))
    cells_out = (out / "cells.jsonl").open("a", encoding="utf-8")
    for mode, blocks, traced in phases:
        for block in range(1, blocks + 1):
            combos = [(arm, language) for arm in arms for language in cfg["languages"]]
            rng.shuffle(combos)
            for position, (arm, language) in enumerate(combos, start=1):
                order.append({"mode": mode, "block": block, "position": position, "arm": arm["name"], "language": language})
                started = time.perf_counter()
                try:
                    cell = run_cell(cfg, out, arm, language, block, position, traced, mode)
                except Exception as error:  # a broken cell is data, not something to hide
                    cell = {"cell_id": f"{mode}-b{block:02d}-p{position}-{arm['name']}-{language}", "mode": mode,
                            "block": block, "position": position, "arm": arm["name"], "language": language,
                            "error": f"harness exception: {type(error).__name__}: {error}"}
                cells_out.write(json.dumps(cell, sort_keys=True) + "\n")
                cells_out.flush()
                print(json.dumps({
                    "event": "cell", "id": cell["cell_id"], "ok": cell.get("independently_verified"),
                    "routes": cell.get("decision_routes"), "verified_outcome_ms": cell.get("verified_outcome_ms"),
                    "lifetime_ms": cell.get("runner_lifetime_ms"), "error": cell.get("error"),
                    "wall_s": round(time.perf_counter() - started, 1)}), flush=True)
                time.sleep(0.3)
    (out / "order.json").write_text(json.dumps(order, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

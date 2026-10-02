#!/usr/bin/env python3
"""Sandbox probe: prove what a sandboxed Driver can and cannot see (run INSIDE the private session).

usage: probe.py --wt <worktree> --driver <bin> --results-dir <dir> --work <dir> --out <probe.json>

1. Plants canary files with random contents in the results dir, the fixture-state dir and
   reads a harness file (allowlist.json).
2. Shell probe: runs /usr/bin/sh through sandbox-driver.sh and tries to stat/read every canary,
   the harness dir, /home, /mnt, writes to / and /usr, lists processes and network interfaces.
3. Driver probe: starts the GTK3 task fixture, spawns the real Driver through sandbox-driver.sh,
   and, while it runs, inspects the Driver process's own mount namespace from outside through
   /proc/<pid>/root (the canaries must be absent there too). Then it checks AT-SPI across the
   namespace: get_window_state must return the full, non-degraded tree and a background
   element click must flip the fixture's own state file.
4. Caller probe: one task, one stale-token negative and one impossible canary through the frozen
   caller (runner/caller.py) to exercise the full trial path. Timing fields are not a measurement.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AR = HERE.parent


def sh_probe(sandbox: str, targets: dict[str, str], mode: str) -> dict:
    script = ["set +e"]
    for name, path in targets.items():
        script.append(f'if [ -e "{path}" ]; then echo "{name} VISIBLE"; cat "{path}" >/dev/null 2>&1 && echo "{name} READABLE"; '
                      f'else echo "{name} ABSENT"; fi')
    script += [
        'touch /probe-root 2>/dev/null && echo "ROOT WRITABLE" || echo "root read-only"',
        'touch /usr/probe 2>/dev/null && echo "USR WRITABLE" || echo "usr read-only"',
        'touch "$HOME/probe" && echo "home writable"',
        'echo "home_entries=$(ls -A "$HOME" | wc -l)"',
        'echo "procs=$(ls -d /proc/[0-9]* | wc -l)"',
        'echo "netdevs=$(tail -n +3 /proc/net/dev | cut -d: -f1 | tr -d " " | tr "\\n" ",")"',
        'echo "top=$(ls / | tr "\\n" ",")"',
        'echo "mnt=$(find /mnt -maxdepth 4 2>/dev/null | tr "\\n" ",")"',
        'echo "home_dirs=$(ls /home | tr "\\n" ",")"',
        'echo "env=$(env | cut -d= -f1 | sort | tr "\\n" ",")"',
    ]
    env = dict(os.environ, AR_SANDBOX_PIDNS=mode)
    proc = subprocess.run([sandbox, "/usr/bin/sh", "-c", "\n".join(script)], capture_output=True, text=True,
                          env=env, timeout=30)
    lines = proc.stdout.splitlines()
    return {"mode": mode, "rc": proc.returncode, "stdout": lines, "stderr": proc.stderr.strip().splitlines()[-5:]}


async def driver_probe(args, sandbox: str, canaries: dict[str, str], ctx: dict, mode: str) -> dict:
    sys.path.insert(0, str(Path(args.wt) / "libs/cua-driver/examples/jev-use/python"))
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from driver_env import driver_environment
    from native import NativeObservation, eligible_controls
    from run import Driver

    sys.path.insert(0, str(AR / "runner"))
    from caller import _children_map, _comm, _descendants, read_state

    env = driver_environment()
    env.pop("CUA_DRIVER_PHASE_TRACE_FILE", None)
    env["AR_A11Y_ADDRESS"] = ctx["a11y_address"]
    env["AR_SANDBOX_PIDNS"] = mode
    out: dict = {"mode": mode}
    params = StdioServerParameters(command=sandbox, args=[args.driver, "mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            children = _children_map()
            mine = [p for p in _descendants(os.getpid(), children) if p != ctx["fixture_pid"]]
            driver = [p for p in mine if _comm(p) not in ("bwrap", "python3", "sh")]
            out["sandbox_processes"] = sorted(_comm(p) for p in mine)
            pid = min(driver)
            root = f"/proc/{pid}/root"
            seen = {}
            for name, path in canaries.items():
                seen[name] = os.path.exists(root + path)
            out["driver_view_canary_present"] = seen
            out["driver_view_top"] = sorted(os.listdir(root))
            mnt = []
            for dirpath, dirnames, filenames in os.walk(root + "/mnt"):
                rel = dirpath[len(root):]
                mnt.extend(f"{rel}/{f}" for f in filenames)
                if rel.count("/") > 8:
                    break
            out["driver_view_mnt_files"] = sorted(mnt)
            out["driver_view_home"] = sorted(os.listdir(root + "/home"))
            with open(f"/proc/{pid}/status") as stream:
                out["driver_nspid"] = [line.split()[1:] for line in stream if line.startswith("NSpid")][0]
            with open(f"/proc/{pid}/environ", "rb") as stream:
                out["driver_env_keys"] = sorted(x.split(b"=", 1)[0].decode() for x in stream.read().split(b"\0") if x)
            d = Driver(session, "ar-probe")
            window = None
            for _ in range(100):
                wins = (await d.call("list_windows", {"pid": ctx["fixture_pid"]})).get("windows", [])
                hits = [w for w in wins if w.get("title") == "CuaTestHarness GTK3 Tasks"]
                if hits:
                    window = hits[0]
                    break
                await asyncio.sleep(0.1)
            out["window_found"] = window is not None
            if window is None:
                return out
            target = {"pid": ctx["fixture_pid"], "window_id": int(window["window_id"])}
            gws = await d.call("get_window_state", {**target, "include_accessibility_tree": True,
                                                    "include_screenshot": True})
            out["get_window_state"] = {k: gws.get(k) for k in ("element_count", "degraded", "degraded_reason",
                                                                "walk_elapsed_ms", "truncated")}
            obs = NativeObservation.from_window_state(gws, expected_pid=ctx["fixture_pid"],
                                                      expected_window_id=target["window_id"])
            controls = [c.label for c in eligible_controls(obs, "linux").controls]
            out["eligible_controls"] = controls
            agree = [c for c in eligible_controls(obs, "linux").controls if c.label == "I agree"][0]
            before, _ = read_state(ctx["state_path"])
            click = await d.call("click", {**target, "element_token": agree.element_token,
                                           "delivery_mode": "background"})
            out["click_structured"] = {k: click.get(k) for k in ("path", "route", "effect", "verified") if k in click}
            deadline = time.monotonic() + 5
            after = before
            while time.monotonic() < deadline:
                after, _ = read_state(ctx["state_path"])
                if after and after.get("seq") != before.get("seq"):
                    break
                time.sleep(0.005)
            out["click_oracle"] = {"before": {k: before.get(k) for k in ("seq", "agreed")},
                                   "after": {k: (after or {}).get(k) for k in ("seq", "agreed")},
                                   "verified": bool(after) and after.get("agreed") != before.get("agreed")
                                   and after.get("seq") == before.get("seq") + 1}
    return out


async def main_async(args) -> int:
    sys.path.insert(0, str(AR / "runner"))
    sys.path.insert(0, str(Path(args.wt) / "libs/cua-driver/examples/jev-use/python"))
    from caller import read_state, run_trial
    from session import a11y_address

    sandbox = str(HERE / "sandbox-driver.sh")
    work = Path(args.work).resolve()
    state_dir = work / "fixture-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    canaries = {
        "results_canary": str(results_dir / "results.jsonl"),
        "fixture_state_canary": str(state_dir / "canary.txt"),
        "fixture_state_file": str(state_dir / "gtk3-task-state.json"),
        "harness_file": str(AR / "allowlist.json"),
        "harness_dir": str(AR),
        "worktree": str(Path(args.wt).resolve()),
    }
    Path(canaries["results_canary"]).write_text(json.dumps({"canary": token}) + "\n")
    Path(canaries["fixture_state_canary"]).write_text(token + "\n")
    report: dict = {"schema": "ar.sandbox_probe.v1", "canary_paths": list(canaries)}

    state_path = state_dir / "gtk3-task-state.json"
    state_path.unlink(missing_ok=True)
    env = dict(os.environ, CUA_GTK3_TASK_STATE=str(state_path))
    fixture = subprocess.Popen(["/usr/bin/python3", str(Path(args.wt) / "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py")],
                               env=env, stdout=open(work / "fixture.log", "w"), stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 15
        while read_state(state_path)[0] is None:
            if time.monotonic() > deadline:
                raise RuntimeError("fixture did not start")
            time.sleep(0.05)
        time.sleep(1.0)
        ctx = {"state_path": state_path, "fixture_pid": fixture.pid, "work": work / "trials",
               "a11y_address": a11y_address(), "sandbox": sandbox}
        report["a11y_address_private"] = ctx["a11y_address"].startswith("unix:path=")
        report["session_pid1_is_session_pidns"] = "AR_SESSION_PIDNS" in Path("/proc/1/cmdline").read_text(errors="replace")
        targets = {**canaries,
                   "fixture_proc_root_state_canary": f"/proc/{fixture.pid}/root{canaries['fixture_state_canary']}",
                   "caller_proc_root_results_canary": f"/proc/{os.getpid()}/root{canaries['results_canary']}",
                   "caller_proc_environ": f"/proc/{os.getpid()}/environ",
                   "fixture_proc_environ": f"/proc/{fixture.pid}/environ"}
        report["shell_probe"] = {mode: sh_probe(sandbox, targets, mode) for mode in ("session", "private")}
        report["driver_probe"] = {}
        for mode in ("session", "private"):
            try:
                report["driver_probe"][mode] = await driver_probe(args, sandbox, canaries, ctx, mode)
            except Exception as exc:
                report["driver_probe"][mode] = {"error": f"{type(exc).__name__}: {exc}"[:500]}
        sha = __import__("hashlib").sha256(Path(args.driver).read_bytes()).hexdigest()
        rows = []
        for i, kind in enumerate(("task", "stale_negative", "impossible_canary")):
            spec = {"trial_id": i, "session": 0, "pair_id": None, "order": None, "position": None,
                    "arm": "champion", "kind": kind, "trace": True, "warmup": False,
                    "binary": args.driver, "binary_sha256": sha}
            row = await run_trial(spec, ctx)
            rows.append({k: row.get(k) for k in ("kind", "verified", "claimed_success", "failure", "refused",
                                                 "refusal_code", "refused_stale", "canary_outcome", "seq_delta",
                                                 "route", "path", "dispatch_calls", "journal_before_done",
                                                 "footprint")}
                        | {"marks_n": len(row.get("marks", [])),
                           "mark_keys": sorted({f"{m['phase']}/{m['session']}" for m in row.get("marks", [])
                                                if m["phase"] in ("focus_guard", "atspi_action", "click")})})
        report["caller_probe"] = rows
    finally:
        fixture.terminate()
        try:
            fixture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fixture.kill()
    Path(args.out).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wt", required=True)
    p.add_argument("--driver", required=True)
    p.add_argument("--results-dir", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: not inside the private X11 session")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

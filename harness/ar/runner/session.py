#!/usr/bin/env python3
"""Run one session chunk of an autoresearch schedule INSIDE a private X11 + AT-SPI session.

usage (always through run_blocks.py, which wraps it in hostless + quiet-timed +
cua-x11-session.sh):
    session.py --wt <worktree> --chunk <chunk.json> --out <raw.jsonl> --work <dir>

Starts the GTK3 task fixture (opt-in ``CUA_GTK3_TASK_STATE`` mode, the app-owned oracle),
samples PSI (/proc/pressure/{cpu,io,memory}) at 10 Hz on a harness thread, and runs every
trial of the chunk in order with a fresh sandboxed Driver each. Each trial's raw row is
appended to ``--out`` (JSONL) as soon as it finishes; nothing is dropped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE_REL = "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
JEV_REL = "libs/cua-driver/examples/jev-use/python"
PSI_HZ = 10.0
TRIAL_START_CUTOFF_S = 540.0  # no new trial after 9 min: a block stays under the 10 min cap


class PsiSampler(threading.Thread):
    """10 Hz /proc/pressure sampler (harness side only; the Driver is untouched)."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.samples: list[tuple[int, dict[str, int]]] = []
        self.stop_event = threading.Event()

    @staticmethod
    def read() -> dict[str, int]:
        out: dict[str, int] = {}
        for res in ("cpu", "io", "memory"):
            try:
                with open(f"/proc/pressure/{res}", encoding="ascii") as stream:
                    for line in stream:
                        kind, *fields = line.split()
                        for field in fields:
                            key, value = field.split("=")
                            if key == "total":
                                out[f"{res}_{kind}_total_us"] = int(value)
                            elif key == "avg10":
                                out[f"{res}_{kind}_avg10_x100"] = int(float(value) * 100)
            except OSError:
                pass
        return out

    def run(self) -> None:
        period = 1.0 / PSI_HZ
        while not self.stop_event.is_set():
            self.samples.append((time.monotonic_ns(), self.read()))
            self.stop_event.wait(period)

    def window(self, t0: int, t1: int) -> dict[str, object]:
        inside = [s for s in self.samples if t0 <= s[0] <= t1]
        before = [s for s in self.samples if s[0] < t0]
        first = before[-1] if before else (inside[0] if inside else None)
        last = inside[-1] if inside else first
        summary: dict[str, object] = {"n": len(inside), "hz": PSI_HZ}
        if first and last:
            for key, value in last[1].items():
                if key.endswith("_total_us"):
                    summary[key.replace("_total_us", "_stall_us")] = value - first[1].get(key, value)
            summary["cpu_some_avg10_max_x100"] = max(
                [s[1].get("cpu_some_avg10_x100", 0) for s in inside] or [0])
        return summary


def a11y_address() -> str:
    out = subprocess.run(
        ["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
         "--method", "org.a11y.Bus.GetAddress"], check=True, capture_output=True, text=True, timeout=10,
    ).stdout
    match = re.search(r"'([^']+)'", out)
    if not match:
        raise RuntimeError("no AT-SPI bus address")
    return match.group(1)


async def main_async(args: argparse.Namespace) -> int:
    wt = Path(args.wt).resolve()
    sys.path.insert(0, str(wt / JEV_REL))
    sys.path.insert(0, str(HERE))
    from caller import loadavg, read_state, run_trial

    session_start = time.monotonic()
    chunk = json.loads(Path(args.chunk).read_text(encoding="utf-8"))
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    state_dir = work / "fixture-state"
    state_dir.mkdir(exist_ok=True)
    state_path = state_dir / "gtk3-task-state.json"
    state_path.unlink(missing_ok=True)
    env = dict(os.environ, CUA_GTK3_TASK_STATE=str(state_path))
    fixture = subprocess.Popen(["/usr/bin/python3", str(wt / FIXTURE_REL)], env=env,
                               stdout=open(work / "fixture.log", "w"), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while read_state(state_path)[0] is None:
        if time.monotonic() > deadline or fixture.poll() is not None:
            raise RuntimeError("fixture did not publish its state file")
        time.sleep(0.05)
    time.sleep(1.0)
    psi = PsiSampler()
    psi.start()
    ctx = {"state_path": state_path, "fixture_pid": fixture.pid, "work": work,
           "a11y_address": a11y_address(), "sandbox": str(HERE.parent / "sandbox" / "sandbox-driver.sh")}
    failures = 0
    out = Path(args.out)
    with open(out, "a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"schema": "ar.session.v1", "event": "start", "session": chunk["session"],
                                 "eval_id": chunk["eval_id"], "trials": len(chunk["trials"]),
                                 "loadavg": loadavg(), "fixture_pid": fixture.pid,
                                 "a11y_private": ctx["a11y_address"].startswith("unix:path=")}) + "\n")
        try:
            for spec in chunk["trials"]:
                if time.monotonic() - session_start > TRIAL_START_CUTOFF_S:
                    # Keep the timed block under 10 minutes: unstarted trials are recorded, not run.
                    ledger.write(json.dumps({"schema": "ar.session.v1", "event": "not_run",
                                             "trial_id": spec["trial_id"], "reason": "block_time_cap"}) + "\n")
                    continue
                row = await run_trial(spec, ctx)
                row["eval_id"] = chunk["eval_id"]
                row["psi"] = psi.window(row["t_spawn_ns"], row.get("t_exit_ns", time.monotonic_ns()))
                ledger.write(json.dumps(row, sort_keys=True) + "\n")
                ledger.flush()
                if row.get("failure"):
                    failures += 1
        finally:
            psi.stop_event.set()
            fixture.terminate()
            try:
                fixture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fixture.kill()
            ledger.write(json.dumps({"schema": "ar.session.v1", "event": "end", "session": chunk["session"],
                                     "failures": failures, "loadavg": loadavg()}) + "\n")
    print(f"session {chunk['session']} done failures={failures}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wt", required=True)
    parser.add_argument("--chunk", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()
    if (os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ)
            or not os.environ.get("DISPLAY")):
        raise SystemExit("refusing: not inside the private X11 session")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

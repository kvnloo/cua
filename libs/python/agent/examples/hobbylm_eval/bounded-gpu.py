#!/usr/bin/env python3
"""Run one owned inference command with explicit GPU/IO admission and limits.

Usage: python bounded-gpu.py -- COMMAND ARG ...
No model or GUI imports. Exits 75 when busy. Never stops another process.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

MAX_SECONDS = 1800
MAX_MIB = 4768  # <= 5,000,000,000 bytes including driver/context attribution


def processes():
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    rows = {}
    for line in result.stdout.splitlines():
        pid, memory = line.split(",", 1)
        rows[int(pid)] = int(memory.strip())
    return rows


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "--":
        raise SystemExit("Usage: bounded-gpu.py -- COMMAND ARG ...")
    pressure = dict(
        field.split("=")
        for field in Path("/proc/pressure/io").read_text().splitlines()[0].split()[1:]
    )
    if float(pressure["avg10"]) >= 40:
        print(
            json.dumps(
                {"status": "busy", "reason": "io_pressure", "some_avg10": pressure["avg10"]}
            ),
            flush=True,
        )
        return 75
    baseline = processes()
    child = subprocess.Popen(["nice", "-n10", *sys.argv[2:]], start_new_session=True)
    start = last_echo = time.monotonic()
    peak = 0
    reason = None
    try:
        while child.poll() is None:
            now = time.monotonic()
            current = processes()
            owned = {}
            for pid, memory in current.items():
                try:
                    own = os.getpgid(pid) == child.pid
                except ProcessLookupError:
                    continue
                if own:
                    owned[pid] = memory
                elif pid not in baseline:
                    reason = "new_user_gpu_process"
            peak = max(peak, sum(owned.values()))
            if peak > MAX_MIB:
                reason = "gpu_memory_limit"
            if now - start >= MAX_SECONDS:
                reason = "timeout"
            if reason:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                break
            if now - last_echo >= 60:
                print(
                    json.dumps(
                        {"status": "running", "elapsed_s": round(now - start), "peak_gpu_mib": peak}
                    ),
                    flush=True,
                )
                last_echo = now
            time.sleep(0.5)
        code = child.wait()
    except BaseException:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=5)
        raise
    print(
        json.dumps(
            {
                "status": "stopped" if reason else "complete",
                "reason": reason,
                "exit_code": code,
                "peak_gpu_mib": peak,
                "wall_s": time.monotonic() - start,
            }
        ),
        flush=True,
    )
    return 124 if reason else code


if __name__ == "__main__":
    raise SystemExit(main())

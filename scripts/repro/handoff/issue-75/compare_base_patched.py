#!/usr/bin/env python3
"""Prove the #75 timing patch changes no runtime behavior.

Runs the BASE and PATCHED native runners (Python and TypeScript) against the same scripted
driver (`fake_native_driver.py`, controlled fixture) and compares, per language and scenario:
  * the ordered Driver tool calls, and
  * every logged event with all `*_ms` fields and `visual_observe_scope` removed.
Anything but an identical result exits 1.

usage: compare_base_patched.py --base EXAMPLES_DIR --patched EXAMPLES_DIR [--out FILE]
Both directories are libs/cua-driver/examples/jev-use checkouts with `uv sync` and `npm ci` done;
the driver and fixtures are taken from --patched.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCENARIOS = {
    "counter": {"task": "appkit-counter", "platform": "macos"},
    "canvas": {"task": "canvas-cancel", "platform": "linux"},
}
PID = "4242"


def strip_timing(value):
    if isinstance(value, dict):
        return {k: strip_timing(v) for k, v in value.items() if not k.endswith("_ms") and k != "visual_observe_scope"}
    if isinstance(value, list):
        return [strip_timing(v) for v in value]
    return value


def run(examples: Path, driver: Path, language: str, scenario: str) -> tuple[list, list[str]]:
    cfg = SCENARIOS[scenario]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = {**os.environ, "CUA_DRIVER_BIN": str(driver), "CUA_DRIVER_FAKE_SCENARIO": scenario,
               "CUA_DRIVER_FAKE_STATE_FILE": str(tmp / "state.json"), "CUA_DRIVER_FAKE_PID": PID,
               "CUA_DRIVER_FAKE_DELAYS_MS": json.dumps({"observe": 5, "parse": 5, "act": 5}),
               "CUA_DRIVER_FAKE_CALLS_FILE": str(tmp / "calls.txt")}
        common = ["--task", cfg["task"], "--pid", PID, "--state-file", str(tmp / "state.json"),
                  "--provider", "mock", "--platform", cfg["platform"], "--log", str(tmp / "events.jsonl")]
        if language == "python":
            cmd = [str(examples / ".venv/bin/python"), "python/run_native.py", *common]
        else:
            cmd = ["node", "--import", "tsx", "typescript/run_native.ts", *common]
        done = subprocess.run(cmd, cwd=examples, env=env, capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            raise SystemExit(f"{language}/{scenario} failed in {examples}: {done.stderr[-500:]}")
        events = [json.loads(line) for line in (tmp / "events.jsonl").read_text().splitlines()]
        return events, (tmp / "calls.txt").read_text().split()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--patched", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    driver = args.patched / "fake_native_driver.py"
    report, ok = [], True
    for language in ("python", "typescript"):
        for scenario in SCENARIOS:
            base_events, base_calls = run(args.base, driver, language, scenario)
            new_events, new_calls = run(args.patched, driver, language, scenario)
            same_calls = base_calls == new_calls
            same_events = strip_timing(base_events) == strip_timing(new_events)
            added = sorted({k for e in new_events if e["event"] == "step" for k in e if k.endswith("_ms") or k == "visual_observe_scope"}
                           - {k for e in base_events if e["event"] == "step" for k in e if k.endswith("_ms")})
            report.append({"language": language, "scenario": scenario, "tool_calls_identical": same_calls,
                           "events_identical_without_timing": same_events, "events": len(new_events),
                           "tool_calls": new_calls, "fields_added_to_step_events": added})
            ok = ok and same_calls and same_events
    text = json.dumps({"identical": ok, "runs": report}, indent=1)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

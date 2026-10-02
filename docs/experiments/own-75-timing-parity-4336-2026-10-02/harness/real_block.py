#!/usr/bin/python3
"""Run one block of OWN-75 REAL trials inside cua-x11-session.sh (private Xvfb + private AT-SPI).

usage: real_block.py --plan <plan.json> --block <id> --out <raw/real> --work <scratch dir>
                     --driver <cua-driver> --fixture <gtk3 main.py> --wt head=<worktree> --wt m0=<worktree>

Each trial launches a fresh canonical GTK3 task-mode fixture (system python3 + PyGObject) with its
own state file, runs one native jev-use runner (python/run_native.py or typescript/run_native.ts
from the arm's worktree) with the deterministic mock chooser against the real Driver through the
transparent tee (harness/mcp_tee.py), then reads the fixture's own state file as the oracle. The
runner processes carry the network guard (harness/netguard). Nothing here is timed as a result.
Paths, the host name and the note text are replaced by placeholders before anything is written to
<out>. Stdlib only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import pwd
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTE_TEXT = "jev-use native note"
STATE_SCHEMA = "cua.gtk3_task_state_v1"
EXPECTED = {
    "gtk3-choose-size": lambda s: s.get("size") == "large" and s.get("agreed") is True,
    "gtk3-save-note": lambda s: s.get("note_saved") == NOTE_TEXT,
}
SCRUB_ENV = ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "CUA_S1_DECISION_URL", "PYTHONPATH", "NODE_OPTIONS")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def loadavg() -> list[float]:
    return [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]


class Sanitizer:
    def __init__(self, pairs: list[tuple[str, str]]) -> None:
        # Longest first so a worktree path wins over its parent.
        self.pairs = sorted(((a, b) for a, b in pairs if a), key=lambda p: -len(p[0]))

    def text(self, value: str) -> str:
        for raw, placeholder in self.pairs:
            value = value.replace(raw, placeholder)
        return value


def wait_for_initial_state(process: subprocess.Popen, state: Path) -> dict:
    for _ in range(150):
        if state.exists():
            try:
                initial = json.loads(state.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                initial = {}
            if initial.get("pid") == process.pid:
                return initial
        if process.poll() is not None:
            raise RuntimeError("fixture exited during launch")
        time.sleep(0.1)
    raise RuntimeError("fixture did not publish its initial task state")


def runner_command(runner: str, jev: Path) -> list[str]:
    if runner == "python":
        return [str(jev / ".venv/bin/python"), "python/run_native.py"]
    return ["node", "--import", (HERE / "netguard/netguard.mjs").as_uri(), "--import", "tsx",
            "typescript/run_native.ts"]


def guard_self_test(block_dir: Path, jev: Path) -> dict:
    """Negative control: a deliberate TEST-NET connect from each guarded runtime must be refused."""
    log = block_dir / "netguard-selftest.jsonl"
    env = {k: v for k, v in os.environ.items() if k not in SCRUB_ENV}
    env.update({"OWN75_NETGUARD_LOG": str(log), "PYTHONPATH": str(HERE / "netguard")})
    py = subprocess.run(
        [str(jev / ".venv/bin/python"), "-c",
         "import socket\ntry:\n socket.create_connection(('192.0.2.1', 443), timeout=2)\n print('CONNECTED')\n"
         "except ConnectionRefusedError as e:\n print('REFUSED', 'netguard' in str(e))"],
        env=env, capture_output=True, text=True, timeout=30)
    node_env = {k: v for k, v in env.items() if k != "PYTHONPATH"}
    node = subprocess.run(
        ["node", "--import", (HERE / "netguard/netguard.mjs").as_uri(), "-e",
         "const s=require('node:net').connect(443,'192.0.2.1');"
         "s.on('connect',()=>{console.log('CONNECTED');process.exit(0)});"
         "s.on('error',(e)=>{console.log('REFUSED',String(e.message).includes('netguard'));process.exit(0)});"],
        env=node_env, capture_output=True, text=True, timeout=30)
    entries = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return {
        "python_stdout": py.stdout.strip(), "node_stdout": node.stdout.strip(),
        "armed": sorted({e["runtime"] for e in entries if e["kind"] == "armed"}),
        "refused": len([e for e in entries if e["kind"] == "refused"]),
        "pass": py.stdout.strip() == "REFUSED True" and node.stdout.strip() == "REFUSED true"
        and len([e for e in entries if e["kind"] == "refused"]) == 2,
    }


def run_trial(trial: dict, args: argparse.Namespace, wts: dict[str, Path], sanitize: Sanitizer,
              block_dir: Path) -> dict:
    tid = trial["trial_id"]
    jev = wts[trial["arm"]] / "libs/cua-driver/examples/jev-use"
    work = Path(args.work) / tid
    work.mkdir(parents=True)
    state, log, trace, guard = work / "state.json", work / "events.jsonl", work / "mcp.jsonl", work / "netguard.jsonl"
    record: dict = {**trial, "block": args.block, "start_utc": utc(), "loadavg_start": loadavg()}
    fixture_env = {k: v for k, v in os.environ.items() if k not in SCRUB_ENV}
    fixture_env["CUA_GTK3_TASK_STATE"] = str(state)
    fixture_env.pop("CUA_GTK3_TASK_DENSITY", None)
    fixture = subprocess.Popen(["/usr/bin/python3", args.fixture], env=fixture_env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stderr_tail = ""
    try:
        initial = wait_for_initial_state(fixture, state)
        env = {k: v for k, v in os.environ.items() if k not in SCRUB_ENV}
        env.update({
            "CUA_DRIVER_BIN": str(HERE / "mcp_tee.py"),
            "CUA_DRIVER_OWN75_REAL_BIN": args.driver,
            "CUA_DRIVER_OWN75_TRACE": str(trace),
            "OWN75_NETGUARD_LOG": str(guard),
        })
        if trial["runner"] == "python":
            env["PYTHONPATH"] = str(HERE / "netguard")
        command = runner_command(trial["runner"], jev) + [
            "--task", trial["task"], "--provider", "mock", "--pid", str(fixture.pid),
            "--state-file", str(state), "--note-text", NOTE_TEXT, "--platform", "linux", "--log", str(log),
        ]
        started = time.monotonic()
        completed = subprocess.run(command, cwd=jev, env=env, capture_output=True, text=True, timeout=300)
        record["runner_wall_s"] = round(time.monotonic() - started, 3)
        record["runner_rc"] = completed.returncode
        stderr_tail = completed.stderr[-2000:]
        observed = json.loads(state.read_text(encoding="utf-8"))
        if observed.get("schema") != STATE_SCHEMA or observed.get("pid") != fixture.pid:
            raise RuntimeError("state file does not belong to the launched fixture")
    finally:
        fixture.kill()  # the fixture this trial launched
        fixture.wait(timeout=10)
    events = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    guard_entries = [json.loads(line) for line in guard.read_text().splitlines()] if guard.exists() else []
    record.update({
        "end_utc": utc(), "loadavg_end": loadavg(),
        "runner_outcome": events[-1].get("outcome") if events else None,
        "oracle_verified": bool(EXPECTED[trial["task"]](observed)),
        "oracle_state": {k: observed.get(k) for k in ("counter", "agreed", "size", "note_saved", "seq")},
        "oracle_initial": {k: initial.get(k) for k in ("counter", "agreed", "size", "note_saved", "seq")},
        "netguard_armed": len([e for e in guard_entries if e["kind"] == "armed"]),
        "netguard_refused": len([e for e in guard_entries if e["kind"] == "refused"]),
        "mcp_lines": len(trace.read_text().splitlines()) if trace.exists() else 0,
        "stderr_tail": sanitize.text(stderr_tail),
    })
    for key in ("oracle_state", "oracle_initial"):
        if record[key].get("note_saved") == NOTE_TEXT:
            record[key]["note_saved"] = "[note text]"
    trial_dir = Path(args.out) / "trials" / tid
    trial_dir.mkdir(parents=True)
    for source, name in ((log, "events.jsonl.gz"), (trace, "mcp.jsonl.gz"), (guard, "netguard.jsonl")):
        if not source.exists():
            continue
        text = sanitize.text(source.read_text(encoding="utf-8")).replace(NOTE_TEXT, "[note text]")
        if name.endswith(".gz"):
            with gzip.open(trial_dir / name, "wt", encoding="utf-8", compresslevel=9) as stream:
                stream.write(text)
        else:
            (trial_dir / name).write_text(text, encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--block", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--wt", action="append", required=True)
    args = parser.parse_args()
    if not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        print("refusing: not inside the isolated X11 session", file=sys.stderr)
        return 97
    wts = {item.split("=", 1)[0]: Path(item.split("=", 1)[1]) for item in args.wt}
    lanes = str(Path(args.driver).resolve().parents[1])
    sanitize = Sanitizer([
        (str(Path(args.work).resolve()), "<work>"), (args.work, "<work>"),
        (str(wts["head"]), "<wt-head>"), (str(wts["m0"]), "<wt-m0>"),
        (str(HERE), "<harness>"), (lanes, "<lanes>"), (str(Path(lanes).parents[1]), "<mnt>"),
        (os.environ.get("HOME", ""), "<session-home>"), (pwd.getpwuid(os.getuid()).pw_dir, "<home>"),
        (socket.gethostname(), "<host>"),
    ])
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    block_dir = out / "blocks" / args.block
    block_dir.mkdir(parents=True)
    Path(args.work).mkdir(parents=True, exist_ok=True)
    version = subprocess.run([args.driver, "--version"], capture_output=True, text=True, timeout=30)
    meta = {
        "block": args.block, "start_utc": utc(), "loadavg": loadavg(),
        "driver_version": version.stdout.strip(), "display_set": bool(os.environ.get("DISPLAY")),
        "at_spi_bus_set": bool(os.environ.get("AT_SPI_BUS_ADDRESS")),
        "wayland_display_set": bool(os.environ.get("WAYLAND_DISPLAY")),
        "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY")),
        "trial_ids": [t["trial_id"] for t in plan],
        "guard_self_test": guard_self_test(block_dir, wts["head"] / "libs/cua-driver/examples/jev-use"),
    }
    (block_dir / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    failures = 0
    for trial in plan:
        try:
            record = run_trial(trial, args, wts, sanitize, block_dir)
        except Exception as error:  # every failure is kept in the denominator
            record = {**trial, "block": args.block, "end_utc": utc(), "harness_error": sanitize.text(repr(error))}
        if not record.get("oracle_verified"):
            failures += 1
        with open(out / "trials.jsonl", "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        print(json.dumps({k: record.get(k) for k in ("trial_id", "runner_rc", "runner_outcome", "oracle_verified",
                                                     "harness_error")}), flush=True)
    meta["end_utc"] = utc()
    meta["failures"] = failures
    (block_dir / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

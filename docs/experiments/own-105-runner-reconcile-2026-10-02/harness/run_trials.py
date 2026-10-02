"""OWN-105 trial orchestrator: runner reconciliation on the real MCP stdio path.

The orchestrator owns the target: the loopback fixture and its journal (the
oracle) plus a harness-only control server for seam barriers. Each trial runs
one runner in a child process (``py_trial.py`` or ``ts_trial.mts``) against the
real ``$CUA_DRIVER_BIN mcp`` and real Chrome. After the child exits the
orchestrator snapshots the journal, releases any held operation, waits until the
journal is quiescent, and records the final journal. The runner's outcome and
receipts are what is under test; the journal is the oracle.

Arms: ``py_fixed`` and ``ts_fixed`` run the runners at the fix head;
``py_unfixed`` runs the unfixed base ``python/run.py`` (discriminating control).

usage (inside cua-x11-session.sh, one block per call):
  python run_trials.py --jev-root <wt jev-use> --base-jev-root <base jev-use>
      --driver-bin <bin> --out <dir> --tmp <dir> --start N --count 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

ROWS: dict[str, dict[str, Any]] = {
    "R0_control": {"fault": "none", "fixture": "immediate"},
    "R1_ack_lost_applied": {"fault": "ack_lost", "barrier": "applied", "fixture": "immediate"},
    "R2_delayed_within_deadline": {"fault": "ack_lost", "barrier": "received", "fixture": "after_unchanged:1"},
    "R3_delayed_past_deadline": {"fault": "ack_lost", "barrier": "received", "fixture": "withheld"},
    "R4_read_failure_after_unverified": {"fault": "read_error", "fixture": "withheld"},
    "R5_replanned_completion": {"fault": "none", "fixture": "withheld"},
    "R6_own_write_raised": {"fault": "pre_dispatch", "fixture": "immediate"},
    # Negative control for the pre-write rule: nothing was sent, but there is no
    # proof that the request's own write raised, so no reconsideration is legal.
    "R6n_unproven_not_written": {"fault": {"py": "request_lost", "ts": "closed_before_request"},
                                 "fixture": "immediate"},
}
QUOTAS: dict[str, dict[str, int]] = {
    "py_fixed": {**{row: 12 for row in ROWS if row != "R6n_unproven_not_written"}, "R6n_unproven_not_written": 4},
    "ts_fixed": {**{row: 8 for row in ROWS if row != "R6n_unproven_not_written"}, "R6n_unproven_not_written": 4},
    "py_unfixed": {"R1_ack_lost_applied": 5, "R3_delayed_past_deadline": 5,
                   "R4_read_failure_after_unverified": 5, "R5_replanned_completion": 5},
}
CHILD_TIMEOUT_S = 150
RUNNER_TIMEOUT_S = 120


def loadavg() -> list[float]:
    try:
        return [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]
    except OSError:
        return []


def schedule() -> list[tuple[str, str]]:
    """Deterministic round-robin over (row, arm) cells, rotated per round, odd rounds reversed."""
    cells = [(row, arm) for arm, rows in QUOTAS.items() for row in ROWS if row in rows]
    left = {cell: QUOTAS[cell[1]][cell[0]] for cell in cells}
    order: list[tuple[str, str]] = []
    rnd = 0
    while any(left.values()):
        k = rnd % len(cells)
        rotated = cells[k:] + cells[:k]
        if rnd % 2:
            rotated.reverse()
        for cell in rotated:
            if left[cell]:
                left[cell] -= 1
                order.append(cell)
        rnd += 1
    return order


def kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class Orchestrator:
    def __init__(self, jev_root: Path, base_jev_root: Path, driver_bin: str, tmp: Path) -> None:
        sys.path[:0] = [str(HERE), str(jev_root), str(jev_root / "python")]
        from ackloss_fixture import AckLossFixture, ControlServer

        self.jev_root, self.base_jev_root, self.tmp = jev_root, base_jev_root, tmp
        self.fixture = AckLossFixture()
        self.control = ControlServer(self.fixture.journal)
        for server in (self.fixture, self.control):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.env = {**os.environ, "CUA_DRIVER_BIN": driver_bin}

    def run_child(self, arm: str, cfg: dict[str, Any], label: str) -> tuple[int | None, dict[str, Any]]:
        cfg_path = self.tmp / f"{label}.cfg.json"
        cfg_path.write_text(json.dumps(cfg))
        if arm.startswith("py_"):
            command = [sys.executable, str(HERE / "py_trial.py"), str(cfg_path)]
            cwd = self.jev_root
        else:
            command = ["node", "--import", "tsx", str(HERE / "ts_trial.mts"), str(cfg_path)]
            cwd = self.jev_root
        with (self.tmp / f"{label}.child.log").open("w") as child_log:
            proc = subprocess.Popen(command, cwd=cwd, env=self.env, stdout=child_log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            try:
                rc: int | None = proc.wait(timeout=CHILD_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                kill_group(proc)
                proc.wait()
                rc = None
        # Reap anything the child left in its own process group (we started it).
        kill_group(proc)
        result_path = Path(cfg["result"])
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        return rc, result

    def trial(self, index: int, row: str, arm: str) -> dict[str, Any]:
        spec = ROWS[row]
        runtime = arm.split("_")[0]
        fault = spec["fault"][runtime] if isinstance(spec["fault"], dict) else spec["fault"]
        token = f"o105-{uuid.uuid4().hex[:12]}"
        label = f"{index:03d}"
        journal = self.fixture.journal
        journal.reset_trial(label, token, spec["fixture"])
        log = self.tmp / f"{label}.events.jsonl"
        cfg = {
            "jev_root": str(self.base_jev_root if arm == "py_unfixed" else self.jev_root),
            "fixture_url": self.fixture.url, "control_url": self.control.url, "token": token,
            "fault": fault, "barrier": spec.get("barrier"), "log": str(log),
            "result": str(self.tmp / f"{label}.result.json"), "timeout_s": RUNNER_TIMEOUT_S,
        }
        la_start = loadavg()
        started = time.perf_counter()
        rc, result = self.run_child(arm, cfg, label)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        at_exit = journal.snapshot()
        journal.release_all("harness_release_after_runner_exit")
        quiescent = journal.wait_quiescent(15)
        final = journal.snapshot()
        text = log.read_text() if log.exists() else ""
        runner_events = [json.loads(line) for line in text.splitlines() if line.strip()]
        return {
            "trial": label, "row": row, "arm": arm, "runtime": runtime, "fault": fault,
            "barrier": spec.get("barrier"), "fixture_mode": spec["fixture"],
            "loadavg_start": la_start, "loadavg_end": loadavg(),
            "child_rc": rc, "child_elapsed_ms_informational": elapsed,
            "token_in_runner_log": token in text,
            "py_outcome": result.get("outcome"), "py_exception_leaves": result.get("exception_leaves"),
            "ts_exit_code": result.get("exit_code"), "ts_transports": result.get("transports"),
            "fault_fired": result.get("fault_fired"),
            "journal_at_runner_exit": {k: v for k, v in at_exit.items() if k != "events"},
            "journal_events_at_runner_exit": len(at_exit["events"]),
            "journal_quiescent": quiescent,
            "journal_received": final["received"], "journal_applied": final["applied"],
            "final_state_matches_token": final["state_matches_token"],
            "runner_events": runner_events,
            "seam_events": result.get("seam_events", []),
            "target_journal": final["events"],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jev-root", type=Path, required=True)
    parser.add_argument("--base-jev-root", type=Path, required=True)
    parser.add_argument("--driver-bin", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tmp", type=Path, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--only", nargs="*", help="pilot: one trial per listed row:arm cell")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.tmp.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(Path(args.driver_bin).read_bytes()).hexdigest()
    order = schedule()
    if args.only:
        wanted = [tuple(cell.split(":")) for cell in args.only]
        order = [cell for cell in wanted if cell in set(order)]
    schedule_path = args.out / "schedule.json"
    if not schedule_path.exists():
        schedule_path.write_text(json.dumps({"driver_sha256": sha, "order": order}, indent=1) + "\n")
    if args.start >= len(order):
        return
    orchestrator = Orchestrator(args.jev_root.resolve(), args.base_jev_root.resolve(), args.driver_bin, args.tmp)
    for index in range(args.start, min(args.start + args.count, len(order))):
        row, arm = order[index]
        record = orchestrator.trial(index, row, arm)
        record["driver_sha256"] = sha
        path = args.out / f"trial-{index:03d}-{row}-{arm}.jsonl"
        detail = {k: record.pop(k) for k in ("runner_events", "seam_events", "target_journal")}
        with path.open("w") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.write(json.dumps({"kind": "runner_events", "events": detail["runner_events"]}, sort_keys=True) + "\n")
            stream.write(json.dumps({"kind": "seam_events", "events": detail["seam_events"]}, sort_keys=True) + "\n")
            stream.write(json.dumps({"kind": "target_journal", "events": detail["target_journal"]}, sort_keys=True) + "\n")
        final = detail["runner_events"][-1] if detail["runner_events"] else {}
        print(json.dumps({"trial": index, "row": row, "arm": arm, "rc": record["child_rc"],
                          "outcome": final.get("outcome"), "event": final.get("event"),
                          "resolution": (final.get("mutation_outcome") or {}).get("resolution"),
                          "received": record["journal_received"], "applied": record["journal_applied"]}),
              flush=True)
    orchestrator.fixture.shutdown()
    orchestrator.control.shutdown()


if __name__ == "__main__":
    main()

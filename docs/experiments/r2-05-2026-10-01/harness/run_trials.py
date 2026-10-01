"""R2-05 trial driver: real ack loss / delayed effect on the real MCP stdio path.

Runs the UNMODIFIED jev-use Python runner (``python/run.py`` at the tested
source, ``--provider mock --guarded-completion --visual-observation off``) in
process. ``run.stdio_client`` is pointed at ``fault_transport.fault_stdio_client``,
which wraps the SDK's real stdio client and the real ``$CUA_DRIVER_BIN mcp``.

After the runner returns, a caller recovery policy consumes only caller-visible
facts (runner outcome, its JSONL ``mutation_outcome`` receipt and error class,
fresh oracle reads through the runner's own ``fixture_state``):

* ``typed``  - follows the #105 receipt. ``ClosedResourceError`` /
  ``BrokenResourceError`` raised by the SDK write call means the request never
  reached the transport: reconsider once from fresh state. Any other ambiguous
  error: bounded reconciliation reads, never another dispatch.
* ``naive``  - counterexample: on ``unknown`` restart the runner from step one
  at once (its own step-start oracle read is its only check).
* ``runner`` - no recovery; the runner's own loop only.

The target journal (fixture thread, never read by the caller) is the oracle.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

ROWS: dict[str, dict[str, Any]] = {
    "R0_control": {"fault": "none", "fixture": "immediate", "arms": ["typed"]},
    "RA_pre_dispatch": {"fault": "pre_dispatch", "fixture": "immediate", "arms": ["typed", "naive"]},
    "RA2_request_lost": {"fault": "request_lost", "fixture": "immediate", "arms": ["typed", "naive"]},
    "RB_ack_lost_applied": {"fault": "ack_lost", "barrier": "applied", "fixture": "immediate",
                            "arms": ["typed", "naive"]},
    "RC_delayed_after_unchanged": {"fault": "ack_lost", "barrier": "received", "fixture": "after_unchanged:1",
                                   "arms": ["typed", "naive"]},
    "RD_delayed_withheld": {"fault": "ack_lost", "barrier": "received", "fixture": "withheld",
                            "arms": ["typed", "naive"]},
    "RE_runner_loop_withheld": {"fault": "none", "fixture": "withheld", "arms": ["runner"]},
}
PRE_WRITE_ERRORS = {"ClosedResourceError", "BrokenResourceError"}
RECONCILE_INTERVAL_S = 0.1
RECONCILE_DEADLINE_S = 3.0
ATTEMPT_TIMEOUT_S = 120.0


def loadavg() -> list[float]:
    try:
        return [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]
    except OSError:
        return []


def cells() -> list[tuple[str, str]]:
    return [(row, arm) for row, spec in ROWS.items() for arm in spec["arms"]]


def schedule(blocks: int) -> list[tuple[int, str, str]]:
    """Block-interleaved order: rotate per block, reverse odd blocks (AB/BA)."""
    base = cells()
    order: list[tuple[int, str, str]] = []
    for b in range(blocks):
        k = b % len(base)
        rotated = base[k:] + base[:k]
        if b % 2:
            rotated = list(reversed(rotated))
        order.extend((b, row, arm) for row, arm in rotated)
    return order


class Harness:
    def __init__(self, jev_root: Path, driver_bin: str, tmp: Path) -> None:
        sys.path.insert(0, str(jev_root / "python"))
        sys.path.insert(0, str(jev_root))
        sys.path.insert(0, str(HERE))
        import run as runner  # unmodified tested runner
        from ackloss_fixture import AckLossFixture
        import fault_transport

        self.runner = runner
        self.ft = fault_transport
        self.fixture = AckLossFixture()
        import threading

        threading.Thread(target=self.fixture.serve_forever, daemon=True).start()
        self.tmp = tmp
        os.environ["CUA_DRIVER_BIN"] = driver_bin

    def attempt(self, token: str, plan: Any, label: str) -> dict[str, Any]:
        log = self.tmp / f"{label}.jsonl"
        args = argparse.Namespace(
            provider="mock", fixture_url=self.fixture.url, token=token, max_steps=4, dry_run=False,
            guarded_completion=True, log=str(log), visual_observation="off",
        )
        self.runner.stdio_client = lambda params: self.ft.fault_stdio_client(params, plan)
        started = time.perf_counter()
        try:
            outcome = asyncio.run(asyncio.wait_for(self.runner.run(args), ATTEMPT_TIMEOUT_S))
        except (asyncio.TimeoutError, TimeoutError):
            outcome = "timeout"
        except BaseException as error:  # noqa: BLE001 - keep every failure in the denominator
            if isinstance(error, KeyboardInterrupt):
                raise
            outcome = f"exception:{type(error).__name__}"
            leaves = []
            stack = [error]
            while stack:
                item = stack.pop()
                if isinstance(item, BaseExceptionGroup):
                    stack.extend(item.exceptions)
                else:
                    leaves.append(type(item).__name__)
            plan.log("attempt_exception", leaves=sorted(leaves))
            if os.environ.get("R205_DEBUG"):
                import traceback

                traceback.print_exception(error)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        events = []
        if log.exists():
            events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
            log.unlink()
        return {"outcome": outcome, "elapsed_ms": elapsed, "runner_events": events,
                "seam_events": plan.events, "fault_fired": plan.fired, "fault_mode": plan.mode}

    def read_oracle(self) -> dict[str, Any]:
        return self.runner.fixture_state(self.fixture.url)

    def trial(self, index: int, block: int, row: str, arm: str) -> dict[str, Any]:
        spec = ROWS[row]
        token = f"r205-{uuid.uuid4().hex[:12]}"
        trial_id = f"{index:03d}"
        journal = self.fixture.journal
        journal.reset_trial(trial_id, token, spec["fixture"])
        plan = self.ft.FaultPlan(mode=spec["fault"], barrier_kind=spec.get("barrier"),
                                 barrier_wait=journal.wait_for)
        t0 = time.perf_counter()
        la = loadavg()
        first = self.attempt(token, plan, f"{trial_id}-a1")
        recovery: dict[str, Any] = {"policy": arm, "classification": None, "reads": [],
                                    "dispatch_attempts_after_first": 0}
        attempts = [first]
        final = first["outcome"]
        outcome_event = first["runner_events"][-1] if first["runner_events"] else {}
        receipt = outcome_event.get("mutation_outcome") if outcome_event.get("outcome") == "unknown" else None
        error_class = outcome_event.get("error") if receipt else None
        journal_before_recovery = {k: v for k, v in journal.snapshot().items() if k != "events"}

        if arm == "typed" and first["outcome"] == "unknown" and receipt:
            if error_class in PRE_WRITE_ERRORS:
                recovery["classification"] = "not_dispatched_proven"
                recovery["dispatch_attempts_after_first"] = 1
                second = self.attempt(token, self.ft.FaultPlan(), f"{trial_id}-a2")
                attempts.append(second)
                final = second["outcome"]
            else:
                recovery["classification"] = "unknown_effect"
                deadline = time.perf_counter() + RECONCILE_DEADLINE_S
                final = "unknown"
                while True:
                    state = self.read_oracle()
                    seen = state.get("submitted") == token
                    recovery["reads"].append({"t_ms": round((time.perf_counter() - t0) * 1000, 2),
                                              "effect_visible": seen})
                    if seen:
                        final = "verified"
                        recovery["resolution"] = "reconciled_applied"
                        break
                    if time.perf_counter() >= deadline:
                        recovery["resolution"] = "unresolved_unknown"
                        break
                    time.sleep(RECONCILE_INTERVAL_S)
        elif arm == "naive" and first["outcome"] == "unknown":
            recovery["classification"] = "restart_from_step_one"
            recovery["dispatch_attempts_after_first"] = 1
            second = self.attempt(token, self.ft.FaultPlan(), f"{trial_id}-a2")
            attempts.append(second)
            final = second["outcome"]
        else:
            recovery["classification"] = "none"

        resolution_ms = round((time.perf_counter() - t0) * 1000, 2)
        # Settle: let any still-held original operation land, then read the journal.
        journal.release_all("harness_release_after_caller_finished")
        quiescent = journal.wait_quiescent(15)
        snap = journal.snapshot()
        applied, received = snap["applied"], snap["received"]
        return {
            "trial": trial_id, "block": block, "row": row, "arm": arm,
            "fault": spec["fault"], "barrier": spec.get("barrier"), "fixture_mode": spec["fixture"],
            "loadavg_start": la, "loadavg_end": loadavg(),
            "first_outcome": first["outcome"], "first_error_class": error_class,
            "first_decision_route": outcome_event.get("decision_route"),
            "first_phase": outcome_event.get("phase"),
            "mutation_outcome_receipt": ({k: v for k, v in receipt.items() if k != "authorityScope"}
                                         if receipt else None),
            "fault_fired": first["fault_fired"],
            "journal_before_recovery": journal_before_recovery,
            "recovery": recovery,
            "final_outcome_reported": final,
            "attempts": len(attempts),
            "journal_received": received, "journal_applied": applied,
            "duplicate_mutations": max(0, applied - 1),
            "journal_quiescent": quiescent,
            "final_state_matches_token": snap["state_matches_token"],
            "resolution_ms_informational": resolution_ms,
            "attempt_detail": attempts,
            "target_journal": snap["events"],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jev-root", type=Path, required=True)
    parser.add_argument("--driver-bin", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tmp", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=10)
    parser.add_argument("--only", nargs="*", help="pilot: restrict to row:arm cells")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.tmp.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(Path(args.driver_bin).read_bytes()).hexdigest()
    harness = Harness(args.jev_root.resolve(), args.driver_bin, args.tmp)
    order = schedule(args.blocks)
    if args.only:
        wanted = {tuple(x.split(":")) for x in args.only}
        order = [o for o in order if (o[1], o[2]) in wanted]
    (args.out / "schedule.json").write_text(json.dumps(
        {"driver_sha256": sha, "blocks": args.blocks, "order": order}, indent=1) + "\n")
    for index, (block, row, arm) in enumerate(order):
        record = harness.trial(index, block, row, arm)
        record["driver_sha256"] = sha
        path = args.out / f"trial-{index:03d}-{row}-{arm}.jsonl"
        with path.open("w") as stream:
            stream.write(json.dumps({k: v for k, v in record.items()
                                     if k not in {"attempt_detail", "target_journal"}}, sort_keys=True) + "\n")
            for n, attempt in enumerate(record["attempt_detail"], 1):
                stream.write(json.dumps({"kind": "attempt", "n": n, **attempt}, sort_keys=True) + "\n")
            stream.write(json.dumps({"kind": "target_journal", "events": record["target_journal"]},
                                    sort_keys=True) + "\n")
        print(json.dumps({"trial": index, "row": row, "arm": arm, "first": record["first_outcome"],
                          "final": record["final_outcome_reported"], "applied": record["journal_applied"],
                          "dup": record["duplicate_mutations"], "cls": record["recovery"]["classification"]}),
              flush=True)
    harness.fixture.shutdown()


if __name__ == "__main__":
    main()

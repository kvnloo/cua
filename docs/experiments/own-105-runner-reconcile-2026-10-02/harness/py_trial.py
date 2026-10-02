"""One OWN-105 trial in a child process: the jev-use Python runner.

Loads ``python/run.py`` from ``jev_root`` (the fixed worktree or the unfixed
base archive) and runs its unmodified ``run()`` with ``--provider mock
--guarded-completion --visual-observation off``. ``run.stdio_client`` points at
``fault_transport.fault_stdio_client``, which wraps the SDK's real stdio client
and the real ``$CUA_DRIVER_BIN mcp``. Barrier waits and journal probes go to the
harness control server; the runner itself only ever reads the fixture ``/state``.

usage: python py_trial.py <config.json>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    jev = Path(cfg["jev_root"])
    sys.path[:0] = [str(HERE), str(jev), str(jev / "python")]
    import fault_transport as ft
    import run as runner

    control = cfg["control_url"]

    def barrier_wait(kind: str, timeout: float) -> bool:
        with urlopen(f"{control}wait?kind={kind}&timeout={timeout}", timeout=timeout + 10) as response:
            return bool(json.load(response)["reached"])

    def probe() -> dict:
        with urlopen(f"{control}snapshot", timeout=10) as response:
            return json.load(response)

    plan = ft.FaultPlan(mode=cfg["fault"], barrier_kind=cfg.get("barrier"),
                        barrier_wait=barrier_wait, probe=probe)
    runner.stdio_client = lambda params: ft.fault_stdio_client(params, plan)
    args = argparse.Namespace(
        provider="mock", fixture_url=cfg["fixture_url"], token=cfg["token"], max_steps=4,
        dry_run=False, guarded_completion=True, log=cfg["log"], visual_observation="off",
    )
    result: dict = {"exception_leaves": None}
    started = time.perf_counter()
    try:
        outcome = asyncio.run(asyncio.wait_for(runner.run(args), cfg["timeout_s"]))
    except (asyncio.TimeoutError, TimeoutError):
        outcome = "timeout"
    except BaseException as error:  # noqa: BLE001 - keep every failure in the denominator
        if isinstance(error, KeyboardInterrupt):
            raise
        outcome = f"exception:{type(error).__name__}"
        leaves, stack = [], [error]
        while stack:
            item = stack.pop()
            if isinstance(item, BaseExceptionGroup):
                stack.extend(item.exceptions)
            else:
                leaves.append(type(item).__name__)
        result["exception_leaves"] = sorted(leaves)
        if os.environ.get("OWN105_DEBUG"):
            import traceback

            traceback.print_exception(error)
    result.update(
        outcome=outcome,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        seam_events=plan.events,
        fault_fired=plan.fired,
    )
    Path(cfg["result"]).write_text(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

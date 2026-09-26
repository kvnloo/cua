"""Auth-cache bench (Python): does verify-once-per-connection beat per-request re-verify?

Follow-up to bench_observation_auth_lifetime.py. Discovery driving this bench:
upstream #3505 ("authenticate history requests lazily", merged 2026-09-03)
already implemented option-(a) scoping in serve.rs — the codesign deep-verify
now runs lazily per-request, only for history_control/history_relaunch_state.
Non-history calls pay zero auth. What #3505 did NOT do: history calls still
RE-verify on every request. This bench prototypes the (a)+(b) hybrid the
dq-3383 draft's third section named: verify once per connection, then history_*
calls skip re-auth on that connection (mock_daemon.py --auth-cache).

Arms (daemon --auth-mode request --auth-scope history for all three; the only
differences are transport and the re-auth cache):

  D4  one-shot connections, re-verify per history request
      (= today's post-#3505 behavior for history calls)
  F   keep-alive, re-verify per history request
      (= conservative: transport change only, no trust-contract change)
  E   keep-alive, verify-once-per-connection
      (= (a)+(b) hybrid: first history call pays, rest skip re-auth)

F vs D4 isolates the keep-alive transport win under scoping.
E vs F isolates the re-auth cache.
E vs D4 is the full hybrid win.

Sequences:
  history-heavy: 4 x history_record (repeated history control-plane calls)
  mixed:         3 steps x (get_browser_state + get_window_state +
                 parse_visual_regions + history_record)

The equivalence gate asserts every arm returns identical-shape results, so a
faster arm cannot win by skipping work.

Run: python3 bench_observation_auth_cache.py (from the python/ directory)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_observation_auth_lifetime import (  # noqa: E402
    AUTH_MAGS,
    CALL_TIMEOUT_S,
    PID,
    WINDOW_ID,
    one_shot_call,
    p90,
    stop_daemon,
)
from keepalive import PersistentDaemonClient  # noqa: E402

ITERS = 30
HISTORY_CALLS = 4
MIXED_STEPS = 3
CallFn = Any


async def history_sequence(call: CallFn, count: int) -> None:
    for _ in range(count):
        result = await call("history_record", {"sequence": 1})
        if result != {"recorded": True}:
            raise AssertionError(f"history shape mismatch: {result!r}")


async def mixed_sequence(call: CallFn, steps: int) -> None:
    for _ in range(steps):
        snapshot = await call(
            "get_browser_state", {"target_id": "t", "tab_id": "tab", "snapshot_format": "semantic_v2"}
        )
        if not isinstance(snapshot.get("refs"), list):
            raise AssertionError("snapshot shape mismatch")
        capture = await call(
            "get_window_state", {"pid": PID, "window_id": WINDOW_ID, "include_accessibility_tree": False}
        )
        if not isinstance(capture.get("capture_id"), str):
            raise AssertionError("capture shape mismatch")
        wire = await call(
            "parse_visual_regions",
            {
                "capture_id": capture["capture_id"],
                "options": {"kinds": ["text", "icon"], "min_confidence": 0.8, "max_regions": 100},
            },
        )
        if not isinstance(wire.get("regions"), list):
            raise AssertionError("parse shape mismatch")
        result = await call("history_record", {"sequence": 1})
        if result != {"recorded": True}:
            raise AssertionError(f"history shape mismatch: {result!r}")


SEQUENCES = {
    "history-heavy": lambda call: history_sequence(call, HISTORY_CALLS),
    "mixed": lambda call: mixed_sequence(call, MIXED_STEPS),
}


async def start_daemon_cache(
    socket_path: str, auth_ms: float, auth_cache: bool
) -> asyncio.subprocess.Process:
    daemon = Path(__file__).resolve().parent / "mock_daemon.py"
    args = [
        sys.executable,
        str(daemon),
        "--socket", socket_path,
        "--regions", "50",
        "--keep-alive",
        "--auth-ms", str(auth_ms),
        "--auth-mode", "request",
        "--auth-scope", "history",
    ]
    if auth_cache:
        args.append("--auth-cache")
    last_error: Exception | None = None
    for attempt in range(3):
        child = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            line = await asyncio.wait_for(child.stdout.readline(), timeout=10.0)
        except (asyncio.TimeoutError, TimeoutError) as error:
            last_error = error
            child.kill()
            await asyncio.sleep(1.0)
            continue
        if b"ready" not in line:
            child.kill()
            last_error = RuntimeError(f"daemon failed to start: {line!r}")
            await asyncio.sleep(1.0)
            continue
        return child
    raise RuntimeError(f"daemon start failed after 3 attempts: {last_error}")


async def run_arm(socket_path: str, seq: str, arm: str) -> float:
    """Run one arm once; returns iteration ms."""
    loop = asyncio.get_running_loop()
    seq_fn = SEQUENCES[seq]
    t0 = loop.time()
    if arm == "D4":
        await seq_fn(one_shot_call_fn(socket_path))
    else:
        persistent = PersistentDaemonClient(socket_path)
        try:
            await seq_fn(persistent.as_unwrapped_call_fn())
        finally:
            await persistent.close()
    return (loop.time() - t0) * 1000.0


def one_shot_call_fn(socket_path: str) -> CallFn:
    async def call(name: str, args: Mapping[str, Any]) -> Any:
        return await one_shot_call(socket_path, name, args)

    return call


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mags", nargs="*", default=None,
                        help="auth magnitudes to run (subset of 5.0 25.0)")
    parser.add_argument("--raw-out", default=None,
                        help="write raw times JSON here (for merging partial runs)")
    cli = parser.parse_args()
    mags = [float(m) for m in cli.mags] if cli.mags else list(AUTH_MAGS)
    socket_path = os.path.join(tempfile.gettempdir(), f"cua-authcache-py-{os.getpid()}.sock")
    # arm -> needs --auth-cache on the daemon
    arms = {"D4": False, "F": False, "E": True}
    times: dict[str, dict[str, dict[str, list[float]]]] = {
        str(m): {s: {a: [] for a in arms} for s in SEQUENCES} for m in mags
    }

    for auth_ms in mags:
        mag = str(auth_ms)
        for it in range(ITERS):
            jobs = [(s, a) for s in SEQUENCES for a in arms]
            for seq, arm in random.sample(jobs, len(jobs)):
                child = await start_daemon_cache(socket_path, auth_ms, arms[arm])
                try:
                    ms = await run_arm(socket_path, seq, arm)
                finally:
                    await stop_daemon(child)
                times[mag][seq][arm].append(ms)
            # Checkpoint: daemon restarts have killed benches mid-run before.
            # Save full raw times so a crash loses nothing.
            with open(os.path.join(tempfile.gettempdir(), "auth_cache_py_partial.json"), "w") as f:
                json.dump(times, f)

    report: dict[str, Any] = {
        "iters": ITERS,
        "transport": "asyncio unix socket, loopback",
        "sequences": {
            "history-heavy": f"{HISTORY_CALLS} x history_record",
            "mixed": f"{MIXED_STEPS} steps x (3 observation calls + history_record)",
        },
        "arms": {
            "D4": "one-shot, re-verify per history request (today, post-#3505)",
            "F": "keep-alive, re-verify per history request (conservative)",
            "E": "keep-alive, verify-once-per-connection (hybrid)",
        },
        "byAuthMs": {},
    }
    for mag in times:
        seq_block: dict[str, Any] = {}
        for seq in SEQUENCES:
            med = {a: statistics.median(times[mag][seq][a]) for a in arms}
            seq_block[seq] = {
                "iterMsMedian": med,
                "iterMsP90": {a: p90(times[mag][seq][a]) for a in arms},
                "speedupVsD4": {a: med["D4"] / med[a] for a in ("F", "E")},
                "cacheWinVsF": med["F"] / med["E"],
            }
        report["byAuthMs"][mag] = seq_block
    print(json.dumps(report, indent=2))
    with open(os.path.join(tempfile.gettempdir(), "auth_cache_py.json"), "w") as f:
        json.dump(report, f, indent=2)
    if cli.raw_out:
        with open(cli.raw_out, "w") as f:
            json.dump(times, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())

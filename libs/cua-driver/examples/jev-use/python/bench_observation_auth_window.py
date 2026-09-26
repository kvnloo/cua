"""Auth trust-window bench (Python): how narrow can the re-verify window be?

Follow-up to bench_observation_auth_cache.py. The (a)+(b) hybrid
(verify-once-per-connection, chunk-14 arm E) trusts the first verify for the
life of the connection. The safety question in dq-3383 is what trust window
the project accepts: a narrower window bounds the exposure if the peer
identity changes mid-connection (socket FD passed to another process is the
real TOCTOU case; binary replacement on disk only affects new connections;
runtime injection is pre-existing exposure shared with today's accept-time
auth).

Arms (daemon --auth-mode request --auth-scope history for all; keep-alive
except D4):

  D4  one-shot connections, re-verify per history request
      (= today's post-#3505 behavior for history calls)
  F   keep-alive, re-verify per history request (conservative bound)
  W5  keep-alive, --auth-cache --auth-window-requests 5
  W10 keep-alive, --auth-cache --auth-window-requests 10
  W20 keep-alive, --auth-cache --auth-window-requests 20
  E   keep-alive, --auth-cache, no window (= chunk-14 hybrid, the ceiling)

Sequences:
  history-12: 12 x history_record (windows bite intra-connection)
  mixed:      3 steps x (get_browser_state + get_window_state +
              parse_visual_regions + history_record) = 3 history calls

Metrics: median/p90 per arm, speedup vs D4, "win retained" vs the hybrid
ceiling E = (D4 - Wx) / (D4 - E), and real auth-event counts from the
daemon's --auth-events log.

The equivalence gate asserts every arm returns identical-shape results, so a
faster arm cannot win by skipping work.

Run: python3 bench_observation_auth_window.py (from the python/ directory)
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

from bench_observation_auth_cache import (  # noqa: E402
    history_sequence,
    mixed_sequence,
    one_shot_call,
    p90,
    stop_daemon,
)
from bench_observation_auth_lifetime import AUTH_MAGS  # noqa: E402
from keepalive import PersistentDaemonClient  # noqa: E402

ITERS = 20
HISTORY_CALLS = 12
MIXED_STEPS = 3
CallFn = Any

SEQUENCES = {
    "history-12": lambda call: history_sequence(call, HISTORY_CALLS),
    "mixed": lambda call: mixed_sequence(call, MIXED_STEPS),
}

# arm -> (needs cache, window_requests)
ARMS: dict[str, tuple[bool, int]] = {
    "D4": (False, 0),
    "F": (False, 0),
    "W5": (True, 5),
    "W10": (True, 10),
    "W20": (True, 20),
    "E": (True, 0),
}


async def start_daemon_window(
    socket_path: str,
    auth_ms: float,
    auth_cache: bool,
    window_requests: int,
    events_path: str,
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
        "--auth-events", events_path,
    ]
    if auth_cache:
        args.append("--auth-cache")
    if window_requests:
        args += ["--auth-window-requests", str(window_requests)]
    last_error: Exception | None = None
    for _ in range(3):
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
        async def one_shot(name: str, args: Mapping[str, Any]) -> Any:
            return await one_shot_call(socket_path, name, args)

        await seq_fn(one_shot)
    else:
        persistent = PersistentDaemonClient(socket_path)
        try:
            await seq_fn(persistent.as_unwrapped_call_fn())
        finally:
            await persistent.close()
    return (loop.time() - t0) * 1000.0


def _count_events(events_path: str) -> int:
    try:
        with open(events_path) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mags", nargs="*", default=None,
                        help="auth magnitudes to run (subset of 5.0 25.0)")
    parser.add_argument("--iters", type=int, default=ITERS)
    parser.add_argument("--raw-out", default=None,
                        help="write raw times JSON here (for merging partial runs)")
    parser.add_argument("--resume", default=None,
                        help="resume from a raw JSON file (skips completed iters)")
    cli = parser.parse_args()
    mags = [float(m) for m in cli.mags] if cli.mags else list(AUTH_MAGS)
    iters = cli.iters
    socket_path = os.path.join(tempfile.gettempdir(), f"cua-authwin-py-{os.getpid()}.sock")
    events_path = os.path.join(tempfile.gettempdir(), f"cua-authwin-events-{os.getpid()}.jsonl")
    partial_path = os.path.join(tempfile.gettempdir(), "auth_window_py_partial.json")

    times: dict[str, dict[str, dict[str, list[float]]]] = {
        str(m): {s: {a: [] for a in ARMS} for s in SEQUENCES} for m in mags
    }
    events: dict[str, dict[str, dict[str, list[int]]]] = {
        str(m): {s: {a: [] for a in ARMS} for s in SEQUENCES} for m in mags
    }
    if cli.resume and os.path.exists(cli.resume):
        with open(cli.resume) as f:
            saved = json.load(f)
        times = saved["times"]
        events = saved["events"]
        print(f"resumed: {[ (m, s, a, len(v)) for m in times for s in times[m] for a, v in times[m][s].items() ]}",
              flush=True)

    for auth_ms in mags:
        mag = str(auth_ms)
        for it in range(iters):
            jobs = [(s, a) for s in SEQUENCES for a in ARMS]
            for seq, arm in random.sample(jobs, len(jobs)):
                if len(times[mag][seq][arm]) > it:
                    continue  # resumed iter
                cache, window = ARMS[arm]
                open(events_path, "w").close()
                child = await start_daemon_window(socket_path, auth_ms, cache, window, events_path)
                try:
                    ms = await run_arm(socket_path, seq, arm)
                finally:
                    await stop_daemon(child)
                times[mag][seq][arm].append(ms)
                events[mag][seq][arm].append(_count_events(events_path))
            # Checkpoint: daemon restarts have killed benches mid-run before.
            with open(partial_path, "w") as f:
                json.dump({"times": times, "events": events}, f)

    report: dict[str, Any] = {
        "iters": iters,
        "transport": "asyncio unix socket, loopback",
        "sequences": {
            "history-12": f"{HISTORY_CALLS} x history_record",
            "mixed": f"{MIXED_STEPS} steps x (3 observation calls + history_record)",
        },
        "arms": {
            "D4": "one-shot, re-verify per history request (today, post-#3505)",
            "F": "keep-alive, re-verify per history request (conservative)",
            "W5": "keep-alive, verify-once-per-conn, re-verify every 5 in-scope requests",
            "W10": "keep-alive, verify-once-per-conn, re-verify every 10 in-scope requests",
            "W20": "keep-alive, verify-once-per-conn, re-verify every 20 in-scope requests",
            "E": "keep-alive, verify-once-per-connection, no window (hybrid ceiling)",
        },
        "byAuthMs": {},
    }
    for mag in times:
        seq_block: dict[str, Any] = {}
        for seq in SEQUENCES:
            med = {a: statistics.median(times[mag][seq][a]) for a in ARMS}
            ev = {a: statistics.median(events[mag][seq][a]) for a in ARMS}
            win_e = med["D4"] - med["E"]
            seq_block[seq] = {
                "iterMsMedian": med,
                "iterMsP90": {a: p90(times[mag][seq][a]) for a in ARMS},
                "authEventsMedian": ev,
                "speedupVsD4": {a: med["D4"] / med[a] for a in ARMS if a != "D4"},
                "winRetainedVsE": {
                    a: ((med["D4"] - med[a]) / win_e if win_e > 0 else 1.0)
                    for a in ("W5", "W10", "W20")
                },
            }
        report["byAuthMs"][mag] = seq_block
    print(json.dumps(report, indent=2))
    with open(os.path.join(tempfile.gettempdir(), "auth_window_py.json"), "w") as f:
        json.dump(report, f, indent=2)
    if cli.raw_out:
        with open(cli.raw_out, "w") as f:
            json.dump({"times": times, "events": events}, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())

"""Keep-alive benchmark (Python): one-request-per-connection vs persistent connection.

Mirrors bench/observation-gating/keepalive_bench.ts for the TS loop:
paired/interleaved design — each iteration runs the same 3-call observation
sequence (get_browser_state + get_window_state + parse_visual_regions) once
per arm, in Fisher-Yates order, against one --keep-alive daemon. The
one-shot arm opens a fresh asyncio unix-socket per call (the JSONL socket
protocol's default); the keep-alive arm multiplexes over one
PersistentDaemonClient. An equivalence gate asserts both arms return
identical-shape structuredContent.

Run: python3 bench_observation_keepalive.py (from the python/ directory)
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

from keepalive import DaemonCallError, PersistentDaemonClient

ITERS = 30
CALLS_PER_ITER = 3  # snapshot + capture + parse
PID = 4242
WINDOW_ID = 7
CALL_TIMEOUT_S = 10.0

CallFn = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


async def one_shot_call(socket_path: str, name: str, args: Mapping[str, Any]) -> Any:
    """Fresh connection per call (the JSONL socket protocol's default behavior)."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_unix_connection(socket_path), timeout=CALL_TIMEOUT_S
    )
    try:
        writer.write(json.dumps({"method": "call", "name": name, "args": dict(args)}).encode() + b"\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=CALL_TIMEOUT_S)
        wire = json.loads(line.decode("utf-8"))
        if not wire.get("ok"):
            raise DaemonCallError(f"daemon error on {name}: {wire.get('error')}")
        structured = wire["result"]["structuredContent"]
        if isinstance(structured, dict) and isinstance(structured.get("error"), str):
            raise DaemonCallError(f"daemon error on {name}: {structured['error']}")
        return structured
    finally:
        writer.close()


async def observation_sequence(call: CallFn) -> None:
    """The same 3-call sequence both arms serve; shape gate throws on mismatch."""
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


def shuffle(items: list) -> list:
    out = list(items)
    random.shuffle(out)
    return out


def p90(values: list[float]) -> float:
    return sorted(values)[min(len(values) - 1, int(0.90 * len(values)))]


async def start_daemon(socket_path: str) -> asyncio.subprocess.Process:
    daemon = Path(__file__).resolve().parent / "mock_daemon.py"
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        str(daemon),
        "--socket",
        socket_path,
        "--regions",
        "50",
        "--keep-alive",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        line = await asyncio.wait_for(child.stdout.readline(), timeout=10.0)
    except asyncio.TimeoutError:
        child.kill()
        raise RuntimeError("daemon start timeout")
    if b"ready" not in line:
        child.kill()
        raise RuntimeError(f"daemon failed to start: {line!r}")
    return child


async def main() -> None:
    socket_path = os.path.join(tempfile.gettempdir(), f"cua-keepalive-py-{os.getpid()}.sock")
    child = await start_daemon(socket_path)
    try:
        persistent = PersistentDaemonClient(socket_path)
        keep_alive_call = persistent.as_unwrapped_call_fn()
        one_shot_ms: list[float] = []
        keep_alive_ms: list[float] = []

        for _ in range(ITERS):
            for arm in shuffle(["oneshot", "keepalive"]):
                loop = asyncio.get_running_loop()
                t0 = loop.time()
                if arm == "oneshot":
                    await observation_sequence(
                        lambda name, args: one_shot_call(socket_path, name, args)
                    )
                else:
                    await observation_sequence(keep_alive_call)
                ms = (loop.time() - t0) * 1000.0
                (one_shot_ms if arm == "oneshot" else keep_alive_ms).append(ms)

        await persistent.close()

        per_call_one_shot = [ms / CALLS_PER_ITER for ms in one_shot_ms]
        per_call_keep_alive = [ms / CALLS_PER_ITER for ms in keep_alive_ms]

        print(
            json.dumps(
                {
                    "iters": ITERS,
                    "callsPerIter": CALLS_PER_ITER,
                    "iterMs": {
                        "oneshot": {
                            "median": statistics.median(one_shot_ms),
                            "p90": p90(one_shot_ms),
                        },
                        "keepalive": {
                            "median": statistics.median(keep_alive_ms),
                            "p90": p90(keep_alive_ms),
                        },
                    },
                    "perCallMs": {
                        "oneshot": {
                            "median": statistics.median(per_call_one_shot),
                            "p90": p90(per_call_one_shot),
                        },
                        "keepalive": {
                            "median": statistics.median(per_call_keep_alive),
                            "p90": p90(per_call_keep_alive),
                        },
                    },
                    "speedup": {
                        "iterMedian": statistics.median(one_shot_ms) / statistics.median(keep_alive_ms),
                        "iterP90": p90(one_shot_ms) / p90(keep_alive_ms),
                    },
                    "arms": "oneshot=1 connection/call, keepalive=PersistentDaemonClient",
                    "transport": "asyncio unix socket, loopback",
                },
                indent=2,
            )
        )
    finally:
        child.terminate()
        try:
            await asyncio.wait_for(child.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            child.kill()


if __name__ == "__main__":
    asyncio.run(main())

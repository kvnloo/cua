"""Auth-lifetime bench (Python): is the auth-lifetime decision the real gate to keep-alive?

Four arms on the same 3-call observation sequence (get_browser_state +
get_window_state + parse_visual_regions), with the mock daemon simulating
#3383's per-connection codesign verification via --auth-ms/--auth-mode/--auth-scope:

  A (today):      one-shot connections, auth at accept        (accept, all)
  B (option b):   keep-alive, auth once per connection        (accept, all)
  C (conservative): keep-alive, re-auth before every request  (request, all)
  D (option a):   one-shot, auth scoped to history_* only     (accept, history)

If C still beats A, the keep-alive transport change is independently
valuable and the auth-lifetime contract is a multiplier on the win, not
the gate. The equivalence gate asserts all arms return identical-shape
structuredContent.

Run: python3 bench_observation_auth_lifetime.py (from the python/ directory)
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
CALLS_PER_ITER = 3
PID = 4242
WINDOW_ID = 7
CALL_TIMEOUT_S = 10.0
AUTH_MAGS = (5.0, 25.0)  # ms; bracket the real codesign-verify cost

CallFn = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


async def one_shot_call(socket_path: str, name: str, args: Mapping[str, Any]) -> Any:
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


async def start_daemon(socket_path: str, auth_ms: float, auth_mode: str, auth_scope: str) -> asyncio.subprocess.Process:
    daemon = Path(__file__).resolve().parent / "mock_daemon.py"
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        str(daemon),
        "--socket", socket_path,
        "--regions", "50",
        "--keep-alive",
        "--auth-ms", str(auth_ms),
        "--auth-mode", auth_mode,
        "--auth-scope", auth_scope,
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


async def stop_daemon(child: asyncio.subprocess.Process) -> None:
    child.terminate()
    try:
        await asyncio.wait_for(child.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        child.kill()


async def run_arms(socket_path: str, arms: list[str]) -> dict[str, float]:
    """Run one block of arms against the live daemon; returns iter-ms per arm."""
    persistent = PersistentDaemonClient(socket_path)
    keep_alive_call = persistent.as_unwrapped_call_fn()
    out: dict[str, float] = {}
    loop = asyncio.get_running_loop()
    for arm in shuffle(arms):
        t0 = loop.time()
        if arm in ("A", "D"):
            await observation_sequence(
                lambda name, args: one_shot_call(socket_path, name, args)
            )
        else:
            await observation_sequence(keep_alive_call)
        out[arm] = (loop.time() - t0) * 1000.0
    await persistent.close()
    return out


async def main() -> None:
    socket_path = os.path.join(tempfile.gettempdir(), f"cua-authlife-py-{os.getpid()}.sock")
    # (label, daemon auth_mode, daemon auth_scope, arms in this block)
    configs = [
        ("accept-all", "accept", "all", ["A", "B"]),
        ("request-all", "request", "all", ["C"]),
        ("accept-history", "accept", "history", ["D"]),
    ]
    times: dict[str, dict[str, list[float]]] = {str(m): {a: [] for a in "ABCD"} for m in AUTH_MAGS}

    for auth_ms in AUTH_MAGS:
        mag = str(auth_ms)
        for it in range(ITERS):
            for label, mode, scope, arms in shuffle(list(configs)):
                child = await start_daemon(socket_path, auth_ms, mode, scope)
                try:
                    got = await run_arms(socket_path, arms)
                finally:
                    await stop_daemon(child)
                for arm, ms in got.items():
                    times[mag][arm].append(ms)
            # Checkpoint: daemon restarts have killed benches mid-run before.
            with open(os.path.join(tempfile.gettempdir(), "auth_lifetime_py_partial.json"), "w") as f:
                json.dump({m: {a: len(times[m][a]) for a in "ABCD"} for m in times}, f)

    report: dict[str, Any] = {
        "iters": ITERS,
        "callsPerIter": CALLS_PER_ITER,
        "transport": "asyncio unix socket, loopback",
        "arms": {
            "A": "one-shot connections, auth at accept (today)",
            "B": "keep-alive, auth once per connection (option b)",
            "C": "keep-alive, re-auth per request (conservative)",
            "D": "one-shot, auth scoped to history_* only (option a)",
        },
        "byAuthMs": {},
    }
    for mag in times:
        med = {a: statistics.median(times[mag][a]) for a in "ABCD"}
        report["byAuthMs"][mag] = {
            "iterMsMedian": med,
            "iterMsP90": {a: p90(times[mag][a]) for a in "ABCD"},
            "speedupVsA": {a: med["A"] / med[a] for a in "BCD"},
        }
    print(json.dumps(report, indent=2))
    out = Path(__file__).resolve().parent / ".." / ".." / ".." / "auth_lifetime_py.json"
    with open(os.path.join(tempfile.gettempdir(), "auth_lifetime_py.json"), "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())

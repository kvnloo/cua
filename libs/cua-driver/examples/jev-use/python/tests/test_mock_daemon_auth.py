"""Tests for mock_daemon.py --auth-cache (verify-once-per-connection prototype).

Behavioral timing test with generous margins: with a 120ms simulated auth,
two sequential history_record calls on one persistent connection must pay
~2x auth without the cache and ~1x with it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keepalive import PersistentDaemonClient  # noqa: E402

AUTH_MS = 120.0
MARGIN_MS = 60.0  # uncached two-call total must exceed this; cached must stay under 2*AUTH_MS


async def _start_daemon(socket_path: str, auth_cache: bool) -> asyncio.subprocess.Process:
    daemon = Path(__file__).resolve().parent.parent / "mock_daemon.py"
    args = [
        sys.executable, str(daemon),
        "--socket", socket_path, "--regions", "1",
        "--keep-alive", "--auth-ms", str(AUTH_MS),
        "--auth-mode", "request", "--auth-scope", "history",
    ]
    if auth_cache:
        args.append("--auth-cache")
    child = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    line = await asyncio.wait_for(child.stdout.readline(), timeout=10.0)
    assert b"ready" in line, f"daemon failed to start: {line!r}"
    return child


async def _two_history_calls_ms(socket_path: str) -> float:
    client = PersistentDaemonClient(socket_path)
    try:
        call = client.as_unwrapped_call_fn()
        t0 = time.monotonic()
        for _ in range(2):
            result = await call("history_record", {"sequence": 1})
            assert result == {"recorded": True}, result
        return (time.monotonic() - t0) * 1000.0
    finally:
        await client.close()


class AuthCacheTest(unittest.TestCase):
    def _measure(self, auth_cache: bool) -> float:
        async def go():
            socket_path = os.path.join(
                tempfile.gettempdir(), f"cua-authcache-test-{os.getpid()}.sock")
            child = await _start_daemon(socket_path, auth_cache)
            try:
                return await _two_history_calls_ms(socket_path)
            finally:
                child.terminate()
                try:
                    await asyncio.wait_for(child.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    child.kill()

        return asyncio.run(go())

    def test_reauth_per_request_without_cache(self):
        ms = self._measure(auth_cache=False)
        self.assertGreater(
            ms, 2 * AUTH_MS - MARGIN_MS,
            f"without --auth-cache two history calls should pay ~2x auth, got {ms:.1f}ms",
        )

    def test_verify_once_per_connection_with_cache(self):
        ms = self._measure(auth_cache=True)
        self.assertLess(
            ms, AUTH_MS + MARGIN_MS,
            f"with --auth-cache two history calls should pay ~1x auth, got {ms:.1f}ms",
        )


if __name__ == "__main__":
    unittest.main()

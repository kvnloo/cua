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


async def _start_daemon(
    socket_path: str,
    auth_cache: bool,
    window_requests: int = 0,
    window_ms: float = 0.0,
    events_path: str | None = None,
) -> asyncio.subprocess.Process:
    daemon = Path(__file__).resolve().parent.parent / "mock_daemon.py"
    args = [
        sys.executable, str(daemon),
        "--socket", socket_path, "--regions", "1",
        "--keep-alive", "--auth-ms", str(AUTH_MS),
        "--auth-mode", "request", "--auth-scope", "history",
    ]
    if auth_cache:
        args.append("--auth-cache")
    if window_requests:
        args += ["--auth-window-requests", str(window_requests)]
    if window_ms:
        args += ["--auth-window-ms", str(window_ms)]
    if events_path:
        args += ["--auth-events", events_path]
    child = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    line = await asyncio.wait_for(child.stdout.readline(), timeout=10.0)
    assert b"ready" in line, f"daemon failed to start: {line!r}"
    return child


async def _history_calls_ms(socket_path: str, count: int, gap_s: float = 0.0) -> float:
    client = PersistentDaemonClient(socket_path)
    try:
        call = client.as_unwrapped_call_fn()
        t0 = time.monotonic()
        for _ in range(count):
            result = await call("history_record", {"sequence": 1})
            assert result == {"recorded": True}, result
            if gap_s:
                await asyncio.sleep(gap_s)
        return (time.monotonic() - t0) * 1000.0
    finally:
        await client.close()


class AuthCacheTest(unittest.TestCase):
    def _measure(
        self,
        auth_cache: bool,
        count: int = 2,
        window_requests: int = 0,
        window_ms: float = 0.0,
        gap_s: float = 0.0,
        events_path: str | None = None,
    ) -> tuple[float, list[dict]]:
        async def go():
            socket_path = os.path.join(
                tempfile.gettempdir(), f"cua-authcache-test-{os.getpid()}.sock")
            child = await _start_daemon(
                socket_path, auth_cache, window_requests, window_ms, events_path)
            try:
                ms = await _history_calls_ms(socket_path, count, gap_s)
            finally:
                child.terminate()
                try:
                    await asyncio.wait_for(child.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    child.kill()
            events: list[dict] = []
            if events_path and os.path.exists(events_path):
                with open(events_path) as f:
                    events = [json.loads(line) for line in f if line.strip()]
            return ms, events

        return asyncio.run(go())

    def test_reauth_per_request_without_cache(self):
        ms, _ = self._measure(auth_cache=False)
        self.assertGreater(
            ms, 2 * AUTH_MS - MARGIN_MS,
            f"without --auth-cache two history calls should pay ~2x auth, got {ms:.1f}ms",
        )

    def test_verify_once_per_connection_with_cache(self):
        ms, _ = self._measure(auth_cache=True)
        self.assertLess(
            ms, AUTH_MS + MARGIN_MS,
            f"with --auth-cache two history calls should pay ~1x auth, got {ms:.1f}ms",
        )

    def test_request_window_reverifies_every_n_requests(self):
        # window 3: verify at call 1; the next 3 in-scope calls are trusted;
        # call 5 re-verifies. Over 5 calls: ~2x auth, not 5x and not 1x.
        events_path = os.path.join(tempfile.gettempdir(),
                                   f"cua-authwin-events-{os.getpid()}.jsonl")
        if os.path.exists(events_path):
            os.unlink(events_path)
        ms, events = self._measure(auth_cache=True, count=5, window_requests=3,
                                   events_path=events_path)
        self.assertGreater(ms, 2 * AUTH_MS - MARGIN_MS,
                           f"window-3 should re-verify once over 5 calls, got {ms:.1f}ms")
        self.assertLess(ms, 3 * AUTH_MS,
                        f"window-3 should NOT re-verify per request, got {ms:.1f}ms")
        self.assertEqual(len(events), 2,
                         f"window-3 over 5 calls should log exactly 2 auth events, got {len(events)}")

    def test_request_window_zero_is_verify_once(self):
        # window 0 = never: 4 history calls pay exactly 1x auth.
        events_path = os.path.join(tempfile.gettempdir(),
                                   f"cua-authwin-events0-{os.getpid()}.jsonl")
        if os.path.exists(events_path):
            os.unlink(events_path)
        ms, events = self._measure(auth_cache=True, count=4, events_path=events_path)
        self.assertLess(ms, AUTH_MS + MARGIN_MS,
                        f"window-0 should pay ~1x auth over 4 calls, got {ms:.1f}ms")
        self.assertEqual(len(events), 1,
                         f"window-0 should log exactly 1 auth event, got {len(events)}")

    def test_time_window_reverifies_after_expiry(self):
        # 150ms time window, 200ms gap after each of 2 calls -> both pay
        # (~2x auth + 2 gaps).
        gap_ms = 200.0
        ms, _ = self._measure(auth_cache=True, count=2, window_ms=150.0,
                              gap_s=gap_ms / 1000.0)
        self.assertGreater(ms, 2 * AUTH_MS + 2 * gap_ms - MARGIN_MS,
                           f"expired time window should re-verify, got {ms:.1f}ms")

    def test_time_window_zero_trusts_within_window(self):
        # no time window, 200ms gap after each of 2 calls -> still 1x auth.
        gap_ms = 200.0
        ms, _ = self._measure(auth_cache=True, count=2, gap_s=gap_ms / 1000.0)
        self.assertLess(ms, AUTH_MS + 2 * gap_ms + MARGIN_MS,
                        f"no time window should keep trust across the gap, got {ms:.1f}ms")


if __name__ == "__main__":
    unittest.main()

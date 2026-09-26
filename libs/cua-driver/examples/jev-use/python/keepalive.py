"""Keep-alive (persistent connection) client for the daemon's JSONL socket
protocol — a fork research prototype, NOT an upstream proposal.

The mock daemon speaks one-request-per-connection: every RPC pays a full
socket connect + handshake + teardown. This client opens ONE unix-socket
connection and sends every request down it, reading one response line per
request. Requests are serialized (the daemon answers in order), matching
how the synchronous recipe loop issues calls.

What it is NOT: a protocol change to the daemon. The daemon side is
``mock_daemon.py --keep-alive``. Upstream, this would require the
auth-lifetime contract question in dq-3383 (authenticate once per
connection vs per request) to be answered first.

Note on the Python run.py loop: it drives the real driver through MCP
stdio (``Driver`` in run.py), which is already a persistent connection —
there is no per-call connect cost there. This prototype is for the JSONL
unix-socket protocol path (the TS loop's mock_daemon.mjs world), answering:
if the Python loop ever spoke that protocol, how large is the per-call
connection overhead, and does a persistent client recover it?

Mirrors typescript/keepalive.ts on the fork's muse/keepalive-prototype
branch.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any, Awaitable, Callable, Mapping

CALL_TIMEOUT_S = 10.0


class DaemonCallError(RuntimeError):
    """Raised when a single daemon RPC fails (transport, timeout, or error payload)."""


class PersistentDaemonClient:
    """One unix-socket connection reused for every daemon call.

    Calls are serialized: each request is sent in turn and matched to the
    next response line, which is what the daemon's in-order answering
    guarantees. If the connection dies, pending waiters are rejected and
    the next call reconnects transparently.
    """

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._waiters: deque[asyncio.Future] = deque()
        self._read_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False

    async def _ensure_connected(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self._writer is not None and not self._writer.is_closing():
            return self._reader, self._writer
        if self._closed:
            raise DaemonCallError("client is closed")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self._socket_path), timeout=CALL_TIMEOUT_S
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise DaemonCallError(f"daemon connect failed: {exc}") from exc
        self._reader, self._writer = reader, writer
        self._read_task = asyncio.ensure_future(self._read_loop())
        return reader, writer

    async def _read_loop(self) -> None:
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    self._on_fatal(DaemonCallError("daemon closed the connection"))
                    return
                try:
                    waiter = self._waiters.popleft()
                except IndexError:
                    continue  # stray line; keep the loop moving
                if waiter.done():
                    continue
                try:
                    waiter.set_result(json.loads(line.decode("utf-8")))
                except Exception as exc:  # noqa: BLE001 - must resolve the waiter
                    waiter.set_exception(DaemonCallError(f"bad response line: {exc}"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - connection-level failure
            self._on_fatal(exc)

    def _on_fatal(self, exc: BaseException) -> None:
        writer, self._writer = self._writer, None
        self._reader = None
        waiters, self._waiters = self._waiters, deque()
        if writer is not None:
            writer.close()
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        for waiter in waiters:
            if not waiter.done():
                if isinstance(exc, BaseException):
                    waiter.set_exception(exc)
                else:
                    waiter.set_exception(DaemonCallError(str(exc)))

    async def call(self, name: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        """One serialized call over the persistent connection."""
        async with self._send_lock:
            _, writer = await self._ensure_connected()
            loop = asyncio.get_running_loop()
            waiter: asyncio.Future = loop.create_future()
            self._waiters.append(waiter)
            writer.write(json.dumps({"method": "call", "name": name, "args": dict(args)}).encode("utf-8") + b"\n")
            try:
                await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError) as exc:
                self._on_fatal(exc)
                raise DaemonCallError(f"daemon write failed on {name}: {exc}") from exc
            try:
                return await asyncio.wait_for(asyncio.shield(waiter), timeout=CALL_TIMEOUT_S)
            except asyncio.TimeoutError as exc:
                try:
                    self._waiters.remove(waiter)
                except ValueError:
                    pass
                if not waiter.done():
                    waiter.cancel()
                raise DaemonCallError(f"daemon call timeout: {name}") from exc

    def as_call_fn(self) -> Callable[[str, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]:
        """The raw-wire CallFn shape: returns the daemon's JSON envelope."""
        return self.call

    def as_unwrapped_call_fn(self) -> Callable[[str, Mapping[str, Any]], Awaitable[Any]]:
        """Bench-convention CallFn: throw on !ok, return structuredContent.

        Use when comparing arms so both arms see identical payloads.
        """

        async def unwrapped(name: str, args: Mapping[str, Any]) -> Any:
            wire = await self.call(name, args)
            if not isinstance(wire, dict) or not wire.get("ok"):
                error = wire.get("error") if isinstance(wire, dict) else None
                raise DaemonCallError(f"daemon error on {name}: {error}")
            structured = wire.get("result", {}).get("structuredContent")
            if isinstance(structured, dict) and isinstance(structured.get("error"), str):
                raise DaemonCallError(f"daemon error on {name}: {structured['error']}")
            return structured

        return unwrapped

    async def close(self) -> None:
        self._closed = True
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, asyncio.TimeoutError):
                pass

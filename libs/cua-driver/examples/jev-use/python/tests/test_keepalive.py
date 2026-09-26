from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keepalive import DaemonCallError, PersistentDaemonClient


def echo_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """In-process unix-socket test daemon: one JSONL response per request line.

    Serves structuredContent={echo: <request>} for call envelopes and a
    metadata response, mirroring mock_daemon.py's wire contract.
    """

    async def serve() -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                request = json.loads(line.decode("utf-8"))
                if request.get("method") == "metadata":
                    payload = {
                        "ok": True,
                        "result": {"driver_version": "test", "embedded": False},
                    }
                else:
                    payload = {
                        "ok": True,
                        "result": {
                            "structuredContent": {"echo": request},
                        },
                    }
                writer.write(json.dumps(payload).encode() + b"\n")
                await writer.drain()
        finally:
            writer.close()

    asyncio.ensure_future(serve())


class KeepAliveTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.socket_path = os.path.join(tempfile.gettempdir(), f"ka-test-{os.getpid()}-{id(self)}.sock")
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        self.server = await asyncio.start_unix_server(echo_handler, path=self.socket_path)
        self.clients: list[PersistentDaemonClient] = []

    async def asyncTearDown(self) -> None:
        for client in self.clients:
            await client.close()
        self.server.close()
        await self.server.wait_closed()

    def _client(self) -> PersistentDaemonClient:
        client = PersistentDaemonClient(self.socket_path)
        self.clients.append(client)
        return client

    async def test_single_call_returns_wire_envelope(self) -> None:
        client = self._client()
        wire = await client.call("get_browser_state", {"target_id": "t"})
        self.assertTrue(wire["ok"])
        self.assertEqual(wire["result"]["structuredContent"]["echo"]["name"], "get_browser_state")

    async def test_unwrapped_returns_structured_content(self) -> None:
        client = self._client()
        structured = await client.as_unwrapped_call_fn()("get_window_state", {"pid": 4242})
        self.assertEqual(structured["echo"]["name"], "get_window_state")

    async def test_sequential_calls_share_one_connection(self) -> None:
        client = self._client()
        await client.call("a", {})
        await client.call("b", {})
        first = client._writer
        await client.call("c", {})
        self.assertIs(first, client._writer, "connection was re-established between calls")

    async def test_concurrent_calls_serialize_in_request_order(self) -> None:
        client = self._client()
        results = await asyncio.gather(
            client.call("first", {}), client.call("second", {}), client.call("third", {})
        )
        names = [r["result"]["structuredContent"]["echo"]["name"] for r in results]
        self.assertEqual(names, ["first", "second", "third"])

    async def test_error_envelope_raises(self) -> None:
        async def bad(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write(b'{"ok": false, "error": "boom"}\n')
            await writer.drain()
            await asyncio.sleep(0.5)
            writer.close()

        bad_server = await asyncio.start_unix_server(bad, path=self.socket_path + ".bad")
        client = PersistentDaemonClient(self.socket_path + ".bad")
        self.clients.append(client)
        try:
            with self.assertRaises(DaemonCallError) as ctx:
                await client.as_unwrapped_call_fn()("x", {})
            self.assertIn("boom", str(ctx.exception))
        finally:
            bad_server.close()
            await bad_server.wait_closed()

    async def test_close_is_idempotent_and_rejects_new_calls(self) -> None:
        client = self._client()
        await client.call("a", {})
        await client.close()
        await client.close()
        with self.assertRaises(DaemonCallError):
            await client.call("b", {})

    async def test_call_to_dead_socket_raises_not_hangs(self) -> None:
        client = PersistentDaemonClient(self.socket_path + ".missing")
        self.clients.append(client)
        with self.assertRaises(DaemonCallError):
            await client.call("a", {})


if __name__ == "__main__":
    unittest.main()

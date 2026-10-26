"""Minimal newline-delimited JSON-RPC MCP stdio client (stdlib only)."""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time

PROTOCOL = "2025-06-18"


class McpError(Exception):
    pass


class McpStdioClient:
    def __init__(self, argv: list[str], env: dict | None = None):
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env=env)
        self._lines: queue.Queue = queue.Queue()
        self._next = 0
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            self._lines.put(raw)
        self._lines.put(None)

    def _send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None, timeout: float) -> dict:
        self._next += 1
        ident = self._next
        self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise McpError(f"timeout waiting for {method}")
            try:
                raw = self._lines.get(timeout=left)
            except queue.Empty:
                raise McpError(f"timeout waiting for {method}") from None
            if raw is None:
                raise McpError("server closed stdout")
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if message.get("id") != ident:
                continue  # notification or unrelated server message
            if "error" in message:
                raise McpError(f"{method} failed: {message['error'].get('message', 'error')}")
            return message.get("result", {})

    def initialize(self, timeout: float) -> None:
        self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                    "clientInfo": {"name": "cua-arm-b", "version": "1"}}, timeout)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
            self.proc.wait()
        finally:
            if self.proc.stdout:
                self.proc.stdout.close()

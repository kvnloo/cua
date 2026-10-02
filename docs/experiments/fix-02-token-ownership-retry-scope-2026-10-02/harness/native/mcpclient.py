"""Minimal MCP stdio client for the OWN-36 harness (measurement only).

Speaks newline-delimited JSON-RPC to `cua-driver mcp` (direct runtime) or to
`cua-driver mcp --socket <path>` (stdio proxy to a `cua-driver serve` daemon).
No Driver code is modified; every response is returned verbatim.
"""

import json
import queue
import subprocess
import threading
import time

PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    pass


class McpClient:
    def __init__(self, argv, stderr_path, env=None, name="own36"):
        self._stderr = open(stderr_path, "ab")
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            env=env,
            bufsize=0,
        )
        self.name = name
        self._next = 1
        self._responses = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                self._responses.put(json.loads(line))
            except json.JSONDecodeError:
                self._responses.put({"_unparsed": line})
        self._responses.put(None)

    def _send(self, message):
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.proc.stdin.flush()

    def request(self, method, params, timeout=120):
        request_id = self._next
        self._next += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpError(f"timeout waiting for {method}")
            message = self._responses.get(timeout=remaining)
            if message is None:
                raise McpError(f"server closed during {method}")
            if message.get("id") == request_id:
                return message

    def initialize(self):
        response = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self.name, "version": "1"},
            },
        )
        if "error" in response:
            raise McpError(f"initialize failed: {response['error']}")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return response

    def tools(self):
        return self.request("tools/list", {})

    def call(self, name, arguments, timeout=120):
        response = self.request("tools/call", {"name": name, "arguments": arguments}, timeout)
        if "error" in response:
            return {"rpc_error": response["error"]}
        return response.get("result", {})

    def close(self, timeout=20):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            return self.proc.wait(timeout=10)
        finally:
            self._stderr.close()


def text_of(result):
    return "\n".join(
        item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"
    )

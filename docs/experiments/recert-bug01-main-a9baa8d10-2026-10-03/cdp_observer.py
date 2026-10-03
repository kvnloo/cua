"""Independent CDP observer for RECERT-BUG01 part B (measurement only, read-only).

A second CDP client, separate from the Driver: it opens its OWN browser-level
WebSocket to the isolated Chrome's DevTools endpoint (port from the profile's
DevToolsActivePort file) and never attaches to a page, never enables a page
domain and never sends a mutating command. Per sample it records:

  - Target.getTargets: the page targets and Chrome's own `attached` flag;
  - Browser.getHistograms {query: "DevTools"}: Chrome's own browser-side
    counters (used only if the pre-registration names one);
  - the observer's own command/reply counts (it receives no page events).

The WebSocket client is a minimal RFC 6455 client on the standard library
(the jev-use venv has no WebSocket package). Runs INSIDE the isolated session.
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import struct
import time
from pathlib import Path
from typing import Any


class CdpWs:
    def __init__(self, port: int, path: str, timeout: float = 10.0) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("handshake closed")
            buf += chunk
        head, self.buf = buf.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise ConnectionError(f"handshake refused: {status!r}")
        self.next_id = 1
        self.events_seen = 0
        self.commands_sent = 0

    def close(self) -> None:
        try:
            self.sock.sendall(bytes([0x88, 0x80]) + os.urandom(4))
        except OSError:
            pass
        self.sock.close()

    def _send(self, obj: dict[str, Any]) -> None:
        data = json.dumps(obj).encode()
        hdr = bytearray([0x81])
        n = len(data)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        self.sock.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise ConnectionError("socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv(self) -> dict[str, Any]:
        payload = b""
        while True:
            b0, b1 = self._read(2)
            op, fin, n = b0 & 0x0F, b0 & 0x80, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                raise ConnectionError("server closed")
            if op == 0x9:
                continue
            if op in (0x0, 0x1, 0x2):
                payload += data
                if fin:
                    return json.loads(payload)

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        i = self.next_id
        self.next_id += 1
        self._send({"id": i, "method": method, "params": params or {}})
        self.commands_sent += 1
        while True:
            msg = self._recv()
            if msg.get("id") == i:
                return msg
            self.events_seen += 1


def devtools_endpoint(browser_pid: int) -> tuple[int, str]:
    raw = Path(f"/proc/{browser_pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    m = re.search(r"--user-data-dir=(\S+)", raw)
    if not m:
        raise RuntimeError("browser cmdline has no --user-data-dir")
    active = Path(m.group(1)) / "DevToolsActivePort"
    for _ in range(100):
        if active.exists():
            lines = active.read_text().split()
            if len(lines) >= 2:
                return int(lines[0]), lines[1]
        time.sleep(0.05)
    raise RuntimeError("DevToolsActivePort not found")


class Observer:
    def __init__(self, browser_pid: int) -> None:
        port, path = devtools_endpoint(browser_pid)
        self.ws = CdpWs(port, path)

    def sample(self, histograms: bool = True) -> dict[str, Any]:
        t0 = time.time() * 1000
        targets = self.ws.call("Target.getTargets").get("result", {}).get("targetInfos", [])
        pages = [t for t in targets if t.get("type") == "page"]
        out: dict[str, Any] = {
            "t_ms": t0,
            "n_targets": len(targets),
            "pages": [{"attached": t.get("attached"), "url_scheme": (t.get("url") or "").split(":", 1)[0]} for t in pages],
            "page_attached": [t.get("attached") for t in pages],
        }
        if histograms:
            h = self.ws.call("Browser.getHistograms", {"query": "DevTools"})
            if "error" in h:
                out["histograms_error"] = h["error"]
            else:
                out["histograms"] = {
                    x["name"]: {"count": x.get("count"), "sum": x.get("sum"), "buckets": x.get("buckets")}
                    for x in h.get("result", {}).get("histograms", [])
                }
        out["observer_commands_sent"] = self.ws.commands_sent
        out["observer_events_seen"] = self.ws.events_seen
        out["t_end_ms"] = time.time() * 1000
        return out

    def close(self) -> None:
        self.ws.close()

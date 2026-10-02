"""Minimal standard-library CDP client and decoy listener for B-02 probes and controls.

Used only inside the isolated X11 session against the lane-started, Driver-owned
browser on loopback. It never launches or configures a browser. ``CdpClient`` is
a second, independent CDP client process-side (STEP 0 "second process" probe and
the N-W2 same-document DOM replacement); ``Decoy`` is the lane-started listener
that takes over a freed DevTools port in N-E1 and counts every connection.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _proc_net_listeners() -> list[tuple[int, int]]:
    out = []
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = open(path).read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            f = line.split()
            if len(f) < 10 or f[3] != "0A":
                continue
            addr, port = f[1].split(":")
            if addr not in ("0100007F", "00000000000000000000000001000000"):
                continue
            out.append((int(port, 16), int(f[9])))
    return out


def devtools_ports_for_pid(pid: int) -> list[int]:
    """Loopback LISTEN ports whose socket inode is held by ``pid`` itself."""
    inodes = set()
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if target.startswith("socket:["):
                inodes.add(int(target[8:-1]))
    except OSError:
        return []
    return sorted({port for port, inode in _proc_net_listeners() if inode in inodes})


def http_get_json(port: int, path: str, timeout: float = 2.0) -> Any:
    """GET + JSON body, reading exactly Content-Length bytes (Chrome's DevTools HTTP
    server keeps the connection open after the reply, so reading to EOF would block)."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n".encode())
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        length = None
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                length = int(value.strip())
        while length is None or len(body) < length:
            chunk = s.recv(65536)
            if not chunk:
                break
            body += chunk
    return json.loads(body if length is None else body[:length])


class CdpClient:
    """Blocking CDP client over one browser-level WebSocket (flattened sessions)."""

    def __init__(self, ws_url: str, timeout: float = 10.0) -> None:
        rest = ws_url.removeprefix("ws://")
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                           f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.sock.recv(1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"websocket upgrade failed: {head[:80]!r}")
        self.next_id = 0
        self.events: list[dict[str, Any]] = []

    def _send_frame(self, text: str) -> None:
        payload = text.encode()
        mask = os.urandom(4)
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("websocket closed")
            buf += chunk
        return buf

    def _recv_message(self) -> dict[str, Any]:
        parts = b""
        while True:
            b0, b1 = self._recv_exact(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv_exact(8))[0]
            data = self._recv_exact(n)
            opcode = b0 & 0x0F
            if opcode == 0x8:
                raise ConnectionError("websocket close frame")
            if opcode in (0x9, 0xA):
                continue
            parts += data
            if b0 & 0x80:
                return json.loads(parts)

    def call(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> Any:
        self.next_id += 1
        msg: dict[str, Any] = {"id": self.next_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self._send_frame(json.dumps(msg))
        while True:
            reply = self._recv_message()
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result")
            self.events.append(reply)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def page_target(client: CdpClient, url_prefix: str) -> str:
    infos = client.call("Target.getTargets")["targetInfos"]
    pages = [t for t in infos if t.get("type") == "page" and t.get("url", "").startswith(url_prefix)]
    if len(pages) != 1:
        raise RuntimeError(f"expected one page for {url_prefix}, found {len(pages)}")
    return pages[0]["targetId"]


# The Driver's SEMANTIC_COMPUTED_STYLES (cua-driver-core browser/semantic.rs).
SNAPSHOT_STYLES = ["display", "visibility", "opacity", "pointer-events", "cursor", "position", "z-index",
                   "overflow-x", "overflow-y"]


def timed_semantic_sequence(client: CdpClient, target_id: str) -> dict[str, float]:
    """The semantic_v2 snapshot's CDP calls, in the Driver's order, each timed (ms)."""
    out: dict[str, float] = {}
    t = time.monotonic_ns()
    sid = client.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
    out["attach"] = (time.monotonic_ns() - t) / 1e6
    t = time.monotonic_ns()
    client.call("DOM.getDocument", {"depth": -1, "pierce": True}, sid)
    out["dom_get_document"] = (time.monotonic_ns() - t) / 1e6
    t = time.monotonic_ns()
    client.call("Page.getFrameTree", {}, sid)
    out["frame_tree"] = (time.monotonic_ns() - t) / 1e6
    t = time.monotonic_ns()
    client.call("DOMSnapshot.captureSnapshot", {"computedStyles": SNAPSHOT_STYLES, "includePaintOrder": True,
                                                "includeDOMRects": True}, sid)
    client.call("Page.getLayoutMetrics", {}, sid)
    out["layout_snapshot"] = (time.monotonic_ns() - t) / 1e6
    t = time.monotonic_ns()
    client.call("Accessibility.getFullAXTree", {}, sid)
    out["ax_tree"] = (time.monotonic_ns() - t) / 1e6
    out["total"] = sum(out.values())
    return out


def evaluate(client: CdpClient, target_id: str, expression: str) -> Any:
    sid = client.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
    try:
        res = client.call("Runtime.evaluate", {"expression": expression, "returnByValue": True}, sid)
    finally:
        client.call("Target.detachFromTarget", {"sessionId": sid})
    return res.get("result", {}).get("value")


class Decoy:
    """Lane-started HTTP listener on a freed DevTools port; serves a plausible /json/version."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.connections = 0
        self.requests: list[str] = []
        decoy = self

        class H(BaseHTTPRequestHandler):
            def setup(self) -> None:
                decoy.connections += 1
                super().setup()

            def do_GET(self) -> None:  # noqa: N802
                decoy.requests.append(self.path.split("?")[0])
                body = json.dumps({
                    "Browser": "Chrome/151.0.0.0", "Protocol-Version": "1.3",
                    "webSocketDebuggerUrl": f"ws://127.0.0.1:{decoy.port}/devtools/browser/{uuid.uuid4()}",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a: Any) -> None:
                return

        ThreadingHTTPServer.allow_reuse_address = True
        deadline = time.monotonic() + 5
        while True:
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", port), H)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

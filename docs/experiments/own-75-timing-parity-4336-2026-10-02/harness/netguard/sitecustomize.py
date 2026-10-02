"""OWN-75 network guard for the Python runner (loaded through PYTHONPATH as sitecustomize).

Measurement harness only; never part of the product. Every AF_INET/AF_INET6 connect or sendto to a
non-loopback address is refused before any packet leaves the process and appended to
OWN75_NETGUARD_LOG as {"kind": "refused", ...}. Loopback and AF_UNIX traffic is untouched. On import
it appends {"kind": "armed", ...} so each trial can prove the guard was active in the runner.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import time

_LOG = os.environ.get("OWN75_NETGUARD_LOG")


def _record(kind: str, **fields: object) -> None:
    if not _LOG:
        return
    entry = {"kind": kind, "runtime": "python", "pid": os.getpid(), "t": time.time(), **fields}
    with open(_LOG, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")


def _is_loopback(host: object) -> bool:
    if not isinstance(host, str):
        return False
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False  # an unresolved name counts as non-loopback


def _guard(sock: socket.socket, address: object, call: str) -> None:
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        return
    host = address[0] if isinstance(address, tuple) and address else address
    if not _is_loopback(host):
        _record("refused", call=call, host=str(host),
                port=address[1] if isinstance(address, tuple) and len(address) > 1 else None)
        raise ConnectionRefusedError(f"OWN-75 netguard refused non-loopback {call} to {host!r}")


if _LOG:
    _connect, _connect_ex, _sendto = socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto

    def connect(self: socket.socket, address: object) -> None:  # type: ignore[override]
        _guard(self, address, "connect")
        return _connect(self, address)

    def connect_ex(self: socket.socket, address: object) -> int:  # type: ignore[override]
        _guard(self, address, "connect_ex")
        return _connect_ex(self, address)

    def sendto(self: socket.socket, data: bytes, *args: object) -> int:  # type: ignore[override]
        _guard(self, args[-1], "sendto")
        return _sendto(self, data, *args)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.socket.sendto = sendto  # type: ignore[method-assign]
    _record("armed", argv=[os.path.basename(a) for a in sys.argv[:1]])

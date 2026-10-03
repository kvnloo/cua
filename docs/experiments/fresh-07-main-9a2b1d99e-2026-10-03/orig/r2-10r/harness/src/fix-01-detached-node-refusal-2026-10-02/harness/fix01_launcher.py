#!/usr/bin/env python3
"""FIX-01 launcher: the unchanged R2-07 measurement-only launcher plus the provider-cap-0 socket guard.

Installs the same non-loopback connect guard as fix01_harness.py in this subprocess, appends one
``nonloopback_refused`` receipt (count only) to R2_07_RECEIPT_LOG at exit, then runs
``r2_07_launcher.main()`` with the original argv (same usage as r2_07_launcher.py).
"""

from __future__ import annotations

import atexit
import json
import os
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R207 = HERE.parents[1] / "r2-07-2026-10-02" / "harness"
REFUSED = {"n": 0}


def _loopback(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return True
    host = str(address[0])
    return host.startswith("127.") or host in ("::1", "localhost")


_connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex


def _guarded(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address):
        REFUSED["n"] += 1
        raise ConnectionRefusedError("FIX-01: non-loopback connect refused (provider cap 0)")
    return _connect(self, address)


def _guarded_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address):
        REFUSED["n"] += 1
        return 111
    return _connect_ex(self, address)


socket.socket.connect, socket.socket.connect_ex = _guarded, _guarded_ex


@atexit.register
def _receipt() -> None:
    log = os.environ.get("R2_07_RECEIPT_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": "nonloopback_refused", "count": REFUSED["n"],
                                     "t_ns": time.monotonic_ns()}, sort_keys=True) + "\n")


sys.path.insert(0, str(R207))
import r2_07_launcher  # noqa: E402

if __name__ == "__main__":
    r2_07_launcher.main()

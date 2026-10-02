#!/usr/bin/env python3
"""x11_handshake.py <unix-socket-path>: open an X11 connection on a socket path and print the setup status.
Protocol-level reachability probe only (connection setup; no requests, no input). status 1 = accepted."""
import json, socket, struct, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(sys.argv[1])
    s.sendall(struct.pack("<BxHHHHxx", 0x6C, 11, 0, 0, 0))  # little-endian, protocol 11.0, no auth
    head = s.recv(8)
    status = head[0] if head else None
    print(json.dumps({"connected": True, "setup_status": status, "accepted": status == 1}))
    sys.exit(0 if status == 1 else 1)
except OSError as e:
    print(json.dumps({"connected": False, "error": f"{type(e).__name__}: {e.strerror or e}"}))
    sys.exit(2)

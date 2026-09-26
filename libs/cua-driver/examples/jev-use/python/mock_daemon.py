"""Mock cua-driver daemon for the Python keep-alive bench.

Speaks the daemon's newline-delimited JSON socket protocol so the bench
drives the REAL wire format: real serialization, real socket IPC, real
client-side handling of the visual payload. The driver itself is fake
(no browser), but every byte the observation path touches is real.

One-request-per-connection by default; --keep-alive drains every complete
request line in the buffer and keeps the connection open (mirrors
mock_daemon.mjs --keep-alive).

Only the three observation calls are served: get_browser_state (dom-complete
fixture shape), get_window_state, parse_visual_regions.

Usage:
  python3 mock_daemon.py --socket /tmp/cua-mock.sock --regions 50
  python3 mock_daemon.py --socket /tmp/cua-mock.sock --regions 50 --keep-alive

Auth simulation (for the #3383 auth-lifetime deep dive):
  --auth-ms N            artificial auth delay per auth event (simulates the
                         macOS accept-loop codesign verification)
  --auth-mode accept|request
                         accept: pay auth once per connection (today's model);
                         request: re-pay before every request (conservative,
                         what option (b) degrades to if per-connection verify
                         is TOCTOU-load-bearing)
  --auth-scope all|history
                         all: every call pays; history: only history_* methods
                         pay (option (a) scoping — the reporter's ask)
  --auth-cache           verify-once-per-connection: once a connection has paid
                         an auth event, subsequent in-scope requests skip
                         re-auth (the (a)+(b) hybrid prototype: history_*
                         calls skip RE-auth after the first verify)
  --auth-window-requests N
                         with --auth-cache: re-verify after N in-scope requests
                         since the last verify (0 = never)
  --auth-window-ms T     with --auth-cache: re-verify after T ms since the last
                         verify (0 = never)
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
import time
from typing import Any

PID = 4242
WINDOW_ID = 7

_capture_seq = 0


def _snapshot() -> dict[str, Any]:
    return {
        "target_id": "t",
        "tab_id": "tab",
        "refs": [
            {"role": "textbox", "name": "verification value", "ref": "r1", "value": "other"},
            {"role": "button", "name": "Submit", "ref": "r2"},
        ],
    }


def _visual_payload(capture_id: str, region_count: int) -> dict[str, Any]:
    regions = []
    for i in range(region_count):
        is_submit = i == 0
        # Keep every region inside the 1280x800 screenshot, mirroring the mjs daemon.
        x = 10 + ((i * 37) % 1150)
        y = 20 + ((i * 53) % 700)
        regions.append(
            {
                "id": f"v{i}",
                "kind": "text",
                "text": "Submit" if is_submit else f"Decoy label {i}",
                "confidence": 0.9 if is_submit else 0.5 + (i % 40) / 100,
                "interactive": True,
                "bounds": {"x": x, "y": y, "width": 80, "height": 30},
            }
        )
    return {
        "schema": "cua.visual_regions_v1",
        "capture": {
            "capture_id": capture_id,
            "source": {"kind": "window", "pid": PID, "window_id": WINDOW_ID},
            "screenshot": {
                "mime_type": "image/png",
                "reference": "sha256:bench",
                "width": 1280,
                "height": 800,
            },
            "action_coordinate_space": {"kind": "screenshot_pixels"},
        },
        "regions": regions,
    }


def _structured_content(request: dict[str, Any], region_count: int) -> dict[str, Any]:
    global _capture_seq
    name = request.get("name")
    args = request.get("args") or {}
    if name == "get_browser_state":
        return _snapshot()
    if name == "get_window_state":
        _capture_seq += 1
        return {"capture_id": f"cap-{_capture_seq}"}
    if name == "parse_visual_regions":
        return _visual_payload(str(args.get("capture_id")), region_count)
    if name == "history_record":
        # Dummy History-method stand-in for the auth-scope experiment.
        return {"recorded": True}
    return {"error": f"mock daemon has no handler for {name}"}


def _auth_applies(name: str | None, scope: str) -> bool:
    return scope == "all" or (isinstance(name, str) and name.startswith("history_"))


def _auth_event(path: str | None, conn_id: int, request: str | None) -> None:
    """Append one JSON line per auth event (bench observability; mock only)."""
    if not path:
        return
    try:
        with open(path, "a") as f:
            f.write(json.dumps({"conn": conn_id, "request": request, "t": time.monotonic()}) + "\n")
    except OSError:
        pass


async def _handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    region_count: int,
    keep_alive: bool,
    auth_ms: float,
    auth_mode: str,
    auth_scope: str,
    auth_cache: bool,
    auth_window_requests: int,
    auth_window_ms: float,
    auth_events: str | None,
    conn_id: int,
) -> None:
    verified = False  # per-connection: has this connection passed auth yet?
    verified_at = 0.0  # loop time of the last verify (for the time window)
    requests_since_verify = 0  # in-scope requests since the last verify
    try:
        if auth_ms > 0 and auth_mode == "accept" and _auth_applies(None, auth_scope):
            # accept-time auth: scope "all" pays once per connection;
            # scope "history" can't decide at accept time, so it defers to
            # per-request below (the honest model for option (a)).
            await asyncio.sleep(auth_ms / 1000.0)
            verified = True
            verified_at = asyncio.get_running_loop().time()
            _auth_event(auth_events, conn_id, None)
        while True:
            line = await reader.readline()
            if not line:
                return
            try:
                request = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                writer.write(json.dumps({"ok": False, "error": "bad json"}).encode() + b"\n")
                await writer.drain()
                return
            if auth_ms > 0:
                pay = False
                if auth_mode == "request":
                    pay = _auth_applies(request.get("name"), auth_scope)
                elif auth_scope == "history":
                    pay = _auth_applies(request.get("name"), auth_scope)
                if pay and auth_cache and verified:
                    # (a)+(b) hybrid with a bounded trust window: skip RE-auth
                    # only while the last verify is still "fresh". A request
                    # window caps exposure per connection burst; a time window
                    # caps exposure for idle connections (and bounds
                    # revocation propagation delay). Both 0 = verify once,
                    # trust forever (chunk-14 behavior).
                    now = asyncio.get_running_loop().time()
                    window_expired = (
                        (auth_window_requests > 0 and requests_since_verify >= auth_window_requests)
                        or (auth_window_ms > 0 and (now - verified_at) * 1000.0 >= auth_window_ms)
                    )
                    if not window_expired:
                        pay = False
                if pay:
                    await asyncio.sleep(auth_ms / 1000.0)
                    verified = True
                    verified_at = asyncio.get_running_loop().time()
                    requests_since_verify = 0
                    _auth_event(auth_events, conn_id, request.get("name"))
                elif _auth_applies(request.get("name"), auth_scope):
                    requests_since_verify += 1
            if request.get("method") == "metadata":
                payload: dict[str, Any] = {
                    "ok": True,
                    "result": {
                        "driver_version": "mock-0.0.0",
                        "contract_version": "0.8.0",
                        "embedded": False,
                    },
                }
            else:
                payload = {
                    "ok": True,
                    "result": {
                        "content": [{"type": "text", "text": "mock daemon"}],
                        "structuredContent": _structured_content(request, region_count),
                        "isError": False,
                    },
                }
            writer.write(json.dumps(payload).encode() + b"\n")
            await writer.drain()
            if not keep_alive:
                return
    finally:
        writer.close()


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--regions", type=int, default=50)
    parser.add_argument("--keep-alive", action="store_true")
    parser.add_argument("--auth-ms", type=float, default=0.0,
                        help="artificial auth delay per auth event, in ms")
    parser.add_argument("--auth-mode", choices=("accept", "request"), default="accept")
    parser.add_argument("--auth-scope", choices=("all", "history"), default="all")
    parser.add_argument("--auth-cache", action="store_true",
                        help="verify-once-per-connection: skip re-auth after the first auth event on a connection")
    parser.add_argument("--auth-window-requests", type=int, default=0,
                        help="with --auth-cache: re-verify after this many in-scope requests since the last verify "
                             "(0 = never; bounds per-connection-burst exposure)")
    parser.add_argument("--auth-window-ms", type=float, default=0.0,
                        help="with --auth-cache: re-verify after this many ms since the last verify "
                             "(0 = never; bounds idle-connection exposure and revocation delay)")
    parser.add_argument("--auth-events", default=None,
                        help="append one JSON line per auth event here (bench observability)")
    args = parser.parse_args()

    try:
        os.unlink(args.socket)
    except FileNotFoundError:
        pass

    conn_ids = itertools.count(1)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_connection(reader, writer, args.regions, args.keep_alive,
                                 args.auth_ms, args.auth_mode, args.auth_scope,
                                 args.auth_cache, args.auth_window_requests,
                                 args.auth_window_ms, args.auth_events,
                                 next(conn_ids))

    server = await asyncio.start_unix_server(handle, path=args.socket)
    print(f"ready {args.socket}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(_main())

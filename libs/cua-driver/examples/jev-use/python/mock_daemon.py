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
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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
    return {"error": f"mock daemon has no handler for {name}"}


async def _handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    region_count: int,
    keep_alive: bool,
) -> None:
    try:
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
    args = parser.parse_args()

    try:
        os.unlink(args.socket)
    except FileNotFoundError:
        pass

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_connection(reader, writer, args.regions, args.keep_alive)

    server = await asyncio.start_unix_server(handle, path=args.socket)
    print(f"ready {args.socket}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(_main())

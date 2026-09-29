#!/usr/bin/env python3
"""Capture the raw MCP ``initialize`` and ``tools/list`` responses of a Cua Driver binary (kvnloo/cua#76).

The bytes written are the server's response lines verbatim (no re-serialization), so byte counts
reflect what an MCP client actually receives on the stdio transport.

usage: capture_tools_list.py --driver BIN --label NAME --out-dir DIR [--env KEY=VALUE ...]
Run it in a scrubbed session (see cua-x11-session.sh): the Driver starts its platform runtime in `mcp`
mode and must not be pointed at a host desktop.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import subprocess
import threading
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--protocol-version", default="2025-06-18")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    for item in args.env:
        key, _, value = item.partition("=")
        env[key] = value
    lines: queue.Queue[bytes | None] = queue.Queue()
    proc = subprocess.Popen([args.driver, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, bufsize=0)
    assert proc.stdin is not None and proc.stdout is not None

    def reader() -> None:
        for line in iter(proc.stdout.readline, b""):  # type: ignore[union-attr]
            lines.put(line)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()

    def send(message: dict) -> None:
        proc.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def response_for(request_id: int, timeout: float = 60.0) -> bytes:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError("driver closed stdout")
            try:
                if json.loads(line).get("id") == request_id:
                    return line
            except ValueError:
                continue
        raise TimeoutError(f"no response for id {request_id}")

    started = time.perf_counter()
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": args.protocol_version, "capabilities": {},
        "clientInfo": {"name": "cua-issue-76-census", "version": "1"}}})
    init_raw = response_for(1)
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    pages: list[bytes] = []
    cursor = None
    request_id = 2
    while True:
        params = {"cursor": cursor} if cursor else {}
        send({"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": params})
        page = response_for(request_id)
        pages.append(page)
        cursor = json.loads(page).get("result", {}).get("nextCursor")
        request_id += 1
        if not cursor:
            break
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    proc.stdin.close()  # type: ignore[union-attr]
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=10)

    out = args.out_dir
    (out / f"{args.label}.initialize.response.json").write_bytes(init_raw)
    for index, page in enumerate(pages, start=1):
        (out / f"{args.label}.tools-list.page{index}.response.json").write_bytes(page)
    version = subprocess.run([args.driver, "--version"], capture_output=True, text=True).stdout.strip()
    meta = {
        "label": args.label,
        "driver": args.driver,
        "driver_sha256": hashlib.sha256(Path(args.driver).read_bytes()).hexdigest(),
        "driver_version": version,
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uname": " ".join(platform.uname()),
        "protocol_version_requested": args.protocol_version,
        "tools_list_pages": len(pages),
        "tools_list_wire_bytes": [len(page) for page in pages],
        "initialize_wire_bytes": len(init_raw),
        "handshake_and_list_ms": elapsed_ms,
        "env_overrides_names_only": sorted(item.partition("=")[0] for item in args.env),
        "cua_env_names_present": sorted(k for k in env if k.startswith("CUA_")),
        "display_set": bool(env.get("DISPLAY")),
        "wayland_display_set": bool(env.get("WAYLAND_DISPLAY")),
    }
    (out / f"{args.label}.meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: meta[k] for k in ("label", "driver_version", "tools_list_wire_bytes", "handshake_and_list_ms")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

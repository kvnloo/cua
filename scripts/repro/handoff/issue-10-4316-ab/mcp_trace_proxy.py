#!/usr/bin/env python3
"""Transparent stdio pass-through for ``cua-driver mcp`` that records the JSON-RPC conversation.

The jev-use runners start the Driver as ``$CUA_DRIVER_BIN mcp``. Point CUA_DRIVER_BIN at a tiny
wrapper that execs this proxy and every request/response that crosses the pipe is appended to a
trace file with monotonic timestamps. The proxy forwards bytes unchanged; it neither injects nor
filters a message. Image payloads are replaced by their length so traces stay small.

usage: mcp_trace_proxy.py --real /path/to/cua-driver --trace trace.jsonl [--] [driver args...]
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import threading
import time

T0_NS = time.perf_counter_ns()
_LOCK = threading.Lock()


def _redact(value):
    """Drop base64 image bytes; keep everything else (refs are opaque and needed as evidence)."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "data" and value.get("type") == "image" and isinstance(item, str):
                out[key] = f"<omitted {len(item)} chars>"
            elif isinstance(key, str) and ("png_b64" in key or "image_base64" in key) and isinstance(item, str):
                out[key] = f"<omitted {len(item)} chars>"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def record(trace, direction: str, raw: bytes) -> None:
    t_ns = time.perf_counter_ns() - T0_NS
    try:
        message = _redact(json.loads(raw))
        entry = {"t_ns": t_ns, "dir": direction, "msg": message}
    except Exception:
        entry = {"t_ns": t_ns, "dir": direction, "unparsed_bytes": len(raw)}
    line = json.dumps(entry, separators=(",", ":"))
    with _LOCK:
        trace.write(line + "\n")
        trace.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("driver_args", nargs="*")
    args = parser.parse_args()

    trace = open(args.trace, "a", encoding="utf-8")
    trace.write(json.dumps({"t_ns": 0, "dir": "proxy", "event": "start", "wall": time.time(), "mono_ns0": T0_NS}) + "\n")
    proc = subprocess.Popen(
        [args.real, *args.driver_args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        bufsize=0,
    )
    assert proc.stdin is not None and proc.stdout is not None
    child_stdin, child_stdout = proc.stdin, proc.stdout

    def _terminate(signum, _frame):
        try:
            proc.terminate()
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGINT, _terminate)

    def pump_stdin() -> None:
        stdin = sys.stdin.buffer
        try:
            while True:
                line = stdin.readline()
                if not line:
                    break
                record(trace, "c2s", line)
                child_stdin.write(line)
                child_stdin.flush()
        except (BrokenPipeError, ValueError):
            pass
        finally:
            try:
                child_stdin.close()
            except Exception:
                pass

    thread = threading.Thread(target=pump_stdin, daemon=True)
    thread.start()

    stdout = sys.stdout.buffer
    try:
        for line in iter(child_stdout.readline, b""):
            record(trace, "s2c", line)
            stdout.write(line)
            stdout.flush()
    except (BrokenPipeError, ValueError):
        pass
    rc = proc.wait()
    trace.write(json.dumps({"t_ns": time.perf_counter_ns() - T0_NS, "dir": "proxy", "event": "driver_exit", "rc": rc}) + "\n")
    trace.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

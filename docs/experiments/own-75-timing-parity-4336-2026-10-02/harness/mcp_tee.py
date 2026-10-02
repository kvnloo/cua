#!/usr/bin/python3
"""Transparent MCP stdio tee between a jev-use runner and the real Cua Driver (OWN-75 harness).

Used as CUA_DRIVER_BIN. It starts the real Driver (CUA_DRIVER_OWN75_REAL_BIN) with the same
arguments and an environment without its own two variables, forwards every newline-delimited
JSON-RPC line unchanged in both directions, and appends each line to CUA_DRIVER_OWN75_TRACE as
{"dir": "c2s"|"s2c", "seq": n, "msg": <parsed message>}. Strings longer than 2048 characters
(screenshot data) are recorded as {"_sha256", "_len"} in the trace only; the forwarded bytes are
never modified. Measurement harness only; never part of the product.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading

REAL = os.environ["CUA_DRIVER_OWN75_REAL_BIN"]
TRACE = os.environ["CUA_DRIVER_OWN75_TRACE"]
LOCK = threading.Lock()
SEQ = [0]


def shrink(value: object) -> object:
    if isinstance(value, str) and len(value) > 2048:
        return {"_sha256": hashlib.sha256(value.encode()).hexdigest(), "_len": len(value)}
    if isinstance(value, dict):
        return {key: shrink(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shrink(item) for item in value]
    return value


def record(direction: str, line: bytes) -> None:
    try:
        parsed = json.loads(line)
        result = parsed.get("result") if isinstance(parsed, dict) else None
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            # tools/list: keep the advertised names and a digest of the full listing only.
            canonical = json.dumps(result, sort_keys=True).encode()
            parsed = {**parsed, "result": {
                "_tool_names": sorted(t.get("name") for t in result["tools"] if isinstance(t, dict)),
                "_sha256": hashlib.sha256(canonical).hexdigest(), "_len": len(canonical)}}
        message: object = shrink(parsed)
    except ValueError:
        message = {"_unparsed_len": len(line)}
    with LOCK:
        SEQ[0] += 1
        with open(TRACE, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"dir": direction, "seq": SEQ[0], "msg": message}, sort_keys=True) + "\n")


def pump(source, sink, direction: str, close_sink: bool) -> None:
    for line in iter(source.readline, b""):
        if line.strip():
            record(direction, line)
        sink.write(line)
        sink.flush()
    if close_sink:
        sink.close()


def main() -> int:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CUA_DRIVER_OWN75_")}
    driver = subprocess.Popen([REAL, *sys.argv[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)

    def stop(signum: int, _frame: object) -> None:
        driver.terminate()  # the Driver this tee started, never anything else
        os._exit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    upstream = threading.Thread(
        target=pump, args=(sys.stdin.buffer, driver.stdin, "c2s", True), daemon=True
    )
    upstream.start()
    pump(driver.stdout, sys.stdout.buffer, "s2c", False)
    return driver.wait()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Arm A (READ-ONLY): one attempt through the unmodified jev-use CUA Driver browser route.

The caller path is the same one libs/cua-driver/examples/jev-use/python/run.py uses:
cua-driver MCP over stdio -> browser_prepare (isolated_new, Driver launches Chrome) ->
get_browser_state -> browser_navigate -> get_browser_state (semantic_v2). No model call.
It reads the fixture status text; it never clicks or types. Emits one cua.pomerado.trial.v1
receipt via arm_common (independent reset, /state + /audit oracle, no retry, no fallback).

Run it from the jev-use project (uv run --frozen python <this file> ...) so `mcp` is importable.
Credit: Pomerado is MIT (Pomerado AI, Inc.); opencli is jackwener/opencli.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "libs/cua-driver/examples/jev-use/python"))

from arm_common import (AttemptError, Invocation, add_common_args, append_receipt,  # noqa: E402
                        require_loopback, run_attempt, sha256_text, spec_from_args)


async def read_status(base: str, timeout: float, pids: list[int]) -> Invocation:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from driver_env import driver_environment
    from run import Driver, select_tab_id, wait_for_window

    params = StdioServerParameters(command=os.getenv("CUA_DRIVER_BIN", "cua-driver"),
                                   args=["mcp"], env=driver_environment())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            driver = Driver(session, f"ab-arm-a-{uuid.uuid4().hex[:8]}")
            prepared = await driver.call(
                "browser_prepare", {"allow_launch": True, "profile": {"mode": "isolated_new"}})
            pid = int(prepared["prepared_pid"])
            pids.append(pid)
            window = await wait_for_window(driver, pid)
            bound = await driver.call("get_browser_state",
                                      {"pid": pid, "window_id": window["window_id"]})
            target_id = bound["target_id"]
            tab_id = select_tab_id(bound["tabs"])
            await driver.call("browser_navigate",
                              {"target_id": target_id, "tab_id": tab_id, "url": base + "/"})
            snapshot = await driver.call(
                "get_browser_state",
                {"target_id": target_id, "tab_id": tab_id, "snapshot_format": "semantic_v2"})
    text = json.dumps(snapshot, sort_keys=True)
    evidence = f"cua-driver:read:browser_prepare+navigate+get_browser_state:snapshot={sha256_text(text)}"
    return Invocation(ok=True, output=snapshot, route_evidence=evidence)


def make_invoker(args, pids: list[int]):
    def invoke(base: str) -> Invocation:
        try:
            return asyncio.run(asyncio.wait_for(read_status(base, args.timeout, pids), args.timeout))
        except asyncio.TimeoutError:
            return Invocation(ok=False, route_evidence="cua-driver:read:timeout", detail="timeout")
        except Exception as error:  # recorded as blocked by run_attempt's judge
            return Invocation(ok=False, route_evidence=f"cua-driver:read:{type(error).__name__}",
                              detail=type(error).__name__)
    return invoke


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    args = parser.parse_args(argv)
    pids: list[int] = []
    try:
        if args.effect != "read":
            raise AttemptError("arm A runner is read-only")
        spec = spec_from_args(args, "A", {"driver_version": os.getenv("AB_DRIVER_VERSION", "")})
        receipt = run_attempt(spec, require_loopback(args.base, what="fixture base"),
                              make_invoker(args, pids))
    except AttemptError as error:
        print(json.dumps({"status": "REFUSED_NOT_RUN", "error": str(error)}), file=sys.stderr)
        return 2
    finally:
        for pid in pids:  # Chrome launched by this attempt only; cleanup is outside the timer
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    append_receipt(args.out, receipt)
    return 0 if receipt["oracle_outcome"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

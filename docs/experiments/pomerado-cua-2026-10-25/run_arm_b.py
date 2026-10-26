#!/usr/bin/env python3
"""Arm B glue: serve a minted Pomerado artifact and call its tool over MCP stdio; emit one receipt.

  pomerado-mcp serve --artifact DIR   (serving makes no model request)

The artifact is minted separately and needs its own budget and authority (PREREG:
BLOCKED_UNTIL_OWNER_APPROVES_BUDGET); this script never mints. Read attempts only
call a tool annotated readOnlyHint. It never answers provide_input and never
replays a tool call. Server spawn, handshake and call are all inside the timed window,
as are opencli's process start and CDP attach in arm C.
Credit: Pomerado is MIT (Pomerado AI, Inc.); opencli is jackwener/opencli.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
import uuid

from arm_common import (AttemptError, Invocation, add_common_args, append_receipt,
                        run_attempt, sha256_text, spec_from_args)
from mcp_stdio import McpError, McpStdioClient

HELPERS = {"mint", "get_job", "provide_input", "cancel_job"}


def structured(result: dict):
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except ValueError:
                return {"text": item["text"]}
    return None


def pick_tool(tools: list[dict], name: str | None, write: bool) -> dict:
    business = [t for t in tools if t.get("name") not in HELPERS]
    if name is None:
        if len(business) != 1:
            raise AttemptError(f"artifact exposes {len(business)} tools; pass --tool")
        tool = business[0]
    else:
        found = [t for t in business if t.get("name") == name]
        if not found:
            raise AttemptError(f"tool {name!r} not offered by artifact")
        tool = found[0]
    read_only = bool((tool.get("annotations") or {}).get("readOnlyHint"))
    if not write and not read_only:
        raise AttemptError("tool is not annotated readOnlyHint; refusing a read attempt")
    if write and read_only:
        raise AttemptError("a write attempt needs a non-read-only tool")
    return tool


def make_invoker(args, spec_value):
    cmd = shlex.split(args.pomerado_cmd)
    argv = [*cmd, "serve", "--artifact", args.artifact]
    if args.endpoint:
        argv += ["--endpoint", args.endpoint]
    try:
        tool_input = json.loads(args.tool_input)
    except ValueError as error:
        raise AttemptError("--tool-input must be JSON") from error
    if args.effect == "write":
        tool_input = {**tool_input, **({"value": spec_value} if "value" not in tool_input else {})}

    def invoke(base: str) -> Invocation:
        deadline = time.monotonic() + args.timeout
        left = lambda: max(deadline - time.monotonic(), 0.1)  # noqa: E731
        client = McpStdioClient(argv)
        trace = {"argv": sha256_text(" ".join(argv)), "calls": []}
        try:
            client.initialize(left())
            tools = client.request("tools/list", None, left()).get("tools", [])
            tool = pick_tool(tools, args.tool, args.effect == "write")
            trace["tool"] = tool["name"]
            arguments: dict = {"input": tool_input}
            if args.effect == "write":
                arguments["idempotency_key"] = str(uuid.uuid5(uuid.NAMESPACE_URL, args.block_id
                                                              + str(args.position)))
            result = client.request("tools/call", {"name": tool["name"], "arguments": arguments},
                                    left())
            trace["calls"].append("tools/call")
            body = structured(result)
            # A tool may answer with a job; observe it with get_job only, never re-call the tool.
            polls = 0
            def is_job(value):
                return isinstance(value, dict) and "job_id" in value and "status" in value

            while not result.get("isError") and is_job(body) \
                    and body["status"] not in ("completed", "failed"):
                if body["status"] in ("needs_input", "input_required", "waiting_for_input") \
                        or polls >= 20:
                    raise McpError(f"job not completed: {body['status']}")
                result = client.request("tools/call", {"name": "get_job", "arguments": {
                    "job_id": body["job_id"], "wait_seconds": 5}}, left())
                trace["calls"].append("get_job")
                body = structured(result)
                polls += 1
            digest = sha256_text(json.dumps(body, sort_keys=True))
            evidence = (f"pomerado-mcp:{args.effect}:tool={trace['tool']}:calls="
                        f"{','.join(trace['calls'])}:result={digest}:argv={trace['argv']}")
            failed = bool(result.get("isError")) or (is_job(body) and body["status"] == "failed")
            output = body.get("output") if is_job(body) else body
            return Invocation(ok=not failed, output=output, route_evidence=evidence,
                              detail="tool error" if failed else "")
        finally:
            client.close()

    return invoke


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--artifact", required=True, help="minted artifact directory")
    parser.add_argument("--pomerado-cmd", default="pomerado-mcp")
    parser.add_argument("--tool", help="integration tool name (default: the only non-helper tool)")
    parser.add_argument("--tool-input", default="{}", help="JSON object for the tool's `input`")
    parser.add_argument("--endpoint", help="native Playwright/CDP endpoint passed to pomerado-mcp")
    parser.add_argument("--expect", default="status=waiting",
                        help="text the read result must contain to be verified")
    args = parser.parse_args(argv)
    try:
        spec = spec_from_args(args, "B")
        receipt = run_attempt(spec, args.base, make_invoker(args, args.value), expect=args.expect)
    except AttemptError as error:
        print(json.dumps({"status": "REFUSED_NOT_RUN", "error": str(error)}), file=sys.stderr)
        return 2
    append_receipt(args.out, receipt)
    return 0 if receipt["oracle_outcome"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

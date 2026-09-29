#!/usr/bin/env python3
"""Capture and analyze Cua Driver MCP tools/list without estimating tokens.

Examples:

  python tools_list_census.py --capture --driver cua-driver --raw raw.json --report report.json
  python tools_list_census.py --input raw.json --report report.json

The report measures UTF-8 bytes only. It never estimates token counts.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = "2025-06-18"


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def read_response(process: subprocess.Popen[str], expected_id: int) -> tuple[dict[str, Any], bytes]:
    assert process.stdout is not None
    while True:
        line = process.stdout.readline()
        if line == "":
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise RuntimeError(f"MCP process ended before response {expected_id}: {stderr[-2000:]}")
        raw = line.encode()
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("id") == expected_id:
            return value, raw


def capture(driver: str, protocol_version: str) -> tuple[dict[str, Any], bytes]:
    process = subprocess.Popen(
        [driver, "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=os.environ.copy(),
    )
    assert process.stdin is not None
    try:
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "cua-tools-list-census", "version": "1"},
            },
        }
        process.stdin.write(json.dumps(initialize, separators=(",", ":")) + "\n")
        process.stdin.flush()
        init, _ = read_response(process, 1)
        if "error" in init:
            raise RuntimeError(f"MCP initialize failed: {init['error']}")

        process.stdin.write(
            '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n'
        )
        process.stdin.write(
            '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
        )
        process.stdin.flush()
        listed, raw = read_response(process, 2)
        if "error" in listed:
            raise RuntimeError(f"tools/list failed: {listed['error']}")
        return listed, raw
    finally:
        try:
            process.stdin.close()
        except Exception:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)


def tools_from(value: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(value.get("result"), dict):
        value = value["result"]
    tools = value.get("tools")
    if not isinstance(tools, list) or not all(isinstance(item, dict) for item in tools):
        raise ValueError("input is not an MCP tools/list result or response")
    return tools


def schema_bytes(value: Any) -> int:
    return len(compact(value)) if value is not None else 0


def top_level_property_duplicates(
    tools: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    groups: dict[bytes, list[tuple[str, str]]] = collections.defaultdict(list)
    for tool in tools:
        name = str(tool.get("name", ""))
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        for property_name, property_schema in properties.items():
            if isinstance(property_schema, dict):
                groups[compact(property_schema)].append((name, str(property_name)))

    rows: list[dict[str, Any]] = []
    duplicate_bytes = 0
    for blob, uses in groups.items():
        if len(uses) < 2:
            continue
        saved = (len(uses) - 1) * len(blob)
        duplicate_bytes += saved
        rows.append(
            {
                "sha256": hashlib.sha256(blob).hexdigest(),
                "schema_bytes": len(blob),
                "uses": len(uses),
                "duplicate_bytes": saved,
                "locations": [
                    {"tool": tool, "property": prop} for tool, prop in uses
                ],
            }
        )
    rows.sort(key=lambda row: (-row["duplicate_bytes"], -row["uses"], row["sha256"]))
    return duplicate_bytes, rows


def element_token_shapes(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for tool in tools:
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        token = properties.get("element_token")
        if isinstance(token, dict):
            rows.append(
                {
                    "tool": tool.get("name"),
                    "type": token.get("type"),
                    "pattern": token.get("pattern"),
                    "description_bytes": len(str(token.get("description", "")).encode()),
                }
            )
    return rows


def analyze(value: dict[str, Any], raw_wire_bytes: int | None) -> dict[str, Any]:
    tools = tools_from(value)
    tool_rows = []
    totals = {
        "input_schema_bytes": 0,
        "output_schema_bytes": 0,
        "description_bytes": 0,
        "annotations_bytes": 0,
    }
    for tool in tools:
        input_bytes = schema_bytes(tool.get("inputSchema"))
        output_bytes = schema_bytes(tool.get("outputSchema"))
        description_bytes = len(str(tool.get("description", "")).encode())
        annotations_bytes = schema_bytes(tool.get("annotations"))
        total_bytes = len(compact(tool))
        totals["input_schema_bytes"] += input_bytes
        totals["output_schema_bytes"] += output_bytes
        totals["description_bytes"] += description_bytes
        totals["annotations_bytes"] += annotations_bytes
        tool_rows.append(
            {
                "name": tool.get("name"),
                "serialized_bytes": total_bytes,
                "input_schema_bytes": input_bytes,
                "output_schema_bytes": output_bytes,
                "description_bytes": description_bytes,
                "annotations_bytes": annotations_bytes,
            }
        )

    duplicate_bytes, duplicate_groups = top_level_property_duplicates(tools)
    result_obj = value.get("result") if isinstance(value.get("result"), dict) else value

    return {
        "measurement": {
            "unit": "utf8_bytes",
            "token_estimate": None,
            "raw_tools_list_response_bytes": raw_wire_bytes,
            "canonical_result_bytes": len(compact(result_obj)),
            "canonical_tools_array_bytes": len(compact(tools)),
            "tool_count": len(tools),
            **totals,
            "exact_duplicate_top_level_input_property_bytes": duplicate_bytes,
        },
        "largest_tools": sorted(
            tool_rows, key=lambda row: (-row["serialized_bytes"], str(row["name"]))
        )[:15],
        "largest_exact_duplicate_top_level_input_properties": duplicate_groups[:20],
        "element_token_input_shapes": element_token_shapes(tools),
        "methodology": {
            "canonical_json": "UTF-8, sorted object keys, separators=(',', ':')",
            "duplicate_scope": (
                "byte-identical top-level inputSchema.properties entries only; "
                "nested overlapping fragments are intentionally not double-counted"
            ),
            "tokens": "not estimated; run a real tokenizer separately if installed",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--capture", action="store_true")
    source.add_argument("--input", type=Path)
    parser.add_argument("--driver", default="cua-driver")
    parser.add_argument("--protocol-version", default=DEFAULT_PROTOCOL)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    raw_wire_bytes: int | None
    if args.capture:
        value, raw = capture(args.driver, args.protocol_version)
        raw_wire_bytes = len(raw)
        if args.raw:
            args.raw.parent.mkdir(parents=True, exist_ok=True)
            args.raw.write_bytes(raw)
    else:
        raw = args.input.read_bytes()
        raw_wire_bytes = len(raw)
        value = json.loads(raw)

    report = analyze(value, raw_wire_bytes)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)


if __name__ == "__main__":
    main()

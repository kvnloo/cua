"""Dump the live MCP tools/list input schemas of a cua-driver binary (no display needed).

usage: python dump_tools_list.py <driver> <out.json>
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TOOLS = ("click", "double_click", "right_click", "scroll", "set_value", "drag", "type_text", "get_window_state")


async def main(driver: str, out: str) -> None:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "TMPDIR", "LANG", "XDG_RUNTIME_DIR")}
    env["CUA_DRIVER_RS_TELEMETRY_ENABLED"] = "0"
    params = StdioServerParameters(command=driver, args=["mcp"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.list_tools()
    tools = {}
    for t in res.tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
        tools[t.name] = schema
    sel = {name: tools.get(name) for name in TOOLS}
    summary = {name: sorted((tools.get(name) or {}).get("properties", {}).keys()) if tools.get(name) else None
               for name in TOOLS}
    json.dump({"driver": os.path.basename(driver), "tool_count": len(tools), "properties": summary,
               "input_schemas": sel}, open(out, "w"), indent=1, sort_keys=True)
    print(json.dumps(summary, indent=1))


asyncio.run(main(sys.argv[1], sys.argv[2]))

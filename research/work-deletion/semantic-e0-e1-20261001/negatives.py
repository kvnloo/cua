"""Re-check stale and foreign-session refusals using both result envelopes."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

JEV = Path("/mnt/zer0models/github/cua-lanes/p0-4316-v3/libs/cua-driver/examples/jev-use")
sys.path.insert(0, str(JEV))
sys.path.insert(0, str(JEV / "python"))
from driver_env import driver_environment  # noqa: E402
from fixture_server import FixtureServer  # noqa: E402


def digest(result) -> dict:
    structured = getattr(result, "structuredContent", None)
    structured = structured if isinstance(structured, dict) else {}
    text = []
    for item in getattr(result, "content", None) or []:
        value = getattr(item, "text", None)
        if isinstance(value, str):
            text.append(value[:240])
    error = structured.get("error") if isinstance(structured.get("error"), dict) else {}
    refusal = structured.get("refusal") if isinstance(structured.get("refusal"), dict) else {}
    return {
        "is_error": bool(getattr(result, "isError", False)),
        "effect": structured.get("effect"),
        "status": structured.get("status"),
        "route": structured.get("route"),
        "code": structured.get("code") or error.get("code") or refusal.get("code"),
        "error_keys": sorted(error.keys()),
        "refusal_keys": sorted(refusal.keys()),
        "structured_keys": sorted(structured.keys()),
        "text": " ".join(text)[:300],
    }


async def main() -> None:
    server = FixtureServer(("127.0.0.1", 0))
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    label = "negative-owner"
    params = StdioServerParameters(
        command=os.environ["CUA_DRIVER_BIN"], args=["mcp"], env=driver_environment()
    )
    out = {}
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def call(name, args, session_label=label):
                    return digest(await session.call_tool(name, {**args, "session": session_label}))

                prepared = await session.call_tool(
                    "browser_prepare",
                    {"allow_launch": True, "profile": {"mode": "isolated_new"}, "session": label},
                )
                prepared_s = prepared.structuredContent
                pid = int(prepared_s["prepared_pid"])
                window = None
                for _ in range(40):
                    listed = await session.call_tool("list_windows", {"pid": pid, "session": label})
                    windows = (listed.structuredContent or {}).get("windows") or []
                    visible = [item for item in windows if item.get("is_on_screen")]
                    if visible:
                        window = max(visible, key=lambda item: item["bounds"]["width"] * item["bounds"]["height"])
                        break
                    await asyncio.sleep(0.25)
                if window is None:
                    raise RuntimeError("no window")
                bound = await session.call_tool(
                    "get_browser_state",
                    {"pid": pid, "window_id": window["window_id"], "session": label},
                )
                target_id = bound.structuredContent["target_id"]
                tabs = bound.structuredContent["tabs"]
                tab_id = str(next((tab for tab in tabs if tab.get("active")), tabs[0])["tab_id"])
                base = {"target_id": target_id, "tab_id": tab_id}
                await call("browser_navigate", {**base, "url": url})
                snap = await session.call_tool(
                    "get_browser_state",
                    {**base, "snapshot_format": "semantic_v2", "session": label},
                )
                button = next(
                    item for item in snap.structuredContent["refs"] if item.get("role") == "button"
                )
                ref = button["ref"]
                out["fresh"] = await call(
                    "browser_click",
                    {**base, "ref": ref, "input_route": "dom_event"},
                )
                out["about_blank"] = await call("browser_navigate", {**base, "url": "about:blank"})
                out["after_about_blank"] = await call(
                    "browser_click",
                    {**base, "ref": ref, "input_route": "dom_event"},
                )
                await call("browser_navigate", {**base, "url": url})
                out["after_renavigate"] = await call(
                    "browser_click",
                    {**base, "ref": ref, "input_route": "dom_event"},
                )
                snap2 = await session.call_tool(
                    "get_browser_state",
                    {**base, "snapshot_format": "semantic_v2", "session": label},
                )
                button2 = next(
                    item for item in snap2.structuredContent["refs"] if item.get("role") == "button"
                )
                out["foreign"] = await call(
                    "browser_click",
                    {**base, "ref": button2["ref"], "input_route": "dom_event"},
                    session_label="foreign-not-owner",
                )
                out["owner_rebind"] = await call(
                    "browser_click",
                    {**base, "ref": button2["ref"], "input_route": "dom_event"},
                )
                out["refs"] = {"first": ref, "second": button2["ref"], "same": ref == button2["ref"]}
    finally:
        server.shutdown()
    path = Path(sys.argv[1])
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

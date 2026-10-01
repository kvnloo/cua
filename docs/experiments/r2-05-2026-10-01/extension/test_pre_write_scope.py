"""Post-verification extension (UNIT): scope of the SDK "pre-write" signal.

Not part of the pre-registered harness (PREREG.json hashes harness/ only).
Added after a blind verifier showed that, in mcp 1.30.0, the error CLASS raised
by ClientSession.call_tool is not by itself a pre-write proof:

    call_tool -> send_request (write ok, tool runs, response arrives)
              -> _validate_tool_result -> name not in _tool_output_schemas
              -> list_tools() -> _write_stream.send on a closed stream
              -> ClosedResourceError AFTER the effect landed.

Three cases against an in-memory FastMCP server whose tool counts its effect:
  A  cache miss, write stream closed before the response is delivered
     -> ClosedResourceError with effect 1 (class name is NOT a pre-write proof)
  B  cache hit (list_tools first), same fault -> no error, effect 1
  C  cache hit, write stream closed before the request (the RA shape)
     -> ClosedResourceError with effect 0 (the request's own write raised)

Run with the jev-use venv:  python -m unittest test_pre_write_scope
"""

from __future__ import annotations

import unittest

import anyio
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_client_server_memory_streams


async def run_case(prelist: bool, close_before_request: bool) -> tuple[str, int]:
    effects = {"n": 0}
    server = FastMCP("scope-probe")

    @server.tool()
    def browser_click(ref: str) -> dict:
        effects["n"] += 1
        return {"route": "dom"}

    async with create_client_server_memory_streams() as (client, srv):
        real_read, real_write = client
        cw_send, cw_recv = anyio.create_memory_object_stream(0)
        cr_send, cr_recv = anyio.create_memory_object_stream(0)
        state: dict = {"armed": False, "call_id": None}

        async def c2s() -> None:
            async for message in cw_recv:
                root = message.message.root
                if getattr(root, "method", None) == "tools/call":
                    state["call_id"] = root.id
                await real_write.send(message)

        async def s2c() -> None:
            async for message in real_read:
                root = getattr(getattr(message, "message", None), "root", None)
                is_call_response = (state["armed"] and getattr(root, "method", None) is None
                                    and getattr(root, "id", None) == state["call_id"])
                if is_call_response:
                    cw_send.close()            # session write stream closed, as after EOF
                    await cr_send.send(message)  # the tools/call response still arrives
                    await cr_send.aclose()       # then EOF
                    return
                await cr_send.send(message)

        error = "none"
        async with anyio.create_task_group() as tg:
            init = server._mcp_server.create_initialization_options()
            tg.start_soon(lambda: server._mcp_server.run(srv[0], srv[1], init))
            tg.start_soon(c2s)
            tg.start_soon(s2c)
            try:
                async with ClientSession(cr_recv, cw_send) as session:
                    await session.initialize()
                    if prelist:
                        await session.list_tools()
                    if close_before_request:
                        cw_send.close()
                    else:
                        state["armed"] = True
                    try:
                        with anyio.fail_after(10):
                            await session.call_tool("browser_click", {"ref": "r"})
                    except BaseException as exc:  # noqa: BLE001 - classify like the runner
                        error = type(exc).__name__
            except BaseException as exc:  # noqa: BLE001
                if error == "none":
                    error = f"outer:{type(exc).__name__}"
            tg.cancel_scope.cancel()
    return error, effects["n"]


class PreWriteScope(unittest.TestCase):
    def test_a_cache_miss_closed_after_write_is_not_pre_write(self) -> None:
        error, applied = anyio.run(run_case, False, False)
        print(f"A cache_miss close_after_write: error={error} effects_applied={applied}")
        self.assertEqual((error, applied), ("ClosedResourceError", 1))

    def test_b_cache_hit_closed_after_write_has_no_error(self) -> None:
        error, applied = anyio.run(run_case, True, False)
        print(f"B cache_hit close_after_write: error={error} effects_applied={applied}")
        self.assertEqual((error, applied), ("none", 1))

    def test_c_cache_hit_closed_before_request_is_pre_write(self) -> None:
        error, applied = anyio.run(run_case, True, True)
        print(f"C cache_hit close_before_request: error={error} effects_applied={applied}")
        self.assertEqual((error, applied), ("ClosedResourceError", 0))


if __name__ == "__main__":
    unittest.main()

"""Fault seam on the real MCP stdio transport (OWN-105; from R2-05).

Copied from the R2-05 packet (``r2-05-2026-10-01/harness/fault_transport.py``,
sha256 6f32e4c1...). Additions: ``read_error`` mode, a ``probe`` callable that
records the target journal counts when a fault fires, and a ``session_start``
event per transport (a reconsideration opens a second one). The barrier wait is
injected by the caller (an HTTP call to the harness control server when the
runner runs in a child process).

``fault_stdio_client`` wraps the SDK's real ``mcp.client.stdio.stdio_client``:
the real ``cua-driver mcp`` child process and its stdio pipes carry every byte.
The seam sits between ``ClientSession`` and the SDK stdio streams and relays
JSON-RPC messages unchanged, except at one pre-registered fault point:

``none``          pure relay.
``pre_dispatch``  when the Driver's response to the first semantic snapshot after
                  a successful ``browser_type`` arrives, close the session's write
                  stream (exactly what the SDK's receive loop does on EOF), deliver
                  that response, then send EOF. The caller's next request (the
                  Submit click) fails inside the SDK write call, before it reaches
                  the transport.
``request_lost``  take the Submit ``browser_click`` request from the session (the
                  SDK write call returns normally), do not forward it, send EOF.
``ack_lost``      forward the Submit click; when the Driver's response arrives,
                  hold it until the target journal reaches ``barrier_kind``
                  (``applied`` or ``received``), drop it, send EOF.
``read_error``    deliver the Submit click's response; forward the next semantic
                  ``get_browser_state`` request to the Driver and replace its real
                  response with a tool error result (``isError``, no structured
                  content), so the runner's read raises ``DriverToolError``.

EOF on the caller-facing read stream is what the SDK sees when the Driver's
stdout closes: its receive loop fails every pending request with
``McpError(CONNECTION_CLOSED)`` and closes the session write stream.

The seam journal is content-free: direction, JSON-RPC id, method, tool name,
selected argument keys, whitelisted scalar result fields and monotonic times.
"""

from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

import anyio
from mcp.client.stdio import stdio_client as real_stdio_client
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCResponse

RESULT_FIELDS = ("status", "route", "input_route", "effect", "delivery", "producer",
                 "acted_path", "post_dispatch_observation", "verification")


@dataclass
class FaultPlan:
    mode: str = "none"  # none | pre_dispatch | request_lost | ack_lost | read_error
    barrier_kind: str | None = None  # applied | received (ack_lost only)
    barrier_wait: Callable[[str, float], bool] | None = None
    barrier_timeout_s: float = 20.0
    probe: Callable[[], dict[str, Any]] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    fired: bool = False
    t0: int = field(default_factory=time.monotonic_ns)

    def log(self, kind: str, **fields: Any) -> None:
        self.events.append({"kind": kind, "t_ms": round((time.monotonic_ns() - self.t0) / 1e6, 3), **fields})


def _root(message: Any) -> Any:
    return getattr(getattr(message, "message", None), "root", None)


def _describe_request(root: Any) -> dict[str, Any]:
    params = getattr(root, "params", None) or {}
    out: dict[str, Any] = {"id": getattr(root, "id", None), "method": getattr(root, "method", None)}
    if out["method"] == "tools/call":
        out["tool"] = params.get("name")
        args = params.get("arguments") or {}
        out["arg_keys"] = sorted(args)
        if "snapshot_format" in args:
            out["snapshot_format"] = args["snapshot_format"]
        if "input_route" in args:
            out["input_route"] = args["input_route"]
    return out


def _describe_response(root: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"id": getattr(root, "id", None)}
    error = getattr(root, "error", None)
    if error is not None:
        out["jsonrpc_error_code"] = getattr(error, "code", None)
        return out
    result = getattr(root, "result", None) or {}
    out["is_error"] = bool(result.get("isError"))
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        picked = {}
        for key in RESULT_FIELDS:
            value = structured.get(key)
            if isinstance(value, (bool, int, float)) or (isinstance(value, str) and len(value) <= 64):
                picked[key] = value
        out["structured"] = picked
    return out


@asynccontextmanager
async def fault_stdio_client(params: Any, plan: FaultPlan, errlog: Any = sys.stderr):
    async with real_stdio_client(params, errlog) as (real_read, real_write):
        cw_send, cw_recv = anyio.create_memory_object_stream(0)  # session -> seam
        cr_send, cr_recv = anyio.create_memory_object_stream(0)  # seam -> session
        pending: dict[Any, dict[str, Any]] = {}
        state = {"typed_ok": False, "click_id": None, "click_delivered": False, "eof": False}
        plan.log("session_start")

        def probe() -> dict[str, Any] | None:
            try:
                return plan.probe() if plan.probe is not None else None
            except Exception as error:  # noqa: BLE001 - a failed probe is recorded, not fatal
                return {"probe_error": type(error).__name__}

        async def eof(reason: str) -> None:
            if not state["eof"]:
                state["eof"] = True
                plan.log("caller_eof", reason=reason)
                await cr_send.aclose()

        async def c2s() -> None:
            async for message in cw_recv:
                root = _root(message)
                if getattr(root, "method", None) is not None and getattr(root, "id", None) is not None:
                    desc = _describe_request(root)
                    pending[desc["id"]] = desc
                    is_submit = desc.get("tool") == "browser_click" and state["typed_ok"]
                    if plan.mode == "request_lost" and is_submit and not plan.fired:
                        plan.fired = True
                        plan.log("request_taken_not_forwarded", **desc,
                                 journal=await anyio.to_thread.run_sync(probe))
                        await eof("request_lost")
                        return
                    if is_submit:
                        state["click_id"] = desc["id"]
                    plan.log("forwarded_request", **desc)
                else:
                    plan.log("forwarded_other", method=getattr(root, "method", None))
                await real_write.send(message)

        async def s2c() -> None:
            async for message in real_read:
                if isinstance(message, Exception):
                    plan.log("transport_exception", type=type(message).__name__)
                    if not state["eof"]:
                        await cr_send.send(message)
                    continue
                root = _root(message)
                rid = getattr(root, "id", None)
                req = pending.pop(rid, None) if getattr(root, "method", None) is None else None
                if req is None:
                    if not state["eof"]:
                        await cr_send.send(message)
                    continue
                desc = _describe_response(root)
                desc["for_tool"] = req.get("tool") or req.get("method")
                if req.get("tool") == "browser_type" and not desc.get("is_error") and "jsonrpc_error_code" not in desc:
                    state["typed_ok"] = True
                if (
                    plan.mode == "pre_dispatch" and not plan.fired and state["typed_ok"]
                    and req.get("tool") == "get_browser_state" and req.get("snapshot_format") == "semantic_v2"
                ):
                    plan.fired = True
                    # Same state the SDK reaches after EOF: session write stream closed.
                    cw_send.close()
                    plan.log("session_write_stream_closed_before_next_request", after=desc,
                             journal=await anyio.to_thread.run_sync(probe))
                    await cr_send.send(message)
                    await eof("pre_dispatch")
                    continue
                if plan.mode == "ack_lost" and not plan.fired and rid == state["click_id"]:
                    plan.fired = True
                    plan.log("driver_response_held", **desc)
                    reached = False
                    if plan.barrier_wait is not None and plan.barrier_kind:
                        reached = await anyio.to_thread.run_sync(
                            plan.barrier_wait, plan.barrier_kind, plan.barrier_timeout_s
                        )
                    plan.log("target_barrier", barrier=plan.barrier_kind, reached=reached,
                             journal=await anyio.to_thread.run_sync(probe))
                    plan.log("driver_response_dropped", id=rid)
                    await eof("ack_lost")
                    continue
                if (
                    plan.mode == "read_error" and not plan.fired and state["click_delivered"]
                    and req.get("tool") == "get_browser_state" and req.get("snapshot_format") == "semantic_v2"
                ):
                    plan.fired = True
                    plan.log("read_error_injected", replaced=desc, journal=await anyio.to_thread.run_sync(probe))
                    injected = JSONRPCResponse(jsonrpc="2.0", id=rid, result={
                        "isError": True, "content": [{"type": "text", "text": "injected read failure"}]})
                    if not state["eof"]:
                        await cr_send.send(SessionMessage(message=JSONRPCMessage(injected)))
                    continue
                if rid == state["click_id"]:
                    state["click_delivered"] = True
                plan.log("delivered_response", **desc)
                if not state["eof"]:
                    await cr_send.send(message)

        async with anyio.create_task_group() as tg:
            tg.start_soon(c2s)
            tg.start_soon(s2c)
            try:
                yield cr_recv, cw_send
            finally:
                plan.log("seam_exit")
                tg.cancel_scope.cancel()

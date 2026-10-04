"""R2-05 / R2-07 fault seam on the real MCP stdio transport, re-pointed at action 2 of a two-click task.

Derived from the R2-07 ``fault_transport.py`` (copied by path, unchanged, under
harness/src/r2-10-composition-2026-10-02/harness/src/r2-07-2026-10-02/harness/). The relay, the
EOF semantics and the content-free seam journal are unchanged. The only change is WHICH request
is the fault point: R2-07 targeted the Submit ``browser_click`` after a successful
``browser_type``; toggle->confirm and modal->act are two clicks, so the fault point is the
``browser_click`` request sent after ``after_clicks`` (default 1) successful ``browser_click``
responses, i.e. action 2 (Confirm / Confirm choice). Only ``ack_lost`` is used by this lane:
forward the action-2 click; when the Driver's response arrives, hold it until the target journal
reaches ``barrier_kind`` (``applied`` or ``received``), drop it, send EOF. The SDK then fails the
pending request with ``McpError(CONNECTION_CLOSED)`` exactly as when the Driver's stdout closes.
"""

from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

import anyio
from mcp.client.stdio import stdio_client as real_stdio_client

import fault_transport as base  # R2-07 seam helpers (_root, _describe_request, _describe_response)


@dataclass
class FaultPlan:
    mode: str = "ack_lost"
    barrier_kind: str | None = None  # applied | received
    barrier_wait: Callable[[str, float], bool] | None = None
    barrier_timeout_s: float = 20.0
    after_clicks: int = 1
    events: list[dict[str, Any]] = field(default_factory=list)
    fired: bool = False
    t0: int = field(default_factory=time.monotonic_ns)

    def log(self, kind: str, **fields: Any) -> None:
        self.events.append({"kind": kind, "t_ms": round((time.monotonic_ns() - self.t0) / 1e6, 3), **fields})


@asynccontextmanager
async def fault_stdio_client(params: Any, plan: FaultPlan, errlog: Any = sys.stderr):
    if plan.mode != "ack_lost":
        raise ValueError("this lane uses only ack_lost")
    async with real_stdio_client(params, errlog) as (real_read, real_write):
        cw_send, cw_recv = anyio.create_memory_object_stream(0)  # session -> seam
        cr_send, cr_recv = anyio.create_memory_object_stream(0)  # seam -> session
        pending: dict[Any, dict[str, Any]] = {}
        state = {"clicks_ok": 0, "target_id": None, "eof": False}

        async def eof(reason: str) -> None:
            if not state["eof"]:
                state["eof"] = True
                plan.log("caller_eof", reason=reason)
                await cr_send.aclose()

        async def c2s() -> None:
            async for message in cw_recv:
                root = base._root(message)
                if getattr(root, "method", None) is not None and getattr(root, "id", None) is not None:
                    desc = base._describe_request(root)
                    pending[desc["id"]] = desc
                    if (desc.get("tool") == "browser_click" and state["clicks_ok"] >= plan.after_clicks
                            and state["target_id"] is None and not plan.fired):
                        state["target_id"] = desc["id"]
                        desc = {**desc, "fault_point": True}
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
                root = base._root(message)
                rid = getattr(root, "id", None)
                req = pending.pop(rid, None) if getattr(root, "method", None) is None else None
                if req is None:
                    if not state["eof"]:
                        await cr_send.send(message)
                    continue
                desc = base._describe_response(root)
                desc["for_tool"] = req.get("tool") or req.get("method")
                if rid == state["target_id"] and not plan.fired:
                    plan.fired = True
                    plan.log("driver_response_held", **desc)
                    reached = False
                    if plan.barrier_wait is not None and plan.barrier_kind:
                        reached = await anyio.to_thread.run_sync(plan.barrier_wait, plan.barrier_kind,
                                                                 plan.barrier_timeout_s)
                    plan.log("target_barrier", barrier=plan.barrier_kind, reached=reached)
                    plan.log("driver_response_dropped", id=rid)
                    await eof("ack_lost")
                    continue
                if (req.get("tool") == "browser_click" and not desc.get("is_error")
                        and "jsonrpc_error_code" not in desc
                        and (desc.get("structured") or {}).get("effect") != "refused"):
                    state["clicks_ok"] += 1
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

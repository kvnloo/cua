"""Refusal injection on the real MCP stdio transport (FIX-02 row F3).

Built on the R2-07/R2-05 fault seam (``harness/r2-07/fault_transport.py``, copied by path from
2d71548b4 and imported unchanged for its message helpers and journal). The real ``cua-driver mcp``
child process and its stdio pipes carry every byte; the seam relays JSON-RPC messages unchanged
except for the FIRST Submit ``browser_click`` (the first browser_click after a successful
browser_type), where it answers with an injected refusal result:

``pre``   the click request is NOT forwarded to the Driver; the caller receives the injected
          refusal instead. Nothing reaches the page (pre-dispatch refusal).
``post``  the click request IS forwarded; the Driver dispatches it and the page applies it. When
          the Driver's response arrives it is dropped and the injected refusal is delivered in
          its place (a refusal after dispatch: the effect landed, delivery is "unknown" to the
          caller).

Injected results use the Driver's own wire shapes:
``browser_ref_stale``                 action projection (``effect: refused``, ``route: dom``) with the
                                      stable ``refused (<code>): ...`` text, as browser_click returns it
``browser_input_trust_unavailable``   action projection (``effect: refused``, ``route: trusted_input``)
                                      with the Driver's exact delivery-unknown message (tools.rs)
``browser_reconnect_exhausted``       the Driver's refusal envelope (``status: refused`` +
                                      ``refusal.detail.retryable: false``, engine.rs) - the shape
                                      in which ``retryable`` is visible to a caller

The seam journal stays content-free (fault_transport's describers).
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE.parent / "r2-07") not in sys.path:
    sys.path.insert(0, str(HERE.parent / "r2-07"))

import anyio  # noqa: E402
import fault_transport as ft  # noqa: E402  (unchanged R2-07 seam: helpers + FaultPlan journal)
from mcp.client.stdio import stdio_client as real_stdio_client  # noqa: E402
from mcp.shared.message import SessionMessage  # noqa: E402
from mcp.types import JSONRPCMessage, JSONRPCResponse  # noqa: E402

TRUST_UNKNOWN_MESSAGE = (
    "trusted click was acknowledged but CDP focus emulation could not be restored "
    "(injected); delivery is unknown and must not be retried automatically"
)

INJECTIONS: dict[str, dict[str, Any]] = {
    "stale": {
        "where": "pre",
        "code": "browser_ref_stale",
        "result": {
            "content": [{"type": "text", "text": "refused (browser_ref_stale): the ref's node is no longer "
                                                 "connected to the document; nothing was dispatched"}],
            "structuredContent": {"effect": "refused", "route": "dom"},
            "isError": False,
        },
    },
    "trust_unknown": {
        "where": "post",
        "code": "browser_input_trust_unavailable",
        "result": {
            "content": [{"type": "text",
                         "text": f"refused (browser_input_trust_unavailable): {TRUST_UNKNOWN_MESSAGE}"}],
            "structuredContent": {"effect": "refused", "route": "trusted_input"},
            "isError": False,
        },
    },
    "not_retryable": {
        "where": "pre",
        "code": "browser_reconnect_exhausted",
        "result": {
            "content": [{"type": "text", "text": "refused (browser_reconnect_exhausted): the bounded "
                                                 "existing-profile reconnect attempts did not establish "
                                                 "a proven browser socket"}],
            "structuredContent": {
                "status": "refused",
                "refusal": {
                    "code": "browser_reconnect_exhausted",
                    "message": "the bounded existing-profile reconnect attempts did not establish a "
                               "proven browser socket",
                    "detail": {"attempt_limit": 3, "last_error": "connection_failed", "retryable": False},
                },
            },
            "isError": False,
        },
    },
}


def _response(request_id: Any, result: dict[str, Any]) -> SessionMessage:
    return SessionMessage(JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)))


@asynccontextmanager
async def refusal_stdio_client(params: Any, plan: ft.FaultPlan, injection: str | None, errlog: Any = sys.stderr):
    """``plan.mode`` is informational here; ``injection`` selects INJECTIONS[...] or None (relay)."""
    spec = INJECTIONS.get(injection) if injection else None
    async with real_stdio_client(params, errlog) as (real_read, real_write):
        cw_send, cw_recv = anyio.create_memory_object_stream(0)  # session -> seam
        cr_send, cr_recv = anyio.create_memory_object_stream(0)  # seam -> session
        pending: dict[Any, dict[str, Any]] = {}
        state = {"typed_ok": False, "post_id": None}

        async def c2s() -> None:
            async for message in cw_recv:
                root = ft._root(message)
                if getattr(root, "method", None) is not None and getattr(root, "id", None) is not None:
                    desc = ft._describe_request(root)
                    pending[desc["id"]] = desc
                    is_submit = desc.get("tool") == "browser_click" and state["typed_ok"]
                    if spec and is_submit and not plan.fired:
                        plan.fired = True
                        if spec["where"] == "pre":
                            pending.pop(desc["id"], None)
                            plan.log("click_not_forwarded_refusal_injected", code=spec["code"], **desc)
                            await cr_send.send(_response(desc["id"], spec["result"]))
                            continue
                        state["post_id"] = desc["id"]
                        plan.log("click_forwarded_refusal_will_replace_response", code=spec["code"], **desc)
                    plan.log("forwarded_request", **desc)
                else:
                    plan.log("forwarded_other", method=getattr(root, "method", None))
                await real_write.send(message)

        async def s2c() -> None:
            async for message in real_read:
                if isinstance(message, Exception):
                    plan.log("transport_exception", type=type(message).__name__)
                    await cr_send.send(message)
                    continue
                root = ft._root(message)
                rid = getattr(root, "id", None)
                req = pending.pop(rid, None) if getattr(root, "method", None) is None else None
                if req is None:
                    await cr_send.send(message)
                    continue
                desc = ft._describe_response(root)
                desc["for_tool"] = req.get("tool") or req.get("method")
                if req.get("tool") == "browser_type" and not desc.get("is_error") and "jsonrpc_error_code" not in desc:
                    state["typed_ok"] = True
                if spec and rid is not None and rid == state["post_id"]:
                    plan.log("driver_response_replaced_by_refusal", driver=desc, code=spec["code"])
                    await cr_send.send(_response(rid, spec["result"]))
                    continue
                plan.log("delivered_response", **desc)
                await cr_send.send(message)

        async with anyio.create_task_group() as tg:
            tg.start_soon(c2s)
            tg.start_soon(s2c)
            try:
                yield cr_recv, cw_send
            finally:
                plan.log("seam_exit")
                tg.cancel_scope.cancel()

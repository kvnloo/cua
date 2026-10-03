"""B-07 caller-side MCP stdio harness (MEASUREMENT HARNESS ONLY, caller side).

Derived from B-05's ``b05_stdio.py`` (harness/b05/, byte-identical copy from a91a86a4a). In the
default arms (``STAMP["prep"] == STAMP["route"] == "default"``) the client does exactly what
B-05's stamped mcp 1.30.0 ``stdio_client`` does: same process setup, streams, framing, decode,
parse, stamps and shutdown. Differences from b05_stdio, all caller side:

* ``STAMP["gc"]``: a ``gc.callbacks`` hook appends (phase, generation, CLOCK_MONOTONIC ns) to a list
  kept OUTSIDE the trial Recorder, so the sub-span decomposition is unchanged; it only lets the
  analysis classify caller stalls (GC pause or not).
* ``STAMP["frames"]`` also receives ``("resobj", obj)``: a reference to the dict handed to
  ``CallToolResult.model_validate`` (no copy, no hashing inside T; the analysis hashes it after the
  trial) for the decoded-identity check.
* PREP_FAST (``STAMP["prep"] == "fast"``): ``ClientSession.call_tool`` for a plain-JSON tools/call
  (arguments made of str / bool / int within +-2**53 / list / dict only; no meta, no progress
  callback, no read timeout) builds the JSON-RPC line directly and writes it to the Driver's stdin
  from the calling task, instead of building the pydantic request models and handing a
  SessionMessage to the stdin-writer task. The bytes must be identical to the library's
  ``model_dump_json(by_alias=True, exclude_none=True)`` line; harness/b07_equivalence.py checks every
  request offline. Anything else goes through the library path unchanged. The response side
  (response stream, result model, output validation) is the library's.
* ROUTE_FAST (``STAMP["route"] == "fast"``): the stdout reader hands a parsed JSON-RPC response or
  error whose integer id has a pending waiter directly to that waiter's response stream
  (``send_nowait``), instead of sending it through the read stream to the session receive loop,
  which would pop the same waiter and send the same object. Only when the session has no response
  routers; any other message, or any failure, takes the library path.
"""

from __future__ import annotations

import codecs
import gc
import json
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, TextIO

import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import (
    PROCESS_TERMINATION_TIMEOUT,
    StdioServerParameters,
    _create_platform_compatible_process,
    _get_executable_command,
    _terminate_process_tree,
    get_default_environment,
)
from mcp.shared.exceptions import McpError
from mcp.shared.message import SessionMessage
from mcp.shared.session import BaseSession

import logging

logger = logging.getLogger("b07_stdio")

STAMP: dict[str, Any] = {"rec": None, "rec_fn": None, "frames": None, "parser": "default", "max_bytes": 65536,
                         "validator": "default", "prep": "default", "route": "default", "gc": None}
PARSERS: dict[str, Any] = {}
# write-stream id -> direct sender (PREP_FAST); read-stream id -> ClientSession (ROUTE_FAST)
DIRECT: dict[int, Any] = {}
SESSION_BY_READ: dict[int, Any] = {}
COUNTS: dict[str, int] = {"prep_fast": 0, "prep_fallback": 0, "route_fast": 0, "route_fallback": 0}


def now() -> int:
    return time.monotonic_ns()


def _rec() -> Any:
    fn = STAMP["rec_fn"]
    return fn() if fn is not None else STAMP["rec"]


def _add(name: str, **fields: Any) -> None:
    rec = _rec()
    if rec is not None:
        rec.add(name, **fields)


def default_parse(line: str) -> types.JSONRPCMessage:
    return types.JSONRPCMessage.model_validate_json(line)


PARSERS["default"] = default_parse


def _msg_id(message: Any) -> Any:
    root = getattr(message, "root", None)
    return getattr(root, "id", None)


@asynccontextmanager
async def stdio_client(server: StdioServerParameters, errlog: TextIO = sys.stderr):
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]
    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)
    parse = PARSERS[STAMP["parser"]]
    max_bytes = int(STAMP["max_bytes"])
    route_fast = STAMP["route"] == "fast"
    busy = {"direct": False, "writer": False}

    try:
        command = _get_executable_command(server.command)
        process = await _create_platform_compatible_process(
            command=command,
            args=server.args,
            env=({**get_default_environment(), **server.env} if server.env is not None else get_default_environment()),
            errlog=errlog,
            cwd=server.cwd,
        )
    except OSError:
        await read_stream.aclose()
        await write_stream.aclose()
        await read_stream_writer.aclose()
        await write_stream_reader.aclose()
        raise

    def _route_direct(message: types.JSONRPCMessage) -> bool:
        """ROUTE_FAST: deliver a response straight to its waiter; False = take the library path."""
        sess = SESSION_BY_READ.get(id(read_stream))
        root = message.root
        if sess is None or sess._response_routers or not isinstance(root, (types.JSONRPCResponse, types.JSONRPCError)) \
                or type(root.id) is not int:
            return False
        stream = sess._response_streams.pop(root.id, None)
        if stream is None:
            return False
        try:
            stream.send_nowait(root)
        except Exception:  # noqa: BLE001  (closed/broken waiter: hand back to the library path)
            sess._response_streams[root.id] = stream
            return False
        return True

    async def stdout_reader():
        assert process.stdout, "Opened process is missing stdout"
        decoder = codecs.getincrementaldecoder(server.encoding)(errors=server.encoding_error_handler)
        try:
            async with read_stream_writer:
                buffer = ""
                line_first_t: int | None = None
                while True:
                    # anyio TextReceiveStream.receive(), inlined so the chunk time is taken at receipt.
                    try:
                        raw = await process.stdout.receive(max_bytes)
                    except (anyio.EndOfStream, anyio.ClosedResourceError):
                        break
                    t_chunk = now()
                    chunk = decoder.decode(raw)
                    if not chunk:
                        continue
                    if line_first_t is None:
                        line_first_t = t_chunk
                    lines = (buffer + chunk).split("\n")
                    buffer = lines.pop()
                    for line in lines:
                        first_t = line_first_t if line_first_t is not None else t_chunk
                        line_first_t = t_chunk  # a following line in this chunk starts here
                        try:
                            message = parse(line)
                        except Exception as exc:  # pragma: no cover
                            logger.exception("Failed to parse JSONRPC message from server")
                            _add("c.parse_failed", n=len(line), t_first=first_t, t_complete=t_chunk)
                            await read_stream_writer.send(exc)
                            continue
                        t_parsed = now()
                        mid = _msg_id(message)
                        rec = _rec()
                        if rec is not None:
                            rec.events.append({"event": "c.first_byte", "t_mono_ns": first_t, "id": mid})
                            rec.events.append({"event": "c.frame_complete", "t_mono_ns": t_chunk, "id": mid,
                                               "n": len(line)})
                            rec.events.append({"event": "c.parsed", "t_mono_ns": t_parsed, "id": mid})
                        frames = STAMP["frames"]
                        if frames is not None:
                            frames.append(("resp", line))
                        if route_fast:
                            if _route_direct(message):
                                COUNTS["route_fast"] += 1
                                continue
                            COUNTS["route_fallback"] += 1
                        session_message = SessionMessage(message)
                        await read_stream_writer.send(session_message)
                    if not buffer:
                        line_first_t = None
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async def stdin_writer():
        assert process.stdin, "Opened process is missing stdin"
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    while busy["direct"]:  # never in a sequential client; keeps the two writers apart
                        await anyio.sleep(0)
                    busy["writer"] = True
                    t_got = now()
                    payload = session_message.message.model_dump_json(by_alias=True, exclude_none=True)
                    data = (payload + "\n").encode(encoding=server.encoding, errors=server.encoding_error_handler)
                    t_ser = now()
                    await process.stdin.send(data)
                    t_wr = now()
                    busy["writer"] = False
                    mid = _msg_id(session_message.message)
                    rec = _rec()
                    if rec is not None:
                        rec.events.append({"event": "c.writer_got", "t_mono_ns": t_got, "id": mid})
                        rec.events.append({"event": "c.req_serialized", "t_mono_ns": t_ser, "id": mid,
                                           "n": len(data)})
                        rec.events.append({"event": "c.req_written", "t_mono_ns": t_wr, "id": mid})
                    frames = STAMP["frames"]
                    if frames is not None:
                        frames.append(("req", payload))
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async def send_direct(payload: str, mid: int) -> bool:
        """PREP_FAST writer: same encoding, same stamps, same frame capture as stdin_writer."""
        if busy["writer"]:
            return False
        busy["direct"] = True
        try:
            t_got = now()
            data = (payload + "\n").encode(encoding=server.encoding, errors=server.encoding_error_handler)
            t_ser = now()
            await process.stdin.send(data)
            t_wr = now()
        finally:
            busy["direct"] = False
        rec = _rec()
        if rec is not None:
            rec.events.append({"event": "c.writer_got", "t_mono_ns": t_got, "id": mid})
            rec.events.append({"event": "c.req_serialized", "t_mono_ns": t_ser, "id": mid, "n": len(data)})
            rec.events.append({"event": "c.req_written", "t_mono_ns": t_wr, "id": mid})
        frames = STAMP["frames"]
        if frames is not None:
            frames.append(("req", payload))
        return True

    DIRECT[id(write_stream)] = send_direct
    async with (
        anyio.create_task_group() as tg,
        process,
    ):
        tg.start_soon(stdout_reader)
        tg.start_soon(stdin_writer)
        try:
            yield read_stream, write_stream
        finally:
            DIRECT.pop(id(write_stream), None)
            SESSION_BY_READ.pop(id(read_stream), None)
            if process.stdin:  # pragma: no branch
                try:
                    await process.stdin.aclose()
                except Exception:  # pragma: no cover
                    pass
            try:
                with anyio.fail_after(PROCESS_TERMINATION_TIMEOUT):
                    await process.wait()
            except TimeoutError:
                await _terminate_process_tree(process)
            except ProcessLookupError:  # pragma: no cover
                pass
            await read_stream.aclose()
            await write_stream.aclose()
            await read_stream_writer.aclose()
            await write_stream_reader.aclose()


# ── CallToolResult model stamps (send_request is unchanged; only the result model is wrapped) ──

class _StampedCallToolResult:
    @staticmethod
    def model_validate(obj: Any, *args: Any, **kwargs: Any) -> types.CallToolResult:
        rec = _rec()
        t0 = now()
        out = types.CallToolResult.model_validate(obj, *args, **kwargs)
        if rec is not None:
            rec.events.append({"event": "c.result_model_start", "t_mono_ns": t0})
            rec.events.append({"event": "c.result_model_done", "t_mono_ns": now()})
        frames = STAMP["frames"]
        if frames is not None:
            frames.append(("resobj", obj))
        return out


_orig_send_request = BaseSession.send_request


async def _send_request(self: Any, request: Any, result_type: Any, *args: Any, **kwargs: Any) -> Any:
    if result_type is types.CallToolResult and _rec() is not None:
        result_type = _StampedCallToolResult
    return await _orig_send_request(self, request, result_type, *args, **kwargs)


# ── PREP_FAST ────────────────────────────────────────────────────────────────

_dumps = json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).encode


def plain_json(value: Any, depth: int = 0) -> bool:
    """Values whose json.dumps text is known to equal pydantic's JSON for the same value."""
    if depth > 16:
        return False
    if isinstance(value, str) or value is True or value is False:
        return True
    if type(value) is int:
        return -(2 ** 53) < value < 2 ** 53
    if isinstance(value, list):
        return all(plain_json(x, depth + 1) for x in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and plain_json(x, depth + 1) for k, x in value.items())
    return False  # None, float, anything else: library path


_orig_call_tool = ClientSession.call_tool


async def _call_tool(self: Any, name: str, arguments: dict[str, Any] | None = None, read_timeout_seconds: Any = None,
                     progress_callback: Any = None, *, meta: dict[str, Any] | None = None) -> types.CallToolResult:
    send = DIRECT.get(id(self._write_stream)) if STAMP["prep"] == "fast" else None
    if (send is None or read_timeout_seconds is not None or progress_callback is not None or meta is not None
            or self._session_read_timeout_seconds is not None or not isinstance(name, str)
            or not isinstance(arguments, dict) or not plain_json(arguments)):
        if STAMP["prep"] == "fast":
            COUNTS["prep_fallback"] += 1
        return await _orig_call_tool(self, name, arguments, read_timeout_seconds, progress_callback, meta=meta)
    request_id = self._request_id
    self._request_id = request_id + 1
    response_stream, response_stream_reader = anyio.create_memory_object_stream[
        types.JSONRPCResponse | types.JSONRPCError](1)
    self._response_streams[request_id] = response_stream
    try:
        payload = ('{"method":"tools/call","params":{"name":' + _dumps(name) + ',"arguments":' + _dumps(arguments)
                   + '},"jsonrpc":"2.0","id":' + str(request_id) + "}")
        if not await send(payload, request_id):
            COUNTS["prep_fallback"] += 1
            self._response_streams.pop(request_id, None)
            self._request_id = request_id  # nothing was sent; the library path reuses the id
            await response_stream.aclose()
            await response_stream_reader.aclose()
            return await _orig_call_tool(self, name, arguments, read_timeout_seconds, progress_callback, meta=meta)
        COUNTS["prep_fast"] += 1
        response_or_error = await response_stream_reader.receive()
        if isinstance(response_or_error, types.JSONRPCError):
            raise McpError(response_or_error.error)
        model = _StampedCallToolResult if _rec() is not None else types.CallToolResult
        result = model.model_validate(response_or_error.result)
    finally:
        self._response_streams.pop(request_id, None)
        await response_stream.aclose()
        await response_stream_reader.aclose()
    if not result.isError:
        await self._validate_tool_result(name, result)
    return result


_orig_session_init = ClientSession.__init__


def _session_init(self: Any, read_stream: Any, write_stream: Any, *args: Any, **kwargs: Any) -> None:
    _orig_session_init(self, read_stream, write_stream, *args, **kwargs)
    SESSION_BY_READ[id(read_stream)] = self


def _gc_callback(phase: str, info: dict[str, Any]) -> None:
    lst = STAMP["gc"]
    if lst is not None:
        lst.append((phase, info.get("generation"), time.monotonic_ns()))


def install() -> None:
    BaseSession.send_request = _send_request  # type: ignore[method-assign]
    ClientSession.call_tool = _call_tool  # type: ignore[method-assign]
    ClientSession.__init__ = _session_init  # type: ignore[method-assign]
    if _gc_callback not in gc.callbacks:
        gc.callbacks.append(_gc_callback)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

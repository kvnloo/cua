"""B-05 caller-side MCP stdio stamps (MEASUREMENT HARNESS ONLY, caller side).

``stdio_client`` below is mcp 1.30.0 ``mcp.client.stdio.stdio_client`` (the version pinned by the
jev-use uv.lock) with the same process setup, streams, framing, decode, parse and shutdown; the only
additions are CLOCK_MONOTONIC stamps (``time.monotonic_ns``) recorded into the current trial
Recorder, an optional raw-frame capture, and the pre-registered caller-side variants selected by
``STAMP["parser"]`` / ``STAMP["max_bytes"]`` (default: the library behaviour, exactly).

Stamps (event name, fields ``id`` = JSON-RPC id, ``n`` = bytes):
  c.writer_got        stdin_writer received the SessionMessage from the session
  c.req_serialized    model_dump_json + encode done
  c.req_written       process.stdin.send returned
  c.first_byte        receive() returned the chunk holding the first byte of a response line
  c.frame_complete    receive() returned the chunk holding the line's newline
  c.parsed            JSONRPCMessage built from the line
  c.result_model_start / c.result_model_done   CallToolResult.model_validate in send_request
The Driver side stamps with CLOCK_MONOTONIC too (phase_trace.rs), so both sides share one clock.
"""

from __future__ import annotations

import codecs
import json
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, TextIO

import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

import mcp.types as types
from mcp.client.stdio import (
    PROCESS_TERMINATION_TIMEOUT,
    StdioServerParameters,
    _create_platform_compatible_process,
    _get_executable_command,
    _terminate_process_tree,
    get_default_environment,
)
from mcp.shared.message import SessionMessage
from mcp.shared.session import BaseSession

import logging

logger = logging.getLogger("b05_stdio")

# rec: the trial Recorder (has .add(name, **fields)) or None; rec_fn: optional callable returning it;
# frames: list or None (capture raw lines);
# parser: "default" (library model_validate_json) or a registered variant name; max_bytes: receive size.
STAMP: dict[str, Any] = {"rec": None, "rec_fn": None, "frames": None, "parser": "default", "max_bytes": 65536,
                         "validator": "default"}
PARSERS: dict[str, Any] = {}


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
                    t_got = now()
                    payload = session_message.message.model_dump_json(by_alias=True, exclude_none=True)
                    data = (payload + "\n").encode(encoding=server.encoding, errors=server.encoding_error_handler)
                    t_ser = now()
                    await process.stdin.send(data)
                    t_wr = now()
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

    async with (
        anyio.create_task_group() as tg,
        process,
    ):
        tg.start_soon(stdout_reader)
        tg.start_soon(stdin_writer)
        try:
            yield read_stream, write_stream
        finally:
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
        return out


_orig_send_request = BaseSession.send_request


async def _send_request(self: Any, request: Any, result_type: Any, *args: Any, **kwargs: Any) -> Any:
    if result_type is types.CallToolResult and _rec() is not None:
        result_type = _StampedCallToolResult
    return await _orig_send_request(self, request, result_type, *args, **kwargs)


def install() -> None:
    BaseSession.send_request = _send_request  # type: ignore[method-assign]


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

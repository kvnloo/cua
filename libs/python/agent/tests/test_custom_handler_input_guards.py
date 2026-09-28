"""Tests: CustomComputerHandler wait/screenshot tolerate malformed input.

CustomComputerHandler.wait (default branch, no user wait function) ran
ms / 1000.0 unguarded: a model-supplied ms of None or "1000" raised
TypeError, and True silently slept 0.001s instead of failing.
_handle_item only catches ToolError, so the TypeError aborted the whole
agent run (same class as the c67 cua.py and c72 sandbox.py wait fixes).

CustomComputerHandler.screenshot only extracted fallback dimensions from
Image.Image/bytes results: a base64-str result (a documented-supported
input of _to_b64_str) left _last_screenshot_size None, so
get_dimensions() then raised AssertionError ("Failed to get screenshot
size") — not a ToolError, so _handle_item killed the run.
"""

import asyncio
import base64
import importlib.util
import io
import os
import sys
import types as _types
from pathlib import Path

import pytest
from PIL import Image

SCRATCH = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[4]
PRISTINE = Path(os.environ.get("C73_PRISTINE_CUSTOM", "")) if os.environ.get("C73_PRISTINE_CUSTOM") else None
FIXED = REPO / "libs/python/agent/cua_agent/computers/custom.py"
SRC_FILE = PRISTINE or FIXED


class ToolError(RuntimeError):
    pass


def _b64_png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 0, 0)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _load_custom():
    for name in ("cu_pkg", "cu_pkg.sub", "cu_pkg.types", "cu_pkg.sub.base", "cu_pkg.sub.custom"):
        sys.modules.pop(name, None)

    pkg = _types.ModuleType("cu_pkg")
    pkg.__path__ = []
    sys.modules["cu_pkg"] = pkg

    sub = _types.ModuleType("cu_pkg.sub")
    sub.__path__ = []
    sys.modules["cu_pkg.sub"] = sub

    types_mod = _types.ModuleType("cu_pkg.types")
    types_mod.ToolError = ToolError
    sys.modules["cu_pkg.types"] = types_mod

    base_mod = _types.ModuleType("cu_pkg.sub.base")

    class AsyncComputerHandler:
        pass

    base_mod.AsyncComputerHandler = AsyncComputerHandler
    sys.modules["cu_pkg.sub.base"] = base_mod

    spec = importlib.util.spec_from_file_location("cu_pkg.sub.custom", str(SRC_FILE))
    custom = importlib.util.module_from_spec(spec)
    sys.modules["cu_pkg.sub.custom"] = custom
    spec.loader.exec_module(custom)
    return custom


def _handler(custom_mod, functions):
    return custom_mod.CustomComputerHandler(functions)


def test_wait_none_is_tool_error():
    m = _load_custom()
    h = _handler(m, {"screenshot": lambda: _b64_png(4, 4)})
    with pytest.raises(ToolError):
        asyncio.run(h.wait(None))


def test_wait_str_is_tool_error():
    m = _load_custom()
    h = _handler(m, {"screenshot": lambda: _b64_png(4, 4)})
    with pytest.raises(ToolError):
        asyncio.run(h.wait("1000"))


def test_wait_bool_is_tool_error():
    m = _load_custom()
    h = _handler(m, {"screenshot": lambda: _b64_png(4, 4)})
    with pytest.raises(ToolError):
        asyncio.run(h.wait(True))


def test_wait_valid_sleeps():
    m = _load_custom()
    h = _handler(m, {"screenshot": lambda: _b64_png(4, 4)})
    asyncio.run(h.wait(50))  # must not raise


def test_wait_user_function_forwarded():
    m = _load_custom()
    seen = {}
    h = _handler(m, {"screenshot": lambda: _b64_png(4, 4), "wait": lambda ms: seen.update(ms=ms)})
    asyncio.run(h.wait(250))
    assert seen["ms"] == 250


def test_screenshot_str_feeds_dimensions_fallback():
    m = _load_custom()
    h = _handler(m, {"screenshot": lambda: _b64_png(10, 20)})
    dims = asyncio.run(h.get_dimensions())
    assert dims == (10, 20), dims


def test_screenshot_bytes_feeds_dimensions_fallback():
    m = _load_custom()
    buf = io.BytesIO()
    Image.new("RGB", (30, 40), (0, 255, 0)).save(buf, format="PNG")
    h = _handler(m, {"screenshot": lambda: buf.getvalue()})
    dims = asyncio.run(h.get_dimensions())
    assert dims == (30, 40), dims


def test_screenshot_returns_b64_str_for_str_input():
    m = _load_custom()
    b64 = _b64_png(8, 8)
    h = _handler(m, {"screenshot": lambda: b64})
    assert asyncio.run(h.screenshot()) == b64

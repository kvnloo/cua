"""Tests: SandboxComputerHandler keypress/wait tolerate malformed model-supplied input.

SandboxComputerHandler.keypress iterated `keys` unguarded: keys=None or an int
raised TypeError, and a non-str element (e.g. [42]) raised AttributeError from
k.lower(). A dict payload was worse: iterating it silently pressed the dict's
key names as keys instead of failing. SandboxComputerHandler.wait ran
ms / 1000.0 unguarded: a non-numeric ms (e.g. "1000") raised TypeError.
_handle_item only catches ToolError, so each of these aborted the whole agent
run on malformed model output. Malformed inputs now raise ToolError, which
degrades to a tool error item on the same call_id.
"""

import asyncio
import importlib.util
import os
import sys
import types as _types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
COMPUTERS_DIR = REPO / "libs/python/agent/cua_agent/computers"
PRISTINE = Path(os.environ.get("C72_PRISTINE_SANDBOX", "")) if os.environ.get("C72_PRISTINE_SANDBOX") else None
SRC_FILE = PRISTINE or (COMPUTERS_DIR / "sandbox.py")


class ToolError(RuntimeError):
    pass


class FakeKeyboard:
    def __init__(self):
        self.calls = []

    async def keypress(self, keys):
        self.calls.append(tuple(keys))


class FakeSandbox:
    def __init__(self):
        self.keyboard = FakeKeyboard()


def _load_sandbox():
    for name in ("sb_pkg", "sb_pkg.sub", "sb_pkg.types"):
        sys.modules.pop(name, None)

    pkg = _types.ModuleType("sb_pkg")
    pkg.__path__ = []
    sys.modules["sb_pkg"] = pkg

    sub = _types.ModuleType("sb_pkg.sub")
    sub.__path__ = [str(COMPUTERS_DIR)]
    sys.modules["sb_pkg.sub"] = sub

    types_mod = _types.ModuleType("sb_pkg.types")
    types_mod.ToolError = ToolError
    sys.modules["sb_pkg.types"] = types_mod

    spec = importlib.util.spec_from_file_location("sb_pkg.sub.base", COMPUTERS_DIR / "base.py")
    base = importlib.util.module_from_spec(spec)
    sys.modules["sb_pkg.sub.base"] = base
    spec.loader.exec_module(base)

    spec = importlib.util.spec_from_file_location("sb_pkg.sub.sandbox", str(SRC_FILE))
    sandbox = importlib.util.module_from_spec(spec)
    sys.modules["sb_pkg.sub.sandbox"] = sandbox
    spec.loader.exec_module(sandbox)
    return sandbox


def _handler(sandbox_mod):
    h = sandbox_mod.SandboxComputerHandler.__new__(sandbox_mod.SandboxComputerHandler)
    h._sandbox = FakeSandbox()
    return h


def test_keypress_none():
    m = _load_sandbox()
    h = _handler(m)
    with pytest.raises(ToolError):
        asyncio.run(h.keypress(None))
    assert h._sandbox.keyboard.calls == []


def test_keypress_int():
    m = _load_sandbox()
    h = _handler(m)
    with pytest.raises(ToolError):
        asyncio.run(h.keypress(42))
    assert h._sandbox.keyboard.calls == []


def test_keypress_dict():
    m = _load_sandbox()
    h = _handler(m)
    with pytest.raises(ToolError):
        asyncio.run(h.keypress({"k": "a"}))
    assert h._sandbox.keyboard.calls == []


def test_keypress_non_str_element():
    m = _load_sandbox()
    h = _handler(m)
    with pytest.raises(ToolError):
        asyncio.run(h.keypress([42]))
    assert h._sandbox.keyboard.calls == []


def test_wait_str():
    m = _load_sandbox()
    h = _handler(m)
    with pytest.raises(ToolError):
        asyncio.run(h.wait("1000"))


def test_wait_none():
    m = _load_sandbox()
    h = _handler(m)
    with pytest.raises(ToolError):
        asyncio.run(h.wait(None))


def test_wait_bool():
    m = _load_sandbox()
    h = _handler(m)
    with pytest.raises(ToolError):
        asyncio.run(h.wait(True))


def test_keypress_str_control():
    m = _load_sandbox()
    h = _handler(m)
    asyncio.run(h.keypress("a"))
    assert h._sandbox.keyboard.calls == [("a",)]


def test_keypress_list_control():
    m = _load_sandbox()
    h = _handler(m)
    asyncio.run(h.keypress(["ctrl", "a"]))
    assert h._sandbox.keyboard.calls == [("ctrl", "a")]


def test_wait_numeric_control():
    m = _load_sandbox()
    h = _handler(m)
    asyncio.run(h.wait(50))

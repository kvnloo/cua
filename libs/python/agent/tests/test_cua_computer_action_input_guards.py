"""Tests: cuaComputerHandler drag/keypress tolerate malformed model-supplied input.

cuaComputerHandler.drag indexed point["x"]/point["y"] unguarded: a non-dict
path point raised TypeError, a point missing x/y raised KeyError, and a
non-list path raised TypeError out of iteration. cuaComputerHandler.keypress
called len(keys) unguarded: a non-list/str keys payload (e.g. int) raised
TypeError. _handle_item only catches ToolError, so all of these aborted the
whole agent run. Malformed per-action inputs now raise ToolError, which
degrades to a tool error item on the same call_id.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
COMPUTERS_DIR = REPO / "libs/python/agent/cua_agent/computers"

SRC_FILE = Path(__file__).resolve().parents[4] / "libs/python/agent/cua_agent/computers/cua.py"


class ToolError(RuntimeError):
    pass


class FakeInterface:
    def __init__(self):
        self.calls = []

    async def mouse_down(self, x, y):
        self.calls.append(("mouse_down", x, y))

    async def move_cursor(self, x, y):
        self.calls.append(("move_cursor", x, y))

    async def mouse_up(self, x, y):
        self.calls.append(("mouse_up", x, y))

    async def press_key(self, key):
        self.calls.append(("press_key", key))

    async def hotkey(self, *keys):
        self.calls.append(("hotkey",) + tuple(keys))


def _load_cua():
    for name in ("t1_pkg", "t1_pkg.sub", "t1_pkg.types", "computer"):
        sys.modules.pop(name, None)

    computer_mod = types.ModuleType("computer")
    computer_mod.Computer = type("Computer", (), {})
    sys.modules["computer"] = computer_mod

    pkg = types.ModuleType("t1_pkg")
    pkg.__path__ = []
    sys.modules["t1_pkg"] = pkg

    sub = types.ModuleType("t1_pkg.sub")
    sub.__path__ = [str(COMPUTERS_DIR)]
    sys.modules["t1_pkg.sub"] = sub

    types_mod = types.ModuleType("t1_pkg.types")
    types_mod.ToolError = ToolError
    sys.modules["t1_pkg.types"] = types_mod

    spec = importlib.util.spec_from_file_location("t1_pkg.sub.base", COMPUTERS_DIR / "base.py")
    base = importlib.util.module_from_spec(spec)
    sys.modules["t1_pkg.sub.base"] = base
    spec.loader.exec_module(base)

    spec = importlib.util.spec_from_file_location("t1_pkg.sub.cua", SRC_FILE)
    cua = importlib.util.module_from_spec(spec)
    sys.modules["t1_pkg.sub.cua"] = cua
    spec.loader.exec_module(cua)
    return cua


def _handler(cua):
    h = cua.cuaComputerHandler.__new__(cua.cuaComputerHandler)
    h.interface = FakeInterface()
    return h


def test_drag_non_dict_point():
    cua = _load_cua()
    h = _handler(cua)
    with pytest.raises(Exception) as exc:
        asyncio.run(h.drag(path=[{"x": 1, "y": 2}, "oops"]))
    assert isinstance(exc.value, ToolError), f"expected ToolError, got {type(exc.value).__name__}"
    assert h.interface.calls == []


def test_drag_point_missing_xy():
    cua = _load_cua()
    h = _handler(cua)
    with pytest.raises(Exception) as exc:
        asyncio.run(h.drag(path=[{"x": 1}]))
    assert isinstance(exc.value, ToolError), f"expected ToolError, got {type(exc.value).__name__}"
    assert h.interface.calls == []


def test_drag_non_list_path():
    cua = _load_cua()
    h = _handler(cua)
    with pytest.raises(Exception) as exc:
        asyncio.run(h.drag(path=42))
    assert isinstance(exc.value, ToolError), f"expected ToolError, got {type(exc.value).__name__}"
    assert h.interface.calls == []


def test_drag_valid_path_control():
    cua = _load_cua()
    h = _handler(cua)
    asyncio.run(h.drag(path=[{"x": 1, "y": 2}, {"x": 3, "y": 4}]))
    assert h.interface.calls == [
        ("mouse_down", 1, 2),
        ("move_cursor", 3, 4),
        ("mouse_up", 3, 4),
    ]


def test_keypress_non_list_keys():
    cua = _load_cua()
    h = _handler(cua)
    with pytest.raises(Exception) as exc:
        asyncio.run(h.keypress(keys=5))
    assert isinstance(exc.value, ToolError), f"expected ToolError, got {type(exc.value).__name__}"
    assert h.interface.calls == []


def test_keypress_string_control():
    cua = _load_cua()
    h = _handler(cua)
    asyncio.run(h.keypress(keys="ctrl+c"))
    assert h.interface.calls == [("hotkey", "ctrl", "c")]


def test_keypress_single_key_control():
    cua = _load_cua()
    h = _handler(cua)
    asyncio.run(h.keypress(keys=["Enter"]))
    assert h.interface.calls == [("press_key", "Enter")]

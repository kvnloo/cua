"""Tests: BrowserTool FARA click/move methods reject malformed coordinates.

The FARA-compatible methods (left_click, right_click, middle_click,
double_click, triple_click, mouse_move, left_click_drag) indexed
coordinate[0]/[1] and called len(coordinate) unguarded. A model-supplied int
raised TypeError — uncaught by _handle_item (except ToolError only), killing
the whole run. A 2-char string silently clicked the wrong point
("ab" -> x='a', y='b'). left_click_drag had the same holes on
start_coordinate/end_coordinate, plus IndexError on a 1-element coordinate.
Malformed shapes now return an error dict.
"""

import asyncio
import importlib.util
import os
import sys
import types as _types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
TOOLS_DIR = REPO / "libs/python/agent/cua_agent/tools"
PRISTINE = Path(os.environ.get("C74_PRISTINE_BROWSER", "")) if os.environ.get("C74_PRISTINE_BROWSER") else None
SRC_FILE = PRISTINE or (TOOLS_DIR / "browser_tool.py")
BASE_FILE = TOOLS_DIR / "base.py"


class FakeAutomation:
    def __init__(self):
        self.cursor_calls = []

    async def move_cursor(self, x, y):
        self.cursor_calls.append((x, y))

    async def mouse_down(self, x, y):
        self.cursor_calls.append(("down", x, y))

    async def mouse_up(self, x, y):
        self.cursor_calls.append(("up", x, y))

    async def hotkey(self, *keys):
        pass


class FakeInterface:
    def __init__(self):
        self.exec_calls = []
        self.interface = FakeAutomation()  # nested automation structure

    async def playwright_exec(self, op, args):
        self.exec_calls.append((op, args))
        return {"success": True}


def _load_browser_tool():
    for name in ("bt_pkg", "bt_pkg.base", "bt_pkg.browser_tool"):
        sys.modules.pop(name, None)
    pkg = _types.ModuleType("bt_pkg")
    pkg.__path__ = []
    sys.modules["bt_pkg"] = pkg
    spec_base = importlib.util.spec_from_file_location("bt_pkg.base", BASE_FILE)
    mod_base = importlib.util.module_from_spec(spec_base)
    sys.modules["bt_pkg.base"] = mod_base
    spec_base.loader.exec_module(mod_base)
    spec = importlib.util.spec_from_file_location("bt_pkg.browser_tool", SRC_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bt_pkg.browser_tool"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def tool():
    mod = _load_browser_tool()
    return mod.BrowserTool(interface=FakeInterface())


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _automation(tool):
    return tool.interface.interface


# --- defect cases: crash or silent-wrong on base, error dict on fix ---

@pytest.mark.parametrize("method", ["left_click", "right_click", "middle_click",
                                     "double_click", "triple_click", "mouse_move"])
def test_int_coordinate_crashes_base(tool, method):
    if PRISTINE:
        with pytest.raises(TypeError):  # len(5); _handle_item can't catch it
            _run(getattr(tool, method)(coordinate=5))
    else:
        res = _run(getattr(tool, method)(coordinate=5))
        assert res["success"] is False
        assert "coordinate" in res["error"]


@pytest.mark.parametrize("method", ["left_click", "right_click", "middle_click",
                                     "double_click", "triple_click", "mouse_move"])
def test_string_coordinate_silently_wrong_on_base(tool, method):
    if PRISTINE:
        res = _run(getattr(tool, method)(coordinate="ab"))
        assert res["success"] is True  # base reports success on a garbage point
        if method in ("right_click", "middle_click", "double_click"):
            assert tool.interface.exec_calls[-1][1]["x"] == "a"
        else:
            assert ("a", "b") in _automation(tool).cursor_calls or \
                   tool.interface.exec_calls[-1][1]["x"] == "a"
    else:
        res = _run(getattr(tool, method)(coordinate="ab"))
        assert res["success"] is False
        assert "coordinate" in res["error"]


def test_drag_int_start_coordinate_crashes_base(tool):
    if PRISTINE:
        with pytest.raises(TypeError):  # start_coordinate[0] on an int
            _run(tool.left_click_drag(start_coordinate=5, end_coordinate=[1, 2]))
    else:
        res = _run(tool.left_click_drag(start_coordinate=5, end_coordinate=[1, 2]))
        assert res["success"] is False
        assert "start_coordinate" in res["error"]


def test_drag_short_coordinate_index_error_on_base(tool):
    if PRISTINE:
        with pytest.raises(IndexError):  # coordinate[1] on a 1-element list
            _run(tool.left_click_drag(coordinate=[500]))
    else:
        res = _run(tool.left_click_drag(coordinate=[500]))
        assert res["success"] is False
        assert "coordinate" in res["error"]


# --- controls: identical on base and fix ---

def test_left_click_pair_clicks(tool):
    res = _run(tool.left_click(coordinate=[100, 200]))
    assert res["success"] is True
    assert tool.interface.exec_calls[-1] == ("click", {"x": 100, "y": 200})


def test_left_click_xy_kwargs(tool):
    res = _run(tool.left_click(x=10, y=20))
    assert res["success"] is True
    assert tool.interface.exec_calls[-1] == ("click", {"x": 10, "y": 20})


def test_left_click_missing_errors(tool):
    res = _run(tool.left_click())
    assert res["success"] is False
    assert "x/y kwargs required" in res["error"]


def test_drag_pair_drags(tool):
    res = _run(tool.left_click_drag(start_coordinate=[1, 2], end_coordinate=[3, 4]))
    assert res["success"] is True
    auto = _automation(tool)
    assert auto.cursor_calls == [(1, 2), ("down", 1, 2), (3, 4), ("up", 3, 4)]


def test_drag_coordinate_moves(tool):
    res = _run(tool.left_click_drag(coordinate=[7, 8]))
    assert res["success"] is True
    assert _automation(tool).cursor_calls == [(7, 8)]


def test_drag_nothing_errors(tool):
    res = _run(tool.left_click_drag())
    assert res["success"] is False
    assert "start_coordinate and end_coordinate or coordinate required" in res["error"]


def test_mouse_move_pair(tool):
    res = _run(tool.mouse_move(coordinate=[9, 10]))
    assert res["success"] is True
    assert _automation(tool).cursor_calls == [(9, 10)]

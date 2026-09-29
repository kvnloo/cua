"""Tests: BrowserTool._action_key rejects non-list keys.

_action_key spread `keys` into automation.hotkey(*keys). A model-supplied
bare string ("Escape") was spread char-by-char — pressing E,s,c,a,p,e while
reporting success. A dict payload pressed the dict's key names. Both are
silent wrong dispatches (same class as the sandbox handler's dict-keys
defect): malformed keys now return an error dict instead of pressing the
wrong keys.
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


class FakeInterface:
    def __init__(self):
        self.hotkey_calls = []

    async def playwright_exec(self, op, args):
        return {"success": True}

    async def hotkey(self, *keys):
        self.hotkey_calls.append(keys)


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


# --- defect cases: silent wrong dispatch on base, error dict on fix ---

def test_string_keys_not_spread_char_by_char(tool):
    if PRISTINE:
        res = _run(tool._action_key({"keys": "Escape"}))
        assert res["success"] is True  # base reports success...
        assert tool.interface.hotkey_calls == [("E", "s", "c", "a", "p", "e")]  # ...on wrong keys
    else:
        res = _run(tool._action_key({"keys": "Escape"}))
        assert res["success"] is False
        assert "list of key names" in res["error"]
        assert tool.interface.hotkey_calls == []


def test_dict_keys_not_pressed(tool):
    if PRISTINE:
        res = _run(tool._action_key({"keys": {"a": 1}}))
        assert res["success"] is True
        assert tool.interface.hotkey_calls == [("a",)]
    else:
        res = _run(tool._action_key({"keys": {"a": 1}}))
        assert res["success"] is False
        assert tool.interface.hotkey_calls == []


def test_keypress_fara_method_guards_string_keys(tool):
    # key()/keypress() funnel into _action_key
    if PRISTINE:
        res = _run(tool.keypress(keys="ab"))
        assert res["success"] is True
        assert tool.interface.hotkey_calls == [("a", "b")]
    else:
        res = _run(tool.keypress(keys="ab"))
        assert res["success"] is False
        assert tool.interface.hotkey_calls == []


# --- controls: identical on base and fix ---

def test_list_keys_press(tool):
    res = _run(tool._action_key({"keys": ["Control", "c"]}))
    assert res["success"] is True
    assert tool.interface.hotkey_calls == [("Control", "c")]


def test_tuple_keys_press(tool):
    res = _run(tool._action_key({"keys": ("Alt", "Tab")}))
    assert res["success"] is True
    assert tool.interface.hotkey_calls == [("Alt", "Tab")]


def test_empty_keys_error(tool):
    res = _run(tool._action_key({"keys": []}))
    assert res["success"] is False
    assert "keys parameter is required" in res["error"]


def test_missing_keys_error(tool):
    res = _run(tool._action_key({}))
    assert res["success"] is False
    assert "keys parameter is required" in res["error"]

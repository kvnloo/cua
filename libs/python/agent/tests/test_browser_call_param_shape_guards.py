"""Tests: BrowserTool.call() degrades malformed params to an error dict.

BrowserTool.call() ran _verify_json_format_args(params) and params_dict.get("action")
OUTSIDE its per-action try/except. Malformed params — a JSON array payload
("[1,2]"), a bare list, a JSON scalar, unparseable JSON, or a dict missing the
required "action" — raised ValueError/AttributeError out of call(), which
agent.py's function-call path (only except ToolError) could not catch: the whole
run died. Malformed params now return {"success": False, ...} like every other
parameter error in this class.
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
        self.exec_calls = []
        self.hotkey_calls = []

    async def playwright_exec(self, op, args):
        self.exec_calls.append((op, args))
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


# --- defect cases: raise on base (run-kill), error dict on fix ---

@pytest.mark.parametrize("params", ["[1, 2]", [1, 2], "123", "{not json", {"foo": 1}])
def test_call_malformed_params_degrade(tool, params):
    if PRISTINE:
        # uncaught on base: ValueError (schema check) or AttributeError (.get on non-dict)
        with pytest.raises((ValueError, AttributeError)):
            tool.call(params)
    else:
        res = tool.call(params)
        assert res["success"] is False
        assert "Invalid parameters" in res["error"]


# --- controls: identical on base and fix ---

def test_call_valid_action_runs(tool):
    res = tool.call({"action": "history_back"})
    assert res["success"] is True
    assert tool.interface.hotkey_calls == [("Alt", "ArrowLeft")]


def test_call_unknown_action_errors(tool):
    res = tool.call({"action": "nope"})
    assert res["success"] is False
    assert "Unknown action" in res["error"]

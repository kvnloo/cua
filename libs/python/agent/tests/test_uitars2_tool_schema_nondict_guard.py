"""Red/green test: uitars2 tool-schema extraction must skip malformed tool entries.

_extract_function_schemas_from_tools called t.get("type") on every tool and
fn.get(...) on every "function" payload without type checks. A malformed
tool entry (a non-dict tool, or a non-dict "function" payload) raised
AttributeError and killed predict_step before the model call. Malformed
entries are now skipped; well-formed extraction is unchanged.

Self-contained: the function is pure, AST-extracted from the real file. The
base version is extracted from actual base file text via `git show HEAD:...`.
"""

import ast
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

LOOPS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"
UITARS2 = LOOPS_DIR / "uitars2.py"
AGENT_ROOT = Path(__file__).resolve().parent.parent


def _exec_fn(tree, path_str):
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and n.name == "_extract_function_schemas_from_tools"
    )
    ns = {"Any": Any, "Dict": Dict, "List": List, "Optional": Optional}
    exec(compile(ast.Module(body=[node], type_ignores=[]), path_str, "exec"), ns)
    return ns["_extract_function_schemas_from_tools"]


def _base_fn():
    src = subprocess.run(
        ["git", "show", "HEAD:libs/python/agent/cua_agent/loops/uitars2.py"],
        capture_output=True,
        text=True,
        cwd=AGENT_ROOT.parent,
        check=True,
    ).stdout
    return _exec_fn(ast.parse(src), "<base_uitars2>")


EXTRACT = _exec_fn(ast.parse(UITARS2.read_text()), str(UITARS2))
BASE_EXTRACT = _base_fn()


def _good_tool():
    return {
        "type": "function",
        "function": {
            "name": "click",
            "description": "click something",
            "parameters": {"type": "object"},
        },
    }


def test_helper_found():
    assert callable(EXTRACT) and callable(BASE_EXTRACT)


def test_well_formed_control():
    expected = [
        {
            "type": "function",
            "name": "click",
            "parameters": {"type": "object"},
            "description": "click something",
        }
    ]
    assert EXTRACT([_good_tool()]) == expected
    assert BASE_EXTRACT([_good_tool()]) == expected


def test_non_dict_tool_skipped():
    tools = ["junk", 42, None, _good_tool()]
    try:
        BASE_EXTRACT(tools)
        base_crashed = False
    except AttributeError:
        base_crashed = True
    assert base_crashed, "base must crash on non-dict tool"
    out = EXTRACT(tools)
    assert len(out) == 1 and out[0]["name"] == "click"


def test_non_dict_function_payload_skipped():
    tools = [{"type": "function", "function": "not a dict"}, _good_tool()]
    try:
        BASE_EXTRACT(tools)
        base_crashed = False
    except AttributeError:
        base_crashed = True
    assert base_crashed, "base must crash on non-dict function payload"
    out = EXTRACT(tools)
    assert len(out) == 1 and out[0]["name"] == "click"


def test_empty_and_none():
    assert EXTRACT([]) == []
    assert EXTRACT(None) == []
    assert BASE_EXTRACT([]) == []
    assert BASE_EXTRACT(None) == []

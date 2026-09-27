"""Red/green test: uitars2 response parsing must not crash on malformed choices.

UITARS2Config.predict_step and predict_click both did
`choices[0].get("message", {})` unguarded, then `msg.get(...)` unguarded. A
malformed provider response -- a non-dict first choice, or a non-dict message
payload -- raised AttributeError AFTER the model call succeeded, killing the
step during result extraction.

Fix: shared `_first_choice_message()` helper; both call sites degrade to an
empty message (empty action set / None click) instead of crashing.

Self-contained: the helper is AST-extracted from the real file (the loop
needs litellm etc. to import). The base expressions are extracted from the
actual base file text via `git show HEAD:...` and exec'd against fake
response dicts.
"""

import ast
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

LOOPS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"
UITARS2 = LOOPS_DIR / "uitars2.py"
AGENT_ROOT = Path(__file__).resolve().parent.parent


def _exec_fn(path, name):
    tree = ast.parse(Path(path).read_text())
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == name
    )
    ns = {"Any": Any, "Dict": Dict, "List": List, "Optional": Optional}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return ns[name]


def _base_text():
    return subprocess.run(
        ["git", "show", "HEAD:libs/python/agent/cua_agent/loops/uitars2.py"],
        capture_output=True,
        text=True,
        cwd=AGENT_ROOT.parent,
        check=True,
    ).stdout


def _block_after(src, marker, stop_markers):
    lines = src.splitlines()
    start = next(i for i, l in enumerate(lines) if marker in l) + 1
    end = next(
        i
        for i, l in enumerate(lines[start:], start)
        if any(m in l for m in stop_markers)
    )
    # drop the response_dict = response.model_dump() line: the wrapped function
    # takes response_dict as its parameter instead
    kept = [l for l in lines[start:end] if "response.model_dump()" not in l]
    return textwrap.dedent("\n".join(kept))


def _base_step_msg():
    src = _base_text()
    block = _block_after(
        src,
        "# Extract text content (first choice)",
        ["# Parse the seed tool calls"],
    )
    fn_src = "def _base_step_msg(response_dict):\n" + textwrap.indent(block, "    ")
    fn_src += '\n    return msg, mc\n'
    ns = {}
    exec(compile(fn_src, "<base_step>", "exec"), ns)
    return ns["_base_step_msg"]


def _base_click_content():
    src = _base_text()
    block = _block_after(
        src,
        "# Extract response content",
        ["# Parse coordinates"],
    )
    fn_src = "def _base_click_content(response_dict):\n" + textwrap.indent(block, "    ")
    fn_src += '\n    return content_text\n'
    ns = {}
    exec(compile(fn_src, "<base_click>", "exec"), ns)
    return ns["_base_click_content"]


FIRST_CHOICE_MESSAGE = _exec_fn(UITARS2, "_first_choice_message")
BASE_STEP_MSG = _base_step_msg()
BASE_CLICK_CONTENT = _base_click_content()


def test_helper_found():
    assert callable(FIRST_CHOICE_MESSAGE)


def test_well_formed_control():
    rd = {"choices": [{"message": {"content": "click(point='(1,2)')" }}]}
    assert FIRST_CHOICE_MESSAGE(rd) == {"content": "click(point='(1,2)')"}


def test_no_choices():
    assert FIRST_CHOICE_MESSAGE({"choices": []}) == {}
    assert FIRST_CHOICE_MESSAGE({}) == {}
    assert FIRST_CHOICE_MESSAGE(None) == {}


def test_non_dict_choice():
    rd = {"choices": ["not a dict"]}
    try:
        BASE_STEP_MSG(rd)
        step_crashed = False
    except AttributeError:
        step_crashed = True
    assert step_crashed, "base predict_step must crash on non-dict choice"
    try:
        BASE_CLICK_CONTENT(rd)
        click_crashed = False
    except AttributeError:
        click_crashed = True
    assert click_crashed, "base predict_click must crash on non-dict choice"
    assert FIRST_CHOICE_MESSAGE(rd) == {}


def test_non_dict_message():
    rd = {"choices": [{"message": "a string, not a dict"}]}
    try:
        BASE_STEP_MSG(rd)
        step_crashed = False
    except AttributeError:
        step_crashed = True
    assert step_crashed, "base predict_step must crash on non-dict message"
    try:
        BASE_CLICK_CONTENT(rd)
        click_crashed = False
    except AttributeError:
        click_crashed = True
    assert click_crashed, "base predict_click must crash on non-dict message"
    assert FIRST_CHOICE_MESSAGE(rd) == {}


def test_missing_message_key():
    rd = {"choices": [{"no_message": True}]}
    assert FIRST_CHOICE_MESSAGE(rd) == {}
    assert BASE_STEP_MSG(rd) == ({}, None)


def test_non_list_choices():
    assert FIRST_CHOICE_MESSAGE({"choices": "nope"}) == {}

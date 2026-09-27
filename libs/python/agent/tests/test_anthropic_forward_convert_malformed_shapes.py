"""Tests: tolerate malformed message shapes in the Anthropic forward converter.

_convert_responses_items_to_completion_messages (Responses -> Chat
Completions direction) called .get() on every message and content item
unconditionally. A non-dict message, a non-dict content item, an
assistant content of None/int, a computer_call with a non-dict action,
or a computer_call_output with a non-dict output raised
AttributeError/TypeError mid-conversion and killed the predict_step
before any model call. Malformed entries are now skipped; a non-dict
action degrades to an empty tool-call list for the entry.

Self-contained: the function is extracted from the loop module by AST and
exec'd standalone (the sandbox lacks litellm).
"""

import ast
import os
from typing import Any, Dict, List

import pytest


def _load_fn():
    path = os.path.join(
        os.path.dirname(__file__), "..", "cua_agent", "loops", "anthropic.py"
    )
    tree = ast.parse(open(path).read())
    fns = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_convert_responses_items_to_completion_messages"
    ]
    assert len(fns) == 1, "converter function not found"
    fn = fns[0]
    # Erase annotations (the sandbox lacks the module's type aliases).
    for node in ast.walk(fn):
        if isinstance(node, ast.arg):
            node.annotation = None
    fn.returns = None
    ns: Dict[str, Any] = {"Any": Any, "Dict": Dict, "List": List}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), path, "exec"), ns)
    return ns["_convert_responses_items_to_completion_messages"]


_convert_raw = _load_fn()


def _convert(messages):
    """Unwrap the (completion_messages, scale_factors) tuple."""
    completion_messages, _ = _convert_raw(messages)
    return completion_messages


def _user_msg(text="hi"):
    return {"role": "user", "content": text}


class TestMalformedMessages:
    def test_non_dict_messages_skipped(self):
        assert _convert(["junk", None, 42]) == []

    def test_mixed_valid_and_malformed(self):
        assert _convert(["junk", _user_msg(), None]) == [
            {"role": "user", "content": "hi"}
        ]

    def test_non_dict_function_output_message_skipped(self):
        assert _convert([_user_msg(), "junk"]) == [
            {"role": "user", "content": "hi"}
        ]


class TestMalformedAssistantContent:
    def test_none_content_becomes_empty(self):
        assert _convert([{"role": "assistant", "content": None}]) == [
            {"role": "assistant", "content": ""}
        ]

    def test_int_content_becomes_empty(self):
        assert _convert([{"role": "assistant", "content": 42}]) == [
            {"role": "assistant", "content": ""}
        ]

    def test_non_dict_content_items_skipped(self):
        msgs = [{"role": "assistant", "content": ["x", None, {"type": "text", "text": "yo"}]}]
        assert _convert(msgs) == [{"role": "assistant", "content": "yo"}]

    def test_string_content_unchanged(self):
        assert _convert([{"role": "assistant", "content": "done"}]) == [
            {"role": "assistant", "content": "done"}
        ]

    def test_well_formed_list_content_unchanged(self):
        msgs = [{"role": "assistant", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}]
        assert _convert(msgs) == [{"role": "assistant", "content": "a\nb"}]


class TestMalformedComputerCall:
    def test_string_action_degrades_to_empty_tool_calls(self):
        result = _convert([{"type": "computer_call", "call_id": "c1", "action": "click"}])
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["tool_calls"] == []

    def test_non_dict_output_skipped(self):
        msgs = [_user_msg(), {"type": "computer_call_output", "call_id": "c1", "output": "junk"}]
        assert _convert(msgs) == [{"role": "user", "content": "hi"}]

    def test_well_formed_user_message_unchanged(self):
        assert _convert([_user_msg()]) == [{"role": "user", "content": "hi"}]

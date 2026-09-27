"""Tests: tolerate malformed message shapes in the Gemini loop converters.

_convert_messages_to_gemini_contents, _find_last_user_text, and
_find_last_screenshot called .get() on every message and content item
unconditionally — a non-dict entry (stray string, None, or a mangled
payload from a lifecycle callback) raised AttributeError mid-conversion
and killed the predict_step before any model call. Malformed entries are
now skipped; a non-dict action degrades to the existing "unknown" path;
a non-list reasoning summary is treated as empty.

Self-contained: the functions are extracted from the loop module by AST and
exec'd standalone (the sandbox lacks litellm/genai).
"""

import ast
import os
from typing import Any, Dict, List, Optional, Tuple

import pytest


def _load_fns():
    path = os.path.join(
        os.path.dirname(__file__), "..", "cua_agent", "loops", "gemini.py"
    )
    tree = ast.parse(open(path).read())
    want = {
        "_convert_messages_to_gemini_contents",
        "_find_last_user_text",
        "_find_last_screenshot",
        "_data_url_to_bytes",
        "_bytes_image_size",
    }
    fns = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in want
    ]
    assert {n.name for n in fns} == want, "converter functions not found"
    ns: Dict[str, Any] = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "Tuple": Tuple,
    }
    exec(compile(ast.Module(body=fns, type_ignores=[]), path, "exec"), ns)
    return ns


_NS = _load_fns()
_convert = _NS["_convert_messages_to_gemini_contents"]
_find_last_user_text = _NS["_find_last_user_text"]
_find_last_screenshot = _NS["_find_last_screenshot"]


class _Part:
    def __init__(self, text=None):
        self.text = text

    @classmethod
    def from_bytes(cls, data=None, mime_type=None):
        return cls(text="<image-bytes>")


class _Content:
    def __init__(self, role=None, parts=None):
        self.role = role
        self.parts = list(parts or [])


class _Types:
    Part = _Part
    Content = _Content


def _roles(contents):
    return [c.role for c in contents]


def _texts(content):
    return [p.text for p in content.parts]


class TestConvertMalformedMessages:
    def test_non_dict_messages_skipped_falls_back_to_placeholder(self):
        # The converter guarantees a non-empty history for Gemini; with every
        # entry malformed it degrades to the existing placeholder prompt.
        contents, _ = _convert(["junk", None, 42], _Types)
        assert _roles(contents) == ["user"]
        assert _texts(contents[0]) == ["Proceed to the next action."]

    def test_mixed_valid_and_malformed(self):
        contents, _ = _convert(
            ["junk", {"role": "user", "content": "hi"}, None], _Types
        )
        assert _roles(contents) == ["user"]
        assert _texts(contents[0]) == ["hi"]

    def test_user_content_non_dict_items_skipped(self):
        contents, _ = _convert(
            [{"role": "user", "content": ["hi", None, {"type": "text", "text": "yo"}]}],
            _Types,
        )
        assert _roles(contents) == ["user"]
        assert _texts(contents[0]) == ["yo"]

    def test_assistant_non_dict_content_items_skipped(self):
        contents, _ = _convert(
            [{"role": "assistant", "content": [None, {"type": "text", "text": "done"}]}],
            _Types,
        )
        # Model-first history gets the existing "Begin the task." user prefix.
        assert _roles(contents) == ["user", "model"]
        assert _texts(contents[1]) == ["done"]

    def test_reasoning_non_dict_summary_items_skipped(self):
        contents, _ = _convert(
            [{"type": "reasoning", "summary": [None, {"type": "summary_text", "text": "hmm"}]}],
            _Types,
        )
        assert _roles(contents) == ["user", "model"]
        assert _texts(contents[1]) == ["[Thinking: hmm]"]

    def test_reasoning_non_list_summary_tolerated(self):
        contents, _ = _convert([{"type": "reasoning", "summary": "junk"}], _Types)
        assert _roles(contents) == ["user"]
        assert _texts(contents[0]) == ["Proceed to the next action."]

    def test_computer_call_string_action_degrades_to_unknown(self):
        contents, _ = _convert(
            [{"type": "computer_call", "call_id": "c1", "action": "click"}], _Types
        )
        assert _roles(contents) == ["user", "model"]
        assert _texts(contents[1]) == ["[Action: unknown]"]

    def test_well_formed_user_message_unchanged(self):
        contents, _ = _convert([{"role": "user", "content": "hi"}], _Types)
        assert _roles(contents) == ["user"]
        assert _texts(contents[0]) == ["hi"]


class TestFindLastUserText:
    def test_non_dict_message_skipped(self):
        assert _find_last_user_text(["junk", {"role": "user", "content": "hi"}]) == ["hi"]

    def test_non_dict_content_item_skipped(self):
        msgs = [{"role": "user", "content": [None, {"type": "input_text", "text": "yo"}]}]
        assert _find_last_user_text(msgs) == ["yo"]

    def test_well_formed_unchanged(self):
        assert _find_last_user_text([{"role": "user", "content": "hi"}]) == ["hi"]


class TestFindLastScreenshot:
    def test_non_dict_message_skipped(self):
        assert _find_last_screenshot(["junk", None]) is None

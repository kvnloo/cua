"""Tests: tolerate non-string image_url in composed-grounded last-image lookup.

ComposedGroundedConfig.predict_step starts by calling
get_last_computer_call_image(messages) to reuse the last screenshot. The
lookup guarded message/output dict-ness but called .startswith() on
image_url unconditionally — a malformed driver payload carrying a None,
dict, or list image_url raised AttributeError and killed the step before
any model call. Non-string image_url values are now treated as absent
(fall through to a fresh screenshot).

Self-contained: the function is extracted from the loop module by AST and
exec'd standalone (the sandbox lacks litellm/PIL).
"""

import ast
import os
from typing import Any, Dict, List, Optional

import pytest


def _load_fn():
    path = os.path.join(
        os.path.dirname(__file__), "..", "cua_agent", "loops",
        "composed_grounded.py",
    )
    tree = ast.parse(open(path).read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == (
            "get_last_computer_call_image"
        ):
            ns: Dict[str, Any] = {
                "Any": Any,
                "Dict": Dict,
                "List": List,
                "Optional": Optional,
            }
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), ns)
            return ns["get_last_computer_call_image"]
    raise AssertionError("function not found")


get_last_computer_call_image = _load_fn()


def _output_msg(image_url):
    return {
        "type": "computer_call_output",
        "call_id": "call_1",
        "output": {"type": "input_image", "image_url": image_url},
    }


class TestMalformedImageUrl:
    def test_none_image_url_returns_none(self):
        assert get_last_computer_call_image([_output_msg(None)]) is None

    def test_dict_image_url_returns_none(self):
        assert (
            get_last_computer_call_image([_output_msg({"url": "data:..."})]) is None
        )

    def test_list_image_url_returns_none(self):
        assert get_last_computer_call_image([_output_msg(["x"])]) is None

    def test_non_data_url_string_returns_none(self):
        assert (
            get_last_computer_call_image([_output_msg("https://example/x.png")])
            is None
        )

    def test_valid_data_url_still_extracted(self):
        out = get_last_computer_call_image(
            [_output_msg("data:image/png;base64,QUJD")]
        )
        assert out == "QUJD"

    def test_valid_image_wins_over_malformed_later_entry(self):
        msgs = [_output_msg(None), _output_msg("data:image/png;base64,WFla")]
        # reversed() visits the valid entry first
        assert get_last_computer_call_image(msgs) == "WFla"

    def test_no_outputs_returns_none(self):
        assert (
            get_last_computer_call_image([{"type": "message", "role": "user"}])
            is None
        )

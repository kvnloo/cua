"""Tests for the computer-action non-dict arguments guard.

Covers:
- tool-call arguments that parse to valid JSON but not an object
  ("null", "123", "[1,2]") or are absent/None: fall back to a function_call
  item instead of crashing on action.get (AttributeError on base, killing the
  run out of the converter)
- well-formed object arguments still become computer_call (control, green on
  both); unparseable JSON still falls back (control, green on both)

The real responses module is loaded (not copied); only the openai type
imports are stubbed.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

RESP = Path(__file__).resolve().parent.parent / "cua_agent" / "responses.py"

_STUB_NAMES = {
    "openai.types.responses.easy_input_message_param": ["EasyInputMessageParam"],
    "openai.types.responses.response_computer_tool_call_param": [
        "ActionClick",
        "ActionDoubleClick",
        "ActionDrag",
        "ActionDragPath",
        "ActionKeypress",
        "ActionMove",
        "ActionScreenshot",
        "ActionScroll",
        "ActionType",
        "ActionWait",
        "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ],
    "openai.types.responses.response_function_tool_call_param": [
        "ResponseFunctionToolCallParam"
    ],
    "openai.types.responses.response_input_image_param": ["ResponseInputImageParam"],
    "openai.types.responses.response_output_message_param": [
        "ResponseOutputMessageParam"
    ],
    "openai.types.responses.response_output_text_param": ["ResponseOutputTextParam"],
    "openai.types.responses.response_reasoning_item_param": [
        "ResponseReasoningItemParam",
        "Summary",
    ],
}


def _ensure():
    if "cua_agent.responses" in sys.modules:
        return sys.modules["cua_agent.responses"]
    for dotted in ("openai", "openai.types", "openai.types.responses"):
        mod = types.ModuleType(dotted)
        mod.__path__ = []
        sys.modules[dotted] = mod
    for dotted, names in _STUB_NAMES.items():
        mod = types.ModuleType(dotted)
        for n in names:
            setattr(mod, n, type(n, (), {}))
        sys.modules[dotted] = mod
    spec = importlib.util.spec_from_file_location("cua_agent.responses", RESP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _convert(arguments):
    mod = _ensure()
    function = {"name": "computer"}
    if arguments is not _MISSING:
        function["arguments"] = arguments
    msg = {
        "role": "assistant",
        "tool_calls": [{"type": "function", "id": "t1", "function": function}],
    }
    return mod.convert_completion_messages_to_responses_items([msg])


_MISSING = object()


@pytest.mark.parametrize("arguments", ["null", "123", "[1,2]", '"str"', None])
def test_non_dict_arguments_fall_back_to_function_call(arguments):
    items = _convert(arguments)  # must not raise
    assert len(items) == 1
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "computer"


def test_unparseable_arguments_still_fall_back():
    items = _convert("{bad json")
    assert len(items) == 1
    assert items[0]["type"] == "function_call"


def test_object_arguments_still_become_computer_call():
    items = _convert('{"action": "click", "x": 10, "y": 20}')
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "computer_call"
    assert item["action"]["type"] == "click"
    assert item["action"]["x"] == 10

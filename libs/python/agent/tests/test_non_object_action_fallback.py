"""Tests for non-object tool arguments in convert_completion_messages_to_responses_items.

A model can emit tool-call arguments that are valid JSON but not an object
(e.g. a bare string, list, null, or number). The converter previously called
action.get("action") on the parsed value unguarded, so these raised
AttributeError and killed predict_step in the composed_grounded/moondream3
loops. The fix degrades to the same function_call fallback the bad-JSON path
already uses, instead of crashing.

The real responses.py is loaded with the openai type imports stubbed (they
are typing-only), so these tests exercise the shipped code, not a mirror.
"""

import importlib.util
import sys
import types

import pytest


def _load_responses():
    stub_openai = types.ModuleType("openai")
    stub_types = types.ModuleType("openai.types")
    stub_responses = types.ModuleType("openai.types.responses")
    names = {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": [
            "ActionClick",
            "ActionDoubleClick",
            "ActionDrag",
            "ActionDragPath",
            "ActionKeypress",
            "ActionMove",
            "ActionScreenshot",
            "ActionScroll",
            "ActionWait",
            "ResponseComputerToolCallParam",
            "ActionType",
            "PendingSafetyCheck",
        ],
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }
    for mod_name, cls_names in names.items():
        mod = types.ModuleType(f"openai.types.responses.{mod_name}")
        for cls_name in cls_names:
            setattr(mod, cls_name, type(cls_name, (), {}))
        sys.modules[f"openai.types.responses.{mod_name}"] = mod
    sys.modules["openai"] = stub_openai
    sys.modules["openai.types"] = stub_types
    sys.modules["openai.types.responses"] = stub_responses

    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[1]  # libs/python/agent/
        / "cua_agent"
        / "responses.py"
    )
    spec = importlib.util.spec_from_file_location("cua_agent_responses", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_responses = _load_responses()
convert = _responses.convert_completion_messages_to_responses_items


def _completion_msg(arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "type": "function",
                "id": "call_1",
                "function": {"name": "computer", "arguments": arguments},
            }
        ],
    }


@pytest.mark.parametrize(
    "arguments",
    ['"click"', '["click"]', "null", "42"],
    ids=["string", "list", "null", "number"],
)
def test_non_object_arguments_fall_back_to_function_call(arguments):
    """Valid JSON that is not an object degrades instead of raising."""
    items = convert([_completion_msg(arguments)])
    assert len(items) == 1
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "computer"
    assert items[0]["arguments"] == arguments


def test_object_arguments_still_become_computer_call():
    items = convert([_completion_msg('{"action":"click","x":1,"y":2}')])
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "computer_call"
    assert item["action"]["type"] == "click"
    assert "action" not in item["action"]
    assert item["action"]["x"] == 1


def test_malformed_json_still_falls_back():
    items = convert([_completion_msg('{"action":')])
    assert len(items) == 1
    assert items[0]["type"] == "function_call"


def test_fallback_item_survives_desc2xy_conversion():
    """The fallback function_call item must flow through the desc<->xy
    converters without crashing (they only touch computer_call items)."""
    items = convert([_completion_msg('"click"')])
    converted = _responses.convert_computer_calls_desc2xy(items, {})
    assert converted[0]["type"] == "function_call"
    converted = _responses.convert_computer_calls_xy2desc(items, {})
    assert converted[0]["type"] == "function_call"

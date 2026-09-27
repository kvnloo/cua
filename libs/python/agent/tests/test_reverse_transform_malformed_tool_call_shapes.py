"""Tests: tolerate malformed tool-call and JSON shapes in the reverse transform.

convert_completion_messages_to_responses_items assumes provider payloads are
well formed:
- tool_calls entries are dicts with a dict "function" value;
- json.loads(content) either raises JSONDecodeError or returns a dict;
- image_url content-block values are dicts carrying "url".

Malformed provider payloads violate each of these and raised AttributeError
mid-conversion. The transform now degrades instead of crashing.

Self-contained: cua_agent/responses.py is loaded by file path with stubbed
openai.types.responses modules (dict subclasses).
"""

import importlib.util
import sys
import types

import pytest


def _load_responses():
    stub_names = [
        "openai.types.responses.easy_input_message_param",
        "openai.types.responses.response_computer_tool_call_param",
        "openai.types.responses.response_function_tool_call_param",
        "openai.types.responses.response_input_image_param",
        "openai.types.responses.response_output_message_param",
        "openai.types.responses.response_output_text_param",
        "openai.types.responses.response_reasoning_item_param",
    ]
    attrs = [
        "EasyInputMessageParam",
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
        "ResponseFunctionToolCallParam",
        "ResponseInputImageParam",
        "ResponseOutputMessageParam",
        "ResponseOutputTextParam",
        "ResponseReasoningItemParam",
        "Summary",
    ]
    for name in ["openai", "openai.types", "openai.types.responses", *stub_names]:
        sys.modules.setdefault(name, types.ModuleType(name))
    for name in stub_names:
        mod = sys.modules[name]
        for attr in attrs:
            if not hasattr(mod, attr):
                setattr(mod, attr, dict)

    path = __file__.replace(
        "tests/test_reverse_transform_malformed_tool_call_shapes.py",
        "cua_agent/responses.py",
    )
    spec = importlib.util.spec_from_file_location("responses_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


responses = _load_responses()
convert = responses.convert_completion_messages_to_responses_items


class TestMalformedToolCallEntries:
    def test_non_dict_tool_call_entries_are_skipped(self):
        out = convert(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        "garbage",
                        None,
                        {
                            "type": "function",
                            "id": "call_1",
                            "function": {
                                "name": "computer",
                                "arguments": '{"action": "left_click", "coordinate": [1, 2]}',
                            },
                        },
                    ],
                }
            ]
        )
        # The valid computer tool call still converts
        assert any(
            m.get("type") == "computer_call" and m.get("call_id") == "call_1"
            for m in out
        )

    def test_non_dict_function_value_does_not_crash(self):
        out = convert(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"type": "function", "id": "call_1", "function": "malformed"}
                    ],
                }
            ]
        )
        # function_name is None -> falls to the regular-function-call branch
        assert out == [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": None,
                "arguments": "{}",
                "status": "completed",
            }
        ]

    def test_missing_function_value_does_not_crash(self):
        out = convert(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"type": "function", "id": "call_1"}],
                }
            ]
        )
        assert out[0]["type"] == "function_call"
        assert out[0]["call_id"] == "call_1"


class TestNonDictParsedJson:
    def test_json_list_content_degrades_to_text_output(self):
        out = convert(
            [
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": '["a", "b"]',
                }
            ]
        )
        assert any(
            m.get("type") == "computer_call_output" and m.get("output") == '["a", "b"]'
            for m in out
        )

    def test_json_string_content_degrades_to_text_output(self):
        out = convert(
            [
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": '"just a string"',
                }
            ]
        )
        assert any(
            m.get("type") == "computer_call_output"
            for m in out
        )

    def test_json_image_dict_still_detected(self):
        out = convert(
            [
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": '{"type": "input_image", "image_url": "data:..."}',
                }
            ]
        )
        assert any(
            m.get("type") == "computer_call_output"
            and m.get("output", {}).get("type") == "input_image"
            for m in out
        )


class TestMalformedImageUrlValues:
    def test_string_image_url_does_not_crash(self):
        out = convert(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": "not-a-dict"},
                        {"type": "text", "text": "look"},
                    ],
                }
            ]
        )
        # text block still converts; malformed image block yields None url
        assert len(out) == 1
        assert out[0]["type"] == "message"
        content = out[0]["content"]
        assert {"type": "input_text", "text": "look"} in content
        assert {"type": "input_image", "image_url": None} in content

    def test_string_image_url_in_screenshot_pattern(self):
        out = convert(
            [
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": [
                        {"type": "image_url", "image_url": "not-a-dict"},
                    ],
                }
            ]
        )
        assert any(
            m.get("type") == "computer_call_output"
            and m.get("output", {}).get("image_url") is None
            for m in out
        )

    def test_dict_image_url_still_converted(self):
        out = convert(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AAA"},
                        },
                    ],
                }
            ]
        )
        assert any(
            m.get("type") == "message"
            and m.get("content", [{}])[0].get("image_url")
            == "data:image/png;base64,AAA"
            for m in out
        )

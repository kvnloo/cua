"""Tests: skip non-dict messages in the message-format transforms.

convert_responses_items_to_completion_messages and
convert_completion_messages_to_responses_items read message.get(...) /
message-level fields on every entry of the input list. Malformed (non-dict)
entries survive the earlier run-loop normalization stages (e.g. raw strings
from a provider), so both transforms must skip them instead of raising
AttributeError mid-run.

Self-contained: cua_agent/responses.py is loaded by file path with stubbed
openai.types.responses modules (the sandbox lacks the openai package; the
stubs are dict subclasses, which matches how the real TypedDicts are used).
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
        "tests/test_transforms_non_dict_message_guard.py",
        "cua_agent/responses.py",
    )
    spec = importlib.util.spec_from_file_location("responses_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


responses = _load_responses()
convert_responses_items_to_completion_messages = (
    responses.convert_responses_items_to_completion_messages
)
convert_completion_messages_to_responses_items = (
    responses.convert_completion_messages_to_responses_items
)


@pytest.fixture
def valid_user_message():
    return {"role": "user", "content": "hello"}


@pytest.fixture
def valid_tool_message():
    return {"role": "tool", "tool_call_id": "call_1", "content": "done"}


class TestForwardTransformNonDictMessages:
    def test_non_dict_messages_are_skipped(self, valid_user_message):
        out = convert_responses_items_to_completion_messages(
            ["garbage", None, 42, ["nested"], valid_user_message]
        )
        assert out == [{"role": "user", "content": "hello"}]

    def test_all_non_dict_input_yields_empty(self):
        assert convert_responses_items_to_completion_messages(["a", None]) == []

    def test_screenshot_lookahead_with_non_dict_next(self):
        # A tool output carrying an image followed by a non-dict message
        # must not crash the lookahead.
        msgs = [
            {
                "type": "computer_call_output",
                "call_id": "call_1",
                "output": {"type": "input_image", "image_url": "data:..."},
            },
            "not-a-dict",
        ]
        out = convert_responses_items_to_completion_messages(msgs)
        assert any(
            m.get("role") == "tool" and m.get("tool_call_id") == "call_1"
            for m in out
        )

    def test_well_formed_roundtrip_control(
        self, valid_user_message
    ):
        out = convert_responses_items_to_completion_messages(
            [
                valid_user_message,
                {
                    "type": "computer_call_output",
                    "call_id": "call_1",
                    "output": "done",
                },
            ]
        )
        assert out[0] == {"role": "user", "content": "hello"}
        assert out[1]["role"] == "tool"
        assert out[1]["tool_call_id"] == "call_1"


class TestReverseTransformNonDictMessages:
    def test_non_dict_messages_are_skipped(self, valid_user_message):
        out = convert_completion_messages_to_responses_items(
            ["garbage", None, {"bad": "entry"}, valid_user_message]
        )
        # "bad" entry is a dict without role/content -> ignored by all branches
        assert out == [{"role": "user", "content": "hello"}]

    def test_dict_message_without_role_and_content_ignored(self):
        out = convert_completion_messages_to_responses_items(
            ["garbage", None, {"role": "assistant", "content": "hi"}]
        )
        assert out == [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hi"}],
            }
        ]

    def test_non_list_tool_calls_treated_as_empty(self):
        out = convert_completion_messages_to_responses_items(
            [{"role": "assistant", "content": "hi", "tool_calls": "malformed"}]
        )
        assert out == [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hi"}],
            }
        ]

    def test_screenshot_lookahead_with_non_dict_next(self):
        msgs = [
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "[Execution completed. See screenshot below]",
            },
            "not-a-dict",
        ]
        out = convert_completion_messages_to_responses_items(msgs)
        # No crash; falls back to a plain text output item
        assert any(m.get("type") == "computer_call_output" for m in out)

    def test_all_non_dict_input_yields_empty(self):
        assert (
            convert_completion_messages_to_responses_items(["a", None, 7]) == []
        )

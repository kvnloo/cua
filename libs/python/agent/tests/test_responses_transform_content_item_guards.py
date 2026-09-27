"""Tests: skip non-dict content items in the message-format transforms.

convert_responses_items_to_completion_messages and
convert_completion_messages_to_responses_items guarded non-dict *messages*
(transforms-non-dict-message-guard), but every content/tool_call list entry
was still read with item.get(...). A malformed (non-dict) content item —
which survives the earlier run-loop stages as raw provider output — raised
AttributeError mid-predict_step and killed the run. Non-dict entries are now
skipped in all content loops (user, assistant, reasoning summary, tool
output, user content, screenshot lookahead) and in the tool_calls loop; a
non-dict image_url value yields a None url instead of crashing.

Self-contained: cua_agent/responses.py is loaded by file path with stubbed
openai.types.responses modules (the sandbox lacks the openai package; the
stubs are dict subclasses, which matches how the real TypedDicts are used).
"""

import importlib.util
import sys
import types


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
        "tests/test_responses_transform_content_item_guards.py",
        "cua_agent/responses.py",
    )
    spec = importlib.util.spec_from_file_location("responses_under_test_c69", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


responses = _load_responses()
to_completion = responses.convert_responses_items_to_completion_messages
to_responses = responses.convert_completion_messages_to_responses_items


class TestForwardContentItems:
    def test_user_content_non_dict_item_skipped(self):
        out = to_completion(
            [
                {
                    "role": "user",
                    "content": ["oops", {"type": "input_text", "text": "hi"}],
                }
            ]
        )
        assert out == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    def test_assistant_content_non_dict_item_skipped(self):
        out = to_completion(
            [
                {
                    "role": "assistant",
                    "content": [None, {"type": "output_text", "text": "done"}],
                }
            ]
        )
        assert out == [{"role": "assistant", "content": "done"}]

    def test_reasoning_summary_non_dict_item_skipped(self):
        out = to_completion(
            [
                {
                    "type": "reasoning",
                    "summary": [42, {"type": "summary_text", "text": "thinking"}],
                }
            ]
        )
        assert out == [{"role": "assistant", "content": "thinking"}]


class TestReverseContentItems:
    def test_tool_output_content_non_dict_item_skipped(self):
        out = to_responses(
            [
                {
                    "role": "tool",
                    "tool_call_id": "c1",
                    "content": ["oops", {"type": "text", "text": "result"}],
                }
            ]
        )
        assert out == [
            {"type": "function_call_output", "call_id": "c1", "output": "result"}
        ]

    def test_tool_output_non_dict_image_url_yields_none_url(self):
        out = to_responses(
            [
                {
                    "role": "tool",
                    "tool_call_id": "c2",
                    "content": [{"type": "image_url", "image_url": "not-a-dict"}],
                }
            ]
        )
        assert out == [
            {
                "type": "computer_call_output",
                "call_id": "c2",
                "output": {"type": "input_image", "image_url": None},
            }
        ]

    def test_user_content_non_dict_item_skipped(self):
        out = to_responses(
            [
                {
                    "role": "user",
                    "content": ["oops", {"type": "text", "text": "hello"}],
                }
            ]
        )
        assert out == [
            {
                "role": "user",
                "type": "message",
                "content": [{"type": "input_text", "text": "hello"}],
            }
        ]

    def test_non_dict_tool_call_entry_skipped(self):
        out = to_responses(
            [
                {
                    "role": "assistant",
                    "content": "working",
                    "tool_calls": ["oops"],
                }
            ]
        )
        # The assistant text message still converts; the malformed tool_call
        # entry is skipped instead of raising.
        assert out == [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "working"}],
            }
        ]

    def test_screenshot_lookahead_non_dict_item_skipped(self):
        out = to_responses(
            [
                {
                    "role": "tool",
                    "tool_call_id": "c3",
                    "content": "[Execution completed. See screenshot below]",
                },
                {
                    "role": "user",
                    "content": [
                        "oops",
                        {"type": "image_url", "image_url": {"url": "data:image/png,AAA"}},
                    ],
                },
            ]
        )
        assert out == [
            {
                "type": "computer_call_output",
                "call_id": "c3",
                "output": {"type": "input_image", "image_url": "data:image/png,AAA"},
            }
        ]


class TestWellFormedUnchanged:
    def test_forward_user_text_and_image(self):
        out = to_completion(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "look"},
                        {"type": "input_image", "image_url": "data:image/png,AAA"},
                    ],
                }
            ]
        )
        assert out == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {"type": "image_url", "image_url": {"url": "data:image/png,AAA"}},
                ],
            }
        ]

    def test_reverse_user_text(self):
        out = to_responses([{"role": "user", "content": "hello"}])
        assert out == [{"role": "user", "content": "hello"}]

    def test_reverse_tool_text_output(self):
        out = to_responses(
            [{"role": "tool", "tool_call_id": "c9", "content": "plain result"}]
        )
        assert out == [
            {"type": "function_call_output", "call_id": "c9", "output": "plain result"}
        ]

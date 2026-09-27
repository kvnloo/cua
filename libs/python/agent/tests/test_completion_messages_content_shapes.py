"""Non-dict content entries must not crash the message transforms.

Both ``convert_responses_items_to_completion_messages`` and
``convert_completion_messages_to_responses_items`` iterate content lists
and call ``item.get("type")`` on each entry. A non-dict entry (bare string
from malformed model output or a corrupted history entry) raised
AttributeError, killing history conversion mid-run.

Fix: non-dict content entries are skipped in place; well-formed content
converts exactly as before.
"""
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "cua_agent"


def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _factory(name):
    return type(name, (dict,), {"__init__": lambda self, **kw: dict.__init__(self, kw)})


def _install_stubs():
    action_names = [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionWait", "ActionType", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ]
    for mod, names in {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": action_names,
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }.items():
        _mod(f"openai.types.responses.{mod}", **{n: _factory(n) for n in names})


_install_stubs()
spec = importlib.util.spec_from_file_location("responses", REPO / "responses.py")
resp = importlib.util.module_from_spec(spec)
sys.modules["responses"] = resp
spec.loader.exec_module(resp)

fwd = resp.convert_responses_items_to_completion_messages
rev = resp.convert_completion_messages_to_responses_items


def test_forward_user_list_content_with_string_entry():
    msgs = [{"role": "user",
             "content": ["raw-string", {"type": "input_text", "text": "hi"}]}]
    out = fwd(msgs)
    assert out == [{"role": "user",
                    "content": [{"type": "text", "text": "hi"}]}]


def test_forward_assistant_list_content_with_string_entry():
    msgs = [{"role": "assistant", "type": "message",
             "content": ["raw", {"type": "output_text", "text": "done"}]}]
    out = fwd(msgs)
    assert out == [{"role": "assistant", "content": "done"}]


def test_forward_reasoning_with_string_summary_entry():
    msgs = [{"type": "reasoning", "summary": ["raw", {"type": "summary_text",
                                                      "text": "thinking"}]}]
    out = fwd(msgs)
    assert out == [{"role": "assistant", "content": "thinking"}]


def test_reverse_tool_list_content_with_string_entry():
    msgs = [{"role": "tool", "tool_call_id": "c1",
             "content": ["raw", {"type": "text", "text": "ok"}]}]
    out = rev(msgs)
    assert out == [{"type": "function_call_output", "call_id": "c1",
                    "output": "ok"}]


def test_reverse_user_list_content_with_string_entry():
    msgs = [{"role": "user",
             "content": ["raw", {"type": "text", "text": "hello"}]}]
    out = rev(msgs)
    assert out == [{"role": "user", "type": "message",
                    "content": [{"type": "input_text", "text": "hello"}]}]


def test_forward_screenshot_lookahead_skips_string_entry():
    msgs = [
        {"role": "tool", "tool_call_id": "c1",
         "content": "[Execution completed. See screenshot below]"},
        {"role": "user",
         "content": ["raw", {"type": "image_url",
                             "image_url": {"url": "http://x/img.png"}}]},
    ]
    out = rev(msgs)
    assert out == [{"type": "computer_call_output", "call_id": "c1",
                    "output": {"type": "input_image",
                               "image_url": "http://x/img.png"}}]


def test_well_formed_roundtrip_unchanged():
    msgs = [{"type": "function_call", "call_id": "c1", "name": "computer",
             "arguments": '{"type": "click", "x": 1, "y": 2}'}]
    out = fwd(msgs)
    assert out[0]["tool_calls"][0]["function"]["name"] == "computer"

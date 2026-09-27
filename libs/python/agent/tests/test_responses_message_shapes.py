"""Non-dict entries in message lists must not crash message transforms.

The run loop tolerates non-dict output entries, so they can reach the
message transforms applied to combined history:

- ``replace_failed_computer_calls_with_function_calls`` called
  ``msg.get("type")`` on every message; a non-dict entry raised
  AttributeError.
- ``convert_computer_calls_desc2xy`` called ``item.get("type")`` on every
  item and ``item["action"].copy()`` on the action; non-dict items or a
  non-dict action raised AttributeError.

Fix: skip non-dict entries (preserving them in place) and pass through
items whose action is not a dict.
"""
import importlib.util
import sys
import types
from pathlib import Path

RESPONSES = (
    Path(__file__).resolve().parents[3] / "python" / "agent" / "cua_agent"
    / "responses.py"
)


def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _dict_factory(**kw):
    return dict(kw)


def _load_responses():
    for key in [k for k in sys.modules if k.startswith("openai") or k == "resp_mod"]:
        del sys.modules[key]
    _mod("openai", __path__=[])
    _mod("openai.types", __path__=[])
    _mod("openai.types.responses", __path__=[])
    _mod("openai.types.responses.easy_input_message_param",
         EasyInputMessageParam=_dict_factory)
    _mod("openai.types.responses.response_computer_tool_call_param",
         ActionClick=_dict_factory, ActionDoubleClick=_dict_factory,
         ActionDrag=_dict_factory, ActionDragPath=_dict_factory,
         ActionKeypress=_dict_factory, ActionMove=_dict_factory,
         ActionScreenshot=_dict_factory, ActionScroll=_dict_factory,
         ActionWait=_dict_factory, ActionType=_dict_factory,
         PendingSafetyCheck=_dict_factory,
         ResponseComputerToolCallParam=_dict_factory)
    _mod("openai.types.responses.response_function_tool_call_param",
         ResponseFunctionToolCallParam=_dict_factory)
    _mod("openai.types.responses.response_input_image_param",
         ResponseInputImageParam=_dict_factory)
    _mod("openai.types.responses.response_output_message_param",
         ResponseOutputMessageParam=_dict_factory)
    _mod("openai.types.responses.response_output_text_param",
         ResponseOutputTextParam=_dict_factory)
    _mod("openai.types.responses.response_reasoning_item_param",
         ResponseReasoningItemParam=_dict_factory, Summary=_dict_factory)
    spec = importlib.util.spec_from_file_location("resp_mod", str(RESPONSES))
    m = importlib.util.module_from_spec(spec)
    sys.modules["resp_mod"] = m
    spec.loader.exec_module(m)
    return m


rm = _load_responses()


def test_replace_failed_calls_skips_non_dict_entries():
    msgs = [
        {"type": "function_call_output", "call_id": "c1"},
        {"type": "computer_call", "call_id": "c1",
         "action": {"type": "click", "x": 1, "y": 2}},
        "junk",
        None,
        42,
    ]
    out = rm.replace_failed_computer_calls_with_function_calls(msgs)
    assert out[2:] == ["junk", None, 42]
    assert out[1]["type"] == "function_call"
    assert out[0]["type"] == "function_call_output"


def test_replace_failed_calls_all_junk():
    assert rm.replace_failed_computer_calls_with_function_calls(["a", None]) == ["a", None]


def test_desc2xy_skips_non_dict_entries():
    items = [
        {"type": "computer_call",
         "action": {"type": "click", "element_description": "btn"}},
        "junk",
        None,
    ]
    out = rm.convert_computer_calls_desc2xy(items, {"btn": (10, 20)})
    assert out[1:] == ["junk", None]
    assert (out[0]["action"]["x"], out[0]["action"]["y"]) == (10, 20)


def test_desc2xy_non_dict_action_passthrough():
    items = [{"type": "computer_call", "action": "click"}]
    assert rm.convert_computer_calls_desc2xy(items, {}) == items


def test_desc2xy_valid_conversion():
    items = [{"type": "computer_call",
              "action": {"type": "click", "element_description": "btn"}}]
    out = rm.convert_computer_calls_desc2xy(items, {"btn": (10, 20)})
    assert (out[0]["action"]["x"], out[0]["action"]["y"]) == (10, 20)
    assert "element_description" not in out[0]["action"]

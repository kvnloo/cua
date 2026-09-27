"""Tests for malformed model coordinates in the Gemini / Yutori / UITARS-2 loops.

All three loops turn model-generated text into coordinates with unguarded
``int(...)`` / ``float(...)`` conversions. On base, a malformed model value
crashed the step:

- ``gemini._map_gemini_fc_to_computer_call``: ``int(args.get("x"))`` raised
  ``ValueError`` on values like ``"abc"``; ``args`` itself could be a
  non-dict, whose ``.get`` raised ``AttributeError``.
- ``yutori._convert_n1_action_to_computer_action``: ``_unnormalize_coordinates``
  did ``coords[0] / N1_COORD_SPACE`` on arbitrary JSON elements (``TypeError``
  on strings); ``int(args.get("amount", 3))`` raised ``ValueError`` on
  ``"abc"``.
- ``uitars2._to_response_items``: the permissive ``([\\-\\d\\.]+)`` regex
  matches strings ``float()`` rejects (``"1.2.3"``, ``"."``), and the
  unguarded ``float(...)`` raised ``ValueError``.

The fix degrades instead of crashing: malformed coordinates drop the action
(the model retries next step); malformed magnitudes fall back to the
documented default; non-object arguments are ignored.

The real ``gemini.py``, ``yutori.py``, and ``uitars2.py`` are loaded with the
litellm / openai type imports stubbed (typing-only), so these tests exercise
the shipped code, not a mirror.
"""

import importlib.util
import sys
import types

import pytest


def _stub_openai():
    """Stub openai.types.responses classes as kwargs-accepting containers."""

    def _mk(name):
        cls = type(name, (), {})

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        cls.__init__ = __init__
        return cls

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
            setattr(mod, cls_name, _mk(cls_name))
        sys.modules[f"openai.types.responses.{mod_name}"] = mod
    sys.modules["openai"] = stub_openai
    sys.modules["openai.types"] = stub_types
    sys.modules["openai.types.responses"] = stub_responses


def _stub_litellm():
    litellm = types.ModuleType("litellm")
    litellm.acompletion = None
    resp = types.ModuleType("litellm.responses")
    trans = types.ModuleType("litellm.responses.litellm_completion_transformation")
    inner = types.ModuleType(
        "litellm.responses.litellm_completion_transformation.transformation"
    )

    class LiteLLMCompletionResponsesConfig:
        @staticmethod
        def _transform_chat_completion_usage_to_responses_usage(u):
            class U:
                def model_dump(self):
                    return {}

            return U()

    inner.LiteLLMCompletionResponsesConfig = LiteLLMCompletionResponsesConfig
    sys.modules["litellm"] = litellm
    sys.modules["litellm.responses"] = resp
    sys.modules["litellm.responses.litellm_completion_transformation"] = trans
    sys.modules[
        "litellm.responses.litellm_completion_transformation.transformation"
    ] = inner


def _load(agent_dir, mod_name, rel_path):
    path = f"{agent_dir}/{rel_path}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _load_modules():
    import pathlib

    agent_dir = str(pathlib.Path(__file__).resolve().parents[1])
    _stub_openai()
    _stub_litellm()

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = [f"{agent_dir}/cua_agent"]
    sys.modules["cua_agent"] = pkg
    loops_pkg = types.ModuleType("cua_agent.loops")
    loops_pkg.__path__ = [f"{agent_dir}/cua_agent/loops"]
    sys.modules["cua_agent.loops"] = loops_pkg

    dec = types.ModuleType("cua_agent.decorators")

    def register_agent(**kwargs):
        def wrap(cls):
            return cls

        return wrap

    dec.register_agent = register_agent
    sys.modules["cua_agent.decorators"] = dec

    base = types.ModuleType("cua_agent.loops.base")

    class AsyncAgentConfig:
        pass

    base.AsyncAgentConfig = AsyncAgentConfig
    sys.modules["cua_agent.loops.base"] = base

    typ = types.ModuleType("cua_agent.types")
    typ.AgentCapability = str
    typ.AgentResponse = object
    typ.Messages = list
    typ.Tools = list
    sys.modules["cua_agent.types"] = typ

    _load(agent_dir, "cua_agent.responses", "cua_agent/responses.py")
    _load(agent_dir, "cua_agent.loops.omniparser", "cua_agent/loops/omniparser.py")
    gemini = _load(agent_dir, "cua_agent.loops.gemini", "cua_agent/loops/gemini.py")
    yutori = _load(agent_dir, "cua_agent.loops.yutori", "cua_agent/loops/yutori.py")
    uitars2 = _load(agent_dir, "cua_agent.loops.uitars2", "cua_agent/loops/uitars2.py")
    return gemini, yutori, uitars2


_gemini, _yutori, _uitars2 = _load_modules()

_gemini_map = _gemini._map_gemini_fc_to_computer_call
_yutori_convert = _yutori._convert_n1_action_to_computer_action
_uitars2_items = _uitars2._to_response_items

W, H = 1920, 1080


# ---------------------------------------------------------------- Gemini


def test_gemini_click_at_malformed_coords_dropped():
    # On base this raised ValueError from int("abc").
    assert (
        _gemini_map({"name": "click_at", "args": {"x": "abc", "y": 500}}, W, H) is None
    )


def test_gemini_click_at_valid_coords():
    item = _gemini_map({"name": "click_at", "args": {"x": 500, "y": 500}}, W, H)
    assert item["type"] == "computer_call"
    action = item["action"]
    assert action["type"] == "click"
    assert action["x"] == 960
    assert action["y"] == 540


def test_gemini_non_dict_args_dropped():
    # On base this raised AttributeError from "click".get.
    assert _gemini_map({"name": "click_at", "args": "click"}, W, H) is None


def test_gemini_scroll_malformed_magnitude_uses_default():
    # On base this raised ValueError from int("abc").
    item = _gemini_map(
        {
            "name": "scroll_at",
            "args": {"x": 500, "y": 500, "direction": "down", "magnitude": "abc"},
        },
        W,
        H,
    )
    assert item["action"]["scroll_y"] == 800


def test_gemini_type_text_at_malformed_coords_dropped():
    assert (
        _gemini_map(
            {"name": "type_text_at", "args": {"x": None, "y": 500, "text": "hi"}},
            W,
            H,
        )
        is None
    )


def test_gemini_drag_malformed_destination_dropped():
    # On base this raised ValueError from int("1.2.3").
    assert (
        _gemini_map(
            {
                "name": "drag_and_drop",
                "args": {"x": 500, "y": 500, "destination_x": "1.2.3", "destination_y": 500},
            },
            W,
            H,
        )
        is None
    )


# ---------------------------------------------------------------- Yutori


def test_yutori_left_click_non_numeric_coords_dropped():
    # On base this raised TypeError from "abc" / N1_COORD_SPACE.
    assert (
        _yutori_convert("left_click", {"coordinates": ["abc", 500]}, W, H) is None
    )


def test_yutori_left_click_valid_coords():
    item = _yutori_convert("left_click", {"coordinates": [500, 500]}, W, H)
    assert item == {"action": "left_click", "x": 960, "y": 540}


def test_yutori_scroll_malformed_amount_uses_default():
    # On base this raised ValueError from int("abc").
    item = _yutori_convert(
        "scroll", {"direction": "down", "amount": "abc"}, W, H
    )
    assert item["action"] == "scroll"
    assert item["scroll_y"] == 300


def test_yutori_drag_non_numeric_start_coords_dropped():
    # On base this raised TypeError in _unnormalize_coordinates.
    assert (
        _yutori_convert(
            "drag",
            {"coordinates": [500, 500], "start_coordinates": ["x", "y"]},
            W,
            H,
        )
        is None
    )


def test_yutori_non_dict_args_do_not_crash():
    # A provider tool_calls entry carrying a non-object value for args.
    assert _yutori_convert("left_click", ["not", "a", "dict"], W, H) is None


# --------------------------------------------------------------- UITARS-2


def _action(fn, point, extra=None):
    params = {"point": point}
    if extra:
        params.update(extra)
    return {"function": fn, "parameters": params}


def test_uitars2_click_malformed_point_skipped():
    # "1.2.3" matches the permissive regex but float() rejects it; on base
    # this raised ValueError and killed the step.
    items = _uitars2_items([_action("click", "<point>1.2.3 4</point>")], set(), W, H)
    assert items == []


def test_uitars2_click_valid_point():
    items = _uitars2_items([_action("click", "<point>500 500</point>")], set(), W, H)
    assert len(items) == 1
    assert items[0].action.x == 960
    assert items[0].action.y == 540


def test_uitars2_move_malformed_point_skipped():
    items = _uitars2_items([_action("move_to", "<point>. .</point>")], set(), W, H)
    assert items == []


def test_uitars2_drag_malformed_point_skipped():
    actions = [
        {
            "function": "drag",
            "parameters": {"start_point": "1.2.3 4", "end_point": "5 6"},
        }
    ]
    items = _uitars2_items(actions, set(), W, H)
    assert items == []


def test_uitars2_scroll_malformed_point_uses_center():
    items = _uitars2_items(
        [_action("scroll", "<point>1.2.3 4</point>", {"direction": "down"})],
        set(),
        W,
        H,
    )
    assert len(items) == 1
    assert items[0].action.x == 960
    assert items[0].action.y == 540

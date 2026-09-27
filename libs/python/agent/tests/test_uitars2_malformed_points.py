"""Malformed UITARS point strings must be skipped, not crash the step.

``_to_response_items`` parsed model-emitted ``<point>x y</point>`` values
with ``float()`` on regex captures. The ``[\\-\\d.]+`` pattern also matches
non-numeric strings like "1.2.3", "-", ".", or "--5", and ``float()`` raised
ValueError on all of them — killing the whole step for a single malformed
action in click, move_to, drag, and scroll branches.

Fix: a ``_parse_point_floats`` helper validates the two captures as finite
floats and returns None when unusable. Malformed click/move/drag actions are
skipped; a malformed scroll point falls back to the viewport center, matching
the existing no-point fallback.
"""
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[3] / "python" / "agent" / "cua_agent"


def _mod(name, path=None, **attrs):
    m = types.ModuleType(name)
    if path is not None:
        m.__path__ = path
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _dict_factory(**kw):
    return dict(kw)


def _install_stubs():
    class BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _deco(*a, **k):
        def wrap(f):
            return f

        return wrap

    _mod("pydantic", BaseModel=BaseModel, field_validator=_deco,
         model_validator=_deco)
    _mod("litellm", path=[], acompletion=None,
         ResponseInputParam=dict, ResponsesAPIResponse=dict, ToolParam=dict)
    _mod("litellm.responses", path=[])
    _mod("litellm.responses.litellm_completion_transformation", path=[])
    _mod("litellm.responses.litellm_completion_transformation.transformation",
         LiteLLMCompletionResponsesConfig=object)
    _mod("litellm.responses.utils", path=[], Usage=dict)
    _mod("litellm.types", path=[])
    _mod("litellm.types.utils", path=[], ModelResponse=dict)
    _mod("openai", path=[])
    _mod("openai.types", path=[])
    _mod("openai.types.responses", path=[])
    for mod, names in {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": [
            "ResponseComputerToolCallParam", "ActionClick", "ActionDoubleClick",
            "ActionDrag", "ActionDragPath", "ActionKeypress", "ActionMove",
            "ActionScreenshot", "ActionScroll", "ActionWait", "ActionType",
            "PendingSafetyCheck",
        ],
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }.items():
        _mod(f"openai.types.responses.{mod}",
             **{n: _dict_factory for n in names})


def _pkg(name, path):
    m = types.ModuleType(name)
    m.__path__ = [path]
    m.__package__ = name
    sys.modules[name] = m
    return m


def _load(dotted, path):
    spec = importlib.util.spec_from_file_location(dotted, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = m
    spec.loader.exec_module(m)
    return m


def _load_uitars2():
    for key in [k for k in sys.modules if k == "cua_agent"
                or k.startswith(("cua_agent.", "pydantic", "litellm", "openai"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _pkg("cua_agent.loops", base + "/loops")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.loops.base", base + "/loops/base.py")
    _load("cua_agent.responses", base + "/responses.py")
    _load("cua_agent.loops.omniparser", base + "/loops/omniparser.py")
    return _load("cua_agent.loops.uitars2", base + "/loops/uitars2.py")


u2 = _load_uitars2()


def _items(fn, params, **kw):
    kw.setdefault("width", 1920)
    kw.setdefault("height", 1080)
    return u2._to_response_items([{"function": fn, "parameters": params}], **kw)


def test_malformed_click_points_are_skipped():
    for bad in ("<point>1.2.3 4</point>", "<point>- 5</point>",
                "<point>. 5</point>", "<point>--5 6</point>", "abc"):
        assert _items("click", {"point": bad}) == [], bad


def test_malformed_move_and_drag_are_skipped():
    assert _items("move_to", {"point": "<point>--5 6</point>"}) == []
    assert _items("drag", {"start_point": "<point>1..2 3</point>",
                           "end_point": "<point>4 5</point>"}) == []


def test_malformed_scroll_point_falls_back_to_center():
    items = _items("scroll", {"direction": "down", "point": "<point>3.4.5 6</point>"})
    assert len(items) == 1
    assert (items[0]["action"]["x"], items[0]["action"]["y"]) == (960, 540)


def test_valid_points_still_convert():
    items = _items("click", {"point": "<point>500 500</point>"})
    assert len(items) == 1
    assert (items[0]["action"]["x"], items[0]["action"]["y"]) == (960, 540)
    items = _items("click", {"point": "500 500"})
    assert len(items) == 1

"""Malformed Yutori n1 model output must degrade gracefully, not crash the step.

``_convert_n1_action_to_computer_action`` divided raw model coordinate
elements by the coordinate space with no validation: string elements raised
TypeError, and a non-dict ``args`` raised AttributeError at ``args.get``.
The scroll path called ``int(args.get("amount", 3))`` unguarded, so a
non-numeric amount raised ValueError. In predict_step, non-dict tool-call or
function entries raised AttributeError, and non-object parsed arguments
reached the converter unchecked.

Fix: a ``_finite_coord_pair`` gate rejects non-sequences, booleans,
unparseable values, and non-finite values; malformed coordinates make the
converter return None (no action) instead of crashing. The scroll amount
falls back to the default on unparseable values, and non-dict tool-call /
function / argument payloads are skipped or normalized at each call site so
the run continues on the model's text.
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
    _mod("PIL", path=[], Image=type("Image", (), {"LANCZOS": 1, "open": staticmethod(lambda *a, **k: None)}))


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


def _load_yutori():
    for key in [k for k in sys.modules if k == "cua_agent"
                or k.startswith(("cua_agent.", "pydantic", "litellm", "openai", "PIL"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _pkg("cua_agent.loops", base + "/loops")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.loops.base", base + "/loops/base.py")
    _load("cua_agent.responses", base + "/responses.py")
    return _load("cua_agent.loops.yutori", base + "/loops/yutori.py")


yu = _load_yutori()
W, H = 1920, 1080


def _convert(fn_name, args):
    return yu._convert_n1_action_to_computer_action(fn_name, args, W, H)


def test_malformed_coordinates_yield_no_action():
    for bad in (["a", "b"], {"x": 1}, "12", [True, False],
                [float("inf"), 5], [float("nan"), 1]):
        assert _convert("left_click", {"coordinates": bad}) is None, bad


def test_non_dict_args_yield_no_action():
    assert _convert("left_click", "left_click") is None
    assert _convert("left_click", None) is None


def test_scroll_bad_amount_falls_back_to_default():
    out = _convert("scroll", {"amount": "many"})
    assert out["scroll_y"] == 300
    out = _convert("scroll", {"amount": None})
    assert out["scroll_y"] == 300


def test_drag_malformed_start_coords_yield_no_action():
    assert _convert("drag", {"start_coordinates": ["a", "b"],
                             "coordinates": [500, 500]}) is None


def test_valid_coordinates_convert():
    out = _convert("left_click", {"coordinates": [500, 500]})
    assert (out["x"], out["y"]) == (960, 540)
    out = _convert("scroll", {"amount": 2})
    assert out["scroll_y"] == 200

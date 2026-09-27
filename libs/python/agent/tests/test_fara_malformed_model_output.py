"""Malformed FARA model output must degrade gracefully, not crash the step.

FARA's loop parsed model-controlled values without guards:

- ``_scale_fara_coordinates`` called ``float(coord[0])`` on raw model output.
  String elements raised ValueError; a non-dict ``args`` raised
  AttributeError. Infinite values were clamped into garbage coordinates and
  booleans (True -> 1.0) scaled silently.
- ``_fara_args_to_sdk_item`` indexed ``coordinate`` directly: None raised
  TypeError, a dict raised KeyError, and a string produced character indexing
  (x="a"). Infinite coordinates flowed into the click item unchecked.
- Priority-1 predict_step crashed on non-dict ``arguments`` at
  ``args.get("action")``; priority-2 (Ollama Cloud) only caught
  JSONDecodeError, so ``json.loads(None)`` / non-object JSON escaped; and
  non-dict ``function`` entries raised AttributeError.
- ``predict_click`` called ``int(coord[0])`` on unvalidated model output.

Fix: a ``_finite_coord_pair`` gate rejects non-sequences, booleans,
unparseable values, and non-finite values. Malformed coordinates are dropped
from the args instead of scaling, SDK items default to (0, 0) when the
coordinate is unusable, and non-dict arguments are skipped/ignored at each
call site so the run continues.
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

    _mod("litellm", path=[],
         acompletion=None,
         ResponseInputParam=dict,
         ResponsesAPIResponse=dict,
         ToolParam=dict)
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
    action_names = [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionWait", "ActionType", "PendingSafetyCheck",
        "ResponseComputerToolCallParam", "EasyInputMessageParam",
        "ResponseInputImageParam", "ResponseOutputMessageParam",
        "ResponseOutputTextParam", "ResponseReasoningItemParam", "Summary",
        "ResponseFunctionToolCallParam",
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


def _load_fara_config():
    for key in [k for k in sys.modules if k == "cua_agent"
                or k.startswith(("cua_agent.", "pydantic", "litellm", "openai"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _pkg("cua_agent.loops", base + "/loops")
    _pkg("cua_agent.loops.fara", base + "/loops/fara")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.loops.base", base + "/loops/base.py")
    _load("cua_agent.responses", base + "/responses.py")
    _load("cua_agent.loops.fara.schema", base + "/loops/fara/schema.py")
    _load("cua_agent.loops.fara.helpers", base + "/loops/fara/helpers.py")
    return _load("cua_agent.loops.fara.config", base + "/loops/fara/config.py")


fc = _load_fara_config()
DIMS = ((100, 100), (50, 50))  # original (w,h), resized (w,h)


def test_scale_drops_string_coordinate():
    out = fc._scale_fara_coordinates({"action": "left_click", "coordinate": ["abc", "def"]},
                                     *DIMS)
    assert "coordinate" not in out
    assert out["action"] == "left_click"


def test_scale_drops_bool_and_inf_coordinates():
    assert "coordinate" not in fc._scale_fara_coordinates({"coordinate": [True, False]}, *DIMS)
    assert "coordinate" not in fc._scale_fara_coordinates({"coordinate": [float("inf"), 5]}, *DIMS)


def test_scale_non_dict_args_passthrough():
    assert fc._scale_fara_coordinates("left_click", *DIMS) == "left_click"


def test_scale_valid_coordinates():
    out = fc._scale_fara_coordinates({"coordinate": [25, 25]}, *DIMS)
    assert out["coordinate"] == [50, 50]


def test_sdk_item_defaults_on_malformed_coordinate():
    for bad in (None, {"x": 1}, "abc", [float("inf"), 5], [True, False]):
        item = fc._fara_args_to_sdk_item({"action": "left_click", "coordinate": bad})
        assert item["action"]["x"] == 0, bad
        assert item["action"]["y"] == 0, bad


def test_sdk_item_keeps_valid_coordinate():
    item = fc._fara_args_to_sdk_item({"action": "left_click", "coordinate": [10, 20]})
    assert item["action"]["x"] == 10
    assert item["action"]["y"] == 20


def test_sdk_item_non_dict_args_returns_none():
    assert fc._fara_args_to_sdk_item("left_click") is None


def test_sdk_item_drag_malformed_coords():
    item = fc._fara_args_to_sdk_item({"action": "left_click_drag",
                                      "start_coordinate": None,
                                      "end_coordinate": {"x": 1}})
    assert item["action"]["path"] == [{"x": 0, "y": 0}, {"x": 0, "y": 0}]

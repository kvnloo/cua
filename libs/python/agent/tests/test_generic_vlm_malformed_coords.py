"""Malformed model coordinates must degrade gracefully, not crash the step.

``generic_vlm._unnormalize_coordinate`` and its ``qwen35`` twin called
``float(coord[0])`` on raw model output: string elements raised ValueError,
a non-dict ``args`` raised AttributeError at ``args.get``. Booleans scaled
silently (True -> 1.0) and infinite values were clamped into garbage
coordinates. The priority-1 path passed non-dict ``arguments`` straight
through, and the priority-2 (Ollama Cloud) path only caught JSONDecodeError,
so ``json.loads(None)`` / non-object JSON escaped and killed the run.

Fix: a ``_finite_coord_pair`` gate rejects non-sequences, booleans,
unparseable values, and non-finite values. Malformed coordinates are dropped
from args instead of scaling, non-dict arguments are skipped at each call
site, and the priority-2 parser tolerates non-string/non-object payloads.
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


def _load_modules():
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
    return (
        _load("cua_agent.loops.generic_vlm", base + "/loops/generic_vlm.py"),
        _load("cua_agent.loops.qwen35", base + "/loops/qwen35.py"),
    )


import asyncio  # noqa: E402

gv, q3 = _load_modules()
DIMS = (1920, 1080)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_unnormalize_drops_malformed_coordinates():
    for mod in (gv, q3):
        for bad in (["abc", "def"], [True, False], [float("inf"), 5],
                    [float("nan"), 1], "12"):
            out = _run(mod._unnormalize_coordinate({"action": "left_click",
                                                    "coordinate": bad}, DIMS))
            assert "coordinate" not in out, (mod.__name__, bad)
            assert out["action"] == "left_click"
        # Absent (None) coordinate passes through unchanged.
        out = _run(mod._unnormalize_coordinate({"action": "left_click",
                                                "coordinate": None}, DIMS))
        assert out["coordinate"] is None


def test_unnormalize_non_dict_args_passthrough():
    for mod in (gv, q3):
        assert _run(mod._unnormalize_coordinate("left_click", DIMS)) == "left_click"


def test_unnormalize_valid_coordinates():
    for mod in (gv, q3):
        out = _run(mod._unnormalize_coordinate({"coordinate": [500, 500]}, DIMS))
        assert out["coordinate"] == [960, 540]


def test_unnormalize_numeric_string_coordinates():
    for mod in (gv, q3):
        out = _run(mod._unnormalize_coordinate({"coordinate": ["500", "500"]}, DIMS))
        assert out["coordinate"] == [960, 540]

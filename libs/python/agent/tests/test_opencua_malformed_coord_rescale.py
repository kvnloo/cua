"""Malformed model output in the OpenCUA loop must degrade, not kill the step.

opencua.predict_step parsed model-generated tool arguments in two paths with
unguarded numeric conversions:

- Priority 2 (<tool_call> XML): ``raw_args.get("coordinate")`` raised
  AttributeError on truthy non-dict arguments, and
  ``int(round(float(coord[0])))`` raised ValueError/TypeError/OverflowError on
  malformed coordinate elements.
- Priority 3 (tool_calls array): ``args.get("coordinate")`` raised
  AttributeError on valid-but-non-object JSON arguments, with the same
  unguarded float() conversions on coordinate elements.

Fix: ``_finite_coord_pair`` validates coordinate pairs (rejects non-sequences,
bools, unparseable and non-finite elements); non-dict arguments and unusable
coordinates degrade to the plain-text path / text items instead of raising.
"""
import asyncio
import base64
import io
import json
import sys
import types
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3] / "python" / "agent" / "cua_agent"
PKG = str(REPO)


def _modpath(*names, path=None):
    prev = None
    for n in names:
        m = types.ModuleType(n)
        if path:
            m.__path__ = path
        sys.modules[n] = m
        if prev is not None:
            setattr(prev, n.split(".")[-1], m)
        prev = m
    return prev


def _install_stubs():
    litellm = _modpath("litellm", path=[])
    litellm.acompletion = None
    litellm.ResponseInputParam = object
    litellm.ResponsesAPIResponse = object
    litellm.ToolParam = object
    trans = _modpath(
        "litellm.responses",
        "litellm.responses.litellm_completion_transformation",
        "litellm.responses.litellm_completion_transformation.transformation",
    )

    class _Usage:
        def model_dump(self):
            return {}

    trans.LiteLLMCompletionResponsesConfig = type(
        "LiteLLMCompletionResponsesConfig",
        (),
        {
            "_transform_chat_completion_usage_to_responses_usage": staticmethod(
                lambda u: _Usage()
            )
        },
    )

    pyd = _modpath("pydantic", path=[])
    pyd.BaseModel = object

    _modpath("openai", path=[])
    _modpath("openai.types", path=[])
    _modpath("openai.types.responses", path=[])
    needs = {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": [
            "ResponseComputerToolCallParam",
            "ResponseComputerToolCall",
            "ActionClick",
            "ActionDoubleClick",
            "ActionDrag",
            "ActionDragPath",
            "ActionKeypress",
            "ActionMove",
            "ActionScreenshot",
            "ActionScroll",
            "ActionType",
            "ActionTypeAction",
            "ActionWait",
            "PendingSafetyCheck",
            "Summary",
        ],
        "response_function_tool_call_param": [
            "ResponseFunctionToolCallParam",
            "ResponseFunctionToolCall",
        ],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }
    for mod, names in needs.items():
        m = _modpath(f"openai.types.responses.{mod}")
        for n in names:
            setattr(m, n, type(n, (), {}))

    # qwen-agent (used by _build_nous_system) and qwen-vl-utils (smart_resize)
    _modpath("qwen_agent", path=[])
    _modpath("qwen_agent.llm", path=[])
    _modpath("qwen_agent.llm.fncall_prompts", path=[])
    nfp = _modpath("qwen_agent.llm.fncall_prompts.nous_fncall_prompt", path=[])

    class _ContentItem:
        def __init__(self, text=None, **kw):
            self.text = text or ""

    class _Message:
        def __init__(self, role=None, content=None, **kw):
            self.role = role
            self.content = content or []

        def model_dump(self):
            return {
                "content": [
                    {"text": c.text if hasattr(c, "text") else c} for c in self.content
                ]
            }

    class _Prompt:
        def preprocess_fncall_messages(self, messages=None, functions=None, lang=None, **kw):
            return [_Message(role="system", content=[_ContentItem(text="sys")])]

    nfp.ContentItem = _ContentItem
    nfp.Message = _Message
    nfp.NousFnCallPrompt = _Prompt
    qvu = _modpath("qwen_vl_utils", path=[])
    qvu.smart_resize = lambda h, w, **kw: (h, w)


def _load_modules():
    for pkg in ("cua_agent", "cua_agent.loops"):
        m = types.ModuleType(pkg)
        m.__path__ = [PKG if pkg == "cua_agent" else PKG + "/loops"]
        sys.modules[pkg] = m
    dec = types.ModuleType("cua_agent.decorators")
    dec.register_agent = lambda *a, **k: (lambda c: c)
    sys.modules["cua_agent.decorators"] = dec
    cg = types.ModuleType("cua_agent.loops.composed_grounded")
    cg.ComposedGroundedConfig = type("ComposedGroundedConfig", (), {})
    sys.modules["cua_agent.loops.composed_grounded"] = cg

    def load(fullname, rel):
        spec = importlib.util.spec_from_file_location(fullname, PKG + "/" + rel)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = mod
        spec.loader.exec_module(mod)
        return mod

    load("cua_agent.types", "types.py")
    load("cua_agent.responses", "responses.py")
    load("cua_agent.loops.base", "loops/base.py")
    load("cua_agent.loops.generic_vlm", "loops/generic_vlm.py")
    return load("cua_agent.loops.opencua", "loops/opencua.py")


_install_stubs()
opencua = _load_modules()

import litellm  # noqa: E402  (stubbed above)

# --- fake litellm response plumbing -----------------------------------------

NEXT_MSG = {}


class _FakeResp:
    usage = None
    _hidden_params = {"response_cost": 0.0}

    def __init__(self, msg):
        self._msg = msg

    def model_dump(self):
        return {"choices": [{"message": self._msg}]}


async def _fake_acompletion(**kw):
    return _FakeResp(NEXT_MSG)


litellm.acompletion = _fake_acompletion

from PIL import Image  # noqa: E402

_buf = io.BytesIO()
Image.new("RGB", (4, 4)).save(_buf, format="PNG")
_IMG = base64.b64encode(_buf.getvalue()).decode()
MSGS = [
    {
        "role": "user",
        "content": [
            {"type": "input_image", "image_url": "data:image/png;base64," + _IMG}
        ],
    }
]


def _run_predict(msg):
    NEXT_MSG.clear()
    NEXT_MSG.update(msg)
    cfg = opencua.OpenCUAConfig()
    return asyncio.run(cfg.predict_step(MSGS, model="opencua/x", tools=None, max_retries=1))


def _p2(args_json):
    return {
        "content": '<tool_call>{"name":"computer","arguments":%s}</tool_call>' % args_json,
        "tool_calls": [],
    }


def _p3(args_str):
    return {
        "content": "",
        "tool_calls": [
            {
                "type": "function",
                "id": "call_0",
                "function": {"name": "computer", "arguments": args_str},
            }
        ],
    }


# --- red-on-base evidence ----------------------------------------------------

MALFORMED = [
    ("p2 non-dict args (string)", _p2('"click"')),
    ("p2 non-dict args (list)", _p2('["click"]')),
    ("p2 non-dict args (null)", _p2("null")),
    ("p2 non-dict args (number)", _p2("42")),
    ("p2 malformed coord elems", _p2('{"coordinate":["abc","def"]}')),
    ("p2 coord None elem", _p2('{"coordinate":[null,5]}')),
    ("p2 coord inf", _p2('{"coordinate":["1e999","2e999"]}')),
    ("p2 coord nan", _p2('{"coordinate":["nan","nan"]}')),
    ("p2 coord bool", _p2('{"coordinate":[true,false]}')),
    ("p3 non-object args (string)", _p3('"click"')),
    ("p3 non-object args (list)", _p3('["click"]')),
    ("p3 malformed coord elems", _p3('{"coordinate":["abc","def"]}')),
    ("p3 coord inf", _p3('{"coordinate":["1e999","2e999"]}')),
]

CONTROLS = [
    ("p2 valid control", _p2('{"coordinate":[500,500]}')),
    ("p3 valid control", _p3('{"coordinate":[500,500]}')),
]


def test_malformed_degrades_without_raising():
    """Every malformed shape must return output items, never raise."""
    for name, msg in MALFORMED:
        out = _run_predict(msg)
        assert isinstance(out, dict) and out["output"], name


def test_valid_controls_still_rescale():
    """Positive controls keep working and produce tool calls."""
    for name, msg in CONTROLS:
        out = _run_predict(msg)
        assert out["output"], name
        kinds = [i.get("type") for i in out["output"]]
        assert any(k in ("computer_call", "function_call") for k in kinds), name


def test_finite_coord_pair_unit():
    f = opencua._finite_coord_pair
    assert f([500, 500]) == (500.0, 500.0)
    assert f(["400", "300"]) == (400.0, 300.0)
    assert f(("1.5", 2)) == (1.5, 2.0)
    assert f(["abc", "def"]) is None
    assert f([None, 5]) is None
    assert f([{"x": 1}, 5]) is None
    assert f(["1e999", "2e999"]) is None
    assert f(["nan", "nan"]) is None
    assert f([True, False]) is None
    assert f("click") is None
    assert f([500]) is None
    assert f(None) is None

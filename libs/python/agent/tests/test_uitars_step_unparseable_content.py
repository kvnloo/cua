"""UITARS predict_step must not raise on None/garbage model content.

``UITARSConfig.predict_step`` extracted the model reply with
``response.choices[0].message.content.strip()`` outside any try block —
a None content (model refusal/empty reply) raised AttributeError, and
``parse_uitars_response`` raised ValueError on content without an
"Action:" line. Both escaped ``predict_step`` (the only try/except in
that function wraps screen-dimension lookup), and the run loop only
retries transient errors, so one malformed model reply killed the run.

Fix: coerce content to ``""`` and wrap the parse/convert block in
try/except, degrading to an empty-output step instead of raising.
"""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "cua_agent"


def _mod(name, path=None, **attrs):
    m = types.ModuleType(name)
    if path is not None:
        m.__path__ = path
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


ACOMPLETION_CONTENT = ""


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]
        self.usage = object()
        self._hidden_params = {"response_cost": 0.0}


async def _fake_acompletion(**kwargs):
    return _Resp(ACOMPLETION_CONTENT)


def _install_stubs():
    class BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _deco(*a, **k):
        def wrap(f):
            return f

        return wrap

    class _Cfg:
        @staticmethod
        def _transform_chat_completion_usage_to_responses_usage(usage):
            class _U:
                def model_dump(self):
                    return {}

            return _U()

    _mod("pydantic", BaseModel=BaseModel, field_validator=_deco,
         model_validator=_deco)

    litellm = _mod("litellm", path=[], acompletion=_fake_acompletion,
                   aresponses=None, ResponseInputParam=dict,
                   ResponsesAPIResponse=dict, ToolParam=dict)
    _mod("litellm.responses", path=[])
    _mod("litellm.responses.utils", path=[], Usage=dict)
    _mod("litellm.types", path=[])
    _mod("litellm.types.utils", path=[], ModelResponse=dict)
    _mod("litellm.responses.litellm_completion_transformation", path=[])
    _mod("litellm.responses.litellm_completion_transformation.transformation",
         path=[], LiteLLMCompletionResponsesConfig=_Cfg)

    _mod("openai", path=[])
    _mod("openai.types", path=[])
    _mod("openai.types.responses", path=[])
    action_names = [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionWait", "ActionType", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ]
    def _factory(name):
        return type(name, (dict,), {"__init__": lambda self, **kw: dict.__init__(self, kw)})

    for mod, names in {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": action_names,
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_param": ["ComputerCallOutput"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }.items():
        _mod(f"openai.types.responses.{mod}",
             **{n: _factory(n) for n in names})

    litellm.__dict__.update({})

    pil = _mod("PIL", path=[])

    class _FakeImage:
        size = (100, 100)
        width = 100
        height = 100

        def resize(self, wh):
            return self

        def save(self, buf, format=None):
            buf.write(b"png")

    class _ImageMod(types.ModuleType):
        Image = _FakeImage

        @staticmethod
        def open(fp):
            return _FakeImage()

    sys.modules["PIL.Image"] = _ImageMod("PIL.Image")
    pil.Image = _ImageMod("PIL.Image")


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


def _load_uitars():
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
    return _load("cua_agent.loops.uitars", base + "/loops/uitars.py")


ut = _load_uitars()

try:
    cfg = ut.UITARSConfig()
except TypeError:
    cfg = ut.UITARSConfig.__new__(ut.UITARSConfig)

# Bypass image processing; the test targets the content-parse path only.
ut.process_image_for_uitars = lambda image_data: (object(), 100, 100)
ut.pil_to_base64 = lambda img: "AAAA"


def step(content):
    global ACOMPLETION_CONTENT
    ACOMPLETION_CONTENT = content
    messages = [
        {
            "type": "computer_call_output",
            "call_id": "c1",
            "output": {
                "type": "input_image",
                "image_url": "data:image/png;base64,AAAA",
            },
        }
    ]
    return asyncio.run(
        cfg.predict_step(messages=messages, model="x+uitars", tools=[])
    )


def test_none_content_returns_empty_step():
    res = step(None)
    assert isinstance(res, dict) and res["output"] == []


def test_empty_content_returns_empty_step():
    res = step("")
    assert isinstance(res, dict) and res["output"] == []


def test_garbage_content_returns_empty_step():
    res = step("no action here at all")
    assert isinstance(res, dict) and res["output"] == []


def test_valid_click_content_still_parses():
    res = step("Thought: click the button\nAction: click(start_box='<|box_start|>(500,500)<|box_end|>')")
    assert isinstance(res, dict) and len(res["output"]) > 0

"""None/empty model content must not crash Omniparser predict_click.

``OmniparserConfig.predict_click`` extracted the model reply with
``response.choices[0].message.content.strip()`` outside any try block —
a None content (model refusal, empty reply) raised AttributeError out
of predict_click, whose contract is to return None on failure.
Sibling loops (holo, internvl) already guard with ``(content or "")``.

Fix: ``(response.choices[0].message.content or "").strip()`` — None
content degrades to the existing ValueError/None path.
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


ACOMPLETION_CONTENT = "3"


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


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

    _mod("pydantic", BaseModel=BaseModel, field_validator=_deco,
         model_validator=_deco)

    _mod("litellm", path=[],
         acompletion=_fake_acompletion,
         aresponses=None,
         ResponseInputParam=dict,
         ResponsesAPIResponse=dict,
         ToolParam=dict)
    _mod("litellm.responses", path=[])
    _mod("litellm.responses.utils", path=[], Usage=dict)

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
             **{n: (lambda **kw: dict(kw)) for n in names})


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


def _load_omniparser():
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
    return _load("cua_agent.loops.omniparser", base + "/loops/omniparser.py")


om = _load_omniparser()


class _Bbox:
    def __init__(self):
        self.x1, self.y1, self.x2, self.y2 = 0, 0, 10, 20


class _El:
    def __init__(self, eid):
        self.id = eid
        self.bbox = _Bbox()


class _ParseResult:
    annotated_image_base64 = "aGVsbG8="
    elements = [_El(3)]


class _FakeParser:
    def parse(self, image_b64):
        return _ParseResult()


om.OMNIPARSER_AVAILABLE = True
om.get_parser = lambda: _FakeParser()

try:
    cfg = om.OmniparserConfig()
except TypeError:
    cfg = om.OmniparserConfig.__new__(om.OmniparserConfig)


def click(content):
    global ACOMPLETION_CONTENT
    ACOMPLETION_CONTENT = content
    return asyncio.run(cfg.predict_click(model="x+yutori",
                                         image_b64="aGVsbG8=",
                                         instruction="click it"))


def test_none_content_returns_none():
    assert click(None) is None


def test_empty_content_returns_none():
    assert click("") is None


def test_valid_element_id_returns_center():
    assert click("3") == (5.0, 10.0)


def test_unparseable_content_returns_none():
    assert click("abc") is None

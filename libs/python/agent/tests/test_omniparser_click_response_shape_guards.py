"""[muse] Degrade (don't crash) on malformed OmniParser predict_click responses.

Defect (fork main): OmniparserConfig.predict_click read
`response.choices[0].message.content.strip()` unguarded:
- provider returns zero choices -> IndexError out of a function contracted
  to return None on failure;
- provider returns a choice with message=None -> AttributeError.

(Sibling branch muse/omniparser-click-none-content covers None *content*;
this branch covers the empty-choices / None-message shapes.)

Fix: missing/empty choices or a missing message degrade to None.

Red-on-base: run this file against fork main (git checkout -- omniparser.py
after copying the fix aside); the malformed cases raise, the valid-ID
control passes on both.
"""
import asyncio
import importlib.util
import sys
import types as pytypes

REPO = "/home/hatch/workspace/scratch/cua-wt-muse-c58/libs/python/agent"


def _stub(name, **attrs):
    mod = pytypes.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load(pkg_name, file_path):
    spec = importlib.util.spec_from_file_location(pkg_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- stubs ------------------------------------------------------------------
class _FakeACompletion:
    response = None

    async def __call__(self, **kwargs):
        return _FakeACompletion.response


litellm = _stub("litellm", acompletion=_FakeACompletion())

pkg = _stub("cua_agent")
pkg.__path__ = [REPO + "/cua_agent"]
loops_pkg = _stub("cua_agent.loops")
loops_pkg.__path__ = [REPO + "/cua_agent/loops"]

_dict_param = type("DictParam", (dict,), {})
_openai = _stub("openai")
_openai_types = _stub("openai.types")
_openai_responses = _stub("openai.types.responses")
for _leaf, _names in {
    "openai.types.responses.easy_input_message_param": ["EasyInputMessageParam"],
    "openai.types.responses.response_computer_tool_call_param": [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionType", "ActionWait", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ],
    "openai.types.responses.response_function_tool_call_param": [
        "ResponseFunctionToolCallParam"
    ],
    "openai.types.responses.response_input_image_param": ["ResponseInputImageParam"],
    "openai.types.responses.response_output_message_param": [
        "ResponseOutputMessageParam"
    ],
    "openai.types.responses.response_output_text_param": ["ResponseOutputTextParam"],
    "openai.types.responses.response_reasoning_item_param": [
        "ResponseReasoningItemParam", "Summary"
    ],
}.items():
    _stub(_leaf, **{n: _dict_param for n in _names})

class _AgentConfigInfo:
    def __init__(self, *a, **k):
        for key, val in k.items():
            setattr(self, key, val)


_stub(
    "cua_agent.types",
    AgentCapability=str,
    AgentConfigInfo=_AgentConfigInfo,
    AgentResponse=object,
    Messages=object,
    Tools=object,
)

# ---- real modules -------------------------------------------------------------
_load("cua_agent.responses", REPO + "/cua_agent/responses.py")
_load("cua_agent.decorators", REPO + "/cua_agent/decorators.py")
_load("cua_agent.loops.base", REPO + "/cua_agent/loops/base.py")
omni = _load("cua_agent.loops.omniparser", REPO + "/cua_agent/loops/omniparser.py")


# ---- fakes --------------------------------------------------------------------
class FakeBBox:
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2


class FakeElement:
    def __init__(self, eid, bbox):
        self.id = eid
        self.bbox = bbox


class FakeParseResult:
    annotated_image_base64 = "ZmFrZQ=="
    elements = [FakeElement(3, FakeBBox(0, 0, 10, 20))]


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, choices):
        self.choices = choices


class FakeParser:
    def parse(self, image_b64):
        return FakeParseResult()


omni.OMNIPARSER_AVAILABLE = True
omni.get_parser = lambda: FakeParser()


def run_click(response):
    async def _go():
        _FakeACompletion.response = response
        cfg = omni.OmniparserConfig()
        return await cfg.predict_click(
            model="omniparser+gpt-4o", image_b64="ZmFrZQ==", instruction="the button"
        )

    return asyncio.run(_go())


def test_empty_choices_returns_none():
    assert run_click(FakeResponse([])) is None


def test_none_choices_returns_none():
    assert run_click(FakeResponse(None)) is None


def test_none_message_returns_none():
    assert run_click(FakeResponse([FakeChoice(None)])) is None


def test_valid_element_id_returns_center():
    assert run_click(FakeResponse([FakeChoice(FakeMessage("3"))])) == (5.0, 10.0)


def test_unparseable_id_returns_none():
    assert run_click(FakeResponse([FakeChoice(FakeMessage("nope"))])) is None


def test_unknown_element_id_returns_none():
    assert run_click(FakeResponse([FakeChoice(FakeMessage("99"))])) is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} green")
    sys.exit(1 if failed else 0)

"""Red-on-base tests: thinking-model response shape guards.

Defect (fork main): composed_grounded, moondream3 and omniparser predict_step
all did `choice_messages = [choice["message"] for choice in
response_dict["choices"]]` with no guards:
- missing "choices" key -> KeyError
- choices None / non-list -> TypeError
- non-dict choice -> TypeError
- choice missing "message" -> KeyError
- choice["message"] None -> AttributeError downstream in
  convert_completion_messages_to_responses_items

Fix: shared responses.iter_thinking_choice_messages() skips malformed
entries; all three loops use it.

Harness: real cua_agent.responses + real composed_grounded/moondream3 loop
modules with stubbed litellm / openai / cua_core / sibling submodules.
omniparser.predict_step needs the `som` package (unavailable here), so it is
covered by the shared-helper unit tests plus a source-level assertion that it
calls the helper.
"""

import asyncio
import importlib.util
import sys
import types as pytypes
from pathlib import Path

AGENT_PKG = Path(__file__).resolve().parents[1] / "cua_agent"
LOOPS_PKG = AGENT_PKG / "loops"


def _stub(name):
    mod = pytypes.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _pkg(name):
    mod = _stub(name)
    mod.__path__ = []
    return mod


def _ensure_harness():
    if "cua_agent.loops.composed_grounded" in sys.modules:
        return
    base = _pkg("cua_agent")
    base.__path__ = [str(AGENT_PKG)]

    openai = _stub("openai")
    otypes = _pkg("openai.types")
    oresp = _pkg("openai.types.responses")
    openai.types = otypes
    otypes.responses = oresp

    def _osub(name, names):
        m = _stub(f"openai.types.responses.{name}")
        for n in names:
            setattr(m, n, type(n, (), {}))
        setattr(oresp, name, m)

    _osub("easy_input_message_param", ["EasyInputMessageParam"])
    _osub(
        "response_computer_tool_call_param",
        [
            "ActionClick",
            "ActionDoubleClick",
            "ActionDrag",
            "ActionDragPath",
            "ActionKeypress",
            "ActionMove",
            "ActionScreenshot",
            "ActionScroll",
            "ActionType",
            "ActionWait",
            "PendingSafetyCheck",
            "ResponseComputerToolCallParam",
        ],
    )
    _osub("response_function_tool_call_param", ["ResponseFunctionToolCallParam"])
    _osub("response_input_image_param", ["ResponseInputImageParam"])
    _osub("response_output_message_param", ["ResponseOutputMessageParam"])
    _osub("response_output_text_param", ["ResponseOutputTextParam"])
    _osub("response_reasoning_item_param", ["ResponseReasoningItemParam", "Summary"])

    litellm = _stub("litellm")
    litellm_utils = _stub("litellm.utils")
    litellm_responses = _pkg("litellm.responses")
    litellm_responses_utils = _stub("litellm.responses.utils")

    class Usage:
        def __init__(self, prompt_tokens=0, completion_tokens=0, total_tokens=0):
            self.prompt_tokens = prompt_tokens
            self.completion_tokens = completion_tokens
            self.total_tokens = total_tokens

    litellm_responses_utils.Usage = Usage
    litellm.responses = litellm_responses
    litellm.utils = litellm_utils
    litellm_responses.utils = litellm_responses_utils

    cua_core = _pkg("cua_core")
    telemetry = _stub("cua_core.telemetry")
    telemetry.is_telemetry_enabled = lambda: False
    telemetry.record_event = lambda *a, **k: None
    cua_core.telemetry = telemetry

    adapters = _pkg("cua_agent.adapters")
    for n in (
        "AzureMLAdapter",
        "CUAAdapter",
        "HuggingFaceLocalAdapter",
        "HumanAdapter",
        "MLXVLMAdapter",
    ):
        setattr(adapters, n, type(n, (), {}))
    callbacks = _pkg("cua_agent.callbacks")
    for n in (
        "BudgetManagerCallback",
        "ImageRetentionCallback",
        "LoggingCallback",
        "OperatorNormalizerCallback",
        "OtelCallback",
        "PromptInstructionsCallback",
        "TelemetryCallback",
        "TrajectorySaverCallback",
    ):
        setattr(callbacks, n, type(n, (), {}))
    computers = _pkg("cua_agent.computers")
    computers.AsyncComputerHandler = type("AsyncComputerHandler", (), {})
    computers.is_agent_computer = lambda t: False
    computers.make_computer_handler = lambda *a, **k: None
    decorators = _pkg("cua_agent.decorators")

    def register_agent(*dargs, **dkwargs):
        def deco(cls):
            return cls

        return deco

    decorators.register_agent = register_agent
    decorators.find_agent_config = lambda model: None
    tools = _pkg("cua_agent.tools")
    tools_base = _stub("cua_agent.tools.base")
    tools_base.BaseComputerTool = type("BaseComputerTool", (), {})
    tools_base.BaseTool = type("BaseTool", (), {})
    tools.base = tools_base
    types_mod = _stub("cua_agent.types")
    types_mod.AgentCapability = str
    types_mod.IllegalArgumentError = type("IllegalArgumentError", (Exception,), {})
    types_mod.Messages = list
    types_mod.ToolError = type("ToolError", (Exception,), {})
    types_mod.AgentResponse = dict
    types_mod.Tools = list
    types_mod.AgentConfigInfo = type("AgentConfigInfo", (), {})
    loops = _pkg("cua_agent.loops")
    loops_base = _stub("cua_agent.loops.base")
    loops_base.AsyncAgentConfig = type("AsyncAgentConfig", (), {})
    loops.base = loops_base

    def _load_real(modname, path):
        spec = importlib.util.spec_from_file_location(modname, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        spec.loader.exec_module(mod)
        return mod

    _load_real("cua_agent.responses", AGENT_PKG / "responses.py")
    _load_real("cua_agent.agent", AGENT_PKG / "agent.py")
    _load_real("cua_agent.loops.composed_grounded", LOOPS_PKG / "composed_grounded.py")
    _load_real("cua_agent.loops.moondream3", LOOPS_PKG / "moondream3.py")


_ensure_harness()
responses = sys.modules["cua_agent.responses"]
litellm = sys.modules["litellm"]
iter_msgs = responses.iter_thinking_choice_messages

# Valid 4x4 PNG (moondream3 decodes the screenshot before the thinking call)
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGP8//8/AwwwMSAB"
    "3BwAlm4DBfIlvvkAAAAASUVORK5CYII="
)

SCREENSHOT_MSG = {
    "type": "computer_call_output",
    "call_id": "c1",
    "output": {
        "type": "input_image",
        "image_url": "data:image/png;base64," + PNG_B64,
    },
}

RESPONSE_SHAPES = {
    # degenerate shapes: must degrade to [] instead of raising
    "missing_choices": {},
    "none_choices": {"choices": None},
    "non_list_choices": {"choices": "oops"},
    "non_dict_choice": {"choices": ["nope"]},
    "missing_message": {"choices": [{"nope": 1}]},
    "none_message": {"choices": [{"message": None}]},
    "non_dict_message": {"choices": [{"message": "nope"}]},
    # well-formed shapes (controls)
    "valid": {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
    "valid_mixed": {
        "choices": [
            {"message": {"role": "assistant", "content": "hi"}},
            {"message": None},
            "junk",
        ]
    },
}


def test_helper_degenerate_shapes():
    for name in (
        "missing_choices",
        "none_choices",
        "non_list_choices",
        "non_dict_choice",
        "missing_message",
        "none_message",
        "non_dict_message",
    ):
        got = iter_msgs(RESPONSE_SHAPES[name])
        assert got == [], f"{name}: expected [], got {got}"


def test_helper_non_dict_response():
    assert iter_msgs(None) == []
    assert iter_msgs(["choices"]) == []


def test_helper_valid_shapes():
    got = iter_msgs(RESPONSE_SHAPES["valid"])
    assert got == [{"role": "assistant", "content": "hi"}]
    got = iter_msgs(RESPONSE_SHAPES["valid_mixed"])
    assert got == [{"role": "assistant", "content": "hi"}]


class _FakeUsage:
    def model_dump(self):
        return {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


class _FakeResp:
    def __init__(self, d):
        self._d = d
        self.usage = _FakeUsage()
        self._hidden_params = {"response_cost": 0.0}

    def model_dump(self):
        return self._d


def _run_step(loop_cls, model, response_dict):
    async def fake_acompletion(**kwargs):
        return _FakeResp(response_dict)

    litellm.acompletion = fake_acompletion
    loop = loop_cls()

    async def go():
        return await loop.predict_step(
            messages=[SCREENSHOT_MSG], model=model, tools=[]
        )

    return asyncio.run(go())


def _check_loop(loop_cls, model):
    for name in (
        "missing_choices",
        "none_choices",
        "non_list_choices",
        "non_dict_choice",
        "missing_message",
        "none_message",
        "non_dict_message",
    ):
        result = _run_step(loop_cls, model, RESPONSE_SHAPES[name])
        assert result["output"] == [], f"{loop_cls.__name__}/{name}: {result['output']}"
    # control: valid shape still produces items
    result = _run_step(loop_cls, model, RESPONSE_SHAPES["valid"])
    assert len(result["output"]) == 1, result
    assert result["output"][0]["type"] == "message"


def test_composed_grounded_predict_step():
    cg = sys.modules["cua_agent.loops.composed_grounded"]
    _check_loop(cg.ComposedGroundedConfig, "grounding+thinking")


def test_moondream3_predict_step():
    md = sys.modules["cua_agent.loops.moondream3"]
    # get_moondream_model() requires torch (not installed here); the
    # choice/message guard under test runs after detection, so stub it.
    md.get_moondream_model = lambda: object()
    md._annotate_detect_and_label_ui = lambda img, model: ("", [])
    _check_loop(md.Moondream3PlusConfig, "moondream3+thinking")


def test_omniparser_uses_helper():
    # omniparser.predict_step needs the `som` package (not installed here);
    # assert the identical one-line fix is in place at the source level.
    src = (LOOPS_PKG / "omniparser.py").read_text()
    assert "choice_messages = iter_thinking_choice_messages(response_dict)" in src
    assert 'choice["message"] for choice in response_dict["choices"]' not in src


if __name__ == "__main__":
    tests = [
        test_helper_degenerate_shapes,
        test_helper_non_dict_response,
        test_helper_valid_shapes,
        test_composed_grounded_predict_step,
        test_moondream3_predict_step,
        test_omniparser_uses_helper,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {str(e)[:160]}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

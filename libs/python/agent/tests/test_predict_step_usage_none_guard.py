"""Red/green tests: predict_step must survive a provider response with usage=None.

LiteLLM leaves ``response.usage`` as ``None`` for providers that do not report
token usage. Three loops (composed_grounded, moondream3, omniparser) expanded
``response.usage.model_dump()`` unconditionally, so a usage-less response
killed the whole run with AttributeError instead of degrading to empty usage.

Self-contained: stubs litellm + the openai.types.responses imports of
responses.py, loads the real responses.py (for the shared helper) and the
real loop modules by file path, and drives predict_step with a fake response.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

LOOPS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"
RESPONSES_PATH = LOOPS_DIR.parent / "responses.py"


def _install_stubs():
    # --- stub litellm -------------------------------------------------------
    litellm = types.ModuleType("litellm")

    class _FakeResponse:
        def __init__(self, usage=None, hidden_params=None):
            self.usage = usage
            if hidden_params is not None:
                self._hidden_params = hidden_params

        def model_dump(self):
            return {
                "choices": [{"message": {"role": "assistant", "content": "done"}}],
            }

    async def _acompletion(**kwargs):
        return _FakeResponse(usage=None)  # provider reported no usage

    litellm.acompletion = _acompletion
    litellm._FakeResponse = _FakeResponse
    sys.modules["litellm"] = litellm

    # --- stub openai.types.responses.* (imported by responses.py) -----------
    openai = types.ModuleType("openai")
    openai_types = types.ModuleType("openai.types")
    openai_responses = types.ModuleType("openai.types.responses")
    for name in [
        "easy_input_message_param",
        "response_computer_tool_call_param",
        "response_function_tool_call_param",
        "response_input_image_param",
        "response_output_message_param",
        "response_output_text_param",
        "response_reasoning_item_param",
    ]:
        sub = types.ModuleType(f"openai.types.responses.{name}")
        sys.modules[sub.__name__] = sub
        setattr(openai_responses, name, sub)
    # names imported from those submodules
    sys.modules["openai.types.responses.easy_input_message_param"].EasyInputMessageParam = dict
    rctc = sys.modules["openai.types.responses.response_computer_tool_call_param"]
    for _n in [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionType", "ActionWait", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ]:
        setattr(rctc, _n, dict)
    rftc = sys.modules["openai.types.responses.response_function_tool_call_param"]
    rftc.ResponseFunctionToolCallParam = dict
    rii = sys.modules["openai.types.responses.response_input_image_param"]
    rii.ResponseInputImageParam = dict
    rom = sys.modules["openai.types.responses.response_output_message_param"]
    rom.ResponseOutputMessageParam = dict
    rot = sys.modules["openai.types.responses.response_output_text_param"]
    rot.ResponseOutputTextParam = dict
    rri = sys.modules["openai.types.responses.response_reasoning_item_param"]
    rri.ResponseReasoningItemParam = dict
    rri.Summary = dict
    sys.modules["openai"] = openai
    sys.modules["openai.types"] = openai_types
    sys.modules["openai.types.responses"] = openai_responses

    # --- stub cua_agent package tree ----------------------------------------
    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    sys.modules["cua_agent"] = pkg
    loops_pkg = types.ModuleType("cua_agent.loops")
    loops_pkg.__path__ = []
    sys.modules["cua_agent.loops"] = loops_pkg

    decorators = types.ModuleType("cua_agent.decorators")

    def register_agent(models, priority=0, tool_type=None):
        def wrap(cls):
            return cls

        return wrap

    decorators.register_agent = register_agent
    sys.modules["cua_agent.decorators"] = decorators

    base = types.ModuleType("cua_agent.loops.base")

    class AsyncAgentConfig:
        pass

    base.AsyncAgentConfig = AsyncAgentConfig
    sys.modules["cua_agent.loops.base"] = base

    types_mod = types.ModuleType("cua_agent.types")
    types_mod.AgentCapability = str
    types_mod.AgentConfigInfo = dict
    types_mod.AgentResponse = dict
    types_mod.Messages = list
    types_mod.Tools = list
    sys.modules["cua_agent.types"] = types_mod

    agent_mod = types.ModuleType("cua_agent.agent")
    agent_mod.find_agent_config = lambda model: None
    sys.modules["cua_agent.agent"] = agent_mod


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_install_stubs()

# Real responses.py (contains the shared usage helper after the fix).
responses = _load("cua_agent.responses", RESPONSES_PATH)

# Neutralize the heavy convert helpers on the real responses module so the
# loops under test exercise only the usage-extraction path.
responses.convert_computer_calls_xy2desc = lambda messages, mapping: messages
responses.convert_responses_items_to_completion_messages = lambda messages, **kw: []
responses.convert_completion_messages_to_responses_items = lambda messages: [
    {"type": "message", "role": "assistant", "content": "done"}
]
responses.get_all_element_descriptions = lambda items: []
responses.convert_computer_calls_desc2xy = lambda items, mapping: items

cg = _load("cua_agent.loops.composed_grounded", LOOPS_DIR / "composed_grounded.py")
md = _load("cua_agent.loops.moondream3", LOOPS_DIR / "moondream3.py")


def _image_messages():
    return [
        {
            "type": "computer_call_output",
            "call_id": "c1",
            "output": {
                "type": "input_image",
                "image_url": "data:image/png;base64,aGVsbG8=",
            },
        }
    ]


def test_composed_grounded_usage_none():
    loop = cg.ComposedGroundedConfig()
    result = asyncio.run(
        loop.predict_step(_image_messages(), model="grounded+gpt-4o", tools=[])
    )
    assert result["usage"] == {"response_cost": 0.0}, result["usage"]
    assert result["output"], "expected output items to survive"


def test_moondream3_usage_none():
    loop = md.Moondream3PlusConfig()
    result = asyncio.run(
        loop.predict_step(
            [{"role": "user", "content": "hi"}],
            model="moondream3+gpt-4o",
            tools=[],
            computer_handler=None,
        )
    )
    assert result["usage"] == {"response_cost": 0.0}, result["usage"]
    assert result["output"] is not None


def test_usage_helper_shapes():
    helper = responses.response_usage_dict
    litellm = sys.modules["litellm"]

    # usage=None, no _hidden_params attribute at all
    class Bare:
        usage = None

    assert helper(Bare()) == {"response_cost": 0.0}

    # usage=None with a reported cost
    assert helper(litellm._FakeResponse(usage=None, hidden_params={"response_cost": 1.5})) == {
        "response_cost": 1.5
    }

    # usage model present: old behavior preserved exactly
    class UsageModel:
        def model_dump(self):
            return {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}

    got = helper(litellm._FakeResponse(usage=UsageModel(), hidden_params={}))
    assert got == {
        "prompt_tokens": 3,
        "completion_tokens": 7,
        "total_tokens": 10,
        "response_cost": 0.0,
    }, got

    # usage as a plain dict
    got = helper(
        litellm._FakeResponse(usage={"prompt_tokens": 1}, hidden_params={})
    )
    assert got == {"prompt_tokens": 1, "response_cost": 0.0}, got


if __name__ == "__main__":
    test_composed_grounded_usage_none()
    print("PASS test_composed_grounded_usage_none")
    test_moondream3_usage_none()
    print("PASS test_moondream3_usage_none")
    test_usage_helper_shapes()
    print("PASS test_usage_helper_shapes")

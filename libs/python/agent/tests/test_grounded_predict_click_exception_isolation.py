"""Red/green test: a failing grounding call must not kill the whole predict_step.

ComposedGroundedConfig.predict_step calls the grounding model's predict_click
up to 3x per element description. If predict_click RAISED (transient API
error, bad response, network failure), the exception escaped predict_step:
the thinking-model output, usage, and pre-output items were discarded, and
the whole step died (a retryable error would even re-run the already-paid
thinking-model call via _predict_step_with_retry).

Fix: wrap each predict_click attempt in try/except Exception. A failing
call is treated like a miss — retried up to 3x, then the description is left
unmapped (convert_computer_calls_desc2xy passes unmapped descriptions
through) and the step returns normally. CancelledError/KeyboardInterrupt
(BaseException) still propagate.

Self-contained: stubs litellm / PIL / cua_agent.agent (find_agent_config) /
decorators / loops.base, loads the REAL responses.py by file path (stubbed
openai.types.responses dict-subclass modules), loads the real
composed_grounded.py by file path, and drives predict_step with a fake
thinking-model response plus a grounding agent whose predict_click raises.
"""

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

PKG_ROOT = Path(__file__).resolve().parent.parent
RESPONSES_PATH = PKG_ROOT / "cua_agent" / "responses.py"
GROUNDED_PATH = PKG_ROOT / "cua_agent" / "loops" / "composed_grounded.py"


def _load_responses():
    stub_names = [
        "openai.types.responses.easy_input_message_param",
        "openai.types.responses.response_computer_tool_call_param",
        "openai.types.responses.response_function_tool_call_param",
        "openai.types.responses.response_input_image_param",
        "openai.types.responses.response_output_message_param",
        "openai.types.responses.response_output_text_param",
        "openai.types.responses.response_reasoning_item_param",
    ]
    attrs = [
        "EasyInputMessageParam",
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
        "ResponseFunctionToolCallParam",
        "ResponseInputImageParam",
        "ResponseOutputMessageParam",
        "ResponseOutputTextParam",
        "ResponseReasoningItemParam",
        "Summary",
    ]
    for name in ["openai", "openai.types", "openai.types.responses", *stub_names]:
        sys.modules.setdefault(name, types.ModuleType(name))
    for name in stub_names:
        mod = sys.modules[name]
        for attr in attrs:
            if not hasattr(mod, attr):
                setattr(mod, attr, dict)
    spec = importlib.util.spec_from_file_location(
        "cua_agent.responses", RESPONSES_PATH
    )
    responses = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.responses"] = responses
    spec.loader.exec_module(responses)
    return responses


class FakeUsage:
    def model_dump(self):
        return {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


class FakeHiddenParams(dict):
    pass


class FakeResponse:
    def __init__(self, message):
        self.usage = FakeUsage()
        self._hidden_params = {"response_cost": 0.0}
        self._message = message

    def model_dump(self):
        return {"choices": [{"message": self._message}]}


class FakeLitellm:
    message = None

    async def acompletion(self, **kwargs):
        return FakeResponse(FakeLitellm.message)


def _install_stubs(responses, grounding_predict_click):
    litellm = types.ModuleType("litellm")
    litellm.acompletion = FakeLitellm().acompletion
    sys.modules["litellm"] = litellm

    pil = types.ModuleType("PIL")
    image_mod = types.ModuleType("PIL.Image")
    image_mod.Image = type("Image", (), {})
    pil.Image = image_mod
    sys.modules["PIL"] = pil
    sys.modules["PIL.Image"] = image_mod

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    pkg.responses = responses
    sys.modules["cua_agent"] = pkg

    loops_pkg = types.ModuleType("cua_agent.loops")
    loops_pkg.__path__ = []
    sys.modules["cua_agent.loops"] = loops_pkg
    loops_base = types.ModuleType("cua_agent.loops.base")

    class AsyncAgentConfig:
        pass

    loops_base.AsyncAgentConfig = AsyncAgentConfig
    sys.modules["cua_agent.loops.base"] = loops_base

    class GroundingAgent:
        async def predict_click(self, model, image_b64, instruction, **kwargs):
            return grounding_predict_click(model, image_b64, instruction, **kwargs)

    agent_mod = types.ModuleType("cua_agent.agent")
    agent_mod.find_agent_config = lambda model: SimpleNamespace(
        agent_class=GroundingAgent
    )
    sys.modules["cua_agent.agent"] = agent_mod

    decorators = types.ModuleType("cua_agent.decorators")
    decorators.register_agent = lambda *a, **k: (lambda cls: cls)
    sys.modules["cua_agent.decorators"] = decorators

    types_mod = types.ModuleType("cua_agent.types")
    types_mod.AgentCapability = str
    types_mod.AgentResponse = dict
    types_mod.Messages = list
    types_mod.Tools = list
    sys.modules["cua_agent.types"] = types_mod


def _load_grounded():
    spec = importlib.util.spec_from_file_location(
        "cua_agent.loops.composed_grounded", GROUNDED_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.loops.composed_grounded"] = mod
    spec.loader.exec_module(mod)
    return mod


def _thinking_message():
    return {
        "role": "assistant",
        "content": "Click the red submit button.",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {
                    "name": "computer",
                    "arguments": json.dumps(
                        {"action": "click", "element_description": "red submit button"}
                    ),
                },
            }
        ],
    }


class FakeComputer:
    async def screenshot(self):
        return "aGVsbG8="


def _run_step(grounding_predict_click, messages=None):
    responses = _load_responses()
    _install_stubs(responses, grounding_predict_click)
    mod = _load_grounded()
    FakeLitellm.message = _thinking_message()
    cfg = mod.ComposedGroundedConfig()
    return asyncio.run(
        cfg.predict_step(
            messages if messages is not None else [],
            model="ground+think",
            tools=[{"type": "computer"}],
            computer_handler=FakeComputer(),
        )
    ), cfg


def test_grounding_exception_does_not_kill_step():
    def raiser(model, image_b64, instruction, **kwargs):
        raise RuntimeError("grounding API exploded")

    result, cfg = _run_step(raiser)
    # Step returns normally; the description is left unmapped.
    assert "output" in result and "usage" in result, result
    assert cfg.desc2xy == {}, cfg.desc2xy
    # Unmapped description passes through desc2xy conversion untouched.
    calls = [i for i in result["output"] if i.get("type") == "computer_call"]
    assert any(
        i.get("action", {}).get("element_description") == "red submit button"
        for i in calls
    ), result["output"]


def test_grounding_success_still_maps_coordinates():
    def ok(model, image_b64, instruction, **kwargs):
        return (100, 200)

    result, cfg = _run_step(ok)
    assert cfg.desc2xy == {"red submit button": (100, 200)}, cfg.desc2xy
    calls = [i for i in result["output"] if i.get("type") == "computer_call"]
    click = next(
        i for i in calls if i.get("action", {}).get("type") == "click"
    )
    assert click["action"]["x"] == 100 and click["action"]["y"] == 200, click


if __name__ == "__main__":
    test_grounding_exception_does_not_kill_step()
    test_grounding_success_still_maps_coordinates()
    print("PASS test_grounded_predict_click_exception_isolation")

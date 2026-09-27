"""Red/green test: moondream3's last-image lookup must tolerate non-string image_url.

Moondream3Config.predict_step inlines its own last-computer-call-image scan
and calls image_url.startswith(...) unconditionally. A malformed
computer_call_output with a non-string image_url (None, dict, list — e.g.
from a buggy driver payload) raised AttributeError and killed the step
before any model call. The composed_grounded helper had the identical defect
and was hardened earlier; this is the unfixed duplicate in moondream3.

Fix: require isinstance(image_url, str); non-strings are treated as absent
and the step falls through to the screenshot fallback.

Self-contained: stubs litellm / PIL / cua_agent.decorators / loops.base /
types, loads the REAL responses.py by file path (stubbed openai.types.responses
dict-subclass modules), loads the real moondream3.py by file path, and drives
predict_step with a stubbed thinking-model response. The computer handler's
screenshot returns None so the Moondream model itself is never loaded.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
RESPONSES_PATH = PKG_ROOT / "cua_agent" / "responses.py"
MOONDREAM_PATH = PKG_ROOT / "cua_agent" / "loops" / "moondream3.py"


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


def _install_stubs(responses):
    litellm = types.ModuleType("litellm")
    litellm.acompletion = FakeLitellm().acompletion
    sys.modules["litellm"] = litellm

    pil = types.ModuleType("PIL")
    for sub in ["Image", "ImageDraw", "ImageFont"]:
        mod = types.ModuleType("PIL." + sub)
        setattr(mod, sub, type(sub, (), {}))
        setattr(pil, sub, mod)
        sys.modules["PIL." + sub] = mod
    sys.modules["PIL"] = pil

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

    decorators = types.ModuleType("cua_agent.decorators")
    decorators.register_agent = lambda *a, **k: (lambda cls: cls)
    sys.modules["cua_agent.decorators"] = decorators

    types_mod = types.ModuleType("cua_agent.types")
    types_mod.AgentCapability = str
    sys.modules["cua_agent.types"] = types_mod


def _load_moondream():
    spec = importlib.util.spec_from_file_location(
        "cua_agent.loops.moondream3", MOONDREAM_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.loops.moondream3"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeComputer:
    async def screenshot(self):
        return None  # no screenshot available; model must not be loaded


def _run_step(messages):
    responses = _load_responses()
    _install_stubs(responses)
    mod = _load_moondream()
    FakeLitellm.message = {
        "role": "assistant",
        "content": "Nothing to do.",
    }
    cfg = mod.Moondream3PlusConfig()
    return asyncio.run(
        cfg.predict_step(
            messages,
            model="moondream3+gpt-4o",
            tools=[{"type": "computer"}],
            computer_handler=FakeComputer(),
        )
    )


def _image_output(image_url):
    return {
        "type": "computer_call_output",
        "call_id": "c1",
        "output": {"type": "input_image", "image_url": image_url},
    }


def test_none_image_url_does_not_raise():
    result = _run_step([_image_output(None)])
    assert "output" in result and "usage" in result, result


def test_dict_image_url_does_not_raise():
    result = _run_step([_image_output({"url": "data:image/png;base64,AAAA"})])
    assert "output" in result and "usage" in result, result


def test_non_image_output_type_skipped_on_both():
    # Control: output items that are not input_image never reach .startswith.
    result = _run_step(
        [
            {
                "type": "computer_call_output",
                "call_id": "c2",
                "output": {"type": "text", "text": "hello"},
            }
        ]
    )
    assert "output" in result and "usage" in result, result


if __name__ == "__main__":
    test_none_image_url_does_not_raise()
    test_dict_image_url_does_not_raise()
    test_non_image_output_type_skipped_on_both()
    print("PASS test_moondream3_last_image_malformed_url")

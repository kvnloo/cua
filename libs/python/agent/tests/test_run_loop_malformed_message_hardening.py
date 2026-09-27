"""Red/green test: run() must tolerate malformed (non-dict / non-list) message
and output shapes at every hop of the run loop.

Four defects, all AttributeError/TypeError on base, all crashing run() instead
of degrading:

1. ``replace_failed_computer_calls_with_function_calls`` (responses.py) called
   ``msg.get("type")`` on every combined message -- a non-dict message in
   history (e.g. a malformed provider output item appended to new_items on a
   previous iteration) killed the NEXT iteration's message preparation.
2. The run-loop head ``new_items[-1].get("role")`` crashed when the last
   accumulated item was not a dict.
3. ``get_output_call_ids`` iterated ``result.get("output", [])`` unguarded --
   a dict/None output crashed at ``message.get`` / iteration.
4. The Ollama image-input guard's ``contains_image_content`` closure called
   ``m.get("content")`` on every preprocessed message -- non-dict messages
   raised before predict_step even ran.

Fix: skip non-dict messages/entries everywhere; coerce non-list outputs to [].
Self-contained: stubs litellm / cua_core / cua_agent subpackage imports, loads
the REAL responses.py (with stubbed openai.types.responses modules) so the
run-loop tests exercise the real replace_failed path end to end.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

AGENT_DIR = Path(__file__).resolve().parent.parent / "cua_agent"
AGENT_PATH = AGENT_DIR / "agent.py"
RESPONSES_PATH = AGENT_DIR / "responses.py"


def _stub_class(name):
    return type(name, (), {"__init__": lambda self, *a, **k: None})


def _install_stubs():
    # --- litellm ------------------------------------------------------------
    litellm = types.ModuleType("litellm")
    litellm_utils = types.ModuleType("litellm.utils")
    litellm_responses = types.ModuleType("litellm.responses")
    litellm_responses_utils = types.ModuleType("litellm.responses.utils")

    class Usage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    litellm_responses_utils.Usage = Usage
    litellm.utils = litellm_utils
    litellm.responses = litellm_responses
    sys.modules["litellm"] = litellm
    sys.modules["litellm.utils"] = litellm_utils
    sys.modules["litellm.responses"] = litellm_responses
    sys.modules["litellm.responses.utils"] = litellm_responses_utils

    # --- openai.types.responses (dict-subclass placeholders) -----------------
    openai = types.ModuleType("openai")
    openai_types = types.ModuleType("openai.types")
    openai_responses_pkg = types.ModuleType("openai.types.responses")
    sys.modules["openai"] = openai
    sys.modules["openai.types"] = openai_types
    sys.modules["openai.types.responses"] = openai_responses_pkg

    def _resp_mod(mod_name, names):
        mod = types.ModuleType(f"openai.types.responses.{mod_name}")
        for n in names:
            setattr(mod, n, type(n, (dict,), {}))
        sys.modules[mod.__name__] = mod

    _resp_mod("easy_input_message_param", ["EasyInputMessageParam"])
    _resp_mod(
        "response_computer_tool_call_param",
        [
            "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
            "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
            "ActionType", "ActionWait", "PendingSafetyCheck",
            "ResponseComputerToolCallParam",
        ],
    )
    _resp_mod("response_function_tool_call_param", ["ResponseFunctionToolCallParam"])
    _resp_mod("response_input_image_param", ["ResponseInputImageParam"])
    _resp_mod("response_output_message_param", ["ResponseOutputMessageParam"])
    _resp_mod("response_output_text_param", ["ResponseOutputTextParam"])
    _resp_mod("response_reasoning_item_param", ["ResponseReasoningItemParam", "Summary"])

    # --- cua_core.telemetry ---------------------------------------------------
    cua_core = types.ModuleType("cua_core")
    telemetry = types.ModuleType("cua_core.telemetry")
    telemetry.is_telemetry_enabled = lambda: False
    telemetry.record_event = lambda *a, **k: None
    cua_core.telemetry = telemetry
    sys.modules["cua_core"] = cua_core
    sys.modules["cua_core.telemetry"] = telemetry

    # --- cua_agent package ----------------------------------------------------
    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    sys.modules["cua_agent"] = pkg

    adapters = types.ModuleType("cua_agent.adapters")
    for n in [
        "AzureMLAdapter", "CUAAdapter", "HuggingFaceLocalAdapter",
        "HumanAdapter", "MLXVLMAdapter",
    ]:
        setattr(adapters, n, _stub_class(n))
    sys.modules["cua_agent.adapters"] = adapters

    callbacks = types.ModuleType("cua_agent.callbacks")
    for n in [
        "BudgetManagerCallback", "ImageRetentionCallback", "LoggingCallback",
        "OperatorNormalizerCallback", "OtelCallback", "PromptInstructionsCallback",
        "TelemetryCallback", "TrajectorySaverCallback",
    ]:
        setattr(callbacks, n, _stub_class(n))
    sys.modules["cua_agent.callbacks"] = callbacks

    computers = types.ModuleType("cua_agent.computers")
    computers.AsyncComputerHandler = _stub_class("AsyncComputerHandler")
    computers.is_agent_computer = lambda obj: False
    computers.make_computer_handler = lambda *a, **k: None
    sys.modules["cua_agent.computers"] = computers

    decorators = types.ModuleType("cua_agent.decorators")
    decorators.find_agent_config = lambda model: None
    sys.modules["cua_agent.decorators"] = decorators

    tools_pkg = types.ModuleType("cua_agent.tools")
    tools_pkg.__path__ = []
    sys.modules["cua_agent.tools"] = tools_pkg
    tools_base = types.ModuleType("cua_agent.tools.base")
    tools_base.BaseComputerTool = _stub_class("BaseComputerTool")
    tools_base.BaseTool = _stub_class("BaseTool")
    sys.modules["cua_agent.tools.base"] = tools_base
    browser_tool = types.ModuleType("cua_agent.tools.browser_tool")
    browser_tool.BrowserTool = _stub_class("BrowserTool")
    sys.modules["cua_agent.tools.browser_tool"] = browser_tool

    types_mod = types.ModuleType("cua_agent.types")

    class IllegalArgumentError(ValueError):
        pass

    class ToolError(Exception):
        pass

    types_mod.AgentCapability = str
    types_mod.IllegalArgumentError = IllegalArgumentError
    types_mod.Messages = list
    types_mod.ToolError = ToolError
    sys.modules["cua_agent.types"] = types_mod


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_install_stubs()
responses_mod = _load("cua_agent.responses", RESPONSES_PATH)  # real module
agent_mod = _load("cua_agent.agent", AGENT_PATH)


class FakeLoop:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def get_capabilities(self):
        return ["step"]

    async def predict_step(self, **kwargs):
        assert self.outputs, "predict_step called with no scripted output left"
        return self.outputs.pop(0)


def _make_agent(model, outputs):
    agent = agent_mod.ComputerAgent(
        model=model,
        custom_loop=FakeLoop(outputs),
        telemetry_enabled=False,
        callbacks=[],
    )
    agent.agent_config_info = SimpleNamespace(
        agent_class=FakeLoop, tool_type=None
    )
    return agent


def _drain(agent, input):
    results = []

    async def go():
        async for r in agent.run(input):
            results.append(r)

    asyncio.run(go())
    return results


def test_replace_failed_skips_non_dict_messages():
    """replace_failed must not raise on malformed history entries."""
    msgs = [
        {"type": "computer_call", "call_id": "c1", "action": {"type": "click", "x": 1, "y": 2}},
        42,
        "garbage",
        None,
        {"type": "function_call_output", "call_id": "c1", "output": "failed"},
        ["nested", "list"],
    ]
    out = responses_mod.replace_failed_computer_calls_with_function_calls(msgs)
    assert len(out) == len(msgs)
    # The failed computer_call was still replaced; malformed entries pass through.
    assert out[0]["type"] == "function_call"
    assert out[0]["call_id"] == "c1"
    assert out[1] == 42 and out[2] == "garbage" and out[3] is None


def test_replace_failed_valid_replacement_unchanged():
    msgs = [
        {"type": "computer_call", "call_id": "c9", "action": {"type": "click", "x": 5, "y": 6}},
        {"type": "function_call_output", "call_id": "c9", "output": "boom"},
    ]
    out = responses_mod.replace_failed_computer_calls_with_function_calls(msgs)
    assert out[0]["type"] == "function_call"
    assert out[0]["name"] == "computer"
    import json

    assert json.loads(out[0]["arguments"])["type"] == "click"


def test_run_loop_tolerates_non_dict_output_item():
    """A non-dict provider output item must not crash the loop head."""
    agent = _make_agent(
        "openai/computer-use-preview",
        [
            {"output": [42], "usage": {}},
            {"output": [{"role": "assistant", "content": "done"}], "usage": {}},
        ],
    )
    results = _drain(agent, [{"role": "user", "content": "hi"}])
    assert len(results) == 2


def test_run_loop_tolerates_dict_output():
    """A dict (non-list) provider output must not crash get_output_call_ids."""
    agent = _make_agent(
        "openai/computer-use-preview",
        [
            {"output": {"type": "computer_call_output", "call_id": "x"}, "usage": {}},
            {"output": [{"role": "assistant", "content": "done"}], "usage": {}},
        ],
    )
    results = _drain(agent, [{"role": "user", "content": "hi"}])
    assert len(results) == 2


def test_run_loop_tolerates_none_output():
    agent = _make_agent(
        "openai/computer-use-preview",
        [
            {"output": None, "usage": {}},
            {"output": [{"role": "assistant", "content": "done"}], "usage": {}},
        ],
    )
    results = _drain(agent, [{"role": "user", "content": "hi"}])
    assert len(results) == 2


def test_get_output_call_ids_malformed_shapes():
    assert agent_mod.get_output_call_ids(None) == []
    assert agent_mod.get_output_call_ids({"type": "computer_call_output"}) == []
    assert agent_mod.get_output_call_ids("notalist") == []
    assert agent_mod.get_output_call_ids(
        [42, None, {"type": "computer_call_output", "call_id": "c1"}]
    ) == ["c1"]


def test_ollama_guard_tolerates_non_dict_messages():
    """The Ollama image guard must skip malformed messages, not raise."""
    agent = _make_agent(
        "ollama/llama3.2",
        [{"output": [{"role": "assistant", "content": "done"}], "usage": {}}],
    )
    results = _drain(agent, [{"role": "user", "content": "hi"}, 42, "junk"])
    assert len(results) == 1


def test_ollama_guard_still_rejects_images():
    """Well-formed image content must still trip the Ollama guard."""
    agent = _make_agent(
        "ollama/llama3.2",
        [{"output": [{"role": "assistant", "content": "done"}], "usage": {}}],
    )
    try:
        _drain(
            agent,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}
                    ],
                }
            ],
        )
    except ValueError as e:
        assert "Ollama" in str(e)
    else:
        raise AssertionError("expected ValueError for image input on ollama model")


if __name__ == "__main__":
    test_replace_failed_skips_non_dict_messages()
    test_replace_failed_valid_replacement_unchanged()
    test_run_loop_tolerates_non_dict_output_item()
    test_run_loop_tolerates_dict_output()
    test_run_loop_tolerates_none_output()
    test_get_output_call_ids_malformed_shapes()
    test_ollama_guard_tolerates_non_dict_messages()
    test_ollama_guard_still_rejects_images()
    print("PASS all 8")

"""Tests for None-returning lifecycle callbacks in ComputerAgent.

_on_llm_start/_on_llm_end chain user callbacks by replacing the message list
with each callback's return value. A callback that logs or mutates in place
and forgets to return (returns None) poisoned the chain: run() then crashed
with TypeError at `new_items += result.get("output")`. The chain now treats
a None return as "unchanged".

The real agent.py is loaded with heavy third-party imports stubbed
(litellm, cua_core.telemetry, openai types); the hook methods under test are
the shipped code.
"""

import asyncio
import importlib.util
import pathlib
import sys
import types

import pytest


def _dummy(name="Dummy"):
    return type(name, (), {})


def _load_agent_module():
    here = pathlib.Path(__file__).resolve()
    cua_agent_dir = here.parents[1] / "cua_agent"

    # --- stub litellm ---
    litellm = types.ModuleType("litellm")
    litellm_utils = types.ModuleType("litellm.utils")
    litellm_utils.function_to_dict = lambda f: {}
    litellm.utils = litellm_utils
    litellm_responses = types.ModuleType("litellm.responses")
    litellm_responses_utils = types.ModuleType("litellm.responses.utils")
    litellm_responses_utils.Usage = _dummy("Usage")
    litellm_responses.utils = litellm_responses_utils
    sys.modules["litellm"] = litellm
    sys.modules["litellm.utils"] = litellm_utils
    sys.modules["litellm.responses"] = litellm_responses
    sys.modules["litellm.responses.utils"] = litellm_responses_utils

    # --- stub cua_core.telemetry ---
    cua_core = types.ModuleType("cua_core")
    cua_core_telemetry = types.ModuleType("cua_core.telemetry")
    cua_core_telemetry.is_telemetry_enabled = lambda: False
    cua_core_telemetry.record_event = lambda *a, **k: None
    sys.modules["cua_core"] = cua_core
    sys.modules["cua_core.telemetry"] = cua_core_telemetry

    # --- stub openai types (typing-only in responses.py) ---
    openai = types.ModuleType("openai")
    sys.modules["openai"] = openai
    sys.modules["openai.types"] = types.ModuleType("openai.types")
    sys.modules["openai.types.responses"] = types.ModuleType("openai.types.responses")
    openai_names = {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": [
            "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
            "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
            "ActionWait", "ResponseComputerToolCallParam", "ActionType",
            "PendingSafetyCheck",
        ],
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }
    for mod_name, cls_names in openai_names.items():
        mod = types.ModuleType(f"openai.types.responses.{mod_name}")
        for cls_name in cls_names:
            setattr(mod, cls_name, _dummy(cls_name))
        sys.modules[f"openai.types.responses.{mod_name}"] = mod

    # --- fake cua_agent package ---
    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = [str(cua_agent_dir)]
    sys.modules["cua_agent"] = pkg

    def stub_submodule(name, attrs):
        mod = types.ModuleType(f"cua_agent.{name}")
        for attr in attrs:
            setattr(mod, attr, _dummy(attr))
        sys.modules[f"cua_agent.{name}"] = mod
        setattr(pkg, name.split(".")[0], mod) if "." not in name else None
        return mod

    stub_submodule(
        "adapters",
        ["AzureMLAdapter", "CUAAdapter", "HuggingFaceLocalAdapter",
         "HumanAdapter", "MLXVLMAdapter"],
    )
    stub_submodule(
        "callbacks",
        ["BudgetManagerCallback", "ImageRetentionCallback", "LoggingCallback",
         "OperatorNormalizerCallback", "OtelCallback", "PromptInstructionsCallback",
         "TelemetryCallback", "TrajectorySaverCallback"],
    )
    stub_submodule(
        "computers", ["AsyncComputerHandler", "is_agent_computer", "make_computer_handler"]
    )
    stub_submodule("decorators", ["find_agent_config"])
    stub_submodule("tools.base", ["BaseComputerTool", "BaseTool"])
    stub_submodule(
        "types", ["AgentCapability", "IllegalArgumentError", "Messages", "ToolError"]
    )

    # --- real responses.py (light: only openai type stubs needed) ---
    spec = importlib.util.spec_from_file_location(
        "cua_agent.responses", str(cua_agent_dir / "responses.py")
    )
    responses_mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.responses"] = responses_mod
    spec.loader.exec_module(responses_mod)

    # --- real agent.py ---
    spec = importlib.util.spec_from_file_location(
        "cua_agent.agent", str(cua_agent_dir / "agent.py")
    )
    agent_mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.agent"] = agent_mod
    spec.loader.exec_module(agent_mod)
    return agent_mod


_agent_mod = _load_agent_module()
ComputerAgent = _agent_mod.ComputerAgent


def _agent_with(*callbacks):
    agent = ComputerAgent.__new__(ComputerAgent)
    agent.callbacks = list(callbacks)
    return agent


class _NoneReturningCallback:
    """Logs and forgets to return — the realistic user mistake."""

    async def on_llm_start(self, messages):
        return None

    async def on_llm_end(self, output):
        return None


class _AppendingCallback:
    async def on_llm_end(self, output):
        return output + [{"role": "assistant", "content": "appended"}]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_none_return_from_on_llm_end_keeps_output():
    agent = _agent_with(_NoneReturningCallback())
    messages = [{"role": "assistant", "content": "hi"}]
    result = _run(agent._on_llm_end(messages))
    assert result is messages


def test_none_return_from_on_llm_start_keeps_messages():
    agent = _agent_with(_NoneReturningCallback())
    messages = [{"role": "user", "content": "hi"}]
    result = _run(agent._on_llm_start(messages))
    assert result is messages


def test_chain_continues_past_none_return():
    """A None-returning callback must not break later callbacks in the chain."""
    agent = _agent_with(_NoneReturningCallback(), _AppendingCallback())
    messages = [{"role": "assistant", "content": "hi"}]
    result = _run(agent._on_llm_end(messages))
    assert len(result) == 2
    assert result[0] is messages[0]
    assert result[1]["content"] == "appended"


def test_normal_callback_return_still_applies():
    agent = _agent_with(_AppendingCallback())
    messages = [{"role": "assistant", "content": "hi"}]
    result = _run(agent._on_llm_end(messages))
    assert len(result) == 2
    assert result[1]["content"] == "appended"


def test_no_callbacks_returns_input_unchanged():
    agent = _agent_with()
    messages = [{"role": "user", "content": "hi"}]
    assert _run(agent._on_llm_end(messages)) is messages
    assert _run(agent._on_llm_start(messages)) is messages

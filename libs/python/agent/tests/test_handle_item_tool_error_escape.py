"""Red/green test: tool execution failures must not escape _handle_item.

ComputerAgent._handle_item caught only ToolError from the function_call path.
Any other exception — malformed ``arguments`` JSON (json.JSONDecodeError is a
ValueError), argument-validation errors, or exceptions raised by the tool
itself (ValueError, RuntimeError, ...) — propagated out of _handle_item and
killed run(), since run() awaits _handle_item with no guard. The model never
saw the error and could not recover.

Fix: wrap the arguments-parse + tool-execution block in its own
try/except Exception and return make_tool_error_item(...), matching the
existing ToolError contract (a function_call_output item carrying
{"error": ...} under the same call_id).

Self-contained: loads the real cua_agent/responses.py by file path (stubbed
openai.types.responses dict-subclass modules, matching how the real TypedDicts
are used) for the genuine make_tool_error_item, stubs litellm / cua_core /
the cua_agent subpackage imports of agent.py, loads the real agent.py by file
path, and drives _handle_item directly with registered function tools.
"""

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
AGENT_PATH = PKG_ROOT / "cua_agent" / "agent.py"
RESPONSES_PATH = PKG_ROOT / "cua_agent" / "responses.py"


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

    # --- cua_core.telemetry ---------------------------------------------------
    cua_core = types.ModuleType("cua_core")
    telemetry = types.ModuleType("cua_core.telemetry")
    telemetry.is_telemetry_enabled = lambda: False
    telemetry.record_event = lambda *a, **k: None
    cua_core.telemetry = telemetry
    sys.modules["cua_core"] = cua_core
    sys.modules["cua_core.telemetry"] = telemetry

    # --- openai.types.responses stubs (dict subclasses) ----------------------
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

    # --- real responses.py (for make_tool_error_item) ------------------------
    spec = importlib.util.spec_from_file_location(
        "cua_agent.responses", RESPONSES_PATH
    )
    responses = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.responses"] = responses
    spec.loader.exec_module(responses)

    # --- cua_agent package ----------------------------------------------------
    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    pkg.responses = responses
    sys.modules["cua_agent"] = pkg

    adapters = types.ModuleType("cua_agent.adapters")
    for n in [
        "AzureMLAdapter",
        "CUAAdapter",
        "HuggingFaceLocalAdapter",
        "HumanAdapter",
        "MLXVLMAdapter",
    ]:
        setattr(adapters, n, _stub_class(n))
    sys.modules["cua_agent.adapters"] = adapters

    callbacks = types.ModuleType("cua_agent.callbacks")
    for n in [
        "BudgetManagerCallback",
        "ImageRetentionCallback",
        "LoggingCallback",
        "OperatorNormalizerCallback",
        "OtelCallback",
        "PromptInstructionsCallback",
        "TelemetryCallback",
        "TrajectorySaverCallback",
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

    # --- cua_agent.types with REAL exception semantics ------------------------
    types_mod = types.ModuleType("cua_agent.types")

    class ToolError(RuntimeError):
        """Base exception for tool-related errors"""

    class IllegalArgumentError(ToolError):
        """Exception raised when function arguments are invalid"""

    types_mod.AgentCapability = str
    types_mod.IllegalArgumentError = IllegalArgumentError
    types_mod.Messages = list
    types_mod.ToolError = ToolError
    sys.modules["cua_agent.types"] = types_mod


def _load_agent():
    spec = importlib.util.spec_from_file_location("cua_agent.agent", AGENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.agent"] = mod
    spec.loader.exec_module(mod)
    return mod


_install_stubs()
agent_mod = _load_agent()
ToolError = sys.modules["cua_agent.types"].ToolError


def boom(x):
    raise ValueError(f"tool exploded on {x}")


async def async_boom(x):
    raise RuntimeError("async tool exploded")


def fine(x):
    return f"ok:{x}"


def _make_agent():
    class FakeLoop:
        def get_capabilities(self):
            return ["step"]

    agent = agent_mod.ComputerAgent(
        model="openai/computer-use-preview",
        custom_loop=FakeLoop(),
        tools=[boom, async_boom, fine],
        telemetry_enabled=False,
    )
    from types import SimpleNamespace

    agent.agent_config_info = SimpleNamespace(agent_class=FakeLoop, tool_type=None)
    return agent


def _item(name, arguments, call_id="call_1"):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
    }


def _error_output(items):
    assert len(items) == 1, items
    assert items[0]["type"] == "function_call_output", items
    assert items[0]["call_id"] == "call_1", items
    return json.loads(items[0]["output"])


def test_sync_tool_raising_valueerror_becomes_error_item():
    agent = _make_agent()
    out = asyncio.run(agent._handle_item(_item("boom", '{"x": 1}')))
    err = _error_output(out)
    assert "ValueError" in err["error"] and "tool exploded" in err["error"], err


def test_async_tool_raising_runtimeerror_becomes_error_item():
    agent = _make_agent()
    out = asyncio.run(agent._handle_item(_item("async_boom", '{"x": 2}')))
    err = _error_output(out)
    assert "RuntimeError" in err["error"] and "async tool exploded" in err["error"], err


def test_malformed_arguments_json_becomes_error_item():
    agent = _make_agent()
    out = asyncio.run(agent._handle_item(_item("fine", "{not-json")))
    err = _error_output(out)
    assert "error" in err, err  # JSONDecodeError surfaced, run not crashed


def test_toolerror_path_unchanged():
    agent = _make_agent()
    out = asyncio.run(agent._handle_item(_item("missing_tool", '{"x": 1}')))
    err = _error_output(out)
    assert "not found" in err["error"], err


def test_successful_tool_still_returns_result():
    agent = _make_agent()
    out = asyncio.run(agent._handle_item(_item("fine", '{"x": 3}')))
    assert len(out) == 1 and out[0]["type"] == "function_call_output", out
    assert out[0]["output"] == "ok:3", out


if __name__ == "__main__":
    test_sync_tool_raising_valueerror_becomes_error_item()
    test_async_tool_raising_runtimeerror_becomes_error_item()
    test_malformed_arguments_json_becomes_error_item()
    test_toolerror_path_unchanged()
    test_successful_tool_still_returns_result()
    print("PASS test_handle_item_tool_error_escape")

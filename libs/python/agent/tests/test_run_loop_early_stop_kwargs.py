"""Red/green test: run() must not raise UnboundLocalError when a lifecycle
callback stops the run before the first model step.

ComputerAgent.run() bound ``loop_kwargs`` inside the step loop, after the
``_on_run_continue`` check. A callback returning falsy on the first iteration
(e.g. a budget manager with zero remaining budget) broke out of the loop, and
the trailing ``_on_run_end(loop_kwargs, ...)`` then raised
``UnboundLocalError``, masking the clean early stop and breaking the
on_run_end contract.

Self-contained: stubs litellm / cua_core / the cua_agent subpackage imports
of agent.py, loads the real agent.py by file path, and drives run() with a
callback whose on_run_continue returns False immediately.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

AGENT_PATH = Path(__file__).resolve().parent.parent / "cua_agent" / "agent.py"


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

    # --- cua_agent package ----------------------------------------------------
    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
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

    responses = types.ModuleType("cua_agent.responses")
    responses.make_tool_error_item = lambda *a, **k: {}
    responses.replace_failed_computer_calls_with_function_calls = lambda msgs: msgs
    sys.modules["cua_agent.responses"] = responses

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


def _load_agent():
    spec = importlib.util.spec_from_file_location("cua_agent.agent", AGENT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.agent"] = mod
    spec.loader.exec_module(mod)
    return mod


_install_stubs()
agent_mod = _load_agent()


class StopImmediately:
    """Lifecycle callback that stops the run before the first step."""

    def __init__(self):
        self.end_kwargs = "not-called"

    async def on_run_continue(self, kwargs, old_items, new_items):
        return False

    async def on_run_end(self, kwargs, old_items, new_items):
        self.end_kwargs = kwargs


class FakeLoop:
    def get_capabilities(self):
        return ["step"]

    async def predict_step(self, **kwargs):
        raise AssertionError("predict_step must not run on an early-stopped run")


def _make_agent(stop_cb):
    agent = agent_mod.ComputerAgent(
        model="openai/computer-use-preview",
        custom_loop=FakeLoop(),
        telemetry_enabled=False,
        callbacks=[stop_cb],
    )
    # custom_loop leaves agent_config_info None; provide the config the run
    # loop needs without touching the network.
    agent.agent_config_info = SimpleNamespace(
        agent_class=FakeLoop, tool_type=None
    )
    return agent


def test_early_stop_does_not_raise_unbound():
    stop_cb = StopImmediately()
    agent = _make_agent(stop_cb)

    async def drain():
        async for _ in agent.run([{"role": "user", "content": "hi"}]):
            pass

    asyncio.run(drain())
    assert stop_cb.end_kwargs == {}, stop_cb.end_kwargs


if __name__ == "__main__":
    test_early_stop_does_not_raise_unbound()
    print("PASS test_early_stop_does_not_raise_unbound")

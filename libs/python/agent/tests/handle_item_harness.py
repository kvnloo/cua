"""Test harness: load the REAL cua_agent/agent.py with targeted stubs.

The full cua_agent package cannot be imported in this environment (litellm,
openai, pydantic, cua_core are not installed), and _handle_item only needs a
handful of names from sibling modules. This harness stubs those modules in
sys.modules and loads agent.py directly, so the code under test is the real
implementation.
"""

import importlib.util
import json
import os
import sys
import types

_AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def load_agent_module():
    if "cua_agent.agent" in sys.modules:
        return sys.modules["cua_agent.agent"]

    # --- litellm stubs ---
    litellm = _stub("litellm", acompletion=None, completion=None)
    _stub("litellm.utils")
    _stub("litellm.exceptions")
    responses_pkg = _stub("litellm.responses")
    litellm.responses = responses_pkg

    class _Usage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    utils_mod = _stub("litellm.responses.utils", Usage=_Usage)
    responses_pkg.utils = utils_mod

    # --- cua_core.telemetry stub ---
    telemetry = _stub(
        "cua_core.telemetry",
        is_telemetry_enabled=lambda: False,
        record_event=lambda *a, **k: None,
    )
    cua_core = _stub("cua_core")
    cua_core.telemetry = telemetry

    # --- cua_agent package shell (real __init__ is NOT executed) ---
    pkg = _stub("cua_agent")
    pkg.__path__ = [os.path.join(_AGENT_DIR, "cua_agent")]

    _stub(
        "cua_agent.adapters",
        AzureMLAdapter=type("AzureMLAdapter", (), {}),
        CUAAdapter=type("CUAAdapter", (), {}),
        HuggingFaceLocalAdapter=type("HuggingFaceLocalAdapter", (), {}),
        HumanAdapter=type("HumanAdapter", (), {}),
        MLXVLMAdapter=type("MLXVLMAdapter", (), {}),
    )
    _stub(
        "cua_agent.callbacks",
        BudgetManagerCallback=object,
        ImageRetentionCallback=object,
        LoggingCallback=object,
        OperatorNormalizerCallback=object,
        OtelCallback=object,
        PromptInstructionsCallback=object,
        TelemetryCallback=object,
        TrajectorySaverCallback=object,
    )
    _stub(
        "cua_agent.computers",
        AsyncComputerHandler=object,
        is_agent_computer=lambda x: False,
        make_computer_handler=lambda *a, **k: None,
    )
    _stub("cua_agent.decorators", find_agent_config=lambda *a, **k: None)

    def make_tool_error_item(error_message, call_id=None):
        # Faithful copy of cua_agent/responses.py:254 (that module needs
        # openai types, unavailable here).
        import uuid as _uuid

        return {
            "type": "function_call_output",
            "call_id": call_id or _uuid.uuid4().hex,
            "output": json.dumps({"error": error_message}),
        }

    _stub(
        "cua_agent.responses",
        make_tool_error_item=make_tool_error_item,
        replace_failed_computer_calls_with_function_calls=lambda messages: messages,
    )

    class _ToolError(RuntimeError):
        pass

    class _IllegalArgumentError(_ToolError):
        pass

    _stub(
        "cua_agent.types",
        AgentCapability=str,
        IllegalArgumentError=_IllegalArgumentError,
        Messages=list,
        ToolError=_ToolError,
    )
    tools_pkg = _stub("cua_agent.tools")
    _stub(
        "cua_agent.tools.base",
        BaseComputerTool=type("BaseComputerTool", (), {}),
        BaseTool=type("BaseTool", (), {}),
    )
    tools_pkg.base = sys.modules["cua_agent.tools.base"]

    # --- load the REAL agent.py ---
    spec = importlib.util.spec_from_file_location(
        "cua_agent.agent", os.path.join(_AGENT_DIR, "cua_agent", "agent.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.agent"] = module
    spec.loader.exec_module(module)
    return module


def make_agent(module, tools):
    """Minimal ComputerAgent exposing only what _handle_item needs."""
    agent = module.ComputerAgent.__new__(module.ComputerAgent)
    agent.tools = tools
    agent.callbacks = []
    agent.telemetry_enabled = False
    agent.screenshot_delay = 0
    return agent

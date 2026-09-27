"""Red/green test: assert_callable_with must tolerate uninspectable callables.

assert_callable_with called inspect.signature(f) and caught only TypeError,
but inspect.signature raises ValueError for some builtins without
introspectable signatures (e.g. dict.update: "no signature found for
builtin"). A user registering such a callable as a function tool crashed
argument validation with an unhandled ValueError instead of either validating
or calling the tool.

Fix: catch (TypeError, ValueError) from inspect.signature. An uninspectable
callable cannot be validated up front, so validation is skipped (return True)
and the call itself raises naturally on bad arguments. The bind-mismatch path
still raises IllegalArgumentError exactly as before, and inspect.signature is
only computed once.

Self-contained: stubs litellm / cua_core / the cua_agent subpackage imports
of agent.py, loads the real agent.py by file path, and exercises the real
assert_callable_with (with the real IllegalArgumentError from a
real-semantics types stub).
"""

import importlib.util
import sys
import types
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parent.parent / "cua_agent" / "agent.py"


def _stub_class(name):
    return type(name, (), {"__init__": lambda self, *a, **k: None})


def _install_stubs():
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

    cua_core = types.ModuleType("cua_core")
    telemetry = types.ModuleType("cua_core.telemetry")
    telemetry.is_telemetry_enabled = lambda: False
    telemetry.record_event = lambda *a, **k: None
    cua_core.telemetry = telemetry
    sys.modules["cua_core"] = cua_core
    sys.modules["cua_core.telemetry"] = telemetry

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
IllegalArgumentError = sys.modules["cua_agent.types"].IllegalArgumentError
assert_callable_with = agent_mod.assert_callable_with


def add(a, b):
    return a + b


def test_uninspectable_builtin_method_does_not_raise():
    # dict.update has no introspectable signature (ValueError from
    # inspect.signature); validation must be skipped, not crash.
    assert assert_callable_with({}.update, {"a": 1}) is True


def test_uninspectable_builtin_still_executes():
    d = {}
    assert assert_callable_with(d.update, {"a": 1}) is True
    d.update({"a": 1})
    assert d == {"a": 1}


def test_bind_mismatch_still_raises_illegal_argument():
    try:
        assert_callable_with(add, 1)
    except IllegalArgumentError as e:
        assert "Expected" in str(e), str(e)
    else:
        raise AssertionError("expected IllegalArgumentError")


def test_valid_call_still_passes():
    assert assert_callable_with(add, 1, 2) is True
    assert assert_callable_with(add, a=1, b=2) is True


if __name__ == "__main__":
    test_uninspectable_builtin_method_does_not_raise()
    test_uninspectable_builtin_still_executes()
    test_bind_mismatch_still_raises_illegal_argument()
    test_valid_call_still_passes()
    print("PASS test_assert_callable_uninspectable_builtin")

"""Red-on-base tests: malformed model tool-call items must stay paired.

ComputerAgent._handle_item must always produce an output item for a tool-call
item. When it returns [] (empty computer action) or raises a non-ToolError
(null/unparseable function arguments), the model turn is left with an unpaired
tool call: the next predict_step sends a computer_call/function_call with no
matching output, which the Responses API rejects, killing the whole run
instead of letting the model recover from a reported error.
"""

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Stub out heavy third-party deps (litellm, openai, pydantic, cua_core) and
# cua_agent subpackages we don't exercise, so this file is self-contained.
# ---------------------------------------------------------------------------

_AGENT_DIR = Path(__file__).resolve().parent.parent


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        mock = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, mock)
        return mock


class _StubLoader:
    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        # Fabricated top-level packages need __path__ so submodule imports
        # (e.g. `import litellm.utils`) resolve through the finder again.
        module.__path__ = []


# Simpler approach than a meta-path finder: pre-register a finder that
# fabricates any module under the stubbed top-level packages.
import importlib.abc
import importlib.machinery


class _FabricatingFinder(importlib.abc.MetaPathFinder):
    PREFIXES = ("openai", "litellm", "pydantic", "cua_core")

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.PREFIXES:
            return importlib.machinery.ModuleSpec(fullname, _StubLoader())
        return None


sys.meta_path.insert(0, _FabricatingFinder())


def _pkg_stub(name, **attrs):
    mod = _StubModule(name)
    mod.__path__ = []  # mark as package
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


_pkg_stub("cua_agent.loops")
_pkg_stub(
    "cua_agent.adapters",
    AzureMLAdapter=MagicMock,
    CUAAdapter=MagicMock,
    HuggingFaceLocalAdapter=MagicMock,
    HumanAdapter=MagicMock,
    MLXVLMAdapter=MagicMock,
)
_pkg_stub(
    "cua_agent.callbacks",
    BudgetManagerCallback=MagicMock,
    ImageRetentionCallback=MagicMock,
    LoggingCallback=MagicMock,
    OperatorNormalizerCallback=MagicMock,
    OtelCallback=MagicMock,
    PromptInstructionsCallback=MagicMock,
    TelemetryCallback=MagicMock,
    TrajectorySaverCallback=MagicMock,
)
_pkg_stub(
    "cua_agent.computers",
    AsyncComputerHandler=MagicMock,
    is_agent_computer=MagicMock,
    make_computer_handler=MagicMock,
)
_pkg_stub("cua_agent.decorators", find_agent_config=MagicMock)
_pkg_stub("cua_agent.tools")
_pkg_stub("cua_agent.tools.base", BaseComputerTool=MagicMock, BaseTool=MagicMock)

sys.path.insert(0, str(_AGENT_DIR))

import cua_agent.agent as agent_module  # noqa: E402

from cua_agent.responses import (  # noqa: E402
    replace_failed_computer_calls_with_function_calls,
)


def _make_agent(tools=None):
    agent = agent_module.ComputerAgent.__new__(agent_module.ComputerAgent)
    agent.callbacks = []
    agent.telemetry_enabled = False
    agent.tools = tools or []
    agent.screenshot_delay = 0
    return agent


def _run(coro):
    return asyncio.run(coro)


def _is_error_output(items, call_id):
    assert isinstance(items, list) and len(items) == 1, f"expected 1 output item, got {items}"
    item = items[0]
    assert item.get("call_id") == call_id, f"output not paired to call {call_id}: {item}"
    assert item.get("type") == "function_call_output", f"unexpected output type: {item}"
    payload = json.loads(item["output"])
    assert "error" in payload, f"output carries no error: {payload}"
    return payload["error"]


def test_empty_computer_action_stays_paired():
    """computer_call with an empty action must produce an error output, not []."""
    agent = _make_agent()
    computer = MagicMock()
    item = {"type": "computer_call", "call_id": "call_empty", "action": {}}
    out = _run(agent._handle_item(item, computer))
    _is_error_output(out, "call_empty")


def test_missing_computer_action_stays_paired():
    """computer_call with no action key must produce an error output, not []."""
    agent = _make_agent()
    computer = MagicMock()
    item = {"type": "computer_call", "call_id": "call_no_action"}
    out = _run(agent._handle_item(item, computer))
    _is_error_output(out, "call_no_action")


def test_non_dict_computer_action_stays_paired():
    """computer_call with a non-dict action must not raise AttributeError."""
    agent = _make_agent()
    computer = MagicMock()
    item = {"type": "computer_call", "call_id": "call_str_action", "action": "click"}
    out = _run(agent._handle_item(item, computer))
    _is_error_output(out, "call_str_action")


def test_missing_computer_handler_stays_paired():
    """computer_call with no handler must produce an error output, not raise."""
    agent = _make_agent()
    item = {
        "type": "computer_call",
        "call_id": "call_no_handler",
        "action": {"type": "click", "x": 1, "y": 2},
    }
    out = _run(agent._handle_item(item, None))
    _is_error_output(out, "call_no_handler")


def test_null_function_arguments_stays_paired():
    """function_call with null arguments must not raise TypeError."""

    def echo(text):
        return text

    agent = _make_agent(tools=[echo])
    item = {
        "type": "function_call",
        "call_id": "call_null_args",
        "name": "echo",
        "arguments": None,
    }
    out = _run(agent._handle_item(item, None))
    _is_error_output(out, "call_null_args")


def test_malformed_function_arguments_stays_paired():
    """function_call with unparseable arguments must not raise."""

    def echo(text):
        return text

    agent = _make_agent(tools=[echo])
    item = {
        "type": "function_call",
        "call_id": "call_bad_args",
        "name": "echo",
        "arguments": "{not json",
    }
    out = _run(agent._handle_item(item, None))
    _is_error_output(out, "call_bad_args")


def test_non_object_function_arguments_stays_paired():
    """function_call with valid JSON that is not an object must not raise."""

    def echo(text):
        return text

    agent = _make_agent(tools=[echo])
    item = {
        "type": "function_call",
        "call_id": "call_list_args",
        "name": "echo",
        "arguments": "[1, 2]",
    }
    out = _run(agent._handle_item(item, None))
    _is_error_output(out, "call_list_args")


def test_error_output_repairs_computer_call_pairing():
    """The run loop's rewrite pairs the failed computer_call via the error output."""
    agent = _make_agent()
    computer = MagicMock()
    call = {"type": "computer_call", "call_id": "call_repair", "action": {}}
    out = _run(agent._handle_item(call, computer))
    repaired = replace_failed_computer_calls_with_function_calls([call] + out)
    kinds = [m.get("type") for m in repaired]
    assert kinds == ["function_call", "function_call_output"], kinds
    assert repaired[0]["call_id"] == repaired[1]["call_id"] == "call_repair"


def test_valid_computer_call_still_works():
    """Positive control: a well-formed computer_call still executes and pairs."""
    agent = _make_agent()
    computer = MagicMock()
    computer.click = AsyncMock(return_value=None)
    computer.screenshot = AsyncMock(return_value="aGVsbG8=")
    item = {
        "type": "computer_call",
        "call_id": "call_ok",
        "action": {"type": "click", "x": 10, "y": 20},
    }
    out = _run(agent._handle_item(item, computer))
    assert len(out) == 1
    assert out[0]["type"] == "computer_call_output"
    assert out[0]["call_id"] == "call_ok"
    computer.click.assert_awaited_once_with(x=10, y=20)


def test_valid_function_call_still_works():
    """Positive control: a well-formed function_call still executes and pairs."""

    def echo(text):
        return f"echo:{text}"

    agent = _make_agent(tools=[echo])
    item = {
        "type": "function_call",
        "call_id": "call_fn_ok",
        "name": "echo",
        "arguments": json.dumps({"text": "hi"}),
    }
    out = _run(agent._handle_item(item, None))
    assert len(out) == 1
    assert out[0]["type"] == "function_call_output"
    assert out[0]["call_id"] == "call_fn_ok"
    assert out[0]["output"] == "echo:hi"

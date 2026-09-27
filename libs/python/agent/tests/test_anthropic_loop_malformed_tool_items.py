"""Malformed model tool items must degrade gracefully in the Anthropic loop.

A model emitting a non-object `input` on a native tool_use item, or malformed
JSON arguments on a computer tool_call, must produce a failed tool call pair
(function_call + function_call_output) so the model can recover — never kill
the run with an uncaught AttributeError/UnboundLocalError.

Self-contained: stubs litellm and openai types, loads the real
cua_agent.responses and cua_agent.loops.anthropic modules.
"""
import importlib.util
import json
import sys
import types
from types import SimpleNamespace

import pytest

WT = "/home/hatch/workspace/cua-wt-muse-c43/libs/python/agent/cua_agent"


def _load_modules():
    def _mkcls(name):
        def __init__(self, **kw):
            self.kw = kw
        return type(name, (object,), {"__init__": __init__})

    NAMES = {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": [
            "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
            "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
            "ActionWait", "ResponseComputerToolCallParam", "ActionType",
            "PendingSafetyCheck"],
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }
    for modname, clslist in NAMES.items():
        mod = types.ModuleType(f"openai.types.responses.{modname}")
        for c in clslist:
            setattr(mod, c, _mkcls(c))
        sys.modules[f"openai.types.responses.{modname}"] = mod
    for name in ["openai", "openai.types", "openai.types.responses"]:
        sys.modules.setdefault(name, types.ModuleType(name))

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    sys.modules["cua_agent"] = pkg
    dec = types.ModuleType("cua_agent.decorators")
    dec.register_agent = lambda *a, **k: (lambda cls: cls)
    sys.modules["cua_agent.decorators"] = dec
    loops_pkg = types.ModuleType("cua_agent.loops")
    loops_pkg.__path__ = []
    sys.modules["cua_agent.loops"] = loops_pkg
    base = types.ModuleType("cua_agent.loops.base")
    base.AsyncAgentConfig = type("AsyncAgentConfig", (), {})
    sys.modules["cua_agent.loops.base"] = base
    types_mod = types.ModuleType("cua_agent.types")
    for n in ["AgentCapability", "AgentResponse", "Messages", "Tools"]:
        setattr(types_mod, n, type(n, (), {}))
    sys.modules["cua_agent.types"] = types_mod

    spec = importlib.util.spec_from_file_location(
        "cua_agent.responses", f"{WT}/responses.py")
    resp = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.responses"] = resp
    spec.loader.exec_module(resp)

    litellm = types.ModuleType("litellm")
    sys.modules["litellm"] = litellm
    sys.modules["litellm.responses"] = types.ModuleType("litellm.responses")
    sys.modules["litellm.responses.litellm_completion_transformation"] = \
        types.ModuleType("litellm.responses.litellm_completion_transformation")
    lrtm = types.ModuleType(
        "litellm.responses.litellm_completion_transformation.transformation")
    lrtm.LiteLLMCompletionResponsesConfig = type(
        "LiteLLMCompletionResponsesConfig", (), {})
    sys.modules[
        "litellm.responses.litellm_completion_transformation.transformation"] = lrtm

    spec = importlib.util.spec_from_file_location(
        "cua_agent.loops.anthropic", f"{WT}/loops/anthropic.py")
    anth = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.loops.anthropic"] = anth
    spec.loader.exec_module(anth)
    return anth._convert_completion_to_responses_items


@pytest.fixture(scope="module")
def convert():
    return _load_modules()


def _native_completion(tool_input, name="computer", call_id="call_1"):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=[
            {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}
        ]))])


def _toolcall_completion(arguments, name="computer", call_id="call_2"):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=None, tool_calls=[
            SimpleNamespace(id=call_id,
                            function=SimpleNamespace(name=name, arguments=arguments))
        ]))])


def _kinds(items):
    out = []
    for i in items:
        if isinstance(i, dict):
            out.append(i.get("type"))
        else:
            out.append(getattr(i, "kw", {}).get("type", type(i).__name__))
    return out


def _error_output(items):
    """Return the error payload text from the function_call_output item."""
    for i in items:
        payload = i if isinstance(i, dict) else getattr(i, "kw", {})
        if payload.get("type") == "function_call_output":
            return payload.get("output", "")
    return ""


@pytest.mark.parametrize("bad_input", ["click", None, ["click"], 42])
def test_non_dict_tool_use_input_degrades_gracefully(convert, bad_input):
    """Non-object tool_use input must not kill the run."""
    items = convert(_native_completion(bad_input))
    kinds = _kinds(items)
    assert kinds == ["function_call", "function_call_output"]
    assert "expected object" in _error_output(items)


def test_malformed_json_tool_call_args_degrades_gracefully(convert):
    """Malformed JSON arguments on a computer tool_call must not kill the run."""
    items = convert(_toolcall_completion("{not valid json"))
    kinds = _kinds(items)
    assert kinds == ["function_call", "function_call_output"]
    assert "JSONDecodeError" in _error_output(items)


def test_valid_computer_tool_use_unchanged(convert):
    items = convert(_native_completion({"action": "click", "coordinate": [100, 200]}))
    assert _kinds(items) == ["computer_call"]


def test_valid_computer_tool_call_unchanged(convert):
    items = convert(_toolcall_completion(json.dumps({"action": "screenshot"})))
    assert _kinds(items) == ["computer_call"]


def test_valid_custom_function_tool_use_unchanged(convert):
    items = convert(_native_completion({"a": 1}, name="my_fn"))
    assert _kinds(items) == ["function_call"]

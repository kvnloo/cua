"""Malformed function-call arguments must degrade to a tool error, not kill the run.

ComputerAgent._handle_item parsed function-call arguments with an unguarded
``json.loads(item.get("arguments"))``. Malformed JSON raised JSONDecodeError,
None raised TypeError, and valid-but-non-object JSON (string/number/list)
crashed later in ``assert_callable_with(function, **args)`` with TypeError.
Only ToolError was caught, so all of these escaped and killed the whole run
instead of producing a tool-error output item the model could recover from.

Fix: parse failures and non-object arguments now return
``make_tool_error_item(...)``; None/null arguments are treated as {}.
"""
import asyncio
import json
import sys
import types
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3] / "python" / "agent" / "cua_agent"
PKG = str(REPO)


def _modpath(*names, path=None):
    prev = None
    for n in names:
        m = types.ModuleType(n)
        if path:
            m.__path__ = path
        sys.modules[n] = m
        if prev is not None:
            setattr(prev, n.split(".")[-1], m)
        prev = m
    return prev


def _install_stubs():
    litellm = _modpath("litellm", path=[])
    litellm.acompletion = None
    litellm.ResponseInputParam = object
    litellm.ResponsesAPIResponse = object
    litellm.ToolParam = object
    lu = _modpath("litellm.utils", path=[])
    lu.function_to_dict = lambda t: {}
    _modpath("litellm.responses", path=[])
    lru = _modpath("litellm.responses.utils", path=[])

    class Usage:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    lru.Usage = Usage
    pyd = _modpath("pydantic", path=[])
    pyd.BaseModel = object
    _modpath("cua_core", path=[])
    cct = _modpath("cua_core.telemetry", path=[])
    cct.is_telemetry_enabled = lambda: False
    cct.record_event = lambda *a, **k: None

    _modpath("openai", path=[])
    _modpath("openai.types", path=[])
    _modpath("openai.types.responses", path=[])
    needs = {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": [
            "ResponseComputerToolCallParam",
            "ResponseComputerToolCall",
            "ActionClick",
            "ActionDoubleClick",
            "ActionDrag",
            "ActionDragPath",
            "ActionKeypress",
            "ActionMove",
            "ActionScreenshot",
            "ActionScroll",
            "ActionType",
            "ActionTypeAction",
            "ActionWait",
            "PendingSafetyCheck",
            "Summary",
        ],
        "response_function_tool_call_param": [
            "ResponseFunctionToolCallParam",
            "ResponseFunctionToolCall",
        ],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }
    for mod, names in needs.items():
        m = _modpath(f"openai.types.responses.{mod}")
        for n in names:
            setattr(m, n, type(n, (), {}))


def _load_agent():
    for p in ("cua_agent", "cua_agent.adapters", "cua_agent.callbacks",
              "cua_agent.computers", "cua_agent.tools"):
        m = types.ModuleType(p)
        m.__path__ = []
        sys.modules[p] = m
    ad = sys.modules["cua_agent.adapters"]
    for n in ("AzureMLAdapter", "CUAAdapter", "HuggingFaceLocalAdapter",
              "HumanAdapter", "MLXVLMAdapter"):
        setattr(ad, n, type(n, (), {}))
    cb = sys.modules["cua_agent.callbacks"]
    for n in ("BudgetManagerCallback", "ImageRetentionCallback", "LoggingCallback",
              "OperatorNormalizerCallback", "OtelCallback",
              "PromptInstructionsCallback", "TelemetryCallback",
              "TrajectorySaverCallback"):
        setattr(cb, n, type(n, (), {}))
    comp = sys.modules["cua_agent.computers"]
    comp.AsyncComputerHandler = object
    comp.is_agent_computer = lambda x: False
    comp.make_computer_handler = lambda **k: None
    dec = types.ModuleType("cua_agent.decorators")
    dec.register_agent = lambda *a, **k: (lambda c: c)
    dec.find_agent_config = lambda *a, **k: None
    sys.modules["cua_agent.decorators"] = dec
    tb = types.ModuleType("cua_agent.tools.base")

    class BaseTool:
        def call(self, args):
            return "tool-result"

    tb.BaseComputerTool = type("BaseComputerTool", (), {})
    tb.BaseTool = BaseTool
    sys.modules["cua_agent.tools.base"] = tb

    def load(fullname, rel):
        spec = importlib.util.spec_from_file_location(fullname, PKG + "/" + rel)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = mod
        spec.loader.exec_module(mod)
        return mod

    load("cua_agent.types", "types.py")
    load("cua_agent.responses", "responses.py")
    return load("cua_agent.agent", "agent.py")


_install_stubs()
agent = _load_agent()


def _make_agent():
    a = agent.ComputerAgent.__new__(agent.ComputerAgent)
    a.callbacks = []
    a.telemetry_enabled = False

    def _tool(**kw):
        return "ok"

    a._get_tool = lambda name: _tool if name == "mytool" else None

    async def _noop(*args, **kw):
        return None

    a._on_function_call_start = _noop
    a._on_function_call_end = _noop
    return a


def _handle(args):
    a = _make_agent()
    item = {
        "type": "function_call",
        "call_id": "call_1",
        "name": "mytool",
        "arguments": args,
    }
    return asyncio.run(a._handle_item(item, None))


def _is_tool_error(out, fragment):
    assert len(out) == 1 and out[0]["type"] == "function_call_output"
    assert out[0]["call_id"] == "call_1"
    body = json.loads(out[0]["output"])
    assert fragment in body["error"], body
    return True


def test_malformed_json_arguments_become_tool_error():
    _is_tool_error(_handle("{not json"), "Invalid tool arguments")


def test_non_object_arguments_become_tool_error():
    for args in ('"click"', "42", '["a"]'):
        _is_tool_error(_handle(args), "must be a JSON object")


def test_none_and_null_arguments_run_with_empty_args():
    for args in (None, "null"):
        out = _handle(args)
        assert len(out) == 1 and out[0]["type"] == "function_call_output"
        assert out[0]["output"] == "ok"


def test_valid_object_arguments_still_run():
    out = _handle('{"x": 1}')
    assert len(out) == 1 and out[0]["output"] == "ok"

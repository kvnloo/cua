"""Malformed run-loop result/output shapes must degrade, not kill the run.

The run loop assumed every predict_step result is a dict with a list
``output`` and every output entry is a dict:

- ``_handle_item`` called ``item.get("call_id")`` on raw output entries;
  a non-dict entry (e.g. from a loop that returned a dict-shaped output)
  raised AttributeError.
- ``get_output_call_ids`` called ``message.get("type")`` on every entry;
  non-dict entries raised AttributeError.
- ``run()`` did ``result["output"] = ...`` on whatever ``get_json`` returned
  and ``new_items += result.get("output")`` — a None/non-dict result or a
  non-list output raised TypeError, and iterating a dict output fed string
  keys into ``_handle_item``.
- The ``while new_items[-1].get("role")`` loop guard crashed on a non-dict
  trailing item.

Fix: ``_normalize_step_result`` coerces any result to the {output, usage}
shape with a list output (applied to the step result and again after the
``_on_llm_end`` callback); ``_handle_item`` returns [] for non-dict items;
``get_output_call_ids`` skips non-dict entries; the loop guard and the
partial-items scan tolerate non-dict entries.
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
    return a


def _handle(item):
    return asyncio.run(_make_agent()._handle_item(item, None))


def test_handle_item_non_dict_items_return_empty():
    for bad in ("oops", None, 42, ["x"], {"type": "computer_call"} and "still-a-string"):
        assert _handle(bad) == []


def test_get_output_call_ids_skips_non_dict_entries():
    out = agent.get_output_call_ids(
        [{"type": "computer_call_output", "call_id": "c1"}, "junk", None, 42,
         {"type": "message", "call_id": "c2"}]
    )
    assert out == ["c1"]


def test_normalize_step_result_non_dict():
    assert agent._normalize_step_result(None) == {"output": [], "usage": {}}
    assert agent._normalize_step_result("oops") == {"output": [], "usage": {}}


def test_normalize_step_result_non_list_output():
    out = agent._normalize_step_result({"output": None, "usage": {}})
    assert out["output"] == []
    out = agent._normalize_step_result({"output": {"type": "x"}, "usage": {}})
    assert out["output"] == []


def test_normalize_step_result_keeps_valid_output():
    items = [{"type": "message", "role": "assistant", "content": []}]
    out = agent._normalize_step_result({"output": items, "usage": {"t": 1}})
    assert out["output"] is items

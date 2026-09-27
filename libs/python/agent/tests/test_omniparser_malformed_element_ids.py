"""Malformed Omniparser model output must degrade gracefully, not crash.

``replace_function_with_computer_call`` parsed model-controlled values unguarded:

- ``json.loads(item.get("arguments", "{}"))`` raised ``json.JSONDecodeError`` on
  malformed JSON and ``TypeError`` when ``arguments`` was None or a non-string.
- A JSON array payload (valid JSON, not an object) raised ``AttributeError`` at
  ``fn_args.get("action")``.
- ``id2xy.get(element_id)`` raised ``TypeError`` when the model emitted an
  unhashable ``element_id`` (list/dict) — reachable from any model output.

``replace_computer_call_with_function`` had the mirror image:

- ``xy2id.get((x, y))`` raised ``TypeError`` on unhashable coordinates.
- ``item.get("action", {}).get(...)`` raised ``AttributeError`` when the action
  was not a dict.
- Non-dict items raised ``AttributeError`` at ``item.get("type")`` in both.

Fix: malformed arguments pass the item through unchanged; unhashable
element ids / coordinates resolve to None instead of crashing; non-dict
items and actions pass through unchanged.
"""
import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "cua_agent"


def _mod(name, path=None, **attrs):
    m = types.ModuleType(name)
    if path is not None:
        m.__path__ = path
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _install_stubs():
    class BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _deco(*a, **k):
        def wrap(f):
            return f

        return wrap

    _mod("pydantic", BaseModel=BaseModel, field_validator=_deco,
         model_validator=_deco)

    _mod("litellm", path=[],
         acompletion=None,
         aresponses=None,
         ResponseInputParam=dict,
         ResponsesAPIResponse=dict,
         ToolParam=dict)
    _mod("litellm.responses", path=[])
    _mod("litellm.responses.utils", path=[], Usage=dict)

    _mod("openai", path=[])
    _mod("openai.types", path=[])
    _mod("openai.types.responses", path=[])
    action_names = [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionWait", "ActionType", "PendingSafetyCheck",
        "ResponseComputerToolCallParam", "EasyInputMessageParam",
        "ResponseInputImageParam", "ResponseOutputMessageParam",
        "ResponseOutputTextParam", "ResponseReasoningItemParam", "Summary",
        "ResponseFunctionToolCallParam",
    ]
    for mod, names in {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": action_names,
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }.items():
        _mod(f"openai.types.responses.{mod}",
             **{n: (lambda **kw: dict(kw)) for n in names})


def _pkg(name, path):
    m = types.ModuleType(name)
    m.__path__ = [path]
    m.__package__ = name
    sys.modules[name] = m
    return m


def _load(dotted, path):
    spec = importlib.util.spec_from_file_location(dotted, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = m
    spec.loader.exec_module(m)
    return m


def _load_omniparser():
    for key in [k for k in sys.modules if k == "cua_agent"
                or k.startswith(("cua_agent.", "pydantic", "litellm", "openai"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _pkg("cua_agent.loops", base + "/loops")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.loops.base", base + "/loops/base.py")
    _load("cua_agent.responses", base + "/responses.py")
    return _load("cua_agent.loops.omniparser", base + "/loops/omniparser.py")


om = _load_omniparser()
ID2XY = {5: (100, 200), 7: (300, 400)}


def _fn_call(arguments, name="computer", item_id="1", call_id="c1"):
    return {
        "type": "function_call",
        "name": name,
        "arguments": arguments,
        "id": item_id,
        "call_id": call_id,
    }


def run(coro):
    return asyncio.run(coro)


def test_malformed_json_arguments_passthrough():
    item = _fn_call("{not valid json")
    assert run(om.replace_function_with_computer_call(item, ID2XY)) == [item]


def test_none_arguments_passthrough():
    item = _fn_call(None)
    assert run(om.replace_function_with_computer_call(item, ID2XY)) == [item]


def test_non_object_json_arguments_passthrough():
    item = _fn_call("[1, 2, 3]")
    assert run(om.replace_function_with_computer_call(item, ID2XY)) == [item]


def test_unhashable_element_id_resolves_to_none():
    item = _fn_call(json.dumps({"action": "click", "element_id": [5]}))
    out = run(om.replace_function_with_computer_call(item, ID2XY))
    assert len(out) == 1 and out[0]["type"] == "computer_call"
    assert "x" not in out[0]["action"] and "y" not in out[0]["action"]


def test_dict_element_id_resolves_to_none():
    item = _fn_call(json.dumps({"action": "click", "element_id": {"id": 5}}))
    out = run(om.replace_function_with_computer_call(item, ID2XY))
    assert len(out) == 1 and out[0]["type"] == "computer_call"
    assert "x" not in out[0]["action"]


def test_unhashable_start_end_element_ids():
    item = _fn_call(json.dumps({
        "action": "drag",
        "start_element_id": [5],
        "end_element_id": {"id": 7},
    }))
    out = run(om.replace_function_with_computer_call(item, ID2XY))
    assert len(out) == 1 and out[0]["type"] == "computer_call"


def test_valid_element_id_still_maps():
    item = _fn_call(json.dumps({"action": "click", "element_id": 5}))
    out = run(om.replace_function_with_computer_call(item, ID2XY))
    assert out[0]["action"]["x"] == 100 and out[0]["action"]["y"] == 200


def test_unknown_element_id_still_none():
    item = _fn_call(json.dumps({"action": "click", "element_id": 999}))
    out = run(om.replace_function_with_computer_call(item, ID2XY))
    assert "x" not in out[0]["action"]


def test_non_dict_item_passthrough():
    assert run(om.replace_function_with_computer_call("oops", ID2XY)) == ["oops"]


def test_reverse_unhashable_coordinates():
    item = {
        "type": "computer_call",
        "action": {"type": "click", "x": [100], "y": [200]},
        "id": "1",
        "call_id": "c1",
    }
    out = run(om.replace_computer_call_with_function(item, {(100, 200): 5}))
    assert len(out) == 1 and out[0]["type"] == "function_call"
    args = json.loads(out[0]["arguments"])
    assert "element_id" not in args


def test_reverse_non_dict_action_passthrough():
    item = {"type": "computer_call", "action": [1, 2], "id": "1", "call_id": "c1"}
    assert run(om.replace_computer_call_with_function(item, {})) == [item]


def test_reverse_valid_roundtrip():
    item = {
        "type": "computer_call",
        "action": {"type": "click", "x": 100, "y": 200},
        "id": "1",
        "call_id": "c1",
    }
    out = run(om.replace_computer_call_with_function(item, {(100, 200): 5}))
    args = json.loads(out[0]["arguments"])
    assert args["element_id"] == 5

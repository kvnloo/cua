"""Malformed shapes must not crash the desc/xy response transforms.

``convert_computer_calls_desc2xy`` did ``if desc in desc2xy`` — an
unhashable element_description (list/dict from malformed model output) raised
TypeError. ``convert_computer_calls_xy2desc`` did the same on unhashable
coords and ``"x" in start_point`` raised TypeError on non-dict path points.
``get_all_element_descriptions`` did substring ``in`` checks on non-dict
actions. All of these killed the run during history conversion.

Fix: non-dict entries/actions pass through untouched; unhashable keys simply
miss the lookup via a membership guard.
"""
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "cua_agent"


def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _factory(name):
    return type(name, (dict,), {"__init__": lambda self, **kw: dict.__init__(self, kw)})


def _install_stubs():
    action_names = [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionWait", "ActionType", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
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
        _mod(f"openai.types.responses.{mod}", **{n: _factory(n) for n in names})


_install_stubs()
spec = importlib.util.spec_from_file_location("responses", REPO / "responses.py")
resp = importlib.util.module_from_spec(spec)
sys.modules["responses"] = resp
spec.loader.exec_module(resp)

DESC2XY = {"Submit": (10, 20), "Cancel": (30, 40)}


def test_desc2xy_unhashable_element_description():
    items = [{
        "type": "computer_call",
        "action": {"type": "click", "element_description": ["Submit"]},
    }]
    out = resp.convert_computer_calls_desc2xy(items, DESC2XY)
    assert out[0]["action"]["element_description"] == ["Submit"]
    assert "x" not in out[0]["action"]


def test_desc2xy_unhashable_drag_descriptions():
    items = [{
        "type": "computer_call",
        "action": {
            "type": "drag",
            "start_element_description": {"d": "Submit"},
            "end_element_description": {"d": "Cancel"},
        },
    }]
    out = resp.convert_computer_calls_desc2xy(items, DESC2XY)
    assert "path" not in out[0]["action"]


def test_desc2xy_non_dict_item_and_action_passthrough():
    items = [
        "raw-string-entry",
        {"type": "computer_call", "action": "click"},
        {"type": "computer_call",
         "action": {"type": "click", "element_description": "Submit"}},
    ]
    out = resp.convert_computer_calls_desc2xy(items, DESC2XY)
    assert out[0] == "raw-string-entry"
    assert out[1]["action"] == "click"
    assert out[2]["action"]["x"] == 10 and out[2]["action"]["y"] == 20


def test_xy2desc_unhashable_coords():
    items = [{
        "type": "computer_call",
        "action": {"type": "click", "x": [10], "y": 20},
    }]
    out = resp.convert_computer_calls_xy2desc(items, DESC2XY)
    assert out[0]["action"]["x"] == [10]
    assert "element_description" not in out[0]["action"]


def test_xy2desc_non_dict_path_points():
    items = [{
        "type": "computer_call",
        "action": {"type": "drag", "path": [7, {"x": 30, "y": 40}]},
    }]
    out = resp.convert_computer_calls_xy2desc(items, DESC2XY)
    assert out[0]["action"]["path"] == [7, {"x": 30, "y": 40}]


def test_xy2desc_valid_roundtrip_still_works():
    items = [{
        "type": "computer_call",
        "action": {"type": "click", "x": 10, "y": 20},
    }]
    out = resp.convert_computer_calls_xy2desc(items, DESC2XY)
    assert out[0]["action"]["element_description"] == "Submit"
    assert "x" not in out[0]["action"]


def test_get_all_element_descriptions_skips_non_dict():
    items = [
        "raw",
        {"type": "computer_call", "action": "click"},
        {"type": "computer_call",
         "action": {"type": "click", "element_description": "Submit"}},
    ]
    descs = resp.get_all_element_descriptions(items)
    assert descs == ["Submit"] or set(descs) == {"Submit"}

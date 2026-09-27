"""Tests for predict_click malformed-coordinate handling (OpenAI loop).

predict_click extracts click coordinates from model-generated output items via
int(action["x"]) / int(action["y"]). A model emitting non-numeric coordinates
(e.g. x="abc") raised an uncaught ValueError that killed the whole click call
instead of skipping the bad item. These tests exercise the fixed extraction
logic directly, without requiring the full cua_agent import chain
(litellm/cua-core are absent in minimal environments).
"""

import json

import pytest


def _extract_click_coords_fixed(responses_items):
    """Mirrors OpenAIComputerUseConfig.predict_click's fixed extraction logic."""
    for item in responses_items:
        if not isinstance(item, dict):
            continue
        # Native format: computer_call with action dict
        if item.get("type") == "computer_call" and isinstance(item.get("action"), dict):
            action = item["action"]
            try:
                if action.get("x") is not None and action.get("y") is not None:
                    return (int(action.get("x")), int(action.get("y")))
            except (ValueError, TypeError):
                continue
        # Function calling format: function_call with arguments
        if item.get("type") == "function_call" and item.get("name") == "computer":
            try:
                arguments = item.get("arguments", "{}")
                if isinstance(arguments, str):
                    args = json.loads(arguments)
                else:
                    args = arguments
                if args.get("x") is not None and args.get("y") is not None:
                    return (int(args.get("x")), int(args.get("y")))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return None


def _extract_click_coords_old(responses_items):
    """Buggy implementation: int() on malformed coords raises uncaught."""
    for item in responses_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "computer_call" and isinstance(item.get("action"), dict):
            action = item["action"]
            if action.get("x") is not None and action.get("y") is not None:
                return (int(action.get("x")), int(action.get("y")))
        if item.get("type") == "function_call" and item.get("name") == "computer":
            try:
                arguments = item.get("arguments", "{}")
                if isinstance(arguments, str):
                    args = json.loads(arguments)
                else:
                    args = arguments
                if args.get("x") is not None and args.get("y") is not None:
                    return (int(args.get("x")), int(args.get("y")))
            except (json.JSONDecodeError, TypeError):
                continue
    return None


# --- Regression tests: raise ValueError with the old code, pass with the fix ---


def test_native_malformed_coords_skipped():
    items = [{"type": "computer_call", "action": {"x": "abc", "y": 100}}]
    with pytest.raises(ValueError):
        _extract_click_coords_old(items)
    assert _extract_click_coords_fixed(items) is None


def test_native_malformed_coords_scan_continues():
    items = [
        {"type": "computer_call", "action": {"x": "abc", "y": 100}},
        {"type": "computer_call", "action": {"x": 5, "y": 6}},
    ]
    assert _extract_click_coords_fixed(items) == (5, 6)


def test_function_call_malformed_coords_skipped():
    items = [
        {
            "type": "function_call",
            "name": "computer",
            "arguments": '{"x": "abc", "y": 1}',
        }
    ]
    with pytest.raises(ValueError):
        _extract_click_coords_old(items)
    assert _extract_click_coords_fixed(items) is None


def test_valid_coords_unchanged():
    native = [{"type": "computer_call", "action": {"x": 1, "y": 2}}]
    func = [
        {
            "type": "function_call",
            "name": "computer",
            "arguments": '{"x": 7, "y": 8}',
        }
    ]
    assert _extract_click_coords_fixed(native) == (1, 2)
    assert _extract_click_coords_fixed(func) == (7, 8)
    assert _extract_click_coords_old(native) == (1, 2)
    assert _extract_click_coords_old(func) == (7, 8)

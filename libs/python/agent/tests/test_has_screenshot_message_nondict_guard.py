"""Red/green test: _has_screenshot_message in generic_vlm / opencua / qwen35
must skip non-dict messages instead of raising AttributeError.

The nested helper scanned completion messages for the 'Taking a screenshot'
marker via m.get("content") on every entry -- a malformed (non-dict) message in
history crashed predict_step before any model call. Fix: skip non-dict entries.

Self-contained: extracts the nested _has_screenshot_message from each loop's
real source by AST and exec's it in isolation (the loops need litellm etc. to
import, so we test the real nested function, not the whole module).
"""

import ast
from pathlib import Path

LOOPS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"
SCREENSHOT_TEXT = "Taking a screenshot to see the current computer screen."


def _extract_helper(path):
    """Return the real _has_screenshot_message defined in path."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_has_screenshot_message":
            code = compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec")
            from typing import Any, Dict, List

            ns = {"List": List, "Dict": Dict, "Any": Any}
            exec(code, ns)
            return ns["_has_screenshot_message"]
    raise AssertionError(f"_has_screenshot_message not found in {path}")


HELPERS = {
    name: _extract_helper(LOOPS_DIR / f"{name}.py")
    for name in ("generic_vlm", "opencua", "qwen35")
}


def test_all_helpers_found():
    assert len(HELPERS) == 3


def test_skips_non_dict_messages():
    for name, fn in HELPERS.items():
        msgs = [
            42,
            "garbage",
            None,
            ["nested", "list"],
            {"role": "user", "content": "hello"},
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ]
        assert fn(msgs) is False, name


def test_still_detects_screenshot_marker():
    for name, fn in HELPERS.items():
        assert fn([{"role": "user", "content": SCREENSHOT_TEXT}]) is True, name
        assert (
            fn(
                [
                    42,
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": SCREENSHOT_TEXT}],
                    },
                ]
            )
            is True
        ), name


def test_returns_false_without_marker():
    for name, fn in HELPERS.items():
        assert fn([]) is False, name
        assert fn([{"role": "user", "content": "plain text"}]) is False, name


if __name__ == "__main__":
    test_all_helpers_found()
    test_skips_non_dict_messages()
    test_still_detects_screenshot_marker()
    test_returns_false_without_marker()
    print("PASS all 4")

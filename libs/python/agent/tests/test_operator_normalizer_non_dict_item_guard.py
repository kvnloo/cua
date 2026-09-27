"""OperatorNormalizerCallback.on_llm_end must tolerate non-dict output items.

The normalizer called item.get("type") on every entry of the model output
list. A malformed model output entry (string, None, int) raised
AttributeError out of the unisolated on_llm_end callback chain and killed
the run. Non-dict entries are now left untouched for downstream handlers
while dict normalization is unchanged.
"""

import asyncio
import importlib.util
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_validator():
    pkg = types.ModuleType("c65_ov_pkg")
    pkg.__path__ = [os.path.join(_HERE, "..", "cua_agent", "callbacks")]
    sys.modules["c65_ov_pkg"] = pkg
    for name in ("base", "operator_validator"):
        spec = importlib.util.spec_from_file_location(
            f"c65_ov_pkg.{name}",
            os.path.join(_HERE, "..", "cua_agent", "callbacks", f"{name}.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"c65_ov_pkg.{name}"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["c65_ov_pkg.operator_validator"]


_validator = _load_validator()


def _run(output):
    cb = _validator.OperatorNormalizerCallback()
    return asyncio.run(cb.on_llm_end(output))


def test_string_item_passes_through():
    out = [{"type": "message"}, "garbage"]
    assert _run(out) == out


def test_none_item_passes_through():
    out = [None, {"type": "message"}]
    assert _run(out) == out


def test_int_item_passes_through():
    out = [42]
    assert _run(out) == out


def test_mixed_items_do_not_crash():
    out = [{"type": "computer_call", "action": {"type": "left_click"}},
           "junk", None, 7]
    result = _run(out)
    assert result[1:] == ["junk", None, 7]
    assert result[0]["action"]["type"] == "click"
    assert result[0]["action"]["button"] == "left"


def test_computer_call_still_normalized():
    out = [{"type": "computer_call", "action": {"type": "hotkey"}}]
    result = _run(out)
    assert result[0]["action"]["type"] == "keypress"


def test_non_computer_call_dicts_untouched():
    out = [{"type": "message", "content": "hi"}]
    assert _run(out) == out


def test_none_output_is_fine():
    assert _run(None) is None


def test_empty_output_is_fine():
    assert _run([]) == []

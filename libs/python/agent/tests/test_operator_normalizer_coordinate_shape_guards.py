"""Tests for the operator-normalizer malformed-coordinate guard.

Covers:
- valid 2-number coordinate still renames to x/y (control, green on both)
- None / short list / dict coordinate no longer crash the normalizer
  (TypeError/IndexError/KeyError on base, killing the run out of on_llm_end)
- string coordinate no longer silently becomes a char pair (on base
  "100,200" produced x="1", y="0" — a wrong click)

The real operator_validator module is loaded (not copied); only the
cua_agent.callbacks.base import is provided.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

CB_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "callbacks"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"cua_agent.callbacks.{name}", CB_DIR / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ensure():
    if "cua_agent.callbacks.operator_validator" in sys.modules:
        return sys.modules["cua_agent.callbacks.operator_validator"]
    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    cb_pkg = types.ModuleType("cua_agent.callbacks")
    cb_pkg.__path__ = []
    sys.modules.setdefault("cua_agent", pkg)
    sys.modules.setdefault("cua_agent.callbacks", cb_pkg)
    _load("base")
    return _load("operator_validator")


def _normalize(coord):
    mod = _ensure()
    item = {"type": "computer_call", "action": {"type": "click", "coordinate": coord}}
    out = asyncio.run(mod.OperatorNormalizerCallback().on_llm_end([item]))
    return out[0]["action"]


def test_valid_coordinate_renames_to_xy():
    action = _normalize([100, 200])
    assert action["x"] == 100 and action["y"] == 200
    assert "coordinate" not in action


def test_valid_tuple_coordinate_renames_to_xy():
    action = _normalize((100, 200))
    assert action["x"] == 100 and action["y"] == 200


@pytest.mark.parametrize("bad", [None, [100], {"x": 1}, "100,200", [True, False]])
def test_malformed_coordinate_dropped_not_crash_or_garbage(bad):
    action = _normalize(bad)  # must not raise
    assert "coordinate" not in action
    assert "x" not in action and "y" not in action

"""Tests for agent callback malformed-input guards.

Covers:
- BudgetManagerCallback.on_usage with None / non-dict usage payloads
- OperatorValidator.on_llm_end with non-dict entries in the output list

The real callbacks modules are loaded (not copied); only the cua_agent
package graph is stubbed.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

CB_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "callbacks"


def _install_stubs():
    cua_agent = types.ModuleType("cua_agent")
    cua_agent.__path__ = []
    cb_pkg = types.ModuleType("cua_agent.callbacks")
    cb_pkg.__path__ = []
    sys.modules.update({"cua_agent": cua_agent, "cua_agent.callbacks": cb_pkg})


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"cua_agent.callbacks.{name}", CB_DIR / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"cua_agent.callbacks.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_install_stubs()
_load("base")
budget_mod = _load("budget_manager")
validator_mod = _load("operator_validator")

BudgetManagerCallback = budget_mod.BudgetManagerCallback
OperatorValidator = validator_mod.OperatorNormalizerCallback


def _run(coro):
    return asyncio.run(coro)


# --- BudgetManagerCallback.on_usage --------------------------------------------

def test_budget_on_usage_none_ignored():
    cb = BudgetManagerCallback(max_budget=10.0)
    _run(cb.on_usage(None))  # base: TypeError ('in' on NoneType)
    assert cb.total_cost == 0.0


def test_budget_on_usage_non_dict_ignored():
    cb = BudgetManagerCallback(max_budget=10.0)
    _run(cb.on_usage("not-a-dict"))  # base: works for str ('in' on str) but wrong
    _run(cb.on_usage(123))
    assert cb.total_cost == 0.0


def test_budget_on_usage_tracks_cost():
    cb = BudgetManagerCallback(max_budget=10.0)
    _run(cb.on_usage({"response_cost": 2.5, "input_tokens": 10}))
    assert cb.total_cost == 2.5


def test_budget_on_usage_without_cost_key():
    cb = BudgetManagerCallback(max_budget=10.0)
    _run(cb.on_usage({"input_tokens": 10}))
    assert cb.total_cost == 0.0


# --- OperatorValidator.on_llm_end ----------------------------------------------

def test_validator_non_dict_items_skipped():
    v = OperatorValidator()
    output = [
        "not-a-dict",  # base: AttributeError on .get
        None,
        42,
        {"type": "message", "role": "assistant"},
    ]
    result = _run(v.on_llm_end(output))
    assert result == output


def test_validator_computer_call_still_normalized():
    v = OperatorValidator()
    output = [
        {
            "type": "computer_call",
            "action": {"type": "left_click", "x": 10, "y": 20},
        }
    ]
    result = _run(v.on_llm_end(output))
    assert result[0]["action"]["type"] == "click"
    assert result[0]["action"]["button"] == "left"


def test_validator_empty_and_none_output():
    v = OperatorValidator()
    assert _run(v.on_llm_end([])) == []
    assert _run(v.on_llm_end(None)) is None

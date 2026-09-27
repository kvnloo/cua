"""Tests for LoggingCallback usage-accumulation guards.

Covers:
- _update_usage with None or non-dict usage payloads (ignored, run survives)
- usage shape drift across calls (scalar vs dict) and non-numeric values

The real logging callback module is loaded (not copied); only the cua_agent
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
base_cb = _load("base")
logging_mod = _load("logging")

LoggingCallback = logging_mod.LoggingCallback


def _cb():
    cb = LoggingCallback()
    cb.total_usage = {}
    return cb


def _run(coro):
    return asyncio.run(coro)


# --- _update_usage ------------------------------------------------------------


def test_update_usage_none_ignored():
    cb = _cb()
    cb._update_usage(None)  # base: AttributeError on None.items()
    assert cb.total_usage == {}


def test_update_usage_non_dict_ignored():
    cb = _cb()
    cb._update_usage("usage-string")  # base: AttributeError on str.items()
    cb._update_usage([1, 2])
    assert cb.total_usage == {}


def test_update_usage_accumulates_numerics():
    cb = _cb()
    cb._update_usage({"prompt_tokens": 10, "completion_tokens": 5})
    cb._update_usage({"prompt_tokens": 3})
    assert cb.total_usage == {"prompt_tokens": 13, "completion_tokens": 5}


def test_update_usage_scalar_to_dict_drift():
    cb = _cb()
    cb._update_usage({"a": 5})
    cb._update_usage({"a": {"b": 1}})  # base: AttributeError (int has no .items)
    assert cb.total_usage["a"] == {"b": 1}


def test_update_usage_dict_to_scalar_drift():
    cb = _cb()
    cb._update_usage({"a": {"b": 1}})
    cb._update_usage({"a": 7})  # base: TypeError (dict += int)
    assert cb.total_usage["a"] == 7


def test_update_usage_non_numeric_carried_over():
    cb = _cb()
    cb._update_usage({"prompt_tokens": 10, "provider": "openai"})
    cb._update_usage({"prompt_tokens": 4, "provider": "anthropic"})  # base: TypeError
    assert cb.total_usage["prompt_tokens"] == 14
    assert cb.total_usage["provider"] == "anthropic"


def test_update_usage_null_values_ignored():
    cb = _cb()
    cb._update_usage({"prompt_tokens": 10})
    cb._update_usage({"prompt_tokens": None})  # base: TypeError (int += None)
    assert cb.total_usage["prompt_tokens"] == 10


def test_on_usage_end_to_end_malformed():
    cb = _cb()
    _run(cb.on_usage(None))
    _run(cb.on_usage("junk"))
    _run(cb.on_usage({"prompt_tokens": "not-a-number"}))
    _run(cb.on_usage({"prompt_tokens": 5}))
    assert cb.total_usage["prompt_tokens"] == 5

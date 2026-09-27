"""Tests for TelemetryCallback malformed usage-input guards.

Covers:
- on_usage with None or non-dict usage payloads (ignored, run survives)
- on_usage with null/non-numeric token counts (totals stay numeric)

The real telemetry callback module is loaded (not copied); only the
cua_agent package graph and cua_core.telemetry are stubbed.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

CB_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "callbacks"

EVENTS = []


def _install_stubs():
    cua_agent = types.ModuleType("cua_agent")
    cua_agent.__path__ = []
    cb_pkg = types.ModuleType("cua_agent.callbacks")
    cb_pkg.__path__ = []
    cua_core = types.ModuleType("cua_core")
    cua_core.__path__ = []
    core_tel = types.ModuleType("cua_core.telemetry")
    core_tel.is_telemetry_enabled = lambda: True
    core_tel.record_event = lambda name, props=None: EVENTS.append((name, props))
    sys.modules.update(
        {
            "cua_agent": cua_agent,
            "cua_agent.callbacks": cb_pkg,
            "cua_core": cua_core,
            "cua_core.telemetry": core_tel,
        }
    )


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
telemetry_mod = _load("telemetry")

TelemetryCallback = telemetry_mod.TelemetryCallback


class _Agent:
    model = "test-model"


def _cb():
    cb = TelemetryCallback(agent=_Agent())
    EVENTS.clear()  # drop the constructor's session-start event
    return cb


def _run(coro):
    return asyncio.run(coro)


# --- on_usage ---------------------------------------------------------------


def test_on_usage_none_ignored():
    cb = _cb()
    _run(cb.on_usage(None))  # base: AttributeError on None.get
    assert cb.total_usage == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "response_cost": 0.0,
    }
    assert EVENTS == []


def test_on_usage_non_dict_ignored():
    cb = _cb()
    _run(cb.on_usage("usage-string"))  # base: AttributeError on str.get
    _run(cb.on_usage([1, 2]))
    assert cb.total_usage["prompt_tokens"] == 0
    assert EVENTS == []


def test_on_usage_null_counts_ignored():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": None, "completion_tokens": None}))
    # base: TypeError on 0 + None
    assert cb.total_usage["prompt_tokens"] == 0
    assert cb.total_usage["completion_tokens"] == 0


def test_on_usage_string_counts_ignored():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": "100", "response_cost": "0.01"}))
    # base: TypeError on 0 + str
    assert cb.total_usage["prompt_tokens"] == 0
    assert cb.total_usage["response_cost"] == 0.0


def test_on_usage_bool_counts_ignored():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": True}))
    assert cb.total_usage["prompt_tokens"] == 0


def test_on_usage_accumulates_wellformed():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": 10, "completion_tokens": 4, "response_cost": 0.02}))
    _run(cb.on_usage({"prompt_tokens": 5}))
    assert cb.total_usage["prompt_tokens"] == 15
    assert cb.total_usage["completion_tokens"] == 4
    assert cb.total_usage["response_cost"] == pytest.approx(0.02)
    assert len([e for e in EVENTS if e[0] == "agent_usage"]) == 2

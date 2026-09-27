"""Tests for the OTEL callback's malformed usage-input guards.

Covers:
- on_usage with None or non-dict usage payloads (ignored, run survives)
- on_usage with null/non-numeric token counts (no TypeError, no bogus record)

The real otel callback module is loaded (not copied); only the cua_agent
package graph and cua_core.telemetry are stubbed.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

CB_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "callbacks"

TOKEN_CALLS = []


def _install_stubs():
    cua_agent = types.ModuleType("cua_agent")
    cua_agent.__path__ = []
    cb_pkg = types.ModuleType("cua_agent.callbacks")
    cb_pkg.__path__ = []
    cua_core = types.ModuleType("cua_core")
    cua_core.__path__ = []
    core_tel = types.ModuleType("cua_core.telemetry")
    core_tel.is_otel_enabled = lambda: True
    core_tel.create_span = lambda *a, **k: None
    core_tel.record_error = lambda *a, **k: None
    core_tel.record_operation = lambda *a, **k: None
    core_tel.record_tokens = lambda **kw: TOKEN_CALLS.append(kw)
    core_tel.track_concurrent = lambda *a, **k: None
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
otel_mod = _load("otel")

OtelCallback = otel_mod.OtelCallback


class _Agent:
    model = "test-model"
    agent_loop = None


def _cb():
    TOKEN_CALLS.clear()
    return OtelCallback(agent=_Agent())


def _run(coro):
    return asyncio.run(coro)


# --- on_usage ---------------------------------------------------------------


def test_on_usage_none_ignored():
    cb = _cb()
    _run(cb.on_usage(None))  # base: AttributeError on None.get
    assert TOKEN_CALLS == []


def test_on_usage_non_dict_ignored():
    cb = _cb()
    _run(cb.on_usage("usage-string"))  # base: AttributeError on str.get
    _run(cb.on_usage([1, 2]))
    assert TOKEN_CALLS == []


def test_on_usage_null_counts_no_raise():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": None, "completion_tokens": None}))
    # base: TypeError on None > 0
    assert TOKEN_CALLS == []


def test_on_usage_string_counts_no_raise():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": "100"}))
    # base: TypeError on str > 0
    assert TOKEN_CALLS == []


def test_on_usage_wellformed_records_tokens():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": 10, "completion_tokens": 4}))
    assert TOKEN_CALLS == [
        {"prompt_tokens": 10, "completion_tokens": 4, "model": "test-model"}
    ]


def test_on_usage_zero_counts_no_record():
    cb = _cb()
    _run(cb.on_usage({"prompt_tokens": 0, "completion_tokens": 0}))
    assert TOKEN_CALLS == []

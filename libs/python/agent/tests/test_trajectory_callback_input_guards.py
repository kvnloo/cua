"""Tests for TrajectorySaverCallback malformed-input guards.

Covers:
- on_usage/_update_usage with None or non-dict usage payloads
- usage shape drift across calls (scalar vs dict) and non-numeric values
- on_screenshot with corrupt base64 (telemetry must not kill the run)

The real callbacks modules are loaded (not copied); only the cua_agent
package graph is stubbed.
"""

import asyncio
import base64
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
saver_mod = _load("trajectory_saver")

TrajectorySaverCallback = saver_mod.TrajectorySaverCallback


def _saver(tmp_path):
    return TrajectorySaverCallback(trajectory_dir=str(tmp_path))


def _run(coro):
    return asyncio.run(coro)


# --- _update_usage ------------------------------------------------------------

def test_update_usage_none_ignored(tmp_path):
    cb = _saver(tmp_path)
    cb._update_usage(None)  # base: AttributeError on None.items()
    assert cb.total_usage == {}


def test_update_usage_non_dict_ignored(tmp_path):
    cb = _saver(tmp_path)
    cb._update_usage("usage-string")  # base: AttributeError on str.items()
    cb._update_usage([1, 2])
    assert cb.total_usage == {}


def test_update_usage_accumulates_numerics(tmp_path):
    cb = _saver(tmp_path)
    cb._update_usage({"input_tokens": 10, "output_tokens": 5})
    cb._update_usage({"input_tokens": 3})
    assert cb.total_usage == {"input_tokens": 13, "output_tokens": 5}


def test_update_usage_scalar_to_dict_drift(tmp_path):
    cb = _saver(tmp_path)
    cb._update_usage({"a": 5})
    cb._update_usage({"a": {"b": 1}})  # base: AttributeError (int has no .items)
    assert cb.total_usage["a"] == {"b": 1}


def test_update_usage_dict_to_scalar_drift(tmp_path):
    cb = _saver(tmp_path)
    cb._update_usage({"a": {"b": 1}})
    cb._update_usage({"a": 7})  # base: TypeError (dict += int)
    assert cb.total_usage["a"] == 7


def test_update_usage_non_numeric_carried_over(tmp_path):
    cb = _saver(tmp_path)
    cb._update_usage({"model": "gpt-5"})  # base: TypeError (0 + "gpt-5")
    assert cb.total_usage["model"] == "gpt-5"


def test_update_usage_bool_not_accumulated(tmp_path):
    cb = _saver(tmp_path)
    cb._update_usage({"cached": True})
    cb._update_usage({"cached": True})
    assert cb.total_usage["cached"] is True


def test_on_usage_none_does_not_raise(tmp_path):
    cb = _saver(tmp_path)
    _run(cb.on_usage(None))  # base: AttributeError propagates out of the callback
    assert cb.total_usage == {}


# --- on_screenshot ------------------------------------------------------------

def test_on_screenshot_corrupt_base64_skipped(tmp_path):
    cb = _saver(tmp_path)
    cb.trajectory_id = "t0"
    _run(cb.on_screenshot("!!!not-base64!!!", "shot"))  # base: binascii.Error
    assert cb.current_artifact == 0


def test_on_screenshot_bytes_still_saved(tmp_path):
    cb = _saver(tmp_path)
    cb.trajectory_id = "t0"
    _run(cb.on_screenshot(b"raw-bytes", "shot"))
    assert cb.current_artifact == 1


def test_on_screenshot_valid_base64_still_saved(tmp_path):
    cb = _saver(tmp_path)
    cb.trajectory_id = "t0"
    payload = base64.b64encode(b"fake-png-bytes").decode()
    _run(cb.on_screenshot(payload, "shot"))
    assert cb.current_artifact == 1

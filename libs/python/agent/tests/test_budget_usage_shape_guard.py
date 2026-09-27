"""BudgetManagerCallback.on_usage must tolerate malformed usage payloads.

A provider usage payload of None or a non-dict raised TypeError out of
on_usage and killed the run. Malformed payloads must be skipped while
well-formed numeric costs still accumulate.
"""

import asyncio
import importlib.util
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_budget_manager():
    pkg = types.ModuleType("c65_bm_pkg")
    pkg.__path__ = [os.path.join(_HERE, "..", "cua_agent", "callbacks")]
    sys.modules["c65_bm_pkg"] = pkg
    for name in ("base", "budget_manager"):
        spec = importlib.util.spec_from_file_location(
            f"c65_bm_pkg.{name}",
            os.path.join(_HERE, "..", "cua_agent", "callbacks", f"{name}.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"c65_bm_pkg.{name}"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["c65_bm_pkg.budget_manager"]


_bm = _load_budget_manager()


def _cb():
    return _bm.BudgetManagerCallback(max_budget=10.0)


def _run(payload):
    cb = _cb()
    asyncio.run(cb.on_usage(payload))
    return cb.total_cost


def test_none_usage_is_ignored():
    assert _run(None) == 0.0


def test_string_usage_is_ignored():
    assert _run("response_cost") == 0.0


def test_int_usage_is_ignored():
    assert _run(42) == 0.0


def test_list_usage_is_ignored():
    assert _run([{"response_cost": 1.0}]) == 0.0


def test_numeric_cost_accumulates():
    assert _run({"response_cost": 1.5}) == 1.5


def test_missing_cost_accumulates_nothing():
    assert _run({"prompt_tokens": 5}) == 0.0


def test_none_cost_is_ignored():
    assert _run({"response_cost": None}) == 0.0


def test_string_cost_is_ignored():
    assert _run({"response_cost": "1.0"}) == 0.0


def test_bool_cost_is_ignored():
    assert _run({"response_cost": True}) == 0.0


def test_empty_dict_is_fine():
    assert _run({}) == 0.0

"""Red-on-base tests: BudgetManagerCallback ignores non-numeric response_cost.

Defect (fork main): BudgetManagerCallback.on_usage did
`self.total_cost += usage["response_cost"]` unguarded. Providers can report
the cost as None or a non-numeric value (e.g. a string); the TypeError then
killed the whole run inside the _on_usage hook. Fixed: only int/float
(non-bool) costs are added.

Harness: loads the REAL cua_agent.callbacks.base + budget_manager modules
(no third-party deps needed).
"""

import asyncio
import importlib.util
import sys
import types as pytypes
from pathlib import Path

CB_PKG = Path(__file__).resolve().parents[1] / "cua_agent" / "callbacks"


def _load(modname, path):
    if modname in sys.modules:
        return sys.modules[modname]
    # parent packages for relative import `from .base import ...`
    for pkg, pth in (
        ("cua_agent", CB_PKG.parent),
        ("cua_agent.callbacks", CB_PKG),
    ):
        if pkg not in sys.modules:
            m = pytypes.ModuleType(pkg)
            m.__path__ = [str(pth)]
            sys.modules[pkg] = m
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


_load("cua_agent.callbacks.base", CB_PKG / "base.py")
bm = _load("cua_agent.callbacks.budget_manager", CB_PKG / "budget_manager.py")


def run_usage(cb, usage):
    asyncio.run(cb.on_usage(usage))


def test_none_cost_ignored():
    cb = bm.BudgetManagerCallback(max_budget=10.0)
    run_usage(cb, {"response_cost": None})
    assert cb.total_cost == 0.0


def test_string_cost_ignored():
    cb = bm.BudgetManagerCallback(max_budget=10.0)
    run_usage(cb, {"response_cost": "0.05"})
    assert cb.total_cost == 0.0


def test_bool_cost_ignored():
    cb = bm.BudgetManagerCallback(max_budget=10.0)
    run_usage(cb, {"response_cost": True})
    assert cb.total_cost == 0.0


def test_numeric_costs_accumulate():
    cb = bm.BudgetManagerCallback(max_budget=10.0)
    run_usage(cb, {"response_cost": 0.05})
    run_usage(cb, {"response_cost": 2})
    run_usage(cb, {"prompt_tokens": 100})  # no cost key: untouched
    assert abs(cb.total_cost - 2.05) < 1e-9


def test_budget_still_trips():
    cb = bm.BudgetManagerCallback(max_budget=1.0)
    run_usage(cb, {"response_cost": 0.5})
    assert asyncio.run(cb.on_run_continue({}, [], [])) is True
    run_usage(cb, {"response_cost": 0.6})
    assert asyncio.run(cb.on_run_continue({}, [], [])) is False


if __name__ == "__main__":
    tests = [
        test_none_cost_ignored,
        test_string_cost_ignored,
        test_bool_cost_ignored,
        test_numeric_costs_accumulate,
        test_budget_still_trips,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {str(e)[:120]}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

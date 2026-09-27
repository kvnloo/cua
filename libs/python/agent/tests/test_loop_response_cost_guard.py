"""Red/green test: loop usage bookkeeping must not crash on missing _hidden_params.

Ten loops built the usage dict with `response._hidden_params.get("response_cost", 0.0)`
unguarded (openai.py only checked hasattr, which passes when the attribute is
None). When a provider (or mock) returns a response without _hidden_params --
or with it set to None -- predict_step raised AttributeError AFTER the model
call succeeded, killing the step. A None response_cost also propagated into
BudgetManagerCallback.total_cost += None.

Fix: shared `response_cost()` helper in cua_agent/responses.py; all ten loops
use it. The remaining three loops (composed_grounded, moondream3, omniparser)
are covered by the sibling branch muse/predict-step-usage-none-guard.

Self-contained: response_cost is a plain function, AST-extracted from the real
file. The base expressions are extracted from actual base file text via
`git show HEAD:...` and exec'd against fake responses.
"""

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

LOOPS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"
RESPONSES = Path(__file__).resolve().parent.parent / "cua_agent" / "responses.py"
AGENT_ROOT = Path(__file__).resolve().parent.parent


def _exec_fn(path, name):
    tree = ast.parse(Path(path).read_text())
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == name
    )
    ns = {"Any": Any}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return ns[name]


def _base_text(rel):
    return subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        capture_output=True,
        text=True,
        cwd=AGENT_ROOT.parent,
        check=True,
    ).stdout


def _base_dict_expr_cost():
    """The base dict-literal usage entry, exec'd against a fake response."""
    src = _base_text("libs/python/agent/cua_agent/loops/generic_vlm.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "response_cost":
                    return ast.get_source_segment(src, v)
    raise AssertionError("base response_cost expression not found")


def _base_openai_cost():
    """The base openai.py usage-cost block as a callable(usage, response)."""
    import textwrap

    src = _base_text("libs/python/agent/cua_agent/loops/openai.py")
    block = "\n".join(
        line
        for line in src.splitlines()
        if "_hidden_params" in line and "response_cost" in line
    )
    # keep the guard lines (if/elif) too so the full base logic is exercised
    lines = src.splitlines()
    start = next(i for i, l in enumerate(lines) if "# Add response cost if available" in l)
    end = next(i for i, l in enumerate(lines[start:], start) if "response_cost" in l and i > start + 1)
    fn_src = (
        "def _base_openai_cost(usage, response):\n"
        + textwrap.indent(textwrap.dedent("\n".join(lines[start : end + 1])), "    ")
        + "\n    return usage\n"
    )
    ns = {}
    exec(compile(fn_src, "<base_openai>", "exec"), ns)
    return ns["_base_openai_cost"]


RESPONSE_COST = _exec_fn(RESPONSES, "response_cost")
BASE_EXPR = _base_dict_expr_cost()
BASE_OPENAI_COST = _base_openai_cost()


def _base_cost(response):
    ns = {"response": response}
    exec(f"d = {{'response_cost': {BASE_EXPR}}}", ns)
    return ns["d"]["response_cost"]


def test_helper_found():
    assert callable(RESPONSE_COST)


def test_well_formed_control():
    r = SimpleNamespace(_hidden_params={"response_cost": 1.5})
    assert RESPONSE_COST(r) == 1.5
    assert _base_cost(r) == 1.5


def test_missing_hidden_params():
    r = SimpleNamespace()
    try:
        _base_cost(r)
        base_crashed = False
    except AttributeError:
        base_crashed = True
    assert base_crashed, "base must crash on missing _hidden_params"
    assert RESPONSE_COST(r) == 0.0


def test_none_hidden_params():
    r = SimpleNamespace(_hidden_params=None)
    try:
        _base_cost(r)
        base_crashed = False
    except AttributeError:
        base_crashed = True
    assert base_crashed, "base must crash on _hidden_params=None"
    assert RESPONSE_COST(r) == 0.0


def test_non_dict_hidden_params():
    r = SimpleNamespace(_hidden_params="junk")
    try:
        _base_cost(r)
        base_crashed = False
    except AttributeError:
        base_crashed = True
    assert base_crashed, "base must crash on non-dict _hidden_params"
    assert RESPONSE_COST(r) == 0.0


def test_none_response_cost():
    r = SimpleNamespace(_hidden_params={"response_cost": None})
    assert RESPONSE_COST(r) == 0.0
    # base propagated the None into the usage dict (crashes downstream at +=)
    assert _base_cost(r) is None


def test_dict_response_preserved():
    # openai.py accepted dict responses; behavior must be preserved
    assert RESPONSE_COST({"_hidden_params": {"response_cost": 2.5}}) == 2.5
    assert RESPONSE_COST({}) == 0.0


def test_openai_base_none_hidden_params():
    r = SimpleNamespace(_hidden_params=None)
    try:
        BASE_OPENAI_COST({"x": 1}, r)
        base_crashed = False
    except AttributeError:
        base_crashed = True
    assert base_crashed, "base openai.py must crash on _hidden_params=None"
    assert RESPONSE_COST(r) == 0.0


def test_all_loops_use_helper():
    for name in [
        "anthropic",
        "generic_vlm",
        "glm45v",
        "opencua",
        "qwen35",
        "uitars",
        "uitars2",
        "yutori",
        "openai",
        "fara/config",
    ]:
        src = (LOOPS_DIR / f"{name}.py").read_text()
        assert "response_cost(response)" in src, name
        assert "response._hidden_params.get(" not in src, name

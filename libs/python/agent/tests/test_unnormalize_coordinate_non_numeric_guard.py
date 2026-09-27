"""Tests: _unnormalize_coordinate tolerates non-numeric coordinate entries.

loops/generic_vlm.py and loops/qwen35.py _unnormalize_coordinate ran
float(coord[0])/float(coord[1]) unguarded: a model-supplied coordinate pair
with non-numeric entries (e.g. ["abc", 200]) raised ValueError out of
predict_step. ValueError is not retryable, so the whole run died. The args
are now left untouched so downstream validation handles them.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
LOOPS_DIR = REPO / "libs/python/agent/cua_agent/loops"

FILES = {
    "generic_vlm": LOOPS_DIR / "generic_vlm.py",
    "qwen35": LOOPS_DIR / "qwen35.py",
}


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load(name):
    for mod_name in list(sys.modules):
        if mod_name == "t3_pkg" or mod_name.startswith("t3_pkg.") or mod_name.startswith("litellm"):
            del sys.modules[mod_name]

    _stub("litellm")
    trans = _stub(
        "litellm.responses.litellm_completion_transformation.transformation",
        LiteLLMCompletionResponsesConfig=object,
    )
    _stub("litellm.responses.litellm_completion_transformation").transformation = trans
    _stub("litellm.responses").litellm_completion_transformation = sys.modules[
        "litellm.responses.litellm_completion_transformation"
    ]

    pkg = _stub("t3_pkg")
    pkg.__path__ = []
    loops_pkg = _stub("t3_pkg.loops")
    loops_pkg.__path__ = []
    _stub("t3_pkg.decorators", register_agent=lambda *a, **k: (lambda cls: cls))
    _stub("t3_pkg.loops.base", AsyncAgentConfig=object)
    _stub(
        "t3_pkg.responses",
        convert_completion_messages_to_responses_items=lambda x: x,
        convert_responses_items_to_completion_messages=lambda x: x,
        make_reasoning_item=lambda x: x,
    )
    _stub("t3_pkg.types", AgentCapability=str)

    spec = importlib.util.spec_from_file_location(f"t3_pkg.loops.{name}", FILES[name])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"t3_pkg.loops.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_non_numeric_coordinate_leaves_args_untouched(loop):
    mod = _load(loop)
    import asyncio

    args = {"action": "left_click", "coordinate": ["abc", 200]}
    out = asyncio.run(mod._unnormalize_coordinate(dict(args), (1920, 1080)))
    assert out == args


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_numeric_string_coordinate_converted(loop):
    mod = _load(loop)
    import asyncio

    out = asyncio.run(
        mod._unnormalize_coordinate({"coordinate": ["500", "500"]}, (1920, 1080))
    )
    assert out["coordinate"] == [960, 540]


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_missing_coordinate_passthrough(loop):
    mod = _load(loop)
    import asyncio

    args = {"action": "wait", "time": 1}
    out = asyncio.run(mod._unnormalize_coordinate(dict(args), (1920, 1080)))
    assert out == args

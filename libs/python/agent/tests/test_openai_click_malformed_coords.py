"""Malformed OpenAI loop click coordinates must degrade gracefully, not crash.

``OpenAIComputerUseConfig.predict_click`` parsed model-controlled coordinates
unguarded:

- Native ``computer_call`` path: ``int(action.get("x"))`` raised ``ValueError``
  on non-numeric strings (e.g. "abc"), ``OverflowError`` on infinite floats,
  and silently coerced bools (``int(True) == 1``).
- Function-call path: the ``except (json.JSONDecodeError, TypeError)`` did not
  cover ``args.get`` on a JSON array payload (``AttributeError``) or
  ``int(args.get("x"))`` on a non-numeric string (``ValueError``).

Fix: a ``_safe_pixel_int`` gate coerces only finite numeric values (bools and
non-numeric strings rejected). Items with unusable coordinates are skipped so
``predict_click`` returns None ("prediction failed") instead of crashing.
"""
import asyncio
import base64
import importlib.util
import io
import json
import sys
import types
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1] / "cua_agent"


def _mod(name, path=None, **attrs):
    m = types.ModuleType(name)
    if path is not None:
        m.__path__ = path
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


RESPONSES = {"output": []}


async def _fake_aresponses(**kwargs):
    return RESPONSES


def _install_stubs():
    class BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _deco(*a, **k):
        def wrap(f):
            return f

        return wrap

    _mod("pydantic", BaseModel=BaseModel, field_validator=_deco,
         model_validator=_deco)

    _mod("litellm", path=[],
         acompletion=None,
         aresponses=_fake_aresponses,
         ResponseInputParam=dict,
         ResponsesAPIResponse=dict,
         ToolParam=dict)
    _mod("litellm.responses", path=[])
    _mod("litellm.responses.utils", path=[], Usage=dict)


def _pkg(name, path):
    m = types.ModuleType(name)
    m.__path__ = [path]
    m.__package__ = name
    sys.modules[name] = m
    return m


def _load(dotted, path):
    spec = importlib.util.spec_from_file_location(dotted, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = m
    spec.loader.exec_module(m)
    return m


def _load_openai():
    for key in [k for k in sys.modules if k == "cua_agent"
                or k.startswith(("cua_agent.", "pydantic", "litellm"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _pkg("cua_agent.loops", base + "/loops")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.loops.base", base + "/loops/base.py")
    return _load("cua_agent.loops.openai", base + "/loops/openai.py")


om = _load_openai()
cfg = om.OpenAIComputerUseConfig()

_buf = io.BytesIO()
Image.new("RGB", (4, 4)).save(_buf, format="PNG")
IMG_B64 = base64.b64encode(_buf.getvalue()).decode()


def click(output):
    global RESPONSES
    RESPONSES = {"output": output}
    return asyncio.run(cfg.predict_click(model="computer-use-preview",
                                         image_b64=IMG_B64,
                                         instruction="click the button"))


def _native(x, y):
    return [{"type": "computer_call",
             "action": {"type": "click", "x": x, "y": y}}]


def _fn(arguments):
    return [{"type": "function_call", "name": "computer",
             "arguments": arguments}]


def test_native_non_numeric_string_skipped():
    assert click(_native("abc", 200)) is None


def test_native_bool_rejected():
    assert click(_native(True, 200)) is None


def test_native_infinite_float_skipped():
    assert click(_native(float("inf"), 200)) is None


def test_native_numeric_string_coerced():
    assert click(_native("150", 200)) == (150, 200)


def test_native_valid_control():
    assert click(_native(100, 200)) == (100, 200)


def test_function_call_array_arguments_skipped():
    assert click(_fn("[1, 2, 3]")) is None


def test_function_call_non_numeric_string_skipped():
    assert click(_fn(json.dumps({"action": "click", "x": "abc", "y": 5}))) is None


def test_function_call_malformed_json_skipped():
    assert click(_fn("{nope")) is None


def test_function_call_valid_control():
    assert click(_fn(json.dumps({"action": "click", "x": 100, "y": 200}))) == (100, 200)


def test_empty_output_returns_none():
    assert click([]) is None

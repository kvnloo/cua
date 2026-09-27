"""UI-Ins predict_click must not raise on None/non-string model content.

``UIInsConfig.predict_click`` passed the raw model reply into
``parse_coordinates``, which calls ``re.findall(pattern, raw_string)`` —
a None content (model refusal/empty reply) or non-string content raised
TypeError out of ``predict_click``, whose contract is to return None on
failure. Sibling loops (holo, internvl, omniparser post-fix) guard with
``(content or "")``; predict_click's contract makes a None return the
right degradation here.

Fix: return None unless the reply is a non-empty string.
"""
import asyncio
import base64
import importlib.util
import sys
import types
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "cua_agent"


def _mod(name, path=None, **attrs):
    m = types.ModuleType(name)
    if path is not None:
        m.__path__ = path
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


ACOMPLETION_CONTENT = ""


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


async def _fake_acompletion(**kwargs):
    return _Resp(ACOMPLETION_CONTENT)


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
    _mod("litellm", path=[], acompletion=_fake_acompletion,
         aresponses=None, ResponseInputParam=dict,
         ResponsesAPIResponse=dict, ToolParam=dict)

    class _FakeImage:
        width = 100
        height = 100

        def resize(self, wh):
            return self

        def save(self, buf, format=None):
            buf.write(b"png")

    class _ImageMod(types.ModuleType):
        @staticmethod
        def open(fp):
            return _FakeImage()

    _mod("PIL", path=[])
    sys.modules["PIL.Image"] = _ImageMod("PIL.Image")


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


def _load_uiins():
    for key in [k for k in sys.modules if k == "cua_agent"
                or k.startswith(("cua_agent.", "pydantic", "litellm", "PIL"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _pkg("cua_agent.loops", base + "/loops")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.loops.base", base + "/loops/base.py")
    return _load("cua_agent.loops.uiins", base + "/loops/uiins.py")


ui = _load_uiins()

try:
    cfg = ui.UIInsConfig()
except TypeError:
    cfg = ui.UIInsConfig.__new__(ui.UIInsConfig)


def click(content):
    global ACOMPLETION_CONTENT
    ACOMPLETION_CONTENT = content
    return asyncio.run(cfg.predict_click(model="x+UI-Ins",
                                        image_b64="aGVsbG8=",
                                        instruction="click it"))


def test_none_content_returns_none():
    assert click(None) is None


def test_non_string_content_returns_none():
    assert click({"oops": "dict"}) is None
    assert click(["[1,2]"]) is None


def test_empty_content_returns_none():
    assert click("") is None


def test_valid_coordinates_still_parse():
    # "[50, 50]" on a 100x100 image resized by smart_resize stays 100x100
    # (3136 <= 10000 <= 8847360, factor 28 -> 84x84 -> scale 100/84)
    x, y = click("[50, 50]")
    assert isinstance(x, int) and isinstance(y, int)

"""Tests for grounding predict_click malformed-input guards.

Covers gelato, gta1, uiins, internvl, and holo predict_click:
- corrupt base64 / non-image bytes degrade to None instead of raising
- empty choices / missing message / non-text content degrade to None
- well-formed controls still return coordinates

The real loop modules are loaded (not copied) with only the heavy
third-party deps (litellm) and the cua_agent package graph stubbed out.
"""

import asyncio
import base64
import importlib.util
import io
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

LOOP_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "loops"


def _install_stubs():
    """Stub litellm and the cua_agent package graph; load real base module."""
    litellm = types.ModuleType("litellm")

    async def _acompletion(**kwargs):
        raise AssertionError("litellm.acompletion must be patched in tests")

    litellm.acompletion = _acompletion

    cua_agent = types.ModuleType("cua_agent")
    cua_agent.__path__ = []
    loops_pkg = types.ModuleType("cua_agent.loops")
    loops_pkg.__path__ = []
    types_mod = types.ModuleType("cua_agent.types")
    types_mod.AgentCapability = str
    types_mod.AgentResponse = dict
    types_mod.Messages = list
    types_mod.Tools = list
    decorators_mod = types.ModuleType("cua_agent.decorators")

    def register_agent(*args, **kwargs):
        def deco(cls):
            return cls

        return deco

    decorators_mod.register_agent = register_agent
    composed = types.ModuleType("cua_agent.loops.composed_grounded")

    class ComposedGroundedConfig:
        pass

    composed.ComposedGroundedConfig = ComposedGroundedConfig

    sys.modules.update(
        {
            "litellm": litellm,
            "cua_agent": cua_agent,
            "cua_agent.loops": loops_pkg,
            "cua_agent.types": types_mod,
            "cua_agent.decorators": decorators_mod,
            "cua_agent.loops.composed_grounded": composed,
        }
    )
    return litellm


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"cua_agent.loops.{name}", LOOP_DIR / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"cua_agent.loops.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


litellm = _install_stubs()
base_mod = _load("base")
gelato_mod = _load("gelato")
gta1_mod = _load("gta1")
uiins_mod = _load("uiins")
internvl_mod = _load("internvl")
holo_mod = _load("holo")

first_choice_text = getattr(base_mod, "first_choice_text", None)
needs_helper = pytest.mark.skipif(
    first_choice_text is None, reason="first_choice_text not present on base"
)


def _png_b64(w=64, h=64):
    img = Image.new("RGB", (w, h), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _resp(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _run(coro):
    return asyncio.run(coro)


def _acompletion_with(response):
    return patch.object(
        litellm, "acompletion", new=AsyncMock(return_value=response)
    )


# --- first_choice_text unit tests -------------------------------------------

MALFORMED_RESPONSES = [
    None,
    SimpleNamespace(),
    SimpleNamespace(choices=[]),
    SimpleNamespace(choices=None),
    SimpleNamespace(choices="not-a-list"),
    SimpleNamespace(choices=[SimpleNamespace()]),
    SimpleNamespace(choices=[SimpleNamespace(message=None)]),
    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace())]),
    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))]),
    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=123))]),
    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=["x"]))]),
]


@needs_helper
@pytest.mark.parametrize("response", MALFORMED_RESPONSES)
def test_first_choice_text_malformed_degrades_to_none(response):
    assert first_choice_text(response) is None


@needs_helper
def test_first_choice_text_wellformed():
    assert first_choice_text(_resp("hello")) == "hello"


# --- gelato / gta1 / uiins ----------------------------------------------------

THREE_LOOPS = [
    (gelato_mod, gelato_mod.GelatoConfig, "(100, 200)"),
    (gta1_mod, gta1_mod.GTA1Config, "(100, 200)"),
    (uiins_mod, uiins_mod.UIInsConfig, "(100, 200)"),
]


@pytest.mark.parametrize("mod,cls,coords", THREE_LOOPS)
def test_click_malformed_base64_returns_none(mod, cls, coords):
    cfg = cls()
    result = _run(cfg.predict_click("m", "!!!not-base64!!!", "click it"))
    assert result is None


@pytest.mark.parametrize("mod,cls,coords", THREE_LOOPS)
def test_click_non_image_bytes_returns_none(mod, cls, coords):
    bad = base64.b64encode(b"this is not an image").decode()
    cfg = cls()
    result = _run(cfg.predict_click("m", bad, "click it"))
    assert result is None


@pytest.mark.parametrize("mod,cls,coords", THREE_LOOPS)
def test_click_empty_choices_returns_none(mod, cls, coords):
    cfg = cls()
    with _acompletion_with(SimpleNamespace(choices=[])):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert result is None


@pytest.mark.parametrize("mod,cls,coords", THREE_LOOPS)
def test_click_none_message_returns_none(mod, cls, coords):
    cfg = cls()
    with _acompletion_with(SimpleNamespace(choices=[SimpleNamespace(message=None)])):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert result is None


@pytest.mark.parametrize("mod,cls,coords", THREE_LOOPS)
def test_click_none_content_returns_none(mod, cls, coords):
    cfg = cls()
    with _acompletion_with(_resp(None)):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert result is None


@pytest.mark.parametrize("mod,cls,coords", THREE_LOOPS)
def test_click_wellformed_returns_coords(mod, cls, coords):
    cfg = cls()
    with _acompletion_with(_resp(coords)):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert isinstance(result, tuple) and len(result) == 2
    assert all(isinstance(v, int) for v in result)


# --- internvl -----------------------------------------------------------------

def test_internvl_empty_choices_returns_none():
    cfg = internvl_mod.InternVLConfig()
    with _acompletion_with(SimpleNamespace(choices=[])):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert result is None


def test_internvl_non_string_content_returns_none():
    cfg = internvl_mod.InternVLConfig()
    with _acompletion_with(_resp(12345)):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert result is None


def test_internvl_wellformed_returns_coords():
    cfg = internvl_mod.InternVLConfig()
    with _acompletion_with(_resp("[[500, 500]]")):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert isinstance(result, tuple) and len(result) == 2


# --- holo ---------------------------------------------------------------------

def test_holo_empty_choices_returns_none():
    cfg = holo_mod.HoloConfig()
    with _acompletion_with(SimpleNamespace(choices=[])):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert result is None


def test_holo_malformed_base64_returns_none():
    # decode was already guarded; kept as a regression control
    cfg = holo_mod.HoloConfig()
    result = _run(cfg.predict_click("m", "!!!not-base64!!!", "click it"))
    assert result is None


def test_holo_wellformed_returns_coords():
    cfg = holo_mod.HoloConfig()
    with _acompletion_with(_resp('{"x": 100, "y": 200}')):
        result = _run(cfg.predict_click("m", _png_b64(), "click it"))
    assert isinstance(result, tuple) and len(result) == 2
    assert all(isinstance(v, int) for v in result)

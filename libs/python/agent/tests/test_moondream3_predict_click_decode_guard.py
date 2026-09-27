"""Red/green test: moondream3 predict_click must not raise on corrupt image data.

Moondream3PlusConfig.predict_click decoded the image BEFORE its try/except
blocks: _decode_image_b64(image_b64) raised binascii.Error on bad base64 (or
PIL errors on non-image bytes), escaping the 3x retry loop in predict_step
and killing the whole step — even though a grounding miss is supposed to
just leave the description unmapped.

Fix: decode inside try/except Exception and return None (a miss), so the
retry loop treats corrupt image data like any other grounding failure.

Self-contained: uses the REAL Pillow (installed) and the REAL responses.py
by file path (stubbed openai.types.responses dict-subclass modules); stubs
litellm / cua_agent.decorators / loops.base / types; loads the real
moondream3.py by file path; monkeypatches get_moondream_model with a fake
point() model so the valid-image control runs without torch.
"""

import base64
import importlib.util
import io
import sys
import types
from pathlib import Path

import asyncio
from PIL import Image

PKG_ROOT = Path(__file__).resolve().parent.parent
RESPONSES_PATH = PKG_ROOT / "cua_agent" / "responses.py"
MOONDREAM_PATH = PKG_ROOT / "cua_agent" / "loops" / "moondream3.py"


def _load_responses():
    stub_names = [
        "openai.types.responses.easy_input_message_param",
        "openai.types.responses.response_computer_tool_call_param",
        "openai.types.responses.response_function_tool_call_param",
        "openai.types.responses.response_input_image_param",
        "openai.types.responses.response_output_message_param",
        "openai.types.responses.response_output_text_param",
        "openai.types.responses.response_reasoning_item_param",
    ]
    attrs = [
        "EasyInputMessageParam",
        "ActionClick",
        "ActionDoubleClick",
        "ActionDrag",
        "ActionDragPath",
        "ActionKeypress",
        "ActionMove",
        "ActionScreenshot",
        "ActionScroll",
        "ActionType",
        "ActionWait",
        "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
        "ResponseFunctionToolCallParam",
        "ResponseInputImageParam",
        "ResponseOutputMessageParam",
        "ResponseOutputTextParam",
        "ResponseReasoningItemParam",
        "Summary",
    ]
    for name in ["openai", "openai.types", "openai.types.responses", *stub_names]:
        sys.modules.setdefault(name, types.ModuleType(name))
    for name in stub_names:
        mod = sys.modules[name]
        for attr in attrs:
            if not hasattr(mod, attr):
                setattr(mod, attr, dict)
    spec = importlib.util.spec_from_file_location(
        "cua_agent.responses", RESPONSES_PATH
    )
    responses = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.responses"] = responses
    spec.loader.exec_module(responses)
    return responses


def _install_stubs(responses):
    litellm = types.ModuleType("litellm")
    litellm.acompletion = lambda **k: None
    sys.modules["litellm"] = litellm

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    pkg.responses = responses
    sys.modules["cua_agent"] = pkg

    loops_pkg = types.ModuleType("cua_agent.loops")
    loops_pkg.__path__ = []
    sys.modules["cua_agent.loops"] = loops_pkg
    loops_base = types.ModuleType("cua_agent.loops.base")

    class AsyncAgentConfig:
        pass

    loops_base.AsyncAgentConfig = AsyncAgentConfig
    sys.modules["cua_agent.loops.base"] = loops_base

    decorators = types.ModuleType("cua_agent.decorators")
    decorators.register_agent = lambda *a, **k: (lambda cls: cls)
    sys.modules["cua_agent.decorators"] = decorators

    types_mod = types.ModuleType("cua_agent.types")
    types_mod.AgentCapability = str
    sys.modules["cua_agent.types"] = types_mod


class FakeModel:
    def point(self, img, instruction, settings=None):
        assert img.size == (8, 8), img.size
        return {"points": [{"x": 0.5, "y": 0.5}]}


def _load_moondream():
    _install_stubs(_load_responses())
    spec = importlib.util.spec_from_file_location(
        "cua_agent.loops.moondream3", MOONDREAM_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.loops.moondream3"] = mod
    spec.loader.exec_module(mod)
    mod.get_moondream_model = lambda: FakeModel()
    return mod


def _valid_b64():
    img = Image.new("RGB", (8, 8), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_corrupt_base64_returns_none():
    mod = _load_moondream()
    cfg = mod.Moondream3PlusConfig()
    assert (
        asyncio.run(
            cfg.predict_click(
                model="moondream3+gpt-4o", image_b64="!!!not-base64!!!", instruction="x"
            )
        )
        is None
    )


def test_non_image_bytes_returns_none():
    mod = _load_moondream()
    cfg = mod.Moondream3PlusConfig()
    not_png = base64.b64encode(b"this is not a png file").decode("ascii")
    assert (
        asyncio.run(
            cfg.predict_click(
                model="moondream3+gpt-4o", image_b64=not_png, instruction="x"
            )
        )
        is None
    )


def test_valid_image_still_returns_coordinates():
    mod = _load_moondream()
    cfg = mod.Moondream3PlusConfig()
    coords = asyncio.run(
        cfg.predict_click(
            model="moondream3+gpt-4o", image_b64=_valid_b64(), instruction="x"
        )
    )
    # 0.5 * 8 = 4.0 px, clamped to W-1 = 7
    assert coords == (4.0, 4.0), coords


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_corrupt_base64_returns_none())
    asyncio.run(test_non_image_bytes_returns_none())
    asyncio.run(test_valid_image_still_returns_coordinates())
    print("PASS test_moondream3_predict_click_decode_guard")

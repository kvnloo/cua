"""[muse] Skip Moondream detection (don't crash the step) on corrupt screenshots.

Defect (fork main): Moondream3PlusConfig.predict_step decoded the last
screenshot with the unguarded module-level _decode_image_b64 before the
thinking-model call. Corrupt driver bytes (bad base64 -> binascii.Error,
or non-image bytes -> PIL.UnidentifiedImageError) killed the whole step
before any model call, even though detection is best-effort annotation.

(This is the predict_step site; predict_click's decode is guarded on
sibling branch muse/moondream3-predict-click-decode-guard.)

Fix: decode failure skips detection (no annotated message) and the step
continues to the thinking-model call.

Red-on-base: run this file against fork main (git checkout -- moondream3.py
after copying the fix aside); the corrupt cases raise, the valid-image
control passes on both.
"""
import asyncio
import base64
import importlib.util
import io
import sys
import types as pytypes

from PIL import Image

REPO = "/home/hatch/workspace/scratch/cua-wt-muse-c58/libs/python/agent"


def _stub(name, **attrs):
    mod = pytypes.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load(pkg_name, file_path):
    spec = importlib.util.spec_from_file_location(pkg_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- stubs ------------------------------------------------------------------
class _FakeACompletion:
    response = None

    async def __call__(self, **kwargs):
        return _FakeACompletion.response


litellm = _stub("litellm", acompletion=_FakeACompletion())

pkg = _stub("cua_agent")
pkg.__path__ = [REPO + "/cua_agent"]
loops_pkg = _stub("cua_agent.loops")
loops_pkg.__path__ = [REPO + "/cua_agent/loops"]

_dict_param = type("DictParam", (dict,), {})
_openai = _stub("openai")
_openai_types = _stub("openai.types")
_openai_responses = _stub("openai.types.responses")
for _leaf, _names in {
    "openai.types.responses.easy_input_message_param": ["EasyInputMessageParam"],
    "openai.types.responses.response_computer_tool_call_param": [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionType", "ActionWait", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ],
    "openai.types.responses.response_function_tool_call_param": [
        "ResponseFunctionToolCallParam"
    ],
    "openai.types.responses.response_input_image_param": ["ResponseInputImageParam"],
    "openai.types.responses.response_output_message_param": [
        "ResponseOutputMessageParam"
    ],
    "openai.types.responses.response_output_text_param": ["ResponseOutputTextParam"],
    "openai.types.responses.response_reasoning_item_param": [
        "ResponseReasoningItemParam", "Summary"
    ],
}.items():
    _stub(_leaf, **{n: _dict_param for n in _names})


class _AgentConfigInfo:
    def __init__(self, *a, **k):
        for key, val in k.items():
            setattr(self, key, val)


_stub(
    "cua_agent.types",
    AgentCapability=str,
    AgentConfigInfo=_AgentConfigInfo,
)

# ---- real modules -------------------------------------------------------------
_load("cua_agent.responses", REPO + "/cua_agent/responses.py")
_load("cua_agent.decorators", REPO + "/cua_agent/decorators.py")
_load("cua_agent.loops.base", REPO + "/cua_agent/loops/base.py")
md3 = _load("cua_agent.loops.moondream3", REPO + "/cua_agent/loops/moondream3.py")


# ---- fakes --------------------------------------------------------------------
class FakeUsage:
    def model_dump(self):
        return {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


class FakeThinkingResponse:
    usage = FakeUsage()
    _hidden_params = {"response_cost": 0.01}

    def model_dump(self):
        return {"choices": [{"message": {"role": "assistant", "content": "done"}}]}


def corrupt_image_message(payload_b64):
    return {
        "type": "computer_call_output",
        "call_id": "c1",
        "output": {
            "type": "input_image",
            "image_url": f"data:image/png;base64,{payload_b64}",
        },
    }


def valid_png_b64():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def run_step(messages):
    async def _go():
        _FakeACompletion.response = FakeThinkingResponse()
        cfg = md3.Moondream3PlusConfig()
        return await cfg.predict_step(
            messages=messages, model="moondream3+gpt-4o", tools=[]
        )

    return asyncio.run(_go())


def _has_detection_message(output):
    return any(
        "Detected form UI elements" in c.get("text", "")
        for item in output
        for c in (item.get("content") or [])
        if isinstance(c, dict)
    )


def test_bad_base64_skips_detection_and_completes_step():
    out = run_step([corrupt_image_message("!!!not-base64!!!")])
    assert not _has_detection_message(out["output"]), out["output"]
    assert out["usage"]["prompt_tokens"] == 1


def test_undecodable_image_skips_detection_and_completes_step():
    garbage = base64.b64encode(b"this is not image data").decode()
    out = run_step([corrupt_image_message(garbage)])
    assert not _has_detection_message(out["output"]), out["output"]
    assert out["usage"]["total_tokens"] == 3


def test_valid_image_still_runs_detection():
    md3.get_moondream_model = lambda: object()
    md3._annotate_detect_and_label_ui = lambda img, m: ("annotb64", ["Submit button"])
    try:
        out = run_step([corrupt_image_message(valid_png_b64())])
    finally:
        del md3.get_moondream_model
        del md3._annotate_detect_and_label_ui
    texts = [
        c.get("text", "")
        for item in out["output"]
        for c in (item.get("content") or [])
        if isinstance(c, dict)
    ]
    assert any("Submit button" in t for t in texts), f"no detection message: {texts!r}"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} green")
    sys.exit(1 if failed else 0)

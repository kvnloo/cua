"""Tests for uitars predict_step empty-choices / missing-message guards.

UITARSConfig.predict_step extracted the model reply with
response.choices[0].message.content outside any try block: empty choices
raised IndexError and message=None raised AttributeError, both escaping
predict_step and killing the run (the run loop only retries transient
errors). Both shapes now degrade to an empty-output step, matching the
documented empty-step behavior. Additive to the live unmerged sibling
muse/uitars-step-unparseable-content, which covers the content shapes.
Real uitars.py is loaded with litellm acompletion stubbed and real PIL.
"""

import asyncio
import base64
import importlib.util
import io
import sys
import types

WT = "/home/hatch/workspace/scratch/cua-wt-muse-c59"
SRC = WT + "/libs/python/agent/cua_agent/loops/uitars.py"


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, choices):
        self.choices = choices
        self.usage = None
        self._hidden_params = {}


NEXT = {"response": None}


async def fake_acompletion(**kwargs):
    return NEXT["response"]


def _cls(name):
    return type(name, (), {})


def load():
    for m in [m for m in sys.modules if m.startswith(("cua_agent", "litellm", "openai"))]:
        del sys.modules[m]

    litellm = types.ModuleType("litellm")
    litellm.acompletion = fake_acompletion
    sys.modules["litellm"] = litellm

    class _Cfg:
        @classmethod
        def _transform_chat_completion_usage_to_responses_usage(cls, usage):
            class _U:
                def model_dump(self):
                    return {}

            return _U()

    trans = types.ModuleType("litellm.responses.litellm_completion_transformation.transformation")
    trans.LiteLLMCompletionResponsesConfig = _Cfg
    sys.modules["litellm.responses"] = types.ModuleType("litellm.responses")
    sys.modules["litellm.responses.litellm_completion_transformation"] = types.ModuleType(
        "litellm.responses.litellm_completion_transformation"
    )
    sys.modules["litellm.responses.litellm_completion_transformation.transformation"] = trans
    sys.modules["litellm.responses.utils"] = types.SimpleNamespace(Usage=_cls("Usage"))
    sys.modules["litellm.types"] = types.ModuleType("litellm.types")
    sys.modules["litellm.types.utils"] = types.SimpleNamespace(ModelResponse=_cls("ModelResponse"))

    sys.modules["openai"] = types.ModuleType("openai")
    sys.modules["openai.types"] = types.ModuleType("openai.types")
    sys.modules["openai.types.responses"] = types.ModuleType("openai.types.responses")
    sys.modules["openai.types.responses.response_computer_tool_call_param"] = types.SimpleNamespace(
        ActionType=_cls("ActionType"),
        ResponseComputerToolCallParam=_cls("ResponseComputerToolCallParam"),
    )
    sys.modules["openai.types.responses.response_input_param"] = types.SimpleNamespace(
        ComputerCallOutput=_cls("ComputerCallOutput")
    )
    sys.modules["openai.types.responses.response_output_message_param"] = types.SimpleNamespace(
        ResponseOutputMessageParam=_cls("ResponseOutputMessageParam")
    )
    sys.modules["openai.types.responses.response_reasoning_item_param"] = types.SimpleNamespace(
        ResponseReasoningItemParam=_cls("ResponseReasoningItemParam"), Summary=_cls("Summary")
    )

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = [WT + "/libs/python/agent/cua_agent"]
    sys.modules["cua_agent"] = pkg
    loops = types.ModuleType("cua_agent.loops")
    loops.__path__ = [WT + "/libs/python/agent/cua_agent/loops"]
    sys.modules["cua_agent.loops"] = loops

    def register_agent(*a, **k):
        def deco(cls):
            return cls

        return deco

    sys.modules["cua_agent.decorators"] = types.SimpleNamespace(register_agent=register_agent)
    sys.modules["cua_agent.responses"] = types.SimpleNamespace(
        **{n: (lambda *a, **k: {"type": n}) for n in (
            "make_click_item", "make_double_click_item", "make_drag_item",
            "make_input_image_item", "make_keypress_item", "make_output_text_item",
            "make_reasoning_item", "make_scroll_item", "make_type_item", "make_wait_item",
        )}
    )
    sys.modules["cua_agent.types"] = types.SimpleNamespace(
        AgentCapability=str, AgentResponse=dict, Messages=list, Tools=list
    )

    spec = importlib.util.spec_from_file_location("cua_agent.loops.uitars", SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.loops.uitars"] = mod
    spec.loader.exec_module(mod)
    return mod


def tiny_png_b64():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def messages(img):
    return [
        {"role": "user", "content": [
            {"type": "text", "text": "click the button"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
        ]}
    ]


async def main():
    mod = load()
    loop = mod.UITARSConfig()
    img = tiny_png_b64()
    results = []

    # 1. empty choices -> empty step, no raise (base: IndexError)
    NEXT["response"] = FakeResponse([])
    try:
        out = await loop.predict_step(messages(img), "ui-tars/x")
        ok = isinstance(out, dict) and out.get("output") == []
        results.append((ok, f"empty choices -> empty step ({out.get('output') if isinstance(out, dict) else out})"))
    except Exception as e:
        results.append((False, f"empty choices raised {type(e).__name__}"))

    # 2. message None -> empty step, no raise (base: AttributeError)
    NEXT["response"] = FakeResponse([FakeChoice(None)])
    try:
        out = await loop.predict_step(messages(img), "ui-tars/x")
        ok = isinstance(out, dict) and out.get("output") == []
        results.append((ok, f"message None -> empty step ({out.get('output') if isinstance(out, dict) else out})"))
    except Exception as e:
        results.append((False, f"message None raised {type(e).__name__}"))

    # 3. content None -> empty step, no raise (sibling shape; stays green)
    NEXT["response"] = FakeResponse([FakeChoice(FakeMessage(None))])
    try:
        out = await loop.predict_step(messages(img), "ui-tars/x")
        ok = isinstance(out, dict) and out.get("output") == []
        results.append((ok, "content None -> empty step"))
    except Exception as e:
        results.append((False, f"content None raised {type(e).__name__}"))

    # 4. control: well-formed click action still yields output items
    NEXT["response"] = FakeResponse([FakeChoice(FakeMessage("Thought: clicking\nAction: click(point='(500,500)')"))])
    try:
        out = await loop.predict_step(messages(img), "ui-tars/x")
        ok = isinstance(out, dict) and len(out.get("output", [])) > 0
        results.append((ok, f"valid response -> {len(out.get('output', [])) if isinstance(out, dict) else '?'} items"))
    except Exception as e:
        results.append((False, f"valid response raised {type(e).__name__}: {e}"))

    n_fail = 0
    for ok, label in results:
        print(("PASS" if ok else "FAIL"), "-", label)
        n_fail += not ok
    print(f"{len(results) - n_fail}/{len(results)} green")
    return n_fail


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

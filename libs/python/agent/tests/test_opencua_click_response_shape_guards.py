"""Red/green harness for OPENCUA predict_click response-shape guards.

Loads the REAL loops/opencua.py with litellm stubbed (mocked acompletion),
PIL real. Cases: empty choices / message None / content None degrade to
None; a well-formed response still returns rescaled floor coordinates.
On base, the degenerate shapes raise IndexError/AttributeError/TypeError.
"""
import asyncio
import base64
import importlib.util
import io
import sys
import types

WT = "/home/hatch/workspace/scratch/cua-wt-muse-c59"
SRC = WT + "/libs/python/agent/cua_agent/loops/opencua.py"


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, choices):
        self.choices = choices


NEXT = {"response": None}


async def fake_acompletion(**kwargs):
    return NEXT["response"]


def load():
    for m in [m for m in sys.modules if m.startswith("cua_agent")]:
        del sys.modules[m]
    litellm = types.ModuleType("litellm")
    litellm.acompletion = fake_acompletion
    sys.modules["litellm"] = litellm

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = [WT + "/libs/python/agent/cua_agent"]
    sys.modules["cua_agent"] = pkg
    loops = types.ModuleType("cua_agent.loops")
    loops.__path__ = [WT + "/libs/python/agent/cua_agent/loops"]
    sys.modules["cua_agent.loops"] = loops

    class AsyncAgentConfig:
        pass

    def register_agent(*a, **k):
        def deco(cls):
            return cls
        return deco

    litellm_pkg = types.ModuleType("litellm.responses")
    litellm_pkg.__path__ = []
    sys.modules["litellm.responses"] = litellm_pkg
    litellm_t = types.ModuleType("litellm.responses.litellm_completion_transformation")
    litellm_t.__path__ = []
    sys.modules["litellm.responses.litellm_completion_transformation"] = litellm_t
    sys.modules["litellm.responses.litellm_completion_transformation.transformation"] = types.SimpleNamespace(LiteLLMCompletionResponsesConfig=type("X", (), {}))
    sys.modules["cua_agent.responses"] = types.SimpleNamespace(
        convert_completion_messages_to_responses_items=lambda m: m,
        convert_responses_items_to_completion_messages=lambda m: m,
        make_reasoning_item=lambda *a, **k: {},
    )
    sys.modules["cua_agent.decorators"] = types.SimpleNamespace(register_agent=register_agent)
    class _CGC:  # avoid dragging composed_grounded -> agent.py into the harness
        pass
    sys.modules["cua_agent.loops.composed_grounded"] = types.SimpleNamespace(ComposedGroundedConfig=_CGC)
    sys.modules["cua_agent.loops.base"] = types.SimpleNamespace(AsyncAgentConfig=AsyncAgentConfig)
    class _AR: pass
    sys.modules["cua_agent.types"] = types.SimpleNamespace(AgentCapability=str, AgentResponse=_AR, Messages=list, Tools=list)

    spec = importlib.util.spec_from_file_location("cua_agent.loops.opencua", SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.loops.opencua"] = mod
    spec.loader.exec_module(mod)
    return mod


def tiny_png_b64():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def main():
    mod = load()
    cfg = mod.OpenCUAConfig() if hasattr(mod, "OpenCUAConfig") else None
    loop = cfg if cfg is not None else object.__new__(mod.OpenCUAConfig)
    img = tiny_png_b64()
    results = []

    # 1. empty choices -> None (base: IndexError)
    NEXT["response"] = FakeResponse([])
    try:
        out = await loop.predict_click("OPENCUA/x", img, "click ok")
        results.append((out is None, "empty choices -> None"))
    except Exception as e:
        results.append((False, f"empty choices raised {type(e).__name__}"))

    # 2. message None -> None (base: AttributeError)
    NEXT["response"] = FakeResponse([FakeChoice(None)])
    try:
        out = await loop.predict_click("OPENCUA/x", img, "click ok")
        results.append((out is None, "message None -> None"))
    except Exception as e:
        results.append((False, f"message None raised {type(e).__name__}"))

    # 3. content None -> None (base: bare-except swallows to (0,0) click)
    NEXT["response"] = FakeResponse([FakeChoice(FakeMessage(None))])
    try:
        out = await loop.predict_click("OPENCUA/x", img, "click ok")
        results.append((out is None, "content None -> None (not phantom (0,0))"))
    except Exception as e:
        results.append((False, f"content None raised {type(e).__name__}"))

    # 4. control: well-formed response still returns coords
    NEXT["response"] = FakeResponse([FakeChoice(FakeMessage("click(x=100, y=200)"))])
    try:
        out = await loop.predict_click("OPENCUA/x", img, "click ok")
        ok = isinstance(out, tuple) and len(out) == 2
        results.append((ok, f"valid response -> {out}"))
    except Exception as e:
        results.append((False, f"valid response raised {type(e).__name__}"))

    n_fail = 0
    for ok, label in results:
        print(("PASS" if ok else "FAIL"), "-", label)
        n_fail += not ok
    print(f"{len(results) - n_fail}/{len(results)} green")
    return n_fail


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Tests for holo predict_click response-shape guards.

HoloConfig.predict_click read response.choices[0].message.content unguarded:
empty choices raised IndexError and message=None raised AttributeError,
killing the click call. The documented contract is "or None if prediction
fails", so both shapes now degrade to None. Real holo.py is loaded with
litellm acompletion stubbed and real PIL.
"""

import asyncio
import base64
import importlib.util
import io
import sys
import types

WT = "/home/hatch/workspace/scratch/cua-wt-muse-c59"
SRC = WT + "/libs/python/agent/cua_agent/loops/holo.py"


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

    sys.modules["cua_agent.decorators"] = types.SimpleNamespace(register_agent=register_agent)
    sys.modules["cua_agent.loops.base"] = types.SimpleNamespace(AsyncAgentConfig=AsyncAgentConfig)
    sys.modules["cua_agent.types"] = types.SimpleNamespace(AgentCapability=str)

    spec = importlib.util.spec_from_file_location("cua_agent.loops.holo", SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.loops.holo"] = mod
    spec.loader.exec_module(mod)
    return mod


def tiny_png_b64():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def main():
    mod = load()
    loop = mod.HoloConfig()
    img = tiny_png_b64()
    results = []

    # 1. empty choices -> None (base: IndexError)
    NEXT["response"] = FakeResponse([])
    try:
        out = await loop.predict_click("Holo/x", img, "click ok")
        results.append((out is None, "empty choices -> None"))
    except Exception as e:
        results.append((False, f"empty choices raised {type(e).__name__}"))

    # 2. message None -> None (base: AttributeError)
    NEXT["response"] = FakeResponse([FakeChoice(None)])
    try:
        out = await loop.predict_click("Holo/x", img, "click ok")
        results.append((out is None, "message None -> None"))
    except Exception as e:
        results.append((False, f"message None raised {type(e).__name__}"))

    # 3. content None -> None (not a phantom click)
    NEXT["response"] = FakeResponse([FakeChoice(FakeMessage(None))])
    try:
        out = await loop.predict_click("Holo/x", img, "click ok")
        results.append((out is None, "content None -> None"))
    except Exception as e:
        results.append((False, f"content None raised {type(e).__name__}"))

    # 4. control: well-formed response still returns coords
    NEXT["response"] = FakeResponse([FakeChoice(FakeMessage('{"x": 32, "y": 48}'))])
    try:
        out = await loop.predict_click("Holo/x", img, "click ok")
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

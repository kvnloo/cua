"""Tests: HUD proxy tolerates malformed agent output shapes.

_map_agent_output_to_openai_blocks called item.get("type") on every output
entry and c["text"] on every message content entry: a non-dict entry (which
the run loop is hardened to tolerate on sibling branches) raised
AttributeError/TypeError and killed the HUD proxy call. Non-dict entries are
now skipped. FakeAsyncOpenAI.create also did agent_result["usage"] /
usage.get(...): a custom loop omitting usage (or reporting None) raised
KeyError/AttributeError; it now degrades to empty usage.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PROXY = (
    REPO / "libs/python/agent/cua_agent/integrations/hud/proxy.py"
)


def _model(name):
    cls = type(
        name,
        (),
        {
            "__init__": lambda self, **kw: setattr(self, "_d", kw) or None,
            "model_dump": lambda self: dict(self._d),
        },
    )
    cls.model_validate = classmethod(lambda c, d: c(**d))
    return cls


def _load_proxy():
    # Stub heavy third-party / sibling modules before loading proxy.py.
    openai_types = types.ModuleType("openai.types.responses")
    for n in [
        "Response",
        "ResponseComputerToolCall",
        "ResponseInputParam",
        "ResponseOutputItem",
        "ResponseOutputMessage",
        "ResponseOutputText",
        "ResponseReasoningItem",
        "ResponseUsage",
    ]:
        setattr(openai_types, n, _model(n))

    cua_agent_pkg = types.ModuleType("cua_agent")
    cua_agent_agent = types.ModuleType("cua_agent.agent")
    cua_agent_agent.ComputerAgent = object
    cua_agent_callbacks = types.ModuleType("cua_agent.callbacks")
    cua_agent_callbacks.PromptInstructionsCallback = object

    hud = types.ModuleType("hud")
    hud_agents = types.ModuleType("hud.agents")
    hud_agents.OperatorAgent = object
    hud_tools = types.ModuleType("hud.tools")
    hud_tools_computer = types.ModuleType("hud.tools.computer")
    hud_tools_computer_settings = types.ModuleType("hud.tools.computer.settings")
    hud_tools_computer_settings.computer_settings = object()

    mods = {
        "openai": types.ModuleType("openai"),
        "openai.types": types.ModuleType("openai.types"),
        "openai.types.responses": openai_types,
        "cua_agent": cua_agent_pkg,
        "cua_agent.agent": cua_agent_agent,
        "cua_agent.callbacks": cua_agent_callbacks,
        "hud": hud,
        "hud.agents": hud_agents,
        "hud.tools": hud_tools,
        "hud.tools.computer": hud_tools_computer,
        "hud.tools.computer.settings": hud_tools_computer_settings,
    }
    try:
        import PIL  # noqa: F401
    except ImportError:
        mods["PIL"] = types.ModuleType("PIL")
        mods["PIL"].Image = object
    for name, mod in mods.items():
        sys.modules.setdefault(name, mod)

    spec = importlib.util.spec_from_file_location("hud_proxy_under_test", PROXY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


proxy = _load_proxy()
map_blocks = proxy._map_agent_output_to_openai_blocks


def test_non_dict_items_skipped():
    out = map_blocks(
        [
            "stray-string",
            None,
            42,
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hi"}],
            },
        ]
    )
    # base: AttributeError on 'str'.get. fixed: stray entries skipped.
    assert len(out) == 1
    assert out[0].model_dump()["type"] == "message"


def test_non_dict_content_entries_skipped():
    out = map_blocks(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    "stray",
                    None,
                    {"type": "output_text", "text": "kept"},
                ],
            }
        ]
    )
    # base: TypeError on "stray"["text"]. fixed: kept.
    assert len(out) == 1
    dumped = out[0].model_dump()["content"]
    texts = [b["text"] if isinstance(b, dict) else b.model_dump()["text"] for b in dumped]
    assert texts == ["kept"]


def test_computer_call_still_mapped():
    out = map_blocks(
        [
            {
                "type": "computer_call",
                "call_id": "c1",
                "action": {"type": "click", "x": 1, "y": 2},
            }
        ]
    )
    assert len(out) == 1
    d = out[0].model_dump()
    assert d["type"] == "computer_call" and d["call_id"] == "c1"


def test_create_tolerates_missing_usage():
    class FakeAgent:
        async def run(self, messages):
            yield {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ]
                # no "usage" key at all
            }

    client = proxy.FakeAsyncOpenAI(FakeAgent())
    resp = asyncio.run(client.responses.create(model="m", input=[]))
    # base: KeyError on agent_result["usage"]. fixed: degrades to zeros.
    assert resp is not None


def test_create_tolerates_none_usage():
    class FakeAgent:
        async def run(self, messages):
            yield {"output": [], "usage": None}

    client = proxy.FakeAsyncOpenAI(FakeAgent())
    resp = asyncio.run(client.responses.create(model="m", input=[]))
    # base: AttributeError on None.get. fixed: degrades.
    assert resp is not None

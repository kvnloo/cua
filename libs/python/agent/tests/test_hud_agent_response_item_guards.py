"""Tests: HUD MCPComputerAgent.get_response tolerates malformed step items.

get_response indexed item["type"] on every step output entry, summary['text']
on every reasoning summary entry, and item["type"] on every message content
entry: non-dict entries (which the run loop is hardened to tolerate on
sibling branches) raised TypeError and killed the HUD eval run. Non-dict
entries are now skipped.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
AGENT = REPO / "libs/python/agent/cua_agent/integrations/hud/agent.py"


def _load_agent_mod():
    hud = types.ModuleType("hud")
    hud.instrument = lambda **kw: (lambda f: f)

    mcp = types.ModuleType("mcp")
    mcp_types = types.ModuleType("mcp.types")

    cua_agent_pkg = types.ModuleType("cua_agent")
    cua_agent_agent = types.ModuleType("cua_agent.agent")
    cua_agent_agent.ComputerAgent = object
    cua_agent_callbacks = types.ModuleType("cua_agent.callbacks")
    cua_agent_callbacks.PromptInstructionsCallback = object
    cua_agent_ts = types.ModuleType("cua_agent.callbacks.trajectory_saver")
    cua_agent_ts.TrajectorySaverCallback = object
    cua_agent_computers = types.ModuleType("cua_agent.computers")
    cua_agent_computers.is_agent_computer = lambda x: False
    cua_agent_responses = types.ModuleType("cua_agent.responses")
    cua_agent_responses.make_failed_tool_call_items = lambda *a, **k: []

    hud_agents = types.ModuleType("hud.agents")
    hud_agents.MCPAgent = object
    hud_tools_computer_settings = types.ModuleType("hud.tools.computer.settings")

    class _ComputerSettings:
        OPENAI_COMPUTER_WIDTH = 1024
        OPENAI_COMPUTER_HEIGHT = 768

    hud_tools_computer_settings.computer_settings = _ComputerSettings()

    hud_types = types.ModuleType("hud.types")

    class MCPToolCall:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class AgentResponse:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    hud_types.MCPToolCall = MCPToolCall
    hud_types.AgentResponse = AgentResponse
    hud_types.MCPToolResult = object
    hud_types.Trace = object

    mods = {
        "hud": hud,
        "mcp": mcp,
        "mcp.types": mcp_types,
        "cua_agent": cua_agent_pkg,
        "cua_agent.agent": cua_agent_agent,
        "cua_agent.callbacks": cua_agent_callbacks,
        "cua_agent.callbacks.trajectory_saver": cua_agent_ts,
        "cua_agent.computers": cua_agent_computers,
        "cua_agent.responses": cua_agent_responses,
        "hud.agents": hud_agents,
        "hud.tools": types.ModuleType("hud.tools"),
        "hud.tools.computer": types.ModuleType("hud.tools.computer"),
        "hud.tools.computer.settings": hud_tools_computer_settings,
        "hud.types": hud_types,
    }
    try:
        import PIL  # noqa: F401
    except ImportError:
        mods["PIL"] = types.ModuleType("PIL")
        mods["PIL"].Image = object
    for name, mod in mods.items():
        sys.modules.setdefault(name, mod)

    spec = importlib.util.spec_from_file_location("hud_agent_under_test", AGENT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


agent_mod = _load_agent_mod()


def _make_instance(step_results):
    cls = agent_mod.MCPComputerAgent
    inst = cls.__new__(cls)

    class FakeAgent:
        async def run(self, messages):
            for r in step_results:
                yield r

    inst.computer_agent = FakeAgent()
    inst.tool_call_inputs = {}
    inst.previous_output = None
    return inst


def test_non_dict_step_items_skipped():
    inst = _make_instance(
        [
            {
                "output": [
                    "stray-string",
                    None,
                    42,
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hi"}],
                    },
                ]
            }
        ]
    )
    resp = asyncio.run(inst.get_response([]))
    # base: TypeError on "stray-string"["type"]. fixed: skipped, text kept.
    assert resp.content == "hi"
    assert resp.done is True


def test_non_dict_summary_and_content_entries_skipped():
    inst = _make_instance(
        [
            {
                "output": [
                    {
                        "type": "reasoning",
                        "summary": ["stray", None, {"text": "why"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": ["stray", {"type": "output_text", "text": "ok"}],
                    },
                ]
            }
        ]
    )
    resp = asyncio.run(inst.get_response([]))
    # base: TypeError on "stray"['text'] / "stray"["type"]. fixed: kept.
    assert "Reasoning: why" in resp.content
    assert "ok" in resp.content


def test_computer_call_still_detected():
    inst = _make_instance(
        [
            {
                "output": [
                    "stray",
                    {
                        "type": "computer_call",
                        "call_id": "c1",
                        "action": {"type": "click", "x": 1, "y": 2},
                    },
                ]
            }
        ]
    )
    resp = asyncio.run(inst.get_response([]))
    assert resp.done is False
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].id == "c1"

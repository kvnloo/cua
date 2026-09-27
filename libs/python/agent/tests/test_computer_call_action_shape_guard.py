"""Tests for the computer-call action shape guard in ComputerAgent._handle_item.

A non-dict `action` (e.g. a bare string from a malformed model response) must
degrade to the existing empty-action path (log + return []) instead of raising
AttributeError on action.get and killing the whole run.
"""

import asyncio

import pytest

from handle_item_harness import load_agent_module, make_agent


class FakeComputer:
    def __init__(self):
        self.calls = []

    async def click(self, x, y):
        self.calls.append(("click", x, y))
        return {"ok": True}

    async def screenshot(self):
        return "ZmFrZQ=="


@pytest.fixture(scope="module")
def module():
    return load_agent_module()


@pytest.fixture
def agent(module):
    return make_agent(module, [])


def run(coro):
    return asyncio.run(coro)


class TestComputerCallActionShapeGuard:
    def test_string_action_degrades_to_empty(self, agent):
        item = {
            "type": "computer_call",
            "call_id": "call_str_action",
            "action": "click",  # malformed: should be a dict
        }
        result = run(agent._handle_item(item, FakeComputer()))
        assert result == []

    def test_none_action_still_empty(self, agent):
        # Pre-existing missing-action path must be unchanged.
        item = {"type": "computer_call", "call_id": "call_none_action", "action": None}
        result = run(agent._handle_item(item, FakeComputer()))
        assert result == []

    def test_valid_action_still_executes(self, agent):
        computer = FakeComputer()
        item = {
            "type": "computer_call",
            "call_id": "call_ok_action",
            "action": {"type": "click", "x": 100, "y": 200},
        }
        result = run(agent._handle_item(item, computer))
        assert computer.calls == [("click", 100, 200)]
        assert len(result) == 1
        out = result[0]
        assert out["type"] == "computer_call_output"
        assert out["call_id"] == "call_ok_action"
        assert out["output"]["type"] == "input_image"

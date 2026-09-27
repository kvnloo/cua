"""Tests for the pending-safety-check shape guard in ComputerAgent._handle_item.

Safety checks arrive from the model; a non-dict entry (e.g. a bare string)
must degrade to its str() instead of raising AttributeError on check.get and
killing the whole run.
"""

import asyncio

import pytest

from handle_item_harness import load_agent_module, make_agent


class FakeComputer:
    async def click(self):
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


class TestSafetyCheckShapeGuard:
    def test_string_check_does_not_kill_run(self, agent):
        item = {
            "type": "computer_call",
            "call_id": "call_str_check",
            "action": {"type": "click"},
            "pending_safety_checks": ["allow-always"],  # malformed: not a dict
        }
        result = run(agent._handle_item(item, FakeComputer()))
        assert len(result) == 1
        out = result[0]
        assert out["type"] == "computer_call_output"
        assert out["acknowledged_safety_checks"] == ["allow-always"]

    def test_dict_check_still_acknowledged(self, agent):
        item = {
            "type": "computer_call",
            "call_id": "call_dict_check",
            "action": {"type": "click"},
            "pending_safety_checks": [{"message": "confirm click"}],
        }
        result = run(agent._handle_item(item, FakeComputer()))
        assert len(result) == 1
        assert result[0]["acknowledged_safety_checks"] == [{"message": "confirm click"}]

    def test_no_checks_still_empty(self, agent):
        item = {
            "type": "computer_call",
            "call_id": "call_no_checks",
            "action": {"type": "click"},
        }
        result = run(agent._handle_item(item, FakeComputer()))
        assert len(result) == 1
        assert result[0]["acknowledged_safety_checks"] == []

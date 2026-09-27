"""Tests for the function-call arguments JSON guard in ComputerAgent._handle_item.

Malformed `arguments` (bad JSON, None, or valid-JSON non-objects) must degrade
to a tool error item instead of raising out of _handle_item and killing the run.
"""

import asyncio
import json

import pytest

from handle_item_harness import load_agent_module, make_agent


def echo_tool(a, b):
    return f"{a}-{b}"


@pytest.fixture(scope="module")
def module():
    return load_agent_module()


@pytest.fixture
def agent(module):
    return make_agent(module, [echo_tool])


def run(coro):
    return asyncio.run(coro)


class TestFunctionCallArgumentsJsonGuard:
    def test_malformed_json_degrades_to_tool_error(self, agent):
        item = {
            "type": "function_call",
            "call_id": "call_bad_json",
            "name": "echo_tool",
            "arguments": '{"a": 1,',  # truncated JSON
        }
        result = run(agent._handle_item(item))
        assert len(result) == 1
        out = result[0]
        assert out["type"] == "function_call_output"
        assert out["call_id"] == "call_bad_json"
        payload = json.loads(out["output"])
        assert "Invalid JSON" in payload["error"]

    def test_none_arguments_degrades_to_tool_error(self, agent):
        item = {
            "type": "function_call",
            "call_id": "call_none_args",
            "name": "echo_tool",
            "arguments": None,
        }
        result = run(agent._handle_item(item))
        assert len(result) == 1
        assert result[0]["type"] == "function_call_output"
        assert result[0]["call_id"] == "call_none_args"

    def test_non_dict_json_degrades_to_tool_error(self, agent):
        item = {
            "type": "function_call",
            "call_id": "call_list_args",
            "name": "echo_tool",
            "arguments": "[1, 2]",
        }
        result = run(agent._handle_item(item))
        assert len(result) == 1
        out = result[0]
        assert out["type"] == "function_call_output"
        payload = json.loads(out["output"])
        assert "must be a JSON object" in payload["error"]

    def test_valid_arguments_still_execute(self, agent):
        item = {
            "type": "function_call",
            "call_id": "call_ok",
            "name": "echo_tool",
            "arguments": '{"a": "x", "b": "y"}',
        }
        result = run(agent._handle_item(item))
        assert len(result) == 1
        out = result[0]
        assert out["type"] == "function_call_output"
        assert out["call_id"] == "call_ok"
        assert out["output"] == "x-y"

    def test_unknown_tool_still_tool_error_item(self, agent):
        # The pre-existing ToolError path must be unchanged.
        item = {
            "type": "function_call",
            "call_id": "call_no_tool",
            "name": "nope",
            "arguments": '{"a": 1}',
        }
        result = run(agent._handle_item(item))
        assert len(result) == 1
        assert result[0]["type"] == "function_call_output"
        payload = json.loads(result[0]["output"])
        assert "not found" in payload["error"]

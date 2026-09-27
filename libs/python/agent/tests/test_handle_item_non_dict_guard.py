"""_handle_item must tolerate non-dict entries in the model output list.

The run loop calls _handle_item for every entry of result["output"]. A
malformed model output entry (string, None, int) raised AttributeError out
of _handle_item (item.get("call_id")) and killed the whole run. Non-dict
entries are now skipped; dict handling is unchanged.
"""

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import handle_item_harness as harness


def _agent():
    mod = harness.load_agent_module()
    return mod.ComputerAgent.__new__(mod.ComputerAgent)


def test_string_item_skipped():
    agent = _agent()
    assert asyncio.run(agent._handle_item("malformed")) == []


def test_none_item_skipped():
    agent = _agent()
    assert asyncio.run(agent._handle_item(None)) == []


def test_int_item_skipped():
    agent = _agent()
    assert asyncio.run(agent._handle_item(123)) == []


def test_list_item_skipped():
    agent = _agent()
    assert asyncio.run(agent._handle_item(["computer_call"])) == []


def test_unknown_dict_type_still_returns_empty():
    # Dict entries keep their existing behavior (fall through, no crash).
    agent = _agent()
    assert asyncio.run(agent._handle_item({"type": "something_else"})) == []


def test_dict_without_type_still_returns_empty():
    agent = _agent()
    assert asyncio.run(agent._handle_item({"call_id": "x"})) == []

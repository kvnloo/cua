"""get_output_call_ids must tolerate non-dict entries in the output list.

The run loop collects output call ids from every entry of result["output"].
A malformed model output entry (string, None, int) raised AttributeError on
message.get("type") and killed the whole run before any item was handled.
Non-dict entries are now skipped; dict handling is unchanged.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import handle_item_harness as harness


def _fn():
    return harness.load_agent_module().get_output_call_ids


def test_string_entry_skipped():
    fn = _fn()
    assert fn(["malformed"]) == []


def test_none_entry_skipped():
    fn = _fn()
    assert fn([None]) == []


def test_int_entry_skipped():
    fn = _fn()
    assert fn([123]) == []


def test_mixed_entries():
    fn = _fn()
    messages = [
        {"type": "computer_call_output", "call_id": "c1"},
        "malformed",
        None,
        {"type": "message"},
        {"type": "function_call_output", "call_id": "c2"},
    ]
    assert fn(messages) == ["c1", "c2"]


def test_empty_list():
    fn = _fn()
    assert fn([]) == []


def test_dict_without_type_unchanged():
    fn = _fn()
    assert fn([{"call_id": "x"}]) == []

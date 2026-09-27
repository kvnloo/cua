"""Tests: image retention tolerates non-dict entries in the message list.

_apply_image_retention called msg.get("type") on every entry of the message
list. _process_input passes user input through get_json, which leaves bare
strings (and other non-dict shapes) untouched, so a user message like
["hello", {...}] raised AttributeError out of on_llm_start and killed the
run before any LLM call. Non-dict entries are now skipped; neighbor lookups
(prev computer_call / reasoning) tolerate non-dict entries too.
"""

import importlib.util
import sys
import types
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "cua_agent" / "callbacks"


def _load_module():
    pkg = types.ModuleType("ir_test_pkg")
    pkg.__path__ = [str(DIR)]
    sys.modules["ir_test_pkg"] = pkg

    base_spec = importlib.util.spec_from_file_location(
        "ir_test_pkg.base", DIR / "base.py"
    )
    base = importlib.util.module_from_spec(base_spec)
    sys.modules["ir_test_pkg.base"] = base
    base_spec.loader.exec_module(base)

    spec = importlib.util.spec_from_file_location(
        "ir_test_pkg.image_retention", DIR / "image_retention.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ir_test_pkg.image_retention"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()


def _cb(n):
    return _mod.ImageRetentionCallback(only_n_most_recent_images=n)


def _img_output(call_id):
    return {
        "type": "computer_call_output",
        "call_id": call_id,
        "output": {"image_url": "data:image/png;base64,AAA"},
    }


def _call(call_id):
    return {"type": "computer_call", "call_id": call_id, "action": {"type": "screenshot"}}


class TestNonDictEntries:
    def test_stray_strings_skipped(self):
        cb = _cb(1)
        msgs = ["hello", _img_output("c1"), _img_output("c2"), _img_output("c3")]
        out = cb._apply_image_retention(msgs)
        # only the 1 most recent image pair kept; stray string survives
        assert "hello" in out
        assert sum(1 for m in out if isinstance(m, dict) and m.get("type") == "computer_call_output") == 1

    def test_none_and_int_entries_skipped(self):
        cb = _cb(1)
        msgs = [None, 42, _img_output("c1"), _img_output("c2")]
        out = cb._apply_image_retention(msgs)
        assert None in out and 42 in out
        assert sum(1 for m in out if isinstance(m, dict) and m.get("type") == "computer_call_output") == 1

    def test_non_dict_neighbor_does_not_crash(self):
        cb = _cb(1)
        msgs = [
            "stray",
            _call("c1"),
            _img_output("c1"),
            _img_output("c2"),
            _img_output("c3"),
        ]
        out = cb._apply_image_retention(msgs)
        assert "stray" in out
        assert sum(1 for m in out if isinstance(m, dict) and m.get("type") == "computer_call_output") == 1

    def test_non_dict_reasoning_neighbor(self):
        cb = _cb(1)
        msgs = [
            {"type": "reasoning"},
            _call("c1"),
            _img_output("c1"),
            "junk",
            _img_output("c2"),
        ]
        out = cb._apply_image_retention(msgs)
        assert "junk" in out

    def test_no_images_returns_input_unchanged(self):
        cb = _cb(1)
        msgs = ["hello", {"role": "user", "content": "x"}]
        assert cb._apply_image_retention(msgs) == msgs

    def test_well_formed_trim_unchanged(self):
        cb = _cb(1)
        msgs = [_call("c1"), _img_output("c1"), _call("c2"), _img_output("c2")]
        out = cb._apply_image_retention(msgs)
        # keeps most recent pair (call + output), drops older output;
        # older call is not adjacent (prev is the other output), so it stays
        assert _img_output("c2") in out
        assert _img_output("c1") not in out

    def test_none_n_returns_input(self):
        cb = _mod.ImageRetentionCallback(only_n_most_recent_images=None)
        msgs = ["hello", _img_output("c1")]
        assert cb._apply_image_retention(msgs) is msgs

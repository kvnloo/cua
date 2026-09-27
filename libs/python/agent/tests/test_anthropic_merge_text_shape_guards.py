"""Tests: tolerate malformed content shapes in the Anthropic message combiner.

_combine_completion_messages / _merge_consecutive_text assumed every content
item was a dict. The forward converter deliberately keeps unknown content
shapes as-is, so a stray string (or a text block missing "text") in a user
message's content list raised AttributeError/KeyError mid-predict_step and
killed the run. Non-dict items are now passed through untouched; text blocks
with missing/non-string text merge via str() instead of raising. A non-list
tool_calls degrades to an empty list instead of raising on .copy()/.extend().
"""

import ast
from pathlib import Path
from typing import Any, Dict, List

PATH = (
    Path(__file__).resolve().parents[1]
    / "cua_agent"
    / "loops"
    / "anthropic.py"
)


def _load_fns():
    src = PATH.read_text()
    tree = ast.parse(src)
    wanted = {
        "_merge_consecutive_text",
        "_combine_completion_messages",
        "_normalize_content",
    }
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert len(fns) == 3, f"expected 3 fns, found {[n.name for n in fns]}"
    ns: Dict[str, Any] = {"Any": Any, "Dict": Dict, "List": List}
    exec(compile(ast.Module(body=fns, type_ignores=[]), str(PATH), "exec"), ns)
    return ns


_fns = _load_fns()
_merge = _fns["_merge_consecutive_text"]
_combine = _fns["_combine_completion_messages"]


class TestMergeConsecutiveText:
    def test_stray_string_passes_through(self):
        out = _merge(
            [{"type": "text", "text": "a"}, "stray", {"type": "text", "text": "b"}]
        )
        assert out == [
            {"type": "text", "text": "a"},
            "stray",
            {"type": "text", "text": "b"},
        ]

    def test_none_and_int_items_pass_through(self):
        out = _merge([None, 42, {"type": "text", "text": "x"}])
        assert out == [None, 42, {"type": "text", "text": "x"}]

    def test_text_block_missing_text_merges(self):
        out = _merge([{"type": "text", "text": "a"}, {"type": "text"}])
        assert out == [{"type": "text", "text": "a\n"}]

    def test_non_string_text_coerced(self):
        out = _merge(
            [{"type": "text", "text": "a"}, {"type": "text", "text": 123}]
        )
        assert out == [{"type": "text", "text": "a\n123"}]

    def test_well_formed_merge_unchanged(self):
        out = _merge(
            [
                {"type": "text", "text": "a"},
                {"type": "text", "text": "b"},
                {"type": "image_url", "image_url": {"url": "u"}},
                {"type": "text", "text": "c"},
            ]
        )
        assert out == [
            {"type": "text", "text": "a\nb"},
            {"type": "image_url", "image_url": {"url": "u"}},
            {"type": "text", "text": "c"},
        ]

    def test_empty(self):
        assert _merge([]) == []


class TestCombineCompletionMessages:
    def test_non_dict_content_item_survives(self):
        msgs = [{"role": "user", "content": [{"type": "text", "text": "hi"}, "junk"]}]
        out = _combine(msgs)
        assert out == [{"role": "user", "content": [{"type": "text", "text": "hi"}, "junk"]}]

    def test_same_role_combine_with_stray_item(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "user", "content": ["world", {"type": "text", "text": "!"}]},
        ]
        out = _combine(msgs)
        assert out == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    "world",
                    {"type": "text", "text": "!"},
                ],
            }
        ]

    def test_non_list_tool_calls_degrades_to_empty(self):
        msgs = [{"role": "assistant", "content": "x", "tool_calls": "bogus"}]
        out = _combine(msgs)
        assert out[0]["tool_calls"] == []

    def test_tool_calls_extend_with_non_list_skips(self):
        msgs = [
            {"role": "assistant", "content": "a", "tool_calls": []},
            {"role": "assistant", "content": "b", "tool_calls": 42},
        ]
        out = _combine(msgs)
        assert out[0]["tool_calls"] == []

    def test_well_formed_tool_calls_unchanged(self):
        tc = [{"id": "1", "type": "function"}]
        msgs = [{"role": "assistant", "content": None, "tool_calls": tc}]
        out = _combine(msgs)
        assert out[0]["tool_calls"] == tc
        assert out[0]["tool_calls"] is not tc  # copied

    def test_empty(self):
        assert _combine([]) == []

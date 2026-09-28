"""Tests: HumanCompletionUI message formatting tolerates malformed provider shapes.

format_messages_for_chatbot and get_last_image_from_messages assumed every
message/item was a dict: a non-dict message (msg.get), a non-dict content
item (item.get), a string image_url payload (.get on str), and non-string
text (text.strip) all raised AttributeError out of the UI refresh path.
A dict-shaped tool-call `arguments` raised TypeError from json.loads, which
only caught JSONDecodeError. Malformed shapes now degrade to skipped items.
"""

import base64
import importlib.util
import io
import os
import sys
import types as _types
from pathlib import Path

SCRATCH = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[4]
PRISTINE = Path(os.environ.get("C73_PRISTINE_UI", "")) if os.environ.get("C73_PRISTINE_UI") else None
SRC_FILE = PRISTINE or (REPO / "libs/python/agent/cua_agent/human_tool/ui.py")


class _FakeGrImage:
    def __init__(self, value=None):
        self.value = value


def _load_ui():
    for name in ("ht_pkg", "ht_pkg.ui", "gradio"):
        sys.modules.pop(name, None)

    pkg = _types.ModuleType("ht_pkg")
    pkg.__path__ = []
    sys.modules["ht_pkg"] = pkg

    gr = _types.ModuleType("gradio")
    gr.Image = _FakeGrImage
    sys.modules["gradio"] = gr

    spec = importlib.util.spec_from_file_location("ht_pkg.ui", str(SRC_FILE))
    ui = importlib.util.module_from_spec(spec)
    sys.modules["ht_pkg.ui"] = ui
    spec.loader.exec_module(ui)
    return ui


def _ui():
    m = _load_ui()
    return m.HumanCompletionUI.__new__(m.HumanCompletionUI)


def test_non_dict_message_skipped():
    u = _ui()
    assert u.format_messages_for_chatbot(["just a string", 42, None]) == []


def test_non_dict_content_item_skipped():
    u = _ui()
    msgs = [{"role": "user", "content": ["raw string item", 42, {"type": "text", "text": "hi"}]}]
    out = u.format_messages_for_chatbot(msgs)
    assert len(out) == 1 and out[0]["content"] == "hi"


def test_non_string_text_skipped():
    u = _ui()
    msgs = [{"role": "user", "content": [{"type": "text", "text": 123}, {"type": "text", "text": "ok"}]}]
    out = u.format_messages_for_chatbot(msgs)
    assert len(out) == 1 and out[0]["content"] == "ok"


def test_string_image_url_payload():
    u = _ui()
    msgs = [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": "https://example.com/x.png"}],
        }
    ]
    out = u.format_messages_for_chatbot(msgs)
    assert len(out) == 1
    assert isinstance(out[0]["content"], _FakeGrImage)
    assert out[0]["content"].value == "https://example.com/x.png"


def test_dict_tool_arguments_no_crash():
    u = _ui()
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "click", "arguments": {"x": 1, "y": 2}}}
            ],
        }
    ]
    out = u.format_messages_for_chatbot(msgs)
    assert len(out) == 1 and "Used click" in out[0]["metadata"]["title"]


def test_non_dict_tool_call_skipped():
    u = _ui()
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": ["bad", {"function": {"name": "type", "arguments": '{"text": "a"}'}}],
        }
    ]
    out = u.format_messages_for_chatbot(msgs)
    assert len(out) == 1 and "Used type" in out[0]["metadata"]["title"]


def test_non_dict_function_payload():
    u = _ui()
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": "click"}],
        }
    ]
    out = u.format_messages_for_chatbot(msgs)
    assert len(out) == 1 and "Used unknown" in out[0]["metadata"]["title"]


def test_well_formed_text_unchanged():
    u = _ui()
    msgs = [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    out = u.format_messages_for_chatbot(msgs)
    assert out == [{"role": "assistant", "content": "hello"}]


def test_well_formed_tool_call_unchanged():
    u = _ui()
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "wait", "arguments": '{"time": 2}'}}],
        }
    ]
    out = u.format_messages_for_chatbot(msgs)
    assert out[0]["metadata"]["title"] == "🛠️ Used wait"
    assert '"time": 2' in out[0]["content"]


def test_get_last_image_malformed_shapes():
    u = _ui()
    msgs = [
        "not a dict",
        {"role": "user", "content": ["not a dict item"]},
        {"role": "user", "content": [{"type": "image_url", "image_url": 42}]},
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": "https://example.com/last.png"}}],
        },
    ]
    assert u.get_last_image_from_messages(msgs) == "https://example.com/last.png"


def test_get_last_image_no_crash_no_image():
    u = _ui()
    assert u.get_last_image_from_messages(["x", {"content": [1, 2]}]) is None

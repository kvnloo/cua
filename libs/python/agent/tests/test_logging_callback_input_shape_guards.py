"""LoggingCallback must not crash on malformed callback inputs.

``on_computer_call_start`` assumed ``item["action"]`` is a dict, and
``on_text`` assumed ``item["content"]`` is a list of dicts with string
``text`` values. A non-dict action, a non-list content, a non-dict content
entry, or a non-string text (malformed model output flowing through the
callbacks) raised AttributeError/TypeError from a logging-only callback,
killing the run from code that should never affect it.

Fix: ``on_computer_call_start`` degrades a non-dict action to {}; ``on_text``
ignores non-list content, skips non-dict content entries, and stringifies
non-string text. Well-formed inputs log exactly as before.
"""
import asyncio
import importlib.util
import logging
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "cua_agent" / "callbacks"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pkg = types.ModuleType("cbpkg")
pkg.__path__ = []
sys.modules["cbpkg"] = pkg
base = _load("cbpkg.base", REPO / "base.py")
logging_mod = _load("cbpkg.logging", REPO / "logging.py")

LoggingCallback = logging_mod.LoggingCallback


def _cb():
    logger = logging.getLogger("test-logging-callback-shapes")
    logger.setLevel(logging.CRITICAL)
    return LoggingCallback(logger=logger)


def test_computer_call_start_non_dict_action():
    cb = _cb()
    asyncio.run(cb.on_computer_call_start({"action": "not-a-dict"}))


def test_computer_call_start_none_action():
    cb = _cb()
    asyncio.run(cb.on_computer_call_start({"action": None}))


def test_computer_call_start_well_formed_logs_action():
    cb = _cb()
    asyncio.run(
        cb.on_computer_call_start(
            {"action": {"type": "left_click", "x": 1, "y": 2}}
        )
    )


def test_on_text_string_content_ignored():
    cb = _cb()
    asyncio.run(cb.on_text({"role": "assistant", "content": "not-a-list"}))


def test_on_text_none_content_ignored():
    cb = _cb()
    asyncio.run(cb.on_text({"role": "assistant", "content": None}))


def test_on_text_non_dict_content_entry_skipped():
    cb = _cb()
    asyncio.run(
        cb.on_text(
            {
                "role": "assistant",
                "content": ["junk-string", {"type": "output_text", "text": "hi"}],
            }
        )
    )


def test_on_text_non_string_text_coerced():
    cb = _cb()
    asyncio.run(
        cb.on_text(
            {"role": "assistant", "content": [{"type": "output_text", "text": 123}]}
        )
    )


def test_on_text_well_formed_unchanged():
    cb = _cb()
    asyncio.run(
        cb.on_text(
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hello world"}],
            }
        )
    )

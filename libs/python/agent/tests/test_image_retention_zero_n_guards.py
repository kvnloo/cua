"""Tests for the image-retention zero-N guard.

Covers:
- only_n_most_recent_images=0 removes every screenshot pair (on base, -0 == 0
  made output_indices[-0:] the whole list, so nothing was removed)
- N=1 / N>=count / N=None behavior unchanged (controls, green on both)

The real image_retention module is loaded (not copied); only the
cua_agent.callbacks.base import is provided.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

CB_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "callbacks"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"cua_agent.callbacks.{name}", CB_DIR / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ensure():
    if "cua_agent.callbacks.image_retention" in sys.modules:
        return sys.modules["cua_agent.callbacks.image_retention"]
    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = []
    cb_pkg = types.ModuleType("cua_agent.callbacks")
    cb_pkg.__path__ = []
    sys.modules.setdefault("cua_agent", pkg)
    sys.modules.setdefault("cua_agent.callbacks", cb_pkg)
    _load("base")
    return _load("image_retention")


def _messages(n):
    msgs = [{"type": "message", "role": "user", "content": "go"}]
    for i in range(n):
        msgs.append({"type": "reasoning", "summary": f"r{i}"})
        msgs.append({"type": "computer_call", "call_id": f"c{i}"})
        msgs.append(
            {
                "type": "computer_call_output",
                "call_id": f"c{i}",
                "output": {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,IMG{i}",
                },
            }
        )
    return msgs


def _run(cb, n):
    return asyncio.run(cb.on_llm_start(_messages(3)))


def test_zero_n_removes_every_screenshot():
    mod = _ensure()
    out = _run(mod.ImageRetentionCallback(only_n_most_recent_images=0), 3)
    assert not [m for m in out if m.get("type") == "computer_call_output"]
    # only the leading user message survives
    assert len(out) == 1


def test_one_n_keeps_last_pair():
    mod = _ensure()
    out = _run(mod.ImageRetentionCallback(only_n_most_recent_images=1), 3)
    kept = [m for m in out if m.get("type") == "computer_call_output"]
    assert [m["call_id"] for m in kept] == ["c2"]


def test_large_n_keeps_everything():
    mod = _ensure()
    out = _run(mod.ImageRetentionCallback(only_n_most_recent_images=10), 3)
    assert len(out) == len(_messages(3))


def test_none_n_returns_messages_untouched():
    mod = _ensure()
    msgs = _messages(3)
    out = asyncio.run(
        mod.ImageRetentionCallback(only_n_most_recent_images=None).on_llm_start(msgs)
    )
    assert out is msgs

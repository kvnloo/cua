"""Red-on-base tests: image retention must not leave unpaired computer_call items.

ImageRetentionCallback drops older computer_call_output items (with their
screenshots) to bound context. When it removes an output it must also remove
the matching computer_call: an unpaired computer_call is rejected by the
Responses API on the next predict_step. The old code only looked at the
message immediately before the output (idx - 1); batched turns emit
[call A, call B, output A, output B] and resumed histories can interleave
arbitrarily, leaving the call behind without its output.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

_CALLBACKS_DIR = Path(__file__).resolve().parent.parent / "cua_agent" / "callbacks"


def _load_callback():
    """Load ImageRetentionCallback with a stubbed base module (no heavy deps)."""
    pkg = types.ModuleType("ir_pkg")
    pkg.__path__ = []
    sys.modules["ir_pkg"] = pkg
    base = types.ModuleType("ir_pkg.base")

    class AsyncCallbackHandler:
        pass

    base.AsyncCallbackHandler = AsyncCallbackHandler
    sys.modules["ir_pkg.base"] = base
    spec = importlib.util.spec_from_file_location(
        "ir_pkg.image_retention", _CALLBACKS_DIR / "image_retention.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ir_pkg.image_retention"] = mod
    spec.loader.exec_module(mod)
    return mod.ImageRetentionCallback


ImageRetentionCallback = _load_callback()


def _call(cid):
    return {"type": "computer_call", "call_id": cid, "action": {"type": "click"}}


def _output(cid):
    return {
        "type": "computer_call_output",
        "call_id": cid,
        "output": {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
    }


def _unpaired_calls(messages):
    out_ids = {
        m.get("call_id") for m in messages if m.get("type") == "computer_call_output"
    }
    return [
        m.get("call_id")
        for m in messages
        if m.get("type") == "computer_call"
        and m.get("call_id") not in out_ids
    ]


def _run(messages, n):
    cb = ImageRetentionCallback(only_n_most_recent_images=n)
    return asyncio.run(cb.on_llm_start([dict(m) for m in messages]))


def test_batched_order_keeps_pairs():
    # [call A, call B, output A, output B], keep 1 -> whole A pair must go.
    got = _run([_call("A"), _call("B"), _output("A"), _output("B")], 1)
    kept = [m.get("call_id") for m in got if m.get("type") == "computer_call"]
    kept_out = [m.get("call_id") for m in got if m.get("type") == "computer_call_output"]
    assert _unpaired_calls(got) == []
    assert kept == ["B"]
    assert kept_out == ["B"]


def test_adjacent_pairs_unchanged():
    # Adjacent [reasoning, call, output] pairs keep the old removal behavior.
    got = _run(
        [
            {"type": "reasoning", "content": "r"},
            _call("A"),
            _output("A"),
            _call("B"),
            _output("B"),
        ],
        1,
    )
    kept = [m.get("call_id") for m in got if m.get("type") == "computer_call"]
    kept_out = [m.get("call_id") for m in got if m.get("type") == "computer_call_output"]
    assert _unpaired_calls(got) == []
    assert kept == ["B"]
    assert kept_out == ["B"]
    # The single reasoning item ahead of the dropped call is still trimmed.
    assert not any(m.get("type") == "reasoning" for m in got)


def test_within_budget_noop():
    got = _run([_call("A"), _output("A")], 2)
    assert len(got) == 2
    assert _unpaired_calls(got) == []

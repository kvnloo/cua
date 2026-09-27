"""Tests: telemetry context-size / trajectory extraction tolerate malformed items.

TelemetryCallback._calculate_context_size called item.get("type") on every
message and len(part["text"]) on every content part: a non-dict entry raised
AttributeError and a non-string text (e.g. None) raised TypeError, killing
the run at on_run_start before any LLM call. _extract_trajectory had the
same non-dict crash on item.get/item.copy. Non-dict entries are now skipped
and only string texts are measured.
"""

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CB_DIR = REPO / "libs/python/agent/cua_agent/callbacks"


def _load_telemetry():
    cua_core = types.ModuleType("cua_core")
    cua_core_telemetry = types.ModuleType("cua_core.telemetry")
    cua_core_telemetry.is_telemetry_enabled = lambda: True
    cua_core_telemetry.record_event = lambda *a, **k: None
    sys.modules.setdefault("cua_core", cua_core)
    sys.modules.setdefault("cua_core.telemetry", cua_core_telemetry)

    pkg = types.ModuleType("tc_pkg")
    pkg.__path__ = [str(CB_DIR)]
    sys.modules.setdefault("tc_pkg", pkg)

    spec = importlib.util.spec_from_file_location("tc_pkg.base", CB_DIR / "base.py")
    base = importlib.util.module_from_spec(spec)
    sys.modules["tc_pkg.base"] = base
    spec.loader.exec_module(base)

    spec = importlib.util.spec_from_file_location(
        "tc_pkg.telemetry", CB_DIR / "telemetry.py"
    )
    tel = importlib.util.module_from_spec(spec)
    sys.modules["tc_pkg.telemetry"] = tel
    spec.loader.exec_module(tel)
    return tel


tel = _load_telemetry()
cb = tel.TelemetryCallback.__new__(tel.TelemetryCallback)


def test_context_size_skips_non_dict_items():
    size = cb._calculate_context_size(
        [
            "stray",
            None,
            42,
            {"type": "message", "content": [{"type": "output_text", "text": "hello"}]},
        ]
    )
    # base: AttributeError on "stray".get. fixed: skipped, only "hello" counted.
    assert size == 5


def test_context_size_ignores_non_string_text():
    size = cb._calculate_context_size(
        [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": None},
                    {"type": "output_text", "text": 123},
                    {"type": "output_text", "text": "ok"},
                ],
            }
        ]
    )
    # base: TypeError on len(None). fixed: only the string is measured.
    assert size == 2


def test_context_size_str_content_still_counted():
    size = cb._calculate_context_size([{"role": "user", "content": "plain"}])
    assert size == 5


def test_extract_trajectory_skips_non_dict_items():
    traj = cb._extract_trajectory(
        [
            "stray",
            None,
            {"role": "user", "content": "hi"},
            {"type": "reasoning", "summary": []},
        ]
    )
    # base: AttributeError on "stray".get. fixed: skipped.
    assert len(traj) == 2
    assert all(isinstance(t, dict) and "logged_at" in t for t in traj)

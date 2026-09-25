from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from shadow_probe import record


class ShadowProbeTest(unittest.TestCase):
    def test_recorded_gtk_text_change_does_not_skip(self) -> None:
        trace = Path(__file__).resolve().parents[6] / "scripts/repro/atspi-census-20260925.json"
        payload = json.loads(trace.read_text(encoding="utf-8"))
        types = tuple(payload["event_types"])
        sample = record("gtk3-entry", "cua-atspi-probe", types)
        self.assertFalse(sample.skip_capture)
        self.assertIn("object:text-changed:insert", sample.invalidators)

    def test_constructor_rejects_a_skip(self) -> None:
        from shadow_probe import ShadowSample

        with self.assertRaises(RuntimeError):
            ShadowSample("x", "y", (), skip_capture=True)


if __name__ == "__main__":
    unittest.main()

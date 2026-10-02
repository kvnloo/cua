"""Unit tests for run_d's refusal rules (never run outside hostless + the private session)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import run_d as R  # noqa: E402

OK_ENV = {"DISPLAY": ":99"}


class IsolationGuardTest(unittest.TestCase):
    def test_hostless_ancestor_is_found_from_the_process_tree(self) -> None:
        if os.environ.get("CUA_HOSTLESS") != "1":
            self.skipTest("unit suite not running under hostless")
        self.assertIsNotNone(R.hostless_ancestor(os.getpid()))

    def test_refuses_without_a_hostless_ancestor(self) -> None:
        with self.assertRaises(SystemExit):
            R.refuse_unsafe_environment(OK_ENV, ancestor=lambda: None)

    def test_accepts_private_display_with_ancestor(self) -> None:
        R.refuse_unsafe_environment(OK_ENV, ancestor=lambda: 123)

    def test_refuses_host_session_variables_and_bypass_knobs(self) -> None:
        for extra in ({"WAYLAND_DISPLAY": "wayland-1"}, {"HYPRLAND_INSTANCE_SIGNATURE": "x"},
                      {"CUA_DRIVER_PHASE_TRACE_FILE": "t"}, {"CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS": "0"},
                      {"CUA_E2E_BROWSER_NO_SANDBOX": "1"}):
            with self.subTest(extra=extra), self.assertRaises(SystemExit):
                R.refuse_unsafe_environment({**OK_ENV, **extra}, ancestor=lambda: 123)
        with self.assertRaises(SystemExit):
            R.refuse_unsafe_environment({}, ancestor=lambda: 123)
        with self.assertRaises(SystemExit):
            R.refuse_unsafe_environment({"DISPLAY": ":0"}, ancestor=lambda: 123)

    def test_isolation_record(self) -> None:
        rec = R.isolation_record({"DISPLAY": ":99"}, ancestor=lambda: 7)
        self.assertEqual(rec["hostless_ancestor_found"], True)
        self.assertEqual(rec["display_is_private"], True)
        self.assertIn("uid_map", rec)


if __name__ == "__main__":
    unittest.main()

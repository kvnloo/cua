"""Unit tests: refusal codes and content-free mutation envelopes recorded by run_d."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_d as R  # noqa: E402


class EnvelopeTest(unittest.TestCase):
    def test_code_from_every_known_place(self) -> None:
        self.assertEqual(R._code({"code": "a"}), "a")
        self.assertEqual(R._code({"refusal": {"code": "b"}}), "b")
        self.assertEqual(R._code({"error": {"code": "browser_ref_stale"}, "effect": "refused"}), "browser_ref_stale")
        self.assertIsNone(R._code({"effect": "unverifiable"}))

    def test_envelope_keeps_short_scalars_and_one_level_of_codes_only(self) -> None:
        env = R.envelope({"effect": "refused", "route": "dom", "error": {"code": "x", "message": "m" * 500},
                          "detail": "y" * 500, "n": 3, "list": [1, 2]})
        self.assertEqual(env["effect"], "refused")
        self.assertEqual(env["n"], 3)
        self.assertEqual(env["error"], {"code": "x"})
        self.assertNotIn("detail", env)
        self.assertEqual(env["_keys"], ["detail", "effect", "error", "list", "n", "route"])


if __name__ == "__main__":
    unittest.main()

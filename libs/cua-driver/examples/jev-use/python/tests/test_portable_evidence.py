from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from portable_evidence import normalize_events


SHA = "0123456789abcdef0123456789abcdef01234567"


class PortableEvidenceTest(unittest.TestCase):
    def test_verified_maps_to_pass(self):
        receipt = normalize_events(
            [{"event": "outcome", "outcome": "verified", "backend": "local"}],
            revision=SHA,
        )
        self.assertEqual(receipt["outcome"], "pass")
        self.assertEqual(receipt["evidence"][0]["result"], "pass")

    def test_refuted_maps_to_fail(self):
        receipt = normalize_events(
            [{"event": "outcome", "outcome": "refuted"}],
            revision=SHA,
        )
        self.assertEqual(receipt["outcome"], "fail")
        self.assertEqual(receipt["evidence"][0]["result"], "fail")

    def test_abstained_never_maps_to_pass(self):
        receipt = normalize_events(
            [{"event": "outcome", "outcome": "abstained", "backend": "browser"}],
            revision=SHA,
        )
        self.assertEqual(receipt["outcome"], "abstain")
        self.assertEqual(receipt["evidence"][0]["result"], "unknown")
        self.assertEqual(receipt["invariants"][0]["result"], "pass")

    def test_missing_outcome_stays_unknown(self):
        receipt = normalize_events(
            [{"event": "step", "step": 1, "backend": "browser"}],
            revision=SHA,
        )
        self.assertEqual(receipt["outcome"], "unknown")

    def test_requires_exact_revision(self):
        with self.assertRaises(ValueError):
            normalize_events([], revision="main")


if __name__ == "__main__":
    unittest.main()

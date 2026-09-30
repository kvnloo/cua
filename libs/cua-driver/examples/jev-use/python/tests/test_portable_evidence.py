from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "python"))

from portable_evidence import load_events, main, normalize_events


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

    def test_load_events_ignores_malformed_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            path.write_text(
                '{"event":"step","step":1}\nnot-json\n'
                '{"event":"outcome","outcome":"verified"}\n',
                encoding="utf-8",
            )
            events = load_events(path)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1]["outcome"], "verified")

    def test_cli_emits_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            path.write_text(
                '{"event":"outcome","outcome":"abstained","backend":"mock"}\n',
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "--log",
                        str(path),
                        "--revision",
                        SHA,
                        "--subject",
                        "cli-proof",
                    ]
                )

        receipt = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(receipt["subject"]["id"], "cli-proof")
        self.assertEqual(receipt["outcome"], "abstain")


if __name__ == "__main__":
    unittest.main()

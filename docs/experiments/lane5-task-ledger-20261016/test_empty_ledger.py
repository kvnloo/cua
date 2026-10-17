"""Regression: a 0-row ledger cannot qualify as a completed comparison."""
import tempfile
from pathlib import Path
import subprocess
import sys
import unittest
from paired_task_gate import analyze
from test_paired_task_gate import pairs

class EmptyLedgerTests(unittest.TestCase):
    def test_empty_rows_rejected(self):
        result = analyze([])
        self.assertFalse(result["valid"])
        self.assertIn("no task attempts", " ".join(result["errors"]))
        self.assertEqual(result["attempts"], 0)
        self.assertFalse(result["speed_claim_eligible"])
        self.assertFalse(result["candidate_for_external_driver_audit"])

    def test_whitespace_only_jsonl_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "trials.jsonl"
            p.write_text("\n  \n")
            completed = subprocess.run([sys.executable,
                str(Path(__file__).with_name("paired_task_gate.py")), str(p)],
                capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 1)
            self.assertIn('"valid": false', completed.stdout)

    def test_normal_matched_pair_stays_valid(self):
        self.assertTrue(analyze(pairs(2))["valid"])

if __name__ == "__main__":
    unittest.main()

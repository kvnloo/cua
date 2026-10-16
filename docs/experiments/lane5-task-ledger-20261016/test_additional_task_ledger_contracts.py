"""Additional malformed-ledger and CLI regressions (offline evidence only)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from paired_task_gate import analyze
from test_paired_task_gate import pairs


class AdditionalContractTests(unittest.TestCase):
    def test_non_scalar_json_enums_fail_closed_without_throwing(self):
        # A JSONL ledger can be supplied by an untrusted/buggy producer.
        # Malformed arrays/maps must return a report, not a traceback.
        for field in ("arm", "outcome", "evidence_class"):
            for invalid in ([], {}, ["verified"], {"value": "verified"}):
                with self.subTest(field=field, invalid=invalid):
                    rows = pairs(2)
                    rows[0][field] = invalid
                    report = analyze(rows)
                    self.assertFalse(report["valid"])
                    self.assertFalse(report["speed_claim_eligible"])
                    self.assertTrue(report["errors"])
        for field in ("delivery", "effect"):
            for invalid in ([], {}, ["applied"], {"value": "applied"}):
                with self.subTest(field=field, invalid=invalid):
                    rows = pairs(2)
                    rows[0]["actions"][0][field] = invalid
                    report = analyze(rows)
                    self.assertFalse(report["valid"])
                    self.assertIn("invalid delivery/effect", " ".join(report["errors"]))

    def test_malformed_fallback_duration_returns_invalid(self):
        for invalid in (None, "0", [], {}, -1, 0):
            with self.subTest(invalid=invalid):
                rows = pairs(2)
                rows[0]["fallback_used"] = True
                rows[0]["timing"]["fallback_ms"] = invalid
                report = analyze(rows)
                self.assertFalse(report["valid"])
                self.assertIn("fallback latency", " ".join(report["errors"]))

    def test_cli_invalid_enum_is_machine_readable_not_traceback(self):
        rows = pairs(2)
        rows[0]["actions"][0]["delivery"] = []
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "bad.jsonl"
            ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("paired_task_gate.py")), str(ledger)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(json.loads(result.stdout)["valid"])
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_enum_not_in_outcome_counts_as_valid(self):
        rows = pairs(2)
        rows[0]["outcome"] = ["verified"]
        report = analyze(rows)
        self.assertEqual(report["outcomes_by_arm"]["run_steps"]["invalid"], 1)
        self.assertFalse(report["candidate_for_external_driver_audit"])

    def test_pair_slot_list_and_map_fail_closed(self):
        for invalid in ([], {}, [0], {"slot": 0}):
            with self.subTest(invalid=invalid):
                rows = pairs(2)
                rows[0]["slot"] = invalid
                result = analyze(rows)
                self.assertFalse(result["valid"])
                self.assertFalse(result["speed_claim_eligible"])

    def test_pair_slot_bool_and_float_fail_closed(self):
        for invalid in (True, False, 0.0, 1.0):
            with self.subTest(invalid=invalid):
                rows = pairs(2)
                rows[0]["slot"] = invalid
                result = analyze(rows)
                self.assertFalse(result["valid"])
                self.assertFalse(result["speed_claim_eligible"])

    def test_valid_int_slots_keep_paired_ledger(self):
        result = analyze(pairs(20))
        self.assertTrue(result["valid"])
        self.assertEqual(result["pairs"], 20)

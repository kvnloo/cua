"""CI entry point for the downstream Pomerado caller-side experiment contract.

Runs only Python UNIT validations and source checks. This must not be
reported as a real Pomerado mint, CUA Driver E2E, or performance result.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[6]
PACKET = ROOT / "docs/experiments/pomerado-cua-2026-10-25"
FIXTURE = ROOT / "libs/cua-driver/examples/jev-use/fixture_server.py"
EXPECTED_FIXTURE_BLOB = "055500f713ba2c33d8544096f4084ebb108757ce"


class PomeradoExperimentGateTests(unittest.TestCase):
    def test_packet_contract_tests_are_in_canonical_jev_ci(self):
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(PACKET),
             "-p", "test_*.py", "-v"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("Ran 16 tests", result.stderr)

    def test_fixture_is_original_source_not_a_parallel_mock(self):
        data = FIXTURE.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()
        self.assertEqual(blob, EXPECTED_FIXTURE_BLOB)

    def test_external_executor_is_never_implicitly_authorized(self):
        prereg = json.loads((PACKET / "PREREG.json").read_text())
        self.assertEqual(prereg["status"], "PREREGISTERED_NOT_RUN")
        self.assertTrue(prereg["ownership"]["default_off"])
        self.assertTrue(prereg["ownership"]["caller_side_only"])
        self.assertTrue(prereg["ownership"]["external_runtime_separate_authority"])
        self.assertFalse(prereg["ownership"]["driver_changed"])
        self.assertFalse(prereg["budget"]["real_site_accounts"])

    def test_smoke_cannot_be_misclassified_as_a_b_data(self):
        script = (PACKET / "smoke_browser.py").read_text()
        self.assertIn("FIXTURE_BROWSER_ONLY", script)
        self.assertIn('"driver_trials": 0, "pomerado_trials": 0', script)


if __name__ == "__main__":
    unittest.main()

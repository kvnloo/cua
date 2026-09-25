"""Focused controller checks; these do not qualify Cua Driver or a native browser."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request, urlopen

from jev_wave1_http import MODEL, Responder, answer, serving, validate_case


class ControllerTests(unittest.TestCase):
    def payload(self):
        return {"model": MODEL, "questions": {"candidate": {"type": "choice", "criteria": {
            "type-verification-value": "Fill owned form", "submit-form": "Submit owned form", "abstain": "Stop"}}}}

    def sample(self, invalid=False):
        return dict(invalid=invalid, code=1 if invalid else 0,
            events=([{"event": "outcome", "outcome": "abstained", "reason": "invalid_response"}] if invalid else [
                {"event": "step", "candidate": "type-verification-value", "dry_run": False},
                {"event": "step", "candidate": "submit-form", "dry_run": False},
                {"event": "outcome", "outcome": "verified", "token": "owned-test"}]),
            calls=[{"tool": "browser_navigate"}] + ([] if invalid else [{"tool": "browser_type"}, {"tool": "browser_click"}]),
            observed={"submitted": None if invalid else "owned-test"}, token="owned-test",
            requests=[{}] * (1 if invalid else 2), errors=[])

    def test_real_http_emits_exact_candidate_distributions(self):
        server = Responder(False)
        with serving(server) as url:
            for expected in ("type-verification-value", "submit-form"):
                request = Request(url + "/v1/systemone", data=json.dumps(self.payload()).encode(), headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=2) as response:
                    candidate = json.load(response)["answers"]["candidate"]
                self.assertEqual(candidate["choice"], expected)
                self.assertEqual(sum(candidate["probabilities"].values()), 1.0)
                self.assertEqual(set(candidate["probabilities"]), set(self.payload()["questions"]["candidate"]["criteria"]))
        self.assertEqual(len(server.requests), 2)
        self.assertFalse(server.errors)

    def test_invalid_control_keeps_mass_valid_but_choice_unknown(self):
        response, receipt = answer(self.payload(), 0, True)
        candidate = response["answers"]["candidate"]
        self.assertNotIn(candidate["choice"], candidate["probabilities"])
        self.assertEqual(sum(candidate["probabilities"].values()), 1.0)
        self.assertNotIn("state", receipt)

    def test_missing_expected_candidate_is_not_repaired(self):
        payload = self.payload()
        del payload["questions"]["candidate"]["criteria"]["type-verification-value"]
        with self.assertRaises(ValueError):
            answer(payload, 0, False)

    def test_valid_and_refused_receipts_have_distinct_acceptance(self):
        self.assertTrue(validate_case(**self.sample())["case_passed"])
        self.assertTrue(validate_case(**self.sample(True))["case_passed"])

    def test_negative_control_detects_input_even_without_submission(self):
        sample = self.sample(True)
        sample["calls"].append({"tool": "browser_type"})
        with self.assertRaises(AssertionError):
            validate_case(**sample)

    def test_positive_control_requires_independent_observed_outcome(self):
        sample = self.sample()
        sample["observed"] = {"submitted": None}
        with self.assertRaises(AssertionError):
            validate_case(**sample)

    def test_positive_control_rejects_dry_run(self):
        sample = self.sample()
        sample["events"][0]["dry_run"] = True
        with self.assertRaises(AssertionError):
            validate_case(**sample)

    def test_proxy_preserves_bytes_and_omits_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child = root / "child.py"
            child.write_text("import sys\nfor line in sys.stdin.buffer:\n sys.stdout.buffer.write(line); sys.stdout.buffer.flush()\n")
            audit = root / "audit.jsonl"
            raw = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"browser_type","arguments":{"text":"private-not-for-audit"}}}\n'
            raw += b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            process = subprocess.run([sys.executable, str(Path(__file__).with_name("jev_wave1_http.py")),
                "proxy", sys.executable, str(audit), str(child)], input=raw, capture_output=True, timeout=5)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, raw)
            self.assertEqual(audit.read_text(), '{"tool": "browser_type"}\n')


if __name__ == "__main__":
    unittest.main()

"""Corrupt-evidence requirements: RED=retained results, GREEN=auditor.

RED consumes saved outputs of the *executed*, unmodified verify() challenge,
not a guessed stand-in. The retained checker is never edited.
"""

import json
import os
from pathlib import Path
import unittest
from prepare import HERE


class AuditorTests(unittest.TestCase):
    def test_success_with_unobserved_fresh_ref_is_nonqualifying(self):
        path = HERE / "retained-matrix/python/accepted/fresh-ref-unobserved"
        result = json.loads((path / "result.json").read_text())
        self.assertTrue(result["retained"]["accepted"])
        self.assertTrue(result["independent"]["state_matches_expected"])
        if os.environ.get("AUDIT_CHECKER") == "retained":
            qualifying = result["retained"]["accepted"]
        else:
            from auditor import audit_historical

            qualifying = audit_historical(path)["qualifying"]
        self.assertFalse(
            qualifying, "Successful /state plus unbound proof does not establish the intended route"
        )

    def capture_data(self, mode="accepted"):
        folder = HERE / "fix-captures" / mode
        return tuple(
            json.loads((folder / name).read_text())
            for name in ["claim.json", "transport-witness.json", "oracle-witness.json"]
        )

    def test_counts_are_correlated_to_provider_entries_not_time(self):
        import auditor

        self.assertTrue(
            hasattr(auditor, "audit_capture"),
            "per-trial independent counter correlation is missing",
        )
        claim, trace, oracle = self.capture_data("declined")
        claim["events"][1]["provider_decision_ms"] = 0
        claim["steps"][1]["provider_decision_ms"] = 0
        self.assertTrue(auditor.audit_capture(claim, trace, oracle)["qualifying"])
        claim["provider_count"] = 1
        bad = auditor.audit_capture(claim, trace, oracle)
        self.assertFalse(bad["qualifying"])
        self.assertIn("provider_counter", bad["errors"])

    def test_proof_binds_to_fresh_observation_and_actual_dispatch(self):
        from auditor import audit_capture
        import copy

        mutations = [
            (
                "fresh-ref",
                lambda c, t, o: c["events"][1]["guarded_completion"].update(fresh_ref="p999:777"),
            ),
            (
                "prior-ref",
                lambda c, t, o: c["events"][1]["guarded_completion"].update(prior_ref="p888:777"),
            ),
            (
                "foreign-session",
                lambda c, t, o: c["events"][1]["guarded_completion"].update(
                    session="foreign-session"
                ),
            ),
            (
                "unproven-field",
                lambda c, t, o: t["events"][3].update(field_contains_expected=False),
            ),
            ("ambiguous-target", lambda c, t, o: t["events"][3]["submit_refs"].append("p2:2")),
            ("wrong-dispatch-ref", lambda c, t, o: t["events"][-1].update(ref="p999:777")),
            (
                "wrong-dispatch-session",
                lambda c, t, o: t["events"][-1].update(session="foreign-session"),
            ),
            ("failed-dispatch", lambda c, t, o: t["events"][-1].update(success=False)),
            ("provider-wrong-order", lambda c, t, o: t["events"][1].update(after_actions=1)),
            ("observation-before-mutation", lambda c, t, o: t["events"][3].update(after_actions=0)),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                c, t, o = self.capture_data()
                mutate(c, t, o)
                c["steps"] = copy.deepcopy(c["events"][:2])
                self.assertFalse(audit_capture(c, t, o)["qualifying"], name)

    def test_oracle_attribution_pins_and_forced_mode_are_mandatory(self):
        from auditor import audit_capture

        mutations = [
            ("oracle-false", lambda c, t, o: o.update(state_matches_expected=False)),
            ("preexisting-state", lambda c, t, o: o.update(initially_empty=False)),
            ("wrong-oracle-trial", lambda c, t, o: o.update(trial_key="foreign-trial")),
            (
                "wrong-journal-trial",
                lambda c, t, o: o["journal"][0].update(trial_key="foreign-trial"),
            ),
            (
                "wrong-journal-language",
                lambda c, t, o: o["journal"][0].update(language="typescript"),
            ),
            (
                "journal-false",
                lambda c, t, o: o["journal"][0].update(committed_expected_value=False),
            ),
            ("journal-duplicate", lambda c, t, o: o["journal"].append(dict(o["journal"][0]))),
            ("claim-wrong-pin", lambda c, t, o: c.update(exact_head="0" * 40)),
            ("trace-wrong-pin", lambda c, t, o: t.update(exact_head="0" * 40)),
            ("oracle-wrong-pin", lambda c, t, o: o.update(exact_head="0" * 40)),
            ("trace-wrong-trial", lambda c, t, o: t["events"][1].update(trial_key="foreign-trial")),
            ("forced-off", lambda c, t, o: c["forced"].update(guarded=False)),
            ("fake-real", lambda c, t, o: c.update(real_driver=True, scope="REAL")),
            ("false-claimed-outcome", lambda c, t, o: c.update(outcome_verified=False)),
            ("receipt-jsonl-disagree", lambda c, t, o: c["steps"][1].update(tool="click")),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                c, t, o = self.capture_data()
                mutate(c, t, o)
                self.assertFalse(audit_capture(c, t, o)["qualifying"], name)

    def test_unknown_counter_fields_and_malformed_inputs_fail_closed(self):
        from auditor import audit_capture

        c, t, o = self.capture_data()
        c["events"][1]["provider_calls"] = 7
        c["steps"][1]["provider_calls"] = 7
        self.assertFalse(audit_capture(c, t, o)["qualifying"])
        for c, t, o in [(None, {}, {}), ({}, None, {}), ({"events": [None]}, {}, {})]:
            with self.subTest(claim=c):
                self.assertFalse(audit_capture(c, t, o)["qualifying"])

    def test_custody_cli_checks_external_anchor_and_witness_hashes(self):
        import auditor
        import shutil
        import subprocess
        import sys
        import tempfile
        from prepare import sha

        self.assertTrue(hasattr(auditor, "audit_bound"), "independent custody loader is missing")
        source = HERE / "fix-captures"
        with tempfile.TemporaryDirectory(dir=HERE / "tmp") as d:
            root = Path(d) / "capture"
            shutil.copytree(source, root)
            custody = root / "custody.json"
            expected = sha(custody)
            command = [
                sys.executable,
                "-B",
                str(HERE / "auditor.py"),
                "--claim",
                str(root / "accepted/claim.json"),
                "--custody",
                str(custody),
                "--custody-sha256",
                expected,
            ]
            ok = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertTrue(json.loads(ok.stdout)["qualifying"])
            self.assertFalse(
                auditor.audit_bound(root / "accepted/claim.json", custody, "0" * 64)["qualifying"]
            )
            oracle = root / "accepted/oracle-witness.json"
            data = json.loads(oracle.read_text())
            data["state_matches_expected"] = False
            oracle.write_text(json.dumps(data))
            bad = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1, bad.stderr)
            self.assertIn("custody_integrity", json.loads(bad.stdout)["errors"])

    def test_duplicate_json_keys_do_not_silently_choose_last_claim(self):
        import subprocess
        import sys
        import tempfile
        from prepare import sha

        with tempfile.TemporaryDirectory(dir=HERE / "tmp") as directory:
            claim = Path(directory) / "claim.json"
            raw = (HERE / "fix-captures/accepted/claim.json").read_text()
            claim.write_text('{"provider_count": 999,' + raw.lstrip()[1:])
            cmd = [
                sys.executable,
                "-B",
                str(HERE / "auditor.py"),
                "--claim",
                str(claim),
                "--custody",
                str(HERE / "fix-captures/custody.json"),
                "--custody-sha256",
                sha(HERE / "fix-captures/custody.json"),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(
                result.returncode, 1, "duplicate JSON keys must be rejected, not resolved last-wins"
            )
            self.assertFalse(json.loads(result.stdout)["qualifying"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

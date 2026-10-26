"""UNIT-only fairness tests. Does not execute CUA, Pomerado or an A/B run."""
import copy
import unittest

from baseline_gate import BaselineError, check

DRIVER = "a" * 40


def rows(tool="run_steps", variant="default"):
    return [
        {
            "evidence_class": "REAL",
            "arm": arm,
            "route_observed": "cua-driver" if arm == "A" else "pomerado-mcp",
            "baseline_tool": tool,
            "driver_sha": DRIVER,
            "workflow": "form",
            "variant": variant,
            **({
                "advertised_driver_tools": ["run_steps", "run_script"],
                "observed_driver_tools": [tool],
                "baseline_trace_evidence": f"redacted-route-trace-{n}",
                "run_script_operator_enabled": True
            } if arm == "A" else {})
        }
        for n, arm in enumerate("ABBA")
    ]


class BaselineGateTests(unittest.TestCase):
    def test_current_run_steps_route_claim_passes_without_speedup_certification(self):
        result = check(rows(), expected_driver_sha=DRIVER)
        self.assertEqual(result["status"], "RECEIPT_SHAPE_ONLY_NOT_RUNTIME_PROOF")
        self.assertEqual(result["real_rows_checked"], 4)

    def test_valid_script_requires_operator_policy_and_actual_dispatch(self):
        result = check(rows("run_script"), expected_driver_sha=DRIVER)
        self.assertEqual(result["baseline_cohorts"]["form/default"], "run_script")

    def test_legacy_alias_is_rejected(self):
        with self.assertRaisesRegex(BaselineError, "stale baseline_tool"):
            check(rows("run_actions"))

    def test_old_jev_use_per_step_is_not_a_current_batch_baseline(self):
        trial = rows()
        for r in trial:
            if r["arm"] == "A":
                r["observed_driver_tools"] = ["get_window_state", "click"]
        with self.assertRaisesRegex(BaselineError, "not observed"):
            check(trial)

    def test_unadvertised_tool_is_rejected(self):
        trial = rows()
        trial[0]["advertised_driver_tools"] = ["click"]
        with self.assertRaisesRegex(BaselineError, "not advertised"):
            check(trial)

    def test_operator_script_opt_out_refuses_script_baseline(self):
        trial = rows("run_script")
        trial[0]["run_script_operator_enabled"] = False
        with self.assertRaisesRegex(BaselineError, "script disabled"):
            check(trial)

    def test_changed_upstream_build_refuses_old_receipts(self):
        with self.assertRaisesRegex(BaselineError, "differs from attested"):
            check(rows(), expected_driver_sha="b" * 40)

    def test_synthetic_data_can_never_upgrade_to_real_proof(self):
        trial = rows()
        trial[0]["evidence_class"] = "UNIT"
        with self.assertRaisesRegex(BaselineError, "REAL receipts required"):
            check(trial)

    def test_stale_per_trial_trace_reference_is_rejected(self):
        trial = rows()
        trial[3]["baseline_trace_evidence"] = trial[0]["baseline_trace_evidence"]
        with self.assertRaisesRegex(BaselineError, "repeated baseline"):
            check(trial)

    def test_mixed_script_batch_is_a_confound(self):
        trial = rows()
        trial[1]["baseline_tool"] = "run_script"
        with self.assertRaisesRegex(BaselineError, "mixed baseline_tool"):
            check(trial)

    def test_legitimate_different_baselines_are_separate_cohorts(self):
        a = rows("run_steps", "batch")
        b = rows("run_script", "script")
        for i, row in enumerate(b):
            if row["arm"] == "A":
                row["baseline_trace_evidence"] = f"unique-script-trace-{i}"
        result = check(a+b)
        self.assertEqual(len(result["baseline_cohorts"]), 2)

    def test_a_failed_route_cannot_be_timed_as_cua_baseline(self):
        trial = rows()
        trial[0]["route_observed"] = "fallback-cua"
        with self.assertRaisesRegex(BaselineError, "route mismatch"):
            check(trial)

    def test_mixed_binary_within_cohort_is_rejected(self):
        trial = rows()
        trial[2]["driver_sha"] = "b" * 40
        with self.assertRaisesRegex(BaselineError, "mixed driver_sha"):
            check(trial)

    def test_unpaired_arms_rejected(self):
        trial = rows()
        for i, row in enumerate(trial):
            row["arm"] = "A"
            row["route_observed"] = "cua-driver"
            row["advertised_driver_tools"] = ["run_steps", "run_script"]
            row["observed_driver_tools"] = ["run_steps"]
            row["baseline_trace_evidence"] = f"all-A-{i}"
        with self.assertRaisesRegex(BaselineError, "unpaired arms"):
            check(trial)


if __name__ == "__main__":
    unittest.main()

import copy
import unittest

from paired_task_gate import analyze


def row(pair=0, arm="run_steps", slot=0, duration=100.0):
    return {
        "pair_id": str(pair), "arm": arm, "route_actual": arm, "slot": slot,
        "task_contract_sha": "task-v1", "initial_state_sha": "reset-independent-oracle-v1",
        "permission_sha": "policy-pinned", "driver_source_sha": "a" * 40,
        "driver_build_sha": "b" * 64, "host_id": "same-host", "fixture_sha": "fixture-v1",
        "provider_id": "provider-v1", "evidence_class": "synthetic", "outcome": "verified", "speed_eligible": True,
        "final_effect_sha": "counter-single-increment", "oracle": {"independent": True,
            "fresh_after_action": True, "observation_sha": f"after-{pair}-{arm}"},
        "timing": {"t_oracle_ms": duration, "t_runner_ms": duration + 8, "fallback_ms": 0.0},
        "fallback_used": False, "actions": [{"attempt_id": f"{pair}/{arm}/0",
            "delivery": "applied", "effect": "verified", "may_have_landed": True,
            "logical_mutation_id": "increment-once",
            "replayed": False, "cancelled": False}],
    }


def pairs(n=20, improvement=0):
    rows = []
    for i in range(n):
        if i % 2 == 0:
            rows.extend([row(i, "run_steps", 0), row(i, "run_script", 1, 100 - improvement)])
        else:
            rows.extend([row(i, "run_script", 0, 100 - improvement), row(i, "run_steps", 1)])
    return rows


class GateTests(unittest.TestCase):
    def test_paired_no_effect_does_not_claim_savings(self):
        result = analyze(pairs())
        self.assertTrue(result["valid"])
        self.assertFalse(result["speed_claim_eligible"])
        self.assertEqual(result["paired_bootstrap_95pct_ms"], [0, 0])

    def test_synthetic_strong_difference_only_tests_statistics(self):
        result = analyze(pairs(improvement=25))
        self.assertTrue(result["statistical_signal_only"])
        self.assertFalse(result["speed_claim_eligible"])
        self.assertEqual(result["paired_bootstrap_95pct_ms"], [-25, -25])

    def test_alternation_is_mandatory(self):
        rows = pairs(20)
        for r in rows:
            r["slot"] = 0 if r["arm"] == "run_steps" else 1
        self.assertIn("order unbalanced", " ".join(analyze(rows)["errors"]))

    def test_fallback_latency_cannot_be_zeroed(self):
        rows = pairs(2)
        rows[0]["fallback_used"] = True
        self.assertFalse(analyze(rows)["valid"])

    def test_unknown_counts_in_denominator_not_as_zero(self):
        rows = pairs(20)
        rows[0]["outcome"] = "unknown"
        rows[0]["speed_eligible"] = False
        report = analyze(rows)
        self.assertTrue(report["valid"])
        self.assertEqual(report["verified_pairs"], 19)
        self.assertFalse(report["speed_claim_eligible"])

    def test_no_blind_replay_after_ack_loss(self):
        rows = pairs(2)
        a = rows[0]["actions"][0]
        a.update(delivery="unknown", effect="unknown", may_have_landed=True, replayed=True)
        self.assertIn("unsafe replay", " ".join(analyze(rows)["errors"]))

    def test_no_replay_after_cancel(self):
        rows = pairs(2)
        rows[0]["actions"][0].update(cancelled=True, replayed=True)
        self.assertIn("cancellation", " ".join(analyze(rows)["errors"]))

    def test_refusal_is_not_success(self):
        rows = pairs(2)
        rows[0]["outcome"] = "refused"
        self.assertFalse(analyze(rows)["valid"])

    def test_effect_parity_is_not_optional(self):
        rows = pairs(2)
        rows[0]["final_effect_sha"] = "two-increments"
        self.assertIn("effects are not equivalent", " ".join(analyze(rows)["errors"]))

    def test_binary_mismatch_is_not_an_ab_test(self):
        rows = pairs(2)
        rows[0]["driver_build_sha"] = "c" * 64
        self.assertIn("unmatched driver_build_sha", " ".join(analyze(rows)["errors"]))

    def test_missing_fresh_independent_oracle(self):
        rows = pairs(2)
        rows[0]["oracle"]["independent"] = False
        self.assertIn("independently", " ".join(analyze(rows)["errors"]))

    def test_nonfinite_and_negative_timing(self):
        for v in [float('nan'), float('inf'), -1]:
            rows = pairs(2)
            rows[0]["timing"]["t_oracle_ms"] = v
            self.assertFalse(analyze(rows)["valid"])

    def test_duplicate_attempt_is_not_silently_dropped(self):
        rows = pairs(2)
        rows.append(copy.deepcopy(rows[0]))
        self.assertIn("missing/duplicate arm", " ".join(analyze(rows)["errors"]))

    def test_route_cannot_be_self_reported_inaccurately(self):
        rows = pairs(2)
        rows[0]["route_actual"] = "run_script"
        self.assertIn("actual route", " ".join(analyze(rows)["errors"]))

    def test_replay_hidden_by_false_replayed_flag_is_detected(self):
        rows = pairs(2)
        original = rows[0]["actions"][0]
        clone = copy.deepcopy(original)
        clone["attempt_id"] += "/again"
        clone["replayed"] = False  # misleading self-report must not hide double mutation
        rows[0]["actions"].append(clone)
        self.assertIn("duplicate logical mutation", " ".join(analyze(rows)["errors"]))

    def test_safe_pre_dispatch_refusal_then_retry_is_allowed(self):
        rows = pairs(2)
        original = rows[0]["actions"][0]
        prior = copy.deepcopy(original)
        prior["attempt_id"] += "/refused"
        prior.update(delivery="refused", effect="none", may_have_landed=False)
        rows[0]["actions"].insert(0, prior)
        self.assertTrue(analyze(rows)["valid"])

    def test_verified_task_requires_mutation_record(self):
        rows = pairs(2)
        rows[0]["actions"] = []
        self.assertIn("no recorded mutations", " ".join(analyze(rows)["errors"]))

    def test_unknown_delivery_requires_reconciliation_not_optimism(self):
        rows = pairs(2)
        rows[0]["actions"][0].update(delivery="unknown", effect="unknown", may_have_landed=True)
        self.assertIn("independent reconciliation", " ".join(analyze(rows)["errors"]))
        rows[0]["actions"][0]["reconciled_by_fresh_oracle"] = True
        self.assertTrue(analyze(rows)["valid"])

    def test_refused_cannot_be_reported_as_verified(self):
        rows = pairs(2)
        rows[0]["actions"][0].update(delivery="refused", effect="verified", may_have_landed=False)
        self.assertIn("contradicts verified", " ".join(analyze(rows)["errors"]))

    def test_missing_sha_is_not_sufficient_provenance(self):
        rows = pairs(2)
        rows[0]["driver_build_sha"] = "unknown"
        self.assertIn("SHA256", " ".join(analyze(rows)["errors"]))

    def test_non_native_stats_are_never_claimable(self):
        rows = pairs(20, improvement=25)
        result = analyze(rows)
        self.assertTrue(result["statistical_signal_only"])
        self.assertFalse(result["speed_claim_eligible"])

    def test_incomplete_pair_is_not_counted(self):
        rows = pairs(2)[:-1]
        report = analyze(rows)
        self.assertFalse(report["valid"])
        self.assertIn("missing/duplicate arm", " ".join(report["errors"]))


if __name__ == "__main__":
    unittest.main()

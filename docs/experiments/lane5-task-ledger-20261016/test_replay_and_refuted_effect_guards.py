"""No unanchored replay claims or refuted/absent effects in verified tasks.

Offline ledger-contract regressions. These do not authenticate a Driver or
independent oracle, and cannot establish performance improvements.
"""
import copy
import unittest

from paired_task_gate import analyze
from test_paired_task_gate import pairs


class ReplayAndRefutedEffectGuards(unittest.TestCase):
    def test_replayed_flag_without_a_prior_logical_mutation_is_invalid(self):
        rows = pairs(2)
        # Preserve an unrelated verified action so this test isolates the
        # missing provenance rather than failing the overall success gate.
        unanchored = copy.deepcopy(rows[0]["actions"][0])
        unanchored.update(
            attempt_id="ghost-retry-1", logical_mutation_id="unseen-mutation",
            delivery="refused", effect="none", may_have_landed=False,
            cancelled=False, replayed=True,
        )
        rows[0]["actions"].append(unanchored)
        report = analyze(rows)
        self.assertFalse(report["valid"])
        self.assertIn("replay flag without a recorded prior attempt", " ".join(report["errors"]))
        self.assertFalse(report["speed_claim_eligible"])

    def test_reconciliation_flag_cannot_turn_refuted_effect_into_verified_task(self):
        rows = pairs(2)
        rows[0]["actions"][0].update(
            delivery="unknown", effect="refuted", may_have_landed=True,
            replayed=False, cancelled=False, reconciled_by_fresh_oracle=True,
        )
        report = analyze(rows)
        self.assertFalse(report["valid"])
        self.assertIn("no verified mutation effect", " ".join(report["errors"]))

    def test_reconciliation_flag_cannot_turn_no_effect_into_verified_task(self):
        rows = pairs(2)
        rows[0]["actions"][0].update(
            delivery="unknown", effect="none", may_have_landed=True,
            replayed=False, cancelled=False, reconciled_by_fresh_oracle=True,
        )
        report = analyze(rows)
        self.assertFalse(report["valid"])
        self.assertIn("no verified mutation effect", " ".join(report["errors"]))

    def test_true_unknown_with_fresh_reconciliation_remains_valid(self):
        rows = pairs(2)
        rows[0]["actions"][0].update(
            delivery="unknown", effect="unknown", may_have_landed=True,
            replayed=False, cancelled=False, reconciled_by_fresh_oracle=True,
        )
        self.assertTrue(analyze(rows)["valid"])

    def test_two_attempt_safe_predispatch_refusal_is_still_valid(self):
        rows = pairs(2)
        before = copy.deepcopy(rows[0]["actions"][0])
        before.update(
            attempt_id="first-refusal", delivery="refused", effect="none",
            may_have_landed=False, replayed=False,
        )
        rows[0]["actions"].insert(0, before)
        self.assertTrue(analyze(rows)["valid"])


if __name__ == "__main__":
    unittest.main()

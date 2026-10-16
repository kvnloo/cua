"""CUA #10 task-ledger safety: verified effects and unknown delivery retain uncertainty."""
import unittest
from paired_task_gate import analyze
from test_paired_task_gate import pairs

class MutationOutcomeConsistency(unittest.TestCase):
    def test_proven_nonlanding_cannot_be_reported_as_verified_effect(self):
        rows = pairs(2)
        rows[0]['actions'][0].update(delivery='attempted', effect='verified', may_have_landed=False)
        out = analyze(rows)
        self.assertFalse(out['valid'])
        self.assertFalse(out['speed_claim_eligible'])
        self.assertIn('verified effect contradicts', ' '.join(out['errors']))

    def test_unknown_delivery_cannot_prove_nonlanding(self):
        rows = pairs(2)
        rows[0]['actions'][0].update(delivery='unknown', effect='verified', may_have_landed=False, reconciled_by_fresh_oracle=True)
        out = analyze(rows)
        self.assertFalse(out['valid'])
        self.assertFalse(out['speed_claim_eligible'])
        self.assertIn('unknown delivery cannot', ' '.join(out['errors']))

    def test_valid_verified_applied_remains_valid(self):
        self.assertTrue(analyze(pairs(2))['valid'])

    def test_unknown_delivery_with_appropriate_uncertainty_remains_valid(self):
        rows = pairs(2)
        rows[0]['actions'][0].update(delivery='unknown', effect='verified', may_have_landed=True, reconciled_by_fresh_oracle=True)
        self.assertTrue(analyze(rows)['valid'])

if __name__=='__main__':
    unittest.main()

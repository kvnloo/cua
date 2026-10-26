"""UNIT-only external ABBA/BAAB plan pin controls; no live executors."""
import copy
import unittest

from test_verify_plan_coverage import HEAD, plan, prereg, receipts
from verify_plan_coverage import CoverageError, digest, verify


class ManifestPinTests(unittest.TestCase):
    def test_pinned_unmodified_plan_still_cannot_claim_real_execution(self):
        p = plan()
        result = verify(p, receipts(p), expected_head=HEAD, prereg=prereg(),
                        expected_manifest_sha256=p['manifest_sha256'])
        self.assertEqual(result['status'], 'COVERAGE_COMPLETE_NOT_AUTHENTICATED')
        self.assertIsNone(result['cua_vs_pomerado_verified_trials'])

    def test_rehashed_balanced_route_reassignment_fails_external_pin(self):
        original = plan()
        pinned_sha256 = original['manifest_sha256']
        changed = copy.deepcopy(original)
        for block in changed['blocks']:
            block['order'] = 'BAAB' if block['order'] == 'ABBA' else 'ABBA'
            for attempt, arm in zip(block['attempts'], block['order']):
                attempt['arm_assigned'] = arm
                attempt['route_assigned_not_observed'] = (
                    'cua-driver' if arm == 'A' else 'pomerado-mcp')
        changed['manifest_sha256'] = digest({k: v for k, v in changed.items()
                                             if k != 'manifest_sha256'})
        self.assertNotEqual(changed['manifest_sha256'], pinned_sha256)
        with self.assertRaisesRegex(CoverageError, 'external manifest'):
            verify(changed, receipts(changed), expected_head=HEAD, prereg=prereg(),
                   expected_manifest_sha256=pinned_sha256)

    def test_wrong_external_pin_is_rejected(self):
        p = plan()
        with self.assertRaisesRegex(CoverageError, 'external manifest'):
            verify(p, receipts(p), expected_head=HEAD, prereg=prereg(),
                   expected_manifest_sha256='f' * 64)


if __name__ == '__main__':
    unittest.main()

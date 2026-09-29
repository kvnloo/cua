"""Receipt validator negative control, written before the validator."""
import copy
import json
from pathlib import Path
import unittest
import subprocess
import sys
import tempfile
from checker import check

PIN = 'c78f50efed1ee7b289ab8947ec997904ea18fd72'


def valid():
    return {
        'schema': 1, 'cell_key': 'unit/fill', 'trial_key': 'unit/fill/python/0',
        'pin': PIN, 'language': 'python', 'kind': 'resolver',
        'branch': 'accepted', 'expected_branch': 'accepted',
        'plan_produced': True, 'producer_reachable': True,
        'proof': {'status': 'accepted', 'prior_ref': 'p1:1', 'fresh_ref': 'p2:1',
                  'verification_field': 'contains_required_token', 'submit_matches': 1,
                  'session': 'session-a'},
        'candidate': {'id': 'submit-form', 'tool': 'browser_click', 'source': 'page',
                      'ref': 'p2:1'},
    }


class ReceiptCheckerTest(unittest.TestCase):
    def test_rejects_corrupt_stale_ref_proof(self):
        row = valid()
        row['proof']['fresh_ref'] = row['proof']['prior_ref']
        self.assertIn('fresh_ref_reused', check([row]))

    def test_rejects_corrupt_receipt_identity_and_claims(self):
        mutations = [
            ('pin_mismatch', lambda r: r.update(pin='0'*40)),
            ('unexpected_branch', lambda r: r.update(branch='no-plan')),
            ('proof_candidate_mismatch', lambda r: r['candidate'].update(ref='foreign')),
            ('accepted_without_plan', lambda r: r.update(plan_produced=False)),
            ('non_page_acceptance', lambda r: r['candidate'].update(source='visual')),
            ('proof_not_unique', lambda r: r['proof'].update(submit_matches=2)),
            ('field_not_proven', lambda r: r['proof'].update(verification_field='unknown')),
        ]
        for error, mutate in mutations:
            with self.subTest(error=error):
                row=valid(); mutate(row)
                self.assertIn(error,check([row]))
        row=valid()
        self.assertIn('duplicate_trial_key',check([row,copy.deepcopy(row)]))
        self.assertEqual(check([valid()]),[])


    def test_rejects_corrupt_runner_receipts(self):
        rows=[json.loads(line) for line in (Path(__file__).parent/'results-05/receipts.jsonl').read_text().splitlines()]
        base=next(r for r in rows if r['kind']=='runner' and r['scenario']=='accepted' and r['guarded'])
        controls=[
            ('no_driver_cleanup',lambda r:r['transport'].update(closed=False)),
            ('field_leak_reported',lambda r:r['transport'].update(token_absent=False)),
            ('cross_session',lambda r:r['transport']['requests'][0].update(session_matches=False)),
            ('wrong_mutation',lambda r:r['oracle'].update(wrong_submissions=1)),
            ('verified_without_oracle',lambda r:r['oracle'].update(submitted_correct=False)),
            ('default_off_guard',lambda r:r.update(guarded=False)),
            ('guarded_model_scores',lambda r:r['events'][1].update(confidence=0.99)),
            ('guarded_provider_work',lambda r:r['events'][1].update(provider_decision_ms=100)),
            ('lost_response_retried',lambda r:r.update(scenario='first-response-lost')),
        ]
        self.assertEqual(check([base]),[])
        for error,mutate in controls:
            with self.subTest(error=error):
                row=copy.deepcopy(base);mutate(row)
                self.assertIn(error,check([row]))

    def test_cli_rejects_corrupt_receipt(self):
        here=Path(__file__).parent
        with tempfile.TemporaryDirectory(dir=here/'results-05/tmp') as directory:
            path=Path(directory)/'corrupt.jsonl';row=valid()
            row['proof']['fresh_ref']=row['proof']['prior_ref']
            path.write_text(json.dumps(row)+'\n')
            result=subprocess.run([sys.executable,str(here/'checker.py'),str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertIn('fresh_ref_reused',result.stdout)

if __name__ == '__main__':
    unittest.main()

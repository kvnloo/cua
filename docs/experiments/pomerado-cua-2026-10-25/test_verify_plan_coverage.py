"""UNIT-only adversarial omission/replay tests. No external executor is run."""
import copy
import unittest
from verify_plan_coverage import CoverageError, digest, verify

HEAD = 'a' * 40


def prereg():
    return {'schema':'cua.pomerado.prereg.v1', 'status':'PREREGISTERED_NOT_RUN',
            'design':{'seed':20261025,'first_fixture':'browser-fixture-form',
                      'blocks_per_workflow_variant':2,'blocks_per_order':1,
                      'attempts_per_block':4,'orders':['ABBA','BAAB'],
                      'negative_variants':[]}}



def plan():
    blocks = []
    for i, order in enumerate(('ABBA','BAAB'), 1):
        blocks.append({'block_id':f'read_only:browser-fixture-form:default:{i:03}',
                       'workflow':'browser-fixture-form','variant':'default', 'order':order,
                       'attempts':[{'position':j, 'arm_assigned':a,
                                    'route_assigned_not_observed': 'cua-driver' if a=='A' else 'pomerado-mcp',
                                    'status':'NOT_RUN','effect_kind_planned':'read',
                                    'blind_retry':'PROHIBITED'}
                                   for j,a in enumerate(order,1)]})
    p={'schema':'cua.pomerado.assignment.v1','evidence_class':'PLAN_ONLY',
       'status':'NOT_RUN','actual_executions':0,'candidate_head_sha':HEAD,
       'prereg_sha256':digest(prereg()),'seed':20261025,'phase':'read_only',
       'read_only_proof_sha256':None,'blocks_per_variant':2,
       'trials_per_block':4,'cohort_orders':{'default':{'ABBA':1,'BAAB':1}},
       'block_count':2,'planned_attempt_count':8,'blocks':blocks}
    p['manifest_sha256']=digest(p)
    return p


def receipts(p):
    return [{'block_id':b['block_id'],'position':x['position'],'arm':x['arm_assigned'],
             'run_id':f"{b['block_id']}/{x['position']}",'workflow':b['workflow'],
             'variant':b['variant'],'effect_kind':'read',
             'route_observed':x['route_assigned_not_observed']}
            for b in p['blocks'] for x in b['attempts']]


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.p=plan(); self.rows=receipts(self.p); self.prereg=prereg()

    def fail_case(self, term):
        with self.assertRaisesRegex(CoverageError, term):
            verify(self.p, self.rows, expected_head=HEAD, prereg=self.prereg)

    def test_complete_coverage_is_integrity_only_not_a_b_claim(self):
        output=verify(self.p,self.rows,expected_head=HEAD,prereg=self.prereg)
        self.assertEqual(output['status'],'COVERAGE_COMPLETE_NOT_AUTHENTICATED')
        self.assertIsNone(output['cua_vs_pomerado_verified_trials'])
        self.assertEqual(output['received_attempts'],8)

    def test_missing_one_attempt_fails(self):
        self.rows.pop()
        self.fail_case('planned attempts missing')

    def test_dropped_entire_block_fails(self):
        self.rows=self.rows[:4]
        self.fail_case('planned attempts missing')

    def test_replayed_attempt_fails(self):
        self.rows[0]=copy.deepcopy(self.rows[1]); self.rows[0]['run_id']='different-id'
        self.fail_case('duplicate planned attempt')

    def test_unplanned_extra_attempt_fails(self):
        r=copy.deepcopy(self.rows[0]); r['block_id']='new-unregistered';r['run_id']='new'
        self.rows.append(r)
        self.fail_case('not in frozen plan')

    def test_wrong_arm_fails(self):
        self.rows[0]['arm']='B'
        self.fail_case('arm/workflow/variant')

    def test_wrong_effect_phase_fails(self):
        self.rows[0]['effect_kind']='write'
        self.fail_case('effect class')

    def test_real_route_fallback_counts_confounds(self):
        self.rows[1]['route_observed']='fallback-cua'
        self.assertEqual(verify(self.p,self.rows,expected_head=HEAD,prereg=self.prereg)['route_mismatches'],1)

    def test_plan_digest_tampering_fails(self):
        self.p['blocks'][0]['order']='BAAB'
        self.fail_case('manifest digest mismatch')

    def test_external_sha_mismatch_fails(self):
        with self.assertRaisesRegex(CoverageError,'plan HEAD'):
            verify(self.p,self.rows,expected_head='f'*40,prereg=self.prereg)

    def test_modified_prereg_fails_source_digest_check(self):
        self.prereg['design']['seed'] += 1
        self.fail_case('prereg digest disagrees')

    def test_unproven_route_is_not_accepted(self):
        self.rows[0]['route_observed'] = 'guess'
        self.fail_case('missing/invalid observed route')

    def test_duplicate_run_identifier_fails(self):
        self.rows[1]['run_id']=self.rows[0]['run_id']
        self.fail_case('reused run_id')

    def test_phase_planned_route_drift_fails_even_with_rehashed_manifest(self):
        self.p['blocks'][0]['attempts'][0]['route_assigned_not_observed']='pomerado-mcp'
        self.p['manifest_sha256']=digest({k:v for k,v in self.p.items() if k!='manifest_sha256'})
        self.fail_case('assigned route mismatch')

    def test_missing_preregistered_order_fails(self):
        self.p['blocks'][1]['order']='ABBA'
        for j,a in enumerate('ABBA'):
            self.p['blocks'][1]['attempts'][j]['arm_assigned']=a
            self.p['blocks'][1]['attempts'][j]['route_assigned_not_observed']= 'cua-driver' if a=='A' else 'pomerado-mcp'
        self.p['manifest_sha256']=digest({k:v for k,v in self.p.items() if k!='manifest_sha256'})
        self.fail_case('balance')

if __name__=='__main__': unittest.main()

"""Evidence contract tests. Synthetic objects here are tests, never real receipts."""
import copy
import unittest
from audit import check


class ReceiptTests(unittest.TestCase):
    def test_wrong_flag_rejected_before_success_can_qualify(self):
        row = {"arm": "guarded", "guarded_flag": False, "rc": 0,
               "oracle": {"final_matches": True}, "routes": ["provider", "guarded-completion"]}
        self.assertIn("intended_flag", check(row))

    def test_route_counter_oracle_refs_and_source_rejected(self):
        for key, row, expected in [
            ('route', {'arm':'guarded','guarded_flag':True,'routes':['provider','provider']}, 'route'),
            ('calls', {'arm':'guarded','guarded_flag':True,'provider_entries':2}, 'provider_calls'),
            ('oracle', {'arm':'baseline','guarded_flag':False,'oracle':{'final_matches':False}}, 'oracle'),
            ('source', {'arm':'baseline','guarded_flag':False,'source_sha':'wrong'}, 'source_pin'),
            ('refs', {'arm':'guarded','guarded_flag':True,'proof_facts':{'fresh_ref_changed':False}}, 'refs'),
        ]:
            with self.subTest(key=key):
                self.assertIn(expected, check(row))

    def test_scrubber_uses_allowlist_not_a_token_replacement(self):
        import safe
        secret = 'unit-only-sensitive-sentinel'
        event = safe.event({'event':'step','candidate':secret,'error':secret,'text':secret,
                            'tool':'browser_type','semantic_observe_ms':1,
                            'guarded_completion':{'status':'accepted','prior_ref':'p1:2','fresh_ref':'p2:3','session':secret,'unknown':secret}})
        request = safe.request({'ref':'p1:2','text':secret,'url':secret,'session':secret})
        result = safe.result({'result':{'content':[{'text':secret}], 'structuredContent':{'outline':secret,'refs':[{'name':'verification value','role':'textbox','value':secret}]}}},'get_browser_state',secret)
        self.assertNotIn(secret,str([event,request,result]))
        self.assertEqual(event['tool'],'browser_type')
        self.assertEqual(request['ref'],'p1:2')
        self.assertTrue(result['field_matches'])

    def test_rejects_http_metadata_not_supported_by_journal(self):
        row={'schema_version':2,'arm':'baseline','guarded_flag':False,
             'oracle':{'final_matches':True,'submit_count':1,'mutation_ns':1,'first_verified_ns':2},'http_evidence':[]}
        self.assertIn('http_evidence',check(row))


if __name__ == "__main__":
    unittest.main()

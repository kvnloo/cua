"""Integration assertions for the finished packet; no product predicate is reimplemented."""
import collections
import hashlib
import json
from pathlib import Path
import unittest
from checker import check, PIN

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RESULT=HERE/'results-05'
def load(name): return json.loads((RESULT/name).read_text())
def lines(name): return [json.loads(x) for x in (RESULT/name).read_text().splitlines()]

class PacketTest(unittest.TestCase):
    def test_receipt_coverage_and_declared_counts(self):
        rows=lines('receipts.jsonl');summary=load('summary.json');cases=json.loads((HERE/'cases.json').read_text())
        self.assertEqual(len(rows),summary['receipts'])
        self.assertEqual(len(rows),270)
        self.assertEqual(len({r['trial_key'] for r in rows}),len(rows))
        self.assertEqual(check(rows),[])
        boundary=[r for r in rows if r['cell_key'].startswith('boundary/')]
        self.assertEqual({(r['case'],r['language']) for r in boundary},{(c['id'],lang) for c in cases for lang in ('python','typescript')})
        self.assertEqual(sum(r['kind']=='resolver' for r in rows),214)
        self.assertEqual(sum(r['kind']=='runner' for r in rows),56)
        self.assertEqual(len(cases),38)
    def test_exact_source_and_hermetic_setup(self):
        pins=load('pins.json');setup=load('hermetic-setup.json')
        self.assertEqual(pins['resolver_pin'],PIN)
        for p in pins['source_files']:
            self.assertEqual(hashlib.sha256((ROOT/p['path']).read_bytes()).hexdigest(),p['sha256'])
        for name,digest in setup['source_files_sha256'].items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),digest,name)
        self.assertTrue(setup['gui_environment_removed'])
        self.assertTrue(setup['driver_executable_nonexistent'])
        self.assertFalse((HERE/'NO_LIVE_DRIVER_ALLOWED').exists())
    def test_original_corpus_hashes_counts_and_links(self):
        summary=load('corpus-summary.json');rows=lines('corpus.jsonl');links=lines('corpus-links.jsonl')
        self.assertEqual(len(rows),240)
        self.assertEqual(len({r['trial_key'] for r in rows}),240)
        self.assertEqual(len({r['cell_key'] for r in rows}),69)
        self.assertEqual(summary['completed_trials'],240)
        self.assertEqual(summary['completed_cells'],69)
        self.assertEqual(len(links),len(rows))
        self.assertEqual({r['trial_key'] for r in rows},{r['trial_key'] for r in links})
        for r in rows:
            self.assertFalse(r['lossless_final_predicate_replay'])
            if r['cell_key'].startswith(('issue24/','issue33/')):self.assertTrue(r['oracle_recomputed_ok'])
        original_files={r['source']:r['source_file_sha256'] for r in rows}
        self.assertTrue(any('guarded-generalization' in p['path'] for p in summary['files_discovered']))
        for path,digest in original_files.items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),digest)
        for p in summary['files_discovered']:
            self.assertEqual(hashlib.sha256(Path(p['path']).read_bytes()).hexdigest(),p['sha256'])
    def test_python_typescript_resolver_parity(self):
        grouped=collections.defaultdict(list)
        for row in lines('receipts.jsonl'):
            if row['kind']=='resolver':grouped[row['cell_key']].append(row)
        for key,pair in grouped.items():
            self.assertEqual(len(pair),2,key)
            self.assertEqual(pair[0]['branch'],pair[1]['branch'],key)
            self.assertEqual(pair[0]['proof'],pair[1]['proof'],key)
            self.assertEqual(pair[0]['candidate'],pair[1]['candidate'],key)
    def test_runner_receipts_match_original_artifacts(self):
        for row in lines('receipts.jsonl'):
            if row['kind']!='runner':continue
            d=RESULT/'runner'/row['scenario']/('guarded' if row['guarded'] else 'baseline')/row['language']
            self.assertEqual(row['oracle'],json.loads((d/'oracle.json').read_text()))
            self.assertEqual(row['transport'],json.loads((d/'transport.json').read_text()))
            self.assertEqual(row['events'],[json.loads(x) for x in (d/'events.jsonl').read_text().splitlines()])
            self.assertEqual(row['oracle']['wrong_submissions'],0)
            for event in row['events']:
                if event.get('decision_route')=='guarded-completion':
                    self.assertEqual(event['guarded_completion']['fresh_ref'],row['transport']['mutations'][event['step']-1]['ref'])
    def test_unknown_oracle_is_not_nonreplay_proof(self):
        rows=[r for r in lines('receipts.jsonl') if r['kind']=='runner' and r['scenario']=='verification-unknown']
        self.assertEqual(len(rows),4)
        for r in rows:
            self.assertEqual(r['oracle']['submit_count'],2)
            self.assertEqual(r['transport']['outcome'],'budget_exhausted')
            self.assertTrue(r['oracle']['submitted_correct'])
    def test_normal_fixture_deletes_exactly_one_provider_decision(self):
        rows=[r for r in lines('receipts.jsonl') if r['kind']=='runner' and r['scenario']=='accepted']
        self.assertEqual(len(rows),4)
        for r in rows:
            self.assertEqual(r['transport']['provider_calls'],1 if r['guarded'] else 2)
            self.assertEqual(r['oracle']['submit_count'],1)
            self.assertEqual(r['transport']['outcome'],'verified')
    def test_other_tasks_are_not_broadened(self):
        ids={c['id'] for c in json.loads((HERE/'cases.json').read_text()) if c.get('task_id')}
        for r in lines('receipts.jsonl'):
            if r['kind']=='resolver' and r['cell_key'].startswith('boundary/') and r['case'] in ids:
                self.assertEqual(r['branch'],'no-plan')
    def test_packet_manifest_when_present(self):
        path=HERE/'SHA256SUMS'
        if not path.exists():self.skipTest('packet not sealed yet')
        for line in path.read_text().splitlines():
            digest,name=line.split('  ',1)
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),digest,name)

if __name__=='__main__': unittest.main(verbosity=2)

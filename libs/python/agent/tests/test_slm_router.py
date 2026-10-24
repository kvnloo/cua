"""Offline router contracts; these are unit checks, not GUI benchmark evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import tempfile

ROUTER = Path(__file__).resolve().parents[1] / 'examples/slm_router'
sys.path.insert(0, str(ROUTER))
import corpus
import remote

class RouterContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen=json.loads((ROUTER/'data/corpus.json').read_text())

    def node(self, task, depth=0):
        return deepcopy(next(n for n in self.frozen['nodes'] if n['task']==task and n['depth']==depth))

    def test_task_split_is_disjoint_and_complete(self):
        train=set(self.frozen['train_tasks']);test=set(self.frozen['test_tasks'])
        self.assertFalse(train & test)
        self.assertEqual(len(train | test),31)
        self.assertGreaterEqual(len(test),10)
        for n in self.frozen['nodes']:
            self.assertEqual(n['split'],'test' if n['task'] in test else 'train')

    def test_features_exclude_oracle_and_candidate_output(self):
        n=self.node('post-demo-split-600')
        before=corpus.features(n)
        n['task_spec']['oracle']={'kind':'refusal'}
        n['snapshot']={};n['initial_snapshot']={};n['candidate_output']='UNKNOWN'
        self.assertEqual(corpus.features(n),before)
        self.assertNotIn('task',before)
        self.assertNotIn('oracle',before)

    def test_correctness_does_not_imitate_failed_source(self):
        n=self.node('post-demo-eggs-seven-minutes')
        self.assertTrue(corpus.correct(n,'TIMER 7'))
        self.assertFalse(corpus.correct(n,'UNKNOWN'))
        self.assertFalse(corpus.correct(n,'DONE'))

    def test_calculator_progress_and_final_state_are_separate(self):
        initial=self.node('post-demo-split-600')
        self.assertTrue(corpus.correct(initial,'OPEN Calculator'))
        self.assertFalse(corpus.correct(initial,'TYPE 600/4='))
        opened=self.node('post-demo-split-600',1)
        self.assertTrue(corpus.correct(opened,'TYPE 600/4='))
        self.assertTrue(corpus.correct(opened,'TYPE 150='))
        self.assertFalse(corpus.correct(opened,'TYPE 600/4'))
        complete=self.node('post-demo-split-600',2)
        self.assertTrue(corpus.correct(complete,'DONE'))
        self.assertFalse(corpus.correct(complete,'UNKNOWN'))

    def test_arithmetic_rejects_code(self):
        for expression in ['__import__("os").system("id")=','2**1000000=','(2+2)=','1/0=']:
            with self.subTest(expression=expression), self.assertRaises((ValueError,SyntaxError,ZeroDivisionError)):
                corpus.arithmetic(expression)

    def test_refusal_requires_unchanged_state(self):
        n=self.node('post-refuse-delete')
        self.assertTrue(corpus.correct(n,'UNKNOWN'))
        self.assertFalse(corpus.correct(n,'DONE'))
        n['snapshot']['volume']=0
        self.assertFalse(corpus.correct(n,'UNKNOWN'))

    def test_calendar_matches_native_confirmation_exactly(self):
        n=self.node('post-local-calendar')
        self.assertTrue(corpus.correct(n,'EVENT Sandbox review | 2030-01-02 | 14:00 UTC | none'))
        self.assertFalse(corpus.correct(n,'EVENT Sandbox review | 2030-01-02 | 14:00 | none'))
        self.assertFalse(corpus.correct(n,'EVENT Sandbox review | 2030-01-02 | 14:00 UTC | stranger'))

class RemoteInferenceTransport(unittest.TestCase):
    def test_protocol_ignores_admission_logs_and_stops_cleanly(self):
        program = """
import json, sys
print('fleet: admitted fixture worker', flush=True)
print('SLM_ROUTER_RPC ' + json.dumps({'ready': True}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if request.get('stop'):
        print('SLM_ROUTER_RPC ' + json.dumps({'stopped': True}), flush=True)
        break
    print('SLM_ROUTER_RPC ' + json.dumps({'model': request['model'], 'node': request['node']}), flush=True)
"""
        with tempfile.TemporaryDirectory() as directory:
            client = remote.Client([sys.executable, '-u', '-c', program],
                                   Path(directory) / 'worker.log', timeout=5)
            try:
                self.assertEqual(client.complete('candidate', {'user': 'state'}),
                                 {'model': 'candidate', 'node': {'user': 'state'}})
            finally:
                client.close()
            self.assertEqual(client.process.returncode, 0)

    def test_worker_error_is_not_an_inference_result(self):
        program = """
import json, sys
print('SLM_ROUTER_RPC ' + json.dumps({'ready': True}), flush=True)
for line in sys.stdin:
    stop = json.loads(line).get('stop')
    print('SLM_ROUTER_RPC ' + json.dumps({'stopped': True} if stop else {'error': 'unsafe memory pressure'}), flush=True)
    if stop:
        break
"""
        with tempfile.TemporaryDirectory() as directory:
            client = remote.Client([sys.executable, '-u', '-c', program],
                                   Path(directory) / 'worker.log', timeout=5)
            try:
                with self.assertRaisesRegex(RuntimeError, 'unsafe memory pressure'):
                    client.complete('candidate', {})
            finally:
                client.close()

if __name__=='__main__':
    unittest.main()

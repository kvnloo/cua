"""Invoke the pinned Python producer/resolver and unmodified runner with hermetic I/O."""
from __future__ import annotations
import argparse, asyncio, contextlib, io, json, os, sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import asynccontextmanager
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EX = ROOT / 'libs/cua-driver/examples/jev-use'
sys.path[:0] = [str(EX / 'python'), str(EX)]
import guarded_completion as gc
from tasks import FixtureFormTask, fixture_sources, TaskSources
from sources import Candidate


def snapshot(case, before, token):
    prefix = 'initial' if before else 'fresh'
    value = '' if before else token
    fs = case.get('field_state') if not before else None
    if fs == 'empty': value = ''
    if fs == 'other': value = 'not-the-required-value'
    if fs == 'unavailable': value = None
    field = {'role': 'textbox', 'name': 'verification value', 'ref': 'p1:0' if before else 'p2:0', 'value': value}
    refs = [] if fs == 'missing' else [field]
    if not before and case.get('duplicate_field'):
        other = {**field, 'ref': 'p2:9', 'value': ''}
        refs = [field, other] if case['duplicate_field'] == 'valid-first' else [other, field]
    if case.get('extra_field'): refs.append({'role': 'textbox', 'name': 'family name', 'ref': 'p2:8', 'value': ''})
    if case.get(prefix + '_submit', True):
        button = {'role': 'button', 'name': case.get(prefix+'_name', 'Submit'), 'ref': case.get(prefix+'_ref', 'p1:1' if before else 'p2:1')}
        refs.append(button)
        if case.get(prefix+'_duplicate'):
            refs.append({**button, 'ref': button['ref'] if case[prefix+'_duplicate'] == 'same' else 'p2:7'})
    result = {'target_id': case.get('fresh_target', 'target') if not before else 'target', 'tab_id': 'tab', 'refs': refs}
    if not before and case.get('content_duplicate'):
        result['content_refs'] = [{'role': 'button', 'name': 'Submit', 'ref': 'p2:7', 'states': {'disabled': True}}]
    return result


def resolve_case(case):
    token = os.urandom(18).hex()
    task = FixtureFormTask(token)
    if case.get('task_id'): object.__setattr__(task, 'id', case['task_id'])
    initial = fixture_sources(snapshot(case, True, token))
    selected = task.candidates(initial)[0]
    selected = replace(selected, **{name: case['first_'+name] for name in ('id','tool','source') if 'first_'+name in case})
    plan = gc.plan_guarded_completion(task, initial, selected, session=case.get('plan_session', 'session-a'))
    row = {'case': case['id'], 'plan_produced': plan is not None, 'producer_reachable': case['reachability'] == 'producer', 'reachability': case['reachability']}
    if plan is None: return {**row, 'branch': 'no-plan', 'proof': None, 'candidate': None}
    if case.get('resolve_task_id'): object.__setattr__(task, 'id', case['resolve_task_id'])
    fresh = TaskSources() if case.get('page_missing') else fixture_sources(snapshot(case, False, token))
    candidates = [] if case.get('page_missing') else task.candidates(fresh)
    change = case.get('candidate_mutation')
    if change == 'none': candidates = []
    elif change == 'duplicate': candidates = [candidates[0], candidates[0]]
    elif change:
        c = candidates[0]
        args = dict(c.arguments)
        if change == 'wrong-ref': args['ref'] = 'p2:foreign'
        if change == 'target': args['target_id'] = 'foreign-target'
        if change == 'session': args['session'] = 'foreign-session'
        opts: dict = {'arguments': args}
        if change in ('visual', 'ax'): opts['source'] = change
        if change == 'wrong-id': opts['id'] = 'another-submit'
        if change == 'capture': opts['capture_id'] = 'stale-capture'
        candidates = [replace(c, **opts)]
    result = gc.resolve_guarded_completion(plan, task, fresh, candidates, session=case.get('resolve_session', 'session-a'))
    c = result.candidate
    row.update(branch=result.telemetry.get('reason',result.telemetry['status']), proof=result.telemetry,
               candidate=None if c is None else {'id': c.id, 'tool': c.tool, 'source': c.source, 'ref': c.arguments.get('ref'), 'target_matches_snapshot': c.arguments.get('target_id') == fresh.page.snapshot['target_id'], 'capture_metadata': c.capture_id is not None})
    assert token not in json.dumps(row)
    return row


@asynccontextmanager
async def transport(_params):
    yield None, None


def runner_case(scenario, output):
    import run
    token = os.environ['AUDIT_TOKEN']
    url = os.environ['AUDIT_URL']
    mutations, requests = [], []
    class Session:
        value = ''
        observations = 0
        label = None
        closed = False
        async def __aenter__(self): return self
        async def __aexit__(self,*_): self.closed = True
        async def initialize(self): pass
        async def list_tools(self):
            if scenario == 'capture-mismatch':
                return SimpleNamespace(tools=[SimpleNamespace(name=n,inputSchema={'properties':{'capture_id':{}}}) for n in ('click','get_window_state','parse_visual_regions')])
            return SimpleNamespace(tools=[])
        async def call_tool(self, name, args):
            if self.label is None: self.label = args.get('session')
            requests.append({'tool':name,'session_matches':args.get('session') == self.label})
            data = {}
            if name == 'browser_prepare': data = {'prepared_pid':42}
            elif name == 'list_windows': data = {'windows':[{'window_id':7,'is_on_screen':True,'bounds':{'width':800,'height':600}}]}
            elif name == 'get_browser_state':
                if args.get('snapshot_format') != 'semantic_v2': data = {'target_id':'target','tabs':[{'tab_id':'tab','active':True}]}
                else:
                    self.observations += 1
                    n = self.observations
                    data = {'target_id':'target','tab_id':'tab','refs':[{'role':'textbox','name':'verification value','ref':f'p{n}:0','value': self.value}]}
                    if scenario == 'field-unavailable' and n == 2: data['refs'][0].pop('value')
                    missing = (scenario == 'reobserve' and n == 2) or (scenario == 'capture-mismatch' and n > 1)
                    if not missing: data['refs'].append({'role':'button','name':'Submit','ref':'p1:1' if scenario == 'ref-reused' else f'p{n}:1'})
                    if scenario in ('duplicate-after','provider-failure') and n == 2: data['refs'].append({'role':'button','name':'Submit','ref':f'p{n}:7'})
            elif name in ('browser_type','browser_click'):
                n = self.observations
                mutations.append({'tool':name,'ref':args.get('ref'),'session_matches':args.get('session')==self.label,'current_ref':args.get('ref') in (f'p{n}:0',f'p{n}:1')})
                refused = (scenario == 'first-refused' and name == 'browser_type') or (scenario in ('second-refused','session-refusal') and name == 'browser_click')
                if refused:
                    return SimpleNamespace(isError=False,structuredContent={'status':'refused','refusal':{'code':'session_mismatch' if scenario=='session-refusal' else 'stale_ref'}})
                if name == 'browser_type':
                    self.value = args['text']
                    req = Request(url+'type',data=self.value.encode(), method='POST')
                else: req = Request(url+'submit',data=self.value.encode(), method='POST')
                with urlopen(req,timeout=2): pass
                if (scenario == 'first-response-lost' and name == 'browser_type') or (scenario == 'second-response-lost' and name == 'browser_click'):
                    raise RuntimeError(token)
            elif name == 'get_window_state': data = {'capture_id':'fresh-capture'}
            elif name == 'parse_visual_regions':
                data = json.loads((EX/'fixtures/jev-visual-replay-v1.json').read_text())['visual_regions']
                data['capture']['capture_id'] = 'wrong-capture'
                data['capture']['source'] = {'kind':'window','pid':42,'window_id':7}
            elif name != 'browser_navigate': raise AssertionError(name)
            return SimpleNamespace(isError=False,structuredContent=data)
    session = Session()
    calls = 0
    original_choose = run.choose_mock_for_task
    def choose(*values):
        nonlocal calls
        calls += 1
        if scenario == 'provider-failure' and calls == 2: raise RuntimeError(token)
        return original_choose(*values)
    args = argparse.Namespace(token=token,fixture_url=url,max_steps=3,log=str(output/'events.jsonl'),provider='mock',guarded_completion=os.environ.get('AUDIT_GUARDED') == '1',visual_observation='auto' if scenario == 'capture-mismatch' else 'off',dry_run=False)
    outcome = None
    exception = None
    with patch.object(run,'stdio_client',transport), patch.object(run,'ClientSession',return_value=session), patch.object(run,'choose_mock_for_task',side_effect=choose), contextlib.redirect_stdout(io.StringIO()):
        try: outcome = asyncio.run(run.run(args))
        except Exception as exc: exception = type(exc).__name__
    raw = (output/'events.jsonl').read_text()
    assert token not in raw
    receipt = {'outcome':outcome,'exception':exception,'closed':session.closed,'provider_calls':calls,'requests':requests,'mutations':mutations,'token_absent':True}
    (output/'transport.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    if sys.argv[1] == 'resolver':
        cases = json.loads(Path(sys.argv[2]).read_text())
        print(json.dumps([resolve_case(c) for c in cases],sort_keys=True))
    else:
        runner_case(sys.argv[2],Path(sys.argv[3]))

"""Source-independent checker: no product/harness imports; same author, not certification."""
import copy
import hashlib
import json
from pathlib import Path

SOURCE = 'c78f50efed1ee7b289ab8947ec997904ea18fd72'
DRIVER = 'f1d7f2d4ce929a8df80338ac57942bc6535ee5bef4f441f6173688b62da722f7'


def check(row):
    errors = []
    def require(ok, code):
        if not ok: errors.append(code)
    arm = row.get('arm')
    require(arm in ('baseline', 'guarded', 'fallback'), 'arm')
    require(row.get('guarded_flag') is (arm != 'baseline'), 'intended_flag')
    require(row.get('source_sha') == SOURCE, 'source_pin')
    require(row.get('driver_sha256') == DRIVER, 'driver_pin')
    require(row.get('rc') == 0 and row.get('timed_out') is False, 'exit')
    require(row.get('routes') == (['provider', 'guarded-completion'] if arm == 'guarded' else ['provider', 'provider']), 'route')
    wanted = 1 if arm == 'guarded' else 2
    providers = row.get('provider_journal', [])
    starts = [p for p in providers if p.get('event') == 'provider_enter']
    ends = [p for p in providers if p.get('event') == 'provider_exit']
    require(row.get('provider_entries') == wanted and len(starts) == wanted and len(ends) == wanted, 'provider_calls')
    require([p.get('index') for p in starts] == list(range(1, wanted+1)) and
            [p.get('index') for p in ends] == list(range(1, wanted+1)) and
            all(a.get('ns', 0) < b.get('ns', 0) for a,b in zip(starts, ends)), 'provider_spans')
    oracle = row.get('oracle', {})
    require(oracle.get('final_matches') is True and oracle.get('submit_count') == 1 and
            oracle.get('first_verified_ns') is not None and oracle.get('mutation_ns') is not None, 'oracle')
    require(row.get('survivors_after_cleanup') == 0 and row.get('private_session') is True, 'isolation')
    calls = row.get('mcp', [])
    obs = [c for c in calls if c.get('name') == 'get_browser_state' and c.get('request', {}).get('semantic')]
    actions = [c for c in calls if c.get('name') in ('browser_type','browser_click')]
    require(len(obs) == 2, 'observations')
    require([c.get('name') for c in actions] == ['browser_type','browser_click'], 'actions')
    require(all(c.get('end_ns') is not None and c.get('result', {}).get('error') is False for c in calls), 'mcp_errors')
    require(row.get('runner_outcome') == 'verified', 'runner_outcome')
    facts = row.get('proof_facts', {})
    require(facts.get('fresh_ref_changed') is True and facts.get('click_uses_fresh_ref') is True and
            facts.get('session_matches') is True and facts.get('field_matches') is True, 'refs')
    if len(obs) == 2 and len(actions) == 2:
        o1,o2 = obs; a1,a2 = actions
        require(o1['end_ns'] < a1['start_ns'] < a1['end_ns'] < o2['start_ns'] < o2['end_ns'] < a2['start_ns'], 'ordering')
        before = o1.get('result', {}).get('submit_refs', []); fresh = o2.get('result', {}).get('submit_refs', [])
        require(len(before) == 1 and len(fresh) == (2 if arm == 'fallback' else 1), 'uniqueness')
        require(a2.get('request', {}).get('ref') in fresh and not set(before).intersection(fresh), 'trace_ref_binding')
        require(o2.get('result', {}).get('field_matches') is True, 'trace_field')
        require(a1['request'].get('session') == a2['request'].get('session') == o2['request'].get('session'), 'trace_session')
    steps = [s for s in row.get('events', []) if s.get('event') == 'step']
    proof = steps[1].get('guarded_completion', {}) if len(steps) == 2 else {}
    if arm == 'guarded':
        require(proof.get('status') == 'accepted' and proof.get('submit_matches') == 1 and proof.get('verification_field') == 'contains_required_token', 'guard_proof')
        if len(obs) == 2 and len(actions) == 2:
            require(proof.get('prior_ref') in obs[0]['result'].get('submit_refs',[]) and
                    proof.get('fresh_ref') == actions[1]['request'].get('ref') and
                    proof.get('session') == actions[1]['request'].get('session'), 'proof_trace_binding')
    elif arm == 'fallback':
        require(proof == {'status':'declined','reason':'submit_not_unique'}, 'decline')
    else:
        require(all('guarded_completion' not in s for s in steps), 'default_off')
    if row.get('schema_version',1)>=2:
        http=row.get('http_evidence',[])
        submits=[h for h in http if h.get('path')=='/submit' and h.get('method')=='POST' and h.get('actor')=='browser' and h.get('status')==200]
        verified=[h for h in http if h.get('path')=='/state' and h.get('matches') is True and h.get('actor')=='observer']
        resets=[h for h in http if h.get('path')=='/reset' and h.get('actor')=='runner' and h.get('status')==204]
        require(len(submits)==1 and len(resets)==1 and bool(verified), 'http_evidence')
        if len(submits)==1 and verified:
            require(submits[0]['start_ns'] <= oracle.get('mutation_ns',0) <= submits[0]['end_ns'] <= verified[0]['end_ns'] <= oracle.get('first_verified_ns',0), 'http_timestamps')
        expected_runner={'python':'b088056874dbd126de2cb7d5bb057a7f44d2ae1a18bec5c4cd4d2348ac9896e6','typescript':'ea625bbb7137590ed554b4c4d8c3625810def4adae38f168b120e5c9da89619c'}
        require(row.get('source_runner_sha256')==expected_runner.get(row.get('language')), 'runner_bytes')
        boot=row.get('bootstrap',[])
        require(len(boot)==1 and boot[0].get('source_file_sha256')==row.get('source_runner_sha256') and boot[0].get('guarded_flag')==row.get('guarded_flag'), 'bootstrap_binding')
        require(('--guarded-completion' in row.get('command',[])) == (arm!='baseline'), 'command_flag')
        require(row.get('routes')==[s.get('decision_route') for s in steps], 'event_routes')
        require(len(steps)==2 and not any(s.get('dry_run') or s.get('action_error_present') for s in steps), 'steps')
    return sorted(set(errors))


def corruption_test(row):
    mutations = {
        'wrong_flag': lambda r: r.update(guarded_flag=not r['guarded_flag']),
        'wrong_route': lambda r: r.update(routes=['not-the-route']),
        'wrong_calls': lambda r: r.update(provider_entries=99),
        'wrong_oracle': lambda r: r['oracle'].update(final_matches=False),
        'missing_http_journal': lambda r: r['oracle'].update(submit_count=0),
        'wrong_source': lambda r: r.update(source_sha='0'*40),
        'wrong_driver': lambda r: r.update(driver_sha256='0'*64),
        'wrong_refs': lambda r: r['proof_facts'].update(fresh_ref_changed=False),
        'wrong_trace_ref': lambda r: next(c for c in r['mcp'] if c['name']=='browser_click')['request'].update(ref='p0:99999'),
        'missing_provider_entry': lambda r: r.update(provider_journal=[]),
        'contamination': lambda r: r.update(survivors_after_cleanup=1),
    }
    if row.get('schema_version',1)>=2:
        mutations.update({
            'missing_actual_http':lambda r:r.update(http_evidence=[]),
            'wrong_actual_http':lambda r:[h.update(matches=False) for h in r['http_evidence'] if h['path']=='/state'],
            'wrong_command_flag':lambda r:r.update(command=[] if r['arm']!='baseline' else ['--guarded-completion']),
            'wrong_bootstrap_hash':lambda r:r['bootstrap'][0].update(source_file_sha256='0'*64),
            'wrong_event_route':lambda r:next(s for s in r['events'] if s['event']=='step').update(decision_route='wrong'),
        })
    result = {}
    for name, mutate in mutations.items():
        changed = copy.deepcopy(row)
        try:
            mutate(changed); result[name] = bool(check(changed))
        except (KeyError, StopIteration): result[name] = False
    return {'all_rejected': all(result.values()), 'cases':result}


def audit_directory(directory):
    receipts = []
    for path in sorted(Path(directory).glob('cells/*/receipt.json')):
        row = json.loads(path.read_text()); errors = check(row); corrupt = corruption_test(row)
        http=json.loads((path.parent/'http-journal.json').read_text())
        mcp=[json.loads(s) for s in (path.parent/'mcp.jsonl').read_text().splitlines()]
        providers=[json.loads(s) for s in (path.parent/'provider.jsonl').read_text().splitlines()]
        if row.get('mcp')!=[r for r in mcp if r.get('event')=='mcp_call']: errors.append('mcp_file_binding')
        if row.get('provider_journal')!=providers: errors.append('provider_file_binding')
        if row.get('events')!=json.loads((path.parent/'runner-events.json').read_text()): errors.append('events_file_binding')
        if row.get('schema_version',1)>=2 and row.get('http_evidence')!=[h for h in http if h['actor']!='observer' or h.get('matches')]: errors.append('http_file_binding')
        for name, digest in row.get('artifact_hashes', {}).items():
            if hashlib.sha256((path.parent/name).read_bytes()).hexdigest() != digest: errors.append('artifact_hash:'+name)
        if not row.get('checker_corruption_test',{}).get('all_rejected') or not corrupt['all_rejected']: errors.append('corruption_gate')
        receipts.append({'trial_id':row['trial_id'], 'errors':errors, 'corruptions':corrupt})
    planned=json.loads((Path(directory)/'plan.json').read_text())
    observed_ids=sorted(r['trial_id'] for r in receipts)
    expected_ids=sorted(r['trial_id'] for r in planned)
    complete=observed_ids==expected_ids and len(set(observed_ids))==len(observed_ids)
    halted=(Path(directory).parent.parent/'SAFETY_HALT.json').exists()
    return {'kind':'source-independent-checker-same-author', 'count':len(receipts),'expected_count':len(planned),
            'plan_complete':complete,'live_focus_qualified':False if halted else None,
            'qualification_note':'Receipt consistency is not focus-isolation or independent-person certification.',
            'passed':bool(receipts) and complete and all(not r['errors'] for r in receipts), 'receipts':receipts}


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('directory'); p.add_argument('--out')
    a=p.parse_args(); result=audit_directory(a.directory); text=json.dumps(result, indent=2)+'\n'
    if a.out: Path(a.out).write_text(text)
    print(json.dumps({'count':result['count'], 'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)

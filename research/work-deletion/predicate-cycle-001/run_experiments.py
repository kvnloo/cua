#!/usr/bin/env python3
"""One-command exact-source hermetic experiment. Only writes this packet's output directory."""
from __future__ import annotations
import argparse, collections, hashlib, json, os, re, subprocess, sys
from pathlib import Path
from urllib.request import urlopen
from oracle import oracle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PIN = 'c78f50efed1ee7b289ab8947ec997904ea18fd72'
EXREL = 'libs/cua-driver/examples/jev-use'
DEPS = Path('/mnt/zer0models/github/cua-lanes/c4316')/EXREL
PYTHON = str(DEPS/'.venv/bin/python')
NODE = '/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin/node'
CORPUS = Path('/mnt/zer0models/github/cua-lanes/evidence/scripts/repro/handoff')


def digest(data): return hashlib.sha256(data).hexdigest()
def canonical(data): return json.dumps(data,sort_keys=True,separators=(',',':')).encode()
def save(path,data): path.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
def jsonl(path,rows): path.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)


def source_pins():
    files=git('ls-tree','-r','--name-only',PIN,'--',EXREL).decode().splitlines()
    hashes=[]
    for name in files:
        if not (name.endswith(('.py','.ts','.json')) or name.endswith('uv.lock')): continue
        raw=git('show',f'{PIN}:{name}')
        assert (ROOT/name).read_bytes()==raw, ('dirty assigned source',name)
        dep=DEPS/Path(name).relative_to(EXREL)
        assert dep.read_bytes()==raw, ('dependency checkout differs from exact pin',name)
        hashes.append({'path':name,'sha256':digest(raw),'blob':git('rev-parse',f'{PIN}:{name}').decode().strip()})
    return {'resolver_pin':PIN,'python_source':str(ROOT/EXREL/'python'),
            'typescript_source':str(DEPS/'typescript'),'typescript_source_byte_equal_to_assigned_pin':True,
            'python_executable':PYTHON,'python_version':subprocess.check_output([PYTHON,'--version'],text=True).strip(),
            'node_executable':NODE,'node_version':subprocess.check_output([NODE,'--version'],text=True).strip(),
            'source_files':hashes,'dependency_lock_sha256':digest((DEPS/'package-lock.json').read_bytes()),
            'driver':'not executed; hermetic transport only','provider':'mock; failure SDK interception only'}


def corpus_inventory(out):
    discovered=[]
    for path in sorted(CORPUS.rglob('*')):
        if path.is_file() and (path.name.startswith(('issue-24-','issue-33-')) or any('guarded-generalization' in part for part in path.parts)):
            discovered.append({'path':str(path),'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size})
    corpus_rows=[]
    sources=[('issue24',CORPUS/'issue-24-live-battery.json'),('issue33',CORPUS/'issue-33-replay.json'),('generalization',CORPUS/'rfc-3963-guarded-generalization/results/trials.json')]
    seen={}
    for name,path in sources:
        data=json.loads(path.read_text()); rows=data['rows'] if isinstance(data,dict) else data
        for index,r in enumerate(rows):
            if name=='issue24':
                cell=f"{name}/{r['task']}/{r['arm']}"; rep=r['rep']; complete='oracle' in r and 'verified' in r
                safe={k:r[k] for k in ['task','arm','rep','driver_sha','authority_rule','expected_route','observed_route','route_ok','provider_decisions','observations','actions','prior_refs','clicked_refs','verified','correctness_failure']}
                task=r['task']
                expected_token=f"t{rep}-{task[:6]}"
                o=r['oracle']
                oracle_ok=(o.get('filled')==expected_token if task=='fill-submit' else o.get('checked') is True if task=='toggle-confirm' else o.get('given')==expected_token and o.get('family')==expected_token+'-b' if task=='two-fields' else o.get('opened') is True and o.get('modal') is True if task=='modal' else o.get('ambiguous') is None)
                safe['oracle_recomputed_ok']=oracle_ok
            elif name=='issue33':
                cell=f"{name}/{r['task']}/{r['policy']}/{r['injection']}"; rep=r['rep']; complete=r['journal_final'].get('count') is not None
                safe={k:r[k] for k in ['task','policy','injection','rep','driver_sha','authority_rule','dispatch_attempted','retry_attempted','duplicate_mutation','held','clicked_ref']}
                safe['journal_after_count']=r['journal_after_dispatch']['count']; safe['journal_final_count']=r['journal_final']['count']
                safe['oracle_recomputed_ok']=(safe['journal_final_count']>safe['journal_after_count'] and safe['retry_attempted']) if r['policy']=='naive' else (safe['journal_final_count']==safe['journal_after_count'] and not safe['retry_attempted'])
            else:
                m=re.fullmatch(r'positive-(\d+)-(baseline|guarded)',r['trial'])
                cell=f"{name}/toggle-confirm/"+(f"positive/{m[2]}" if m else r['trial']); rep=int(m[1]) if m else 0
                complete='oracle' in r and 'route' in r
                safe={k:r[k] for k in ['trial','variant','guarded_flag','route','counts','verified_by_independent_oracle','prior_ref','dispatched_completion_ref','second_action_fresh_ref']}
                safe['task']='toggle-confirm'; safe['oracle']={k:v for k,v in r['oracle'].items() if isinstance(v,(bool,int))}
                safe['oracle_recomputed_ok']=r['oracle'].get('confirmed') is True
            if not complete: continue
            key=f'{cell}/rep-{rep}'
            row={'cell_key':cell,'trial_key':key,'source':str(path),'source_row':index,'source_file_sha256':digest(path.read_bytes()),'source_row_sha256':digest(canonical(r)),'lossless_final_predicate_replay':False,'missing':['pre/post semantic snapshots','final task/candidate objects','session-bound plan'],**safe}
            if key in seen:
                assert seen[key]['source_row_sha256']==row['source_row_sha256'], ('conflicting duplicate',key)
                seen[key].setdefault('duplicate_locations',[]).append({'source':str(path),'row':index})
            else: seen[key]=row
    corpus_rows=sorted(seen.values(),key=lambda r:r['trial_key'])
    jsonl(out/'corpus.jsonl',corpus_rows)
    summary={'files_discovered':discovered,'completed_trials':len(corpus_rows),'completed_cells':len({r['cell_key'] for r in corpus_rows}),'by_corpus':dict(collections.Counter(r['cell_key'].split('/')[0] for r in corpus_rows)),
             'exclusions':{'issue-24-battery.json':'theoretical counts; live_success null, not a completed live cell','issue-33-dispatch.json':'summary-only unit assertions, no trial identity or snapshots','issue-33-injections.json':'summary-only unit assertions, no exact final task/candidates','visual-only':'explicit pending entry, not completed'},
             'lossless_replay':'BLOCKED: no complete snapshots retained; do not relabel reconstructions as recorded observations'}
    save(out/'corpus-summary.json',summary)
    # One exact-resolver invocation per deduplicated completed cell in each language.
    # These are structural adaptations, NOT lossless replay of the old rules.
    cells={}
    for r in corpus_rows: cells.setdefault(r['cell_key'],r)
    cases=[]
    links=[]
    for cell,r in sorted(cells.items()):
        task=r['task']; c={'id':cell,'corpus_cell':cell,'reachability':'corpus-structural-adaptation','expected':'no-plan'}
        if task=='fill-submit':
            c['expected']='accepted'
            refs=r.get('prior_refs'); clicked=r.get('clicked_refs')
            if refs: c['initial_ref']=refs[0]
            if clicked: c['fresh_ref']=clicked[-1]
            # #33 captures only final click, so prior ref cannot be recovered.
            if r.get('clicked_ref'): c['fresh_ref']=r['clicked_ref']; c['initial_ref']='reconstructed-prior-ref'
        elif task=='ambiguous': c['initial_duplicate']=True
        else:
            c.update(task_id=task,first_id='toggle-feature' if task=='toggle-confirm' else 'open-dialog' if task=='modal' else 'type-given',first_tool='browser_type' if task=='two-fields' else 'browser_click')
            if task=='modal': c['initial_submit']=False
        cases.append(c)
    for row in corpus_rows:
        links.append({'trial_key':row['trial_key'],'cell_key':row['cell_key'],'executed_structural_case':row['cell_key'],'lossless':False,
            'historical_policy_is_not_final_predicate':True,'oracle':'historical state only; no fresh mutation in resolver replay'})
    save(out/'corpus-cases.json',cases); jsonl(out/'corpus-links.jsonl',links)
    return corpus_rows,cases


def run_all(out):
    out.mkdir(parents=True,exist_ok=False)
    save(out/'pins.json',source_pins())
    corpus,corpus_cases=corpus_inventory(out)
    excluded_env={'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','XDG_SESSION_TYPE','XDG_CURRENT_DESKTOP'}
    env={**{k:v for k,v in os.environ.items() if k not in excluded_env and not k.startswith('CUA_DRIVER_')},'PYTHONDONTWRITEBYTECODE':'1','TSX_DISABLE_CACHE':'1','AUDIT_TS_EX':str(DEPS),'TMPDIR':str(out/'tmp'),'CUA_DRIVER_BIN':str(HERE/'NO_LIVE_DRIVER_ALLOWED')}
    assert not Path(env['CUA_DRIVER_BIN']).exists()
    save(out/'hermetic-setup.json',{'gui_environment_removed':True,'driver_executable_nonexistent':True,'transport_mock':'Python ClientSession; TypeScript SDK ESM Client.prototype','source_files_sha256':{p.name:digest(p.read_bytes()) for p in HERE.iterdir() if p.suffix in ('.py','.mjs') or p.name=='cases.json'}})
    (out/'tmp').mkdir()
    commands={'python':[PYTHON,str(HERE/'probe_python.py')], 'typescript':[NODE,'--import',str(DEPS/'node_modules/tsx/dist/loader.mjs'),str(HERE/'probe_typescript.mjs')]}
    rows=[]; commands_log=[]
    for language,cmd in commands.items():
        for case_file,prefix in [(HERE/'cases.json','boundary'),(out/'corpus-cases.json','corpus-adaptation')]:
            command=cmd+['resolver',str(case_file)]
            result=subprocess.run(command,capture_output=True,text=True,env=env,timeout=45)
            commands_log.append({'argv':command,'exit':result.returncode})
            if result.returncode: raise RuntimeError(result.stderr)
            cases=json.loads(case_file.read_text()); received=json.loads(result.stdout)
            assert len(received)==len(cases)
            for case,r in zip(cases,received):
                cell=f"{prefix}/{case['id']}"
                row={'schema':1,'kind':'resolver','pin':PIN,'language':language,'cell_key':cell,'trial_key':f'{cell}/{language}/0','expected_branch':case['expected'],**r}
                assert row['branch']==row['expected_branch'],row
                rows.append(row)
            jsonl(out/'receipts.jsonl',rows)
    for scenario in ['accepted','duplicate-after','ref-reused','reobserve','field-unavailable','provider-failure','first-response-lost','second-response-lost','first-refused','second-refused','session-refusal','verification-unavailable','verification-unknown','capture-mismatch']:
        paired={}
        for language,cmd in commands.items():
            for guarded in (False,True):
                arm='guarded' if guarded else 'baseline'; cell=f'runner/{scenario}/{arm}'; trial=f'{cell}/{language}/0'
                directory=out/'runner'/scenario/arm/language; directory.mkdir(parents=True)
                token=os.urandom(24).hex()
                with oracle(token,scenario) as url:
                    command=cmd+['runner',scenario,str(directory)]
                    result=subprocess.run(command,capture_output=True,text=True,env={**env,'AUDIT_TOKEN':token,'AUDIT_URL':url,'AUDIT_GUARDED':'1' if guarded else '0'},timeout=25)
                    with urlopen(url+'audit',timeout=2) as response: audit=json.load(response)
                assert token not in result.stdout+result.stderr, 'field leak from child'
                commands_log.append({'argv':command,'exit':result.returncode,'environment_inputs':['AUDIT_TOKEN (ephemeral, not persisted)','AUDIT_URL (owned oracle)','AUDIT_GUARDED']})
                if not (directory/'transport.json').exists(): raise RuntimeError(result.stderr or 'transport receipt missing')
                transport=json.loads((directory/'transport.json').read_text())
                events=[json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
                save(directory/'oracle.json',audit)
                guards=[e for e in events if 'guarded_completion' in e]
                row={'schema':1,'kind':'runner','pin':PIN,'language':language,'cell_key':cell,'trial_key':trial,
                     'scenario':scenario,'guarded':guarded,'events':events,'transport':transport,'oracle':audit,
                     'child_exit':result.returncode,'oracle_kind':'owned-loopback-http-state','evidence_tier':'hermetic-exact-runner',
                     'branch':[e.get('decision_route') for e in events if e.get('decision_route')],
                     'proof':[e['guarded_completion'] for e in guards], 'reachability':'invalid-driver-snapshot' if scenario=='ref-reused' else 'external-I/O-boundary'}
                rows.append(row);jsonl(out/'receipts.jsonl',rows)
                paired[(language,guarded)]=row
                assert transport['closed'] and transport['token_absent']
                assert audit['wrong_submissions']==0, 'STOP: wrong mutation'
                assert all(v['session_matches'] for v in transport['requests'])
                if scenario in ('first-response-lost','first-refused','verification-unavailable','provider-failure','capture-mismatch'): assert audit['submit_count']==0
                if scenario=='second-response-lost': assert audit['submit_count']==1
                if scenario in ('second-refused','session-refusal'): assert audit['submit_count']==0
                if scenario=='accepted':
                    assert audit['submit_count']==1 and audit['submitted_correct']
                    assert transport['provider_calls']==(1 if guarded else 2)
                if not guarded: assert not guards
        for language in commands:
            b,g=paired[(language,False)],paired[(language,True)]
            if g['oracle']['submit_count']>max(1,b['oracle']['submit_count']):
                save(out/'STOP.json',{'reason':'optimization-attributable repeated mutation','baseline':b,'guarded':g})
                raise RuntimeError('STOP: optimization-attributable repeated mutation; notify parent')
    save(out/'commands.json',commands_log)
    # Compare both language resolver branches/proofs without trusting expected labels.
    grouped=collections.defaultdict(list)
    for row in rows:
        if row['kind']=='resolver': grouped[row['cell_key']].append(row)
    for cell, pair in grouped.items():
        assert len(pair)==2
        assert pair[0]['branch']==pair[1]['branch'] and pair[0]['proof']==pair[1]['proof'],cell
    summary={'receipts':len(rows),'resolver_receipts':sum(r['kind']=='resolver' for r in rows),'runner_receipts':sum(r['kind']=='runner' for r in rows),'completed_historical_trials':len(corpus),'completed_historical_cells':len({r['cell_key'] for r in corpus}),
             'resolver_branch_counts':dict(collections.Counter(r['branch'] for r in rows if r['kind']=='resolver')),
             'runner_wrong_submissions':sum(r['oracle']['wrong_submissions'] for r in rows if r['kind']=='runner'),'independent_auditor':'PENDING parent audit; this checker is not an independent auditor'}
    save(out/'summary.json',summary)
    print(json.dumps(summary,sort_keys=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,default=HERE/'results');args=parser.parse_args()
    output=args.out.resolve(); assert output.is_relative_to(HERE), 'output must stay inside assigned packet'
    run_all(output)

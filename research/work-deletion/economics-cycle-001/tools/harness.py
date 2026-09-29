#!/usr/bin/env python3
"""Scrubbed whole-task envelope for exact c78 runners + real Driver/MCP/Chromium.
Adapted conceptually from #10, never imports or edits the unsafe original harness.
All raw pipe/HTTP content remains in memory. One fresh private browser per trial.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import random
import secrets
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
import audit
import safe

HERE=Path(__file__).resolve().parent
SOURCE=Path('/mnt/zer0models/github/cua-lanes/c4316')
EXAMPLES=SOURCE/'libs/cua-driver/examples/jev-use'
DRIVER=Path('/mnt/zer0models/github/cua-lanes/evidence/4316-maintainer-proof-review/cua-driver-current-main')
BUILD=DRIVER.parent/'driver-build-receipt.json'
NODE=Path('/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin/node')
LAUNCHER=Path('/home/kvn/.hermes/profiles/clean/cache/scratch/cua-4316-x11-session.sh')
SEED=20260929
sys.dont_write_bytecode=True
sys.path.insert(0,str(EXAMPLES))
import fixture_server as fixture


def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(['git','-C',str(SOURCE),*args],text=True).strip()
def save(path,data): Path(path).write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def load_lines(path): return [json.loads(s) for s in Path(path).read_text().splitlines()] if Path(path).exists() else []


def marked(marker=None):
    result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid(): continue
        try:
            env=(p/'environ').read_bytes().split(b'\0')
            matching=[s for s in env if s.startswith(b'CUA_DRIVER_ECON_CELL=')]
            if matching and (marker is None or matching[0]==f'CUA_DRIVER_ECON_CELL={marker}'.encode()):
                # Zombies cannot interact, but report them separately as reaping work.
                stat=(p/'stat').read_text().rsplit(')',1)[1].split()
                if stat[0]!='Z': result.append(int(p.name))
        except (OSError,ValueError,IndexError): pass
    return result


def union_ns(spans,lo,hi):
    intervals=sorted((max(lo,a),min(hi,b)) for a,b in spans if a<hi and b>lo)
    total=0; end=lo
    for a,b in intervals:
        if b>max(a,end): total+=b-max(a,end)
        end=max(end,b)
    return total


def run_cell(spec,out,manifest):
    if marked(): raise RuntimeError('process_contamination_before_cell')
    trial=spec['trial_id']; cdir=out/'cells'/trial; cdir.mkdir(parents=True,exist_ok=False)
    token=secrets.token_hex(24)  # secret is NEVER an argv field or artifact value
    journal=[]; mutations=[]; lock=threading.Lock(); oracle_seen=[]; events=[]; boot=[]
    class Handler(fixture.FixtureHandler):
        def do_GET(self):
            self.begin=time.monotonic_ns(); return super().do_GET()
        def do_POST(self):
            self.begin=time.monotonic_ns(); return super().do_POST()
        def _send(self,status,content_type,body):
            actor='observer' if self.headers.get('User-Agent')=='EconOracle/1' else ('browser' if 'Chrome/' in self.headers.get('User-Agent','') else 'runner')
            row={'start_ns':self.begin,'end_ns':time.monotonic_ns(),'method':self.command,
                 'path':self.path if self.path in ('/','/state','/submit','/reset') else 'other','actor':actor,'status':int(status)}
            if self.path=='/state': row['matches']=json.loads(body).get('submitted')==token
            with lock: journal.append(row)
            return super()._send(status,content_type,body)
    server=fixture.FixtureServer(('127.0.0.1',0)); server.RequestHandlerClass=Handler
    original_submit=server.state.submit
    def submitted(value):
        original_submit(value)
        with lock: mutations.append({'ns':time.monotonic_ns(),'matches':value==token})
    server.state.submit=submitted
    page=fixture.PAGE
    if spec['arm']=='fallback':
        # Invalidate uniqueness through real application DOM after the first input.
        # This never submits, replaces Driver data or chooses the fallback action.
        fixture.PAGE=page.replace(b'</html>',b'''<script>document.querySelector('input').addEventListener('input',()=>{const b=document.querySelector('button');b.after(b.cloneNode(true))},{once:true});</script></html>''')
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    url=f'http://127.0.0.1:{server.server_port}/'
    wrapper=cdir/'driver.sh'
    wrapper.write_text('#!/bin/bash\nexec /usr/bin/python3 '+shlex.quote(str(HERE/'mcp_scrub_proxy.py'))+' --real '+shlex.quote(str(DRIVER))+' --trace '+shlex.quote(str(cdir/'mcp.jsonl'))+' --observe-ms '+str(spec['observe_ms'])+' -- "$@"\n')
    wrapper.chmod(0o700)
    common=['--provider','mock','--fixture-url',url,'--max-steps','4','--visual-observation','auto']
    if spec['arm']!='baseline': common+=['--guarded-completion']
    lang=spec['language']
    cmd=([str(EXAMPLES/'.venv/bin/python'),str(HERE/'python_entry.py')] if lang=='python' else
         [str(NODE),'--import',str(EXAMPLES/'node_modules/tsx/dist/esm/index.mjs'),str(HERE/'typescript_entry.mjs')])+common
    env=dict(os.environ)
    env.update(CUA_DRIVER_BIN=str(wrapper),CUA_DRIVER_PERMISSION_MODE='unrestricted',CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS='1',
               CUA_DRIVER_ECON_CELL=trial,ECON_EXAMPLES=str(EXAMPLES),ECON_PROVIDER_JOURNAL=str(cdir/'provider.jsonl'),
               ECON_PROVIDER_MS=str(spec['provider_ms']),PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    stop=threading.Event(); stream_counts={'stdout_discarded_bytes':0,'stderr_discarded_bytes':0}
    def stream_stdout(pipe):
        for line in iter(pipe.readline,b''):
            try:
                raw=json.loads(line)
                if raw.get('event')=='bootstrap':
                    boot.append({'guarded_flag':raw.get('guarded_flag') is True,'source_file_sha256':raw.get('source_file_sha256')})
                elif raw.get('event') in ('step','outcome'):
                    row=safe.event(raw); row['arrival_ns']=time.monotonic_ns(); events.append(row)
                else: stream_counts['stdout_discarded_bytes']+=len(line)
            except (ValueError,TypeError,AttributeError): stream_counts['stdout_discarded_bytes']+=len(line)
    def stream_stderr(pipe):
        for chunk in iter(lambda:pipe.read(65536),b''): stream_counts['stderr_discarded_bytes']+=len(chunk)
    def observe():
        while not stop.is_set():
            try:
                with urlopen(Request(url+'state',headers={'User-Agent':'EconOracle/1'}),timeout=1) as response:
                    data=json.load(response)
                if data.get('submitted')==token:
                    oracle_seen.append(time.monotonic_ns()); return
            except Exception: pass
            stop.wait(.01)
    t0=time.monotonic_ns(); proc=subprocess.Popen(cmd,cwd=EXAMPLES,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    proc.stdin.write(json.dumps({'token':token}).encode()); proc.stdin.close()
    workers=[threading.Thread(target=stream_stdout,args=(proc.stdout,),daemon=True),threading.Thread(target=stream_stderr,args=(proc.stderr,),daemon=True),threading.Thread(target=observe,daemon=True)]
    for w in workers:w.start()
    timed_out=False
    try: rc=proc.wait(timeout=90)
    except subprocess.TimeoutExpired:
        timed_out=True; os.killpg(proc.pid,signal.SIGKILL); rc=proc.wait()
    exit_ns=time.monotonic_ns(); stop.set()
    for w in workers:w.join(timeout=2)
    try:
        with urlopen(Request(url+'state',headers={'User-Agent':'EconOracle/1'}),timeout=2) as response: final_matches=json.load(response).get('submitted')==token
    except Exception: final_matches=False
    cleanup_start=time.monotonic_ns(); leftovers=marked(trial)
    for pid in leftovers:
        try: os.kill(pid,signal.SIGTERM)
        except ProcessLookupError: pass
    deadline=time.monotonic()+3
    while marked(trial) and time.monotonic()<deadline: time.sleep(.02)
    for pid in marked(trial):
        try: os.kill(pid,signal.SIGKILL)
        except ProcessLookupError: pass
    deadline=time.monotonic()+1
    while marked(trial) and time.monotonic()<deadline: time.sleep(.02)
    survivors=marked(trial); cleanup_end=time.monotonic_ns()
    server.shutdown(); server.server_close(); fixture.PAGE=page
    mcp_all=load_lines(cdir/'mcp.jsonl'); calls=[r for r in mcp_all if r.get('event')=='mcp_call']
    providers=load_lines(cdir/'provider.jsonl'); starts=[r for r in providers if r.get('event')=='provider_enter']; ends=[r for r in providers if r.get('event')=='provider_exit']
    steps=[r for r in events if r.get('event')=='step']; outcomes=[r for r in events if r.get('event')=='outcome']
    observations=[c for c in calls if c['name']=='get_browser_state' and c['request']['semantic']]
    actions=[c for c in calls if c['name'] in ('browser_type','browser_click','click')]
    proof={}
    if len(observations)==2 and len(actions)==2:
        old=observations[0]['result'].get('submit_refs',[]); fresh=observations[1]['result'].get('submit_refs',[])
        proof={'fresh_ref_changed':bool(old) and bool(fresh) and not set(old).intersection(fresh),
               'click_uses_fresh_ref':actions[1]['request'].get('ref') in fresh,
               'session_matches':len({c['request'].get('session') for c in observations+actions})==1,
               'field_matches':observations[1]['result'].get('field_matches') is True}
    oracle={'final_matches':final_matches,'submit_count':len(mutations),'mutation_ns':mutations[0]['ns'] if mutations else None,
            'first_verified_ns':oracle_seen[0] if oracle_seen else None,
            'http_runner_state_reads':sum(r['actor']=='runner' and r['path']=='/state' for r in journal),
            'http_observer_state_reads':sum(r['actor']=='observer' and r['path']=='/state' for r in journal)}
    spans=[{'name':c['name']+(':semantic' if c['request']['semantic'] else ''),'start_ns':c['start_ns'],'end_ns':c['end_ns']} for c in calls if c.get('end_ns')]
    spans += [{'name':'provider_entry','start_ns':a['ns'],'end_ns':b['ns']} for a,b in zip(starts,ends)]
    spans += [{'name':'runner_http:'+r['path'],'start_ns':r['start_ns'],'end_ns':r['end_ns']} for r in journal if r['actor']=='runner']
    spans += [{'name':'runner_post_outcome_shutdown','start_ns':outcomes[-1]['arrival_ns'],'end_ns':exit_ns}] if outcomes else []
    observed=oracle['first_verified_ns']; union=union_ns([(s['start_ns'],s['end_ns']) for s in spans],t0,exit_ns)
    first_semantic=observations[0]['start_ns'] if observations else None
    times={'spawn_ns':t0,'exit_ns':exit_ns,'cleanup_start_ns':cleanup_start,'cleanup_end_ns':cleanup_end,
           'runner_lifetime_ms':(exit_ns-t0)/1e6,'external_cleanup_ms':(cleanup_end-cleanup_start)/1e6,
           'startup_to_first_semantic_ms':(first_semantic-t0)/1e6 if first_semantic else None,
           'verified_outcome_ms':(observed-t0)/1e6 if observed else None,
           'runner_post_verified_ms':(exit_ns-observed)/1e6 if observed else None,
           'critical_path_union_ms':union/1e6,'residual_runner_ms':(exit_ns-t0-union)/1e6,
           'pre_verified_union_ms':union_ns([(s['start_ns'],s['end_ns']) for s in spans],t0,observed)/1e6 if observed else None}
    row={**spec,'schema_version':2,'http_evidence':[h for h in journal if h['actor']!='observer' or h.get('matches')],
         'source_sha':audit.SOURCE,'driver_sha256':manifest['driver_sha256'],'guarded_flag':boot[0]['guarded_flag'] if len(boot)==1 else None,
         'bootstrap':boot,'source_runner_sha256':manifest['source_hashes'][f'{lang}/run.'+('py' if lang=='python' else 'ts')],
         'harness_hashes':manifest['harness_hashes'],'command':cmd,'protected_parameter_transport':'stdin-memory-only',
         'provider_kind':'deterministic-original-mock-with-entry-counter','provider_entries':len(starts),'provider_journal':providers,
         'mcp':calls,'events':events,'routes':[s.get('decision_route') for s in steps],
         'runner_outcome':outcomes[-1].get('outcome') if outcomes else None,'oracle':oracle,'proof_facts':proof,
         'rc':rc,'timed_out':timed_out,'private_session':manifest['private_session'],'survivors_after_cleanup':len(survivors),
         'leftovers_terminated':len(leftovers),'times':times,'named_spans':spans,**stream_counts}
    save(cdir/'http-journal.json',journal); save(cdir/'runner-events.json',events)
    row['artifact_hashes']={name:digest(cdir/name) for name in ('http-journal.json','runner-events.json','mcp.jsonl','provider.jsonl','driver.sh') if (cdir/name).exists()}
    row['checker_errors']=audit.check(row); row['checker_corruption_test']=audit.corruption_test(row)
    row['qualifies']=not row['checker_errors'] and row['checker_corruption_test']['all_rejected']
    row['secret_scan_passed']=all(token not in (cdir/name).read_text(errors='replace') for name in row['artifact_hashes']) and token not in json.dumps(row)
    if not row['secret_scan_passed']: raise RuntimeError('secret_scan_failed')
    save(cdir/'receipt.json',row)
    print(json.dumps({'trial_id':trial,'qualifies':row['qualifies'],'errors':row['checker_errors'],'routes':row['routes'],'provider_entries':len(starts),'observations':len(observations),'verified_ms':times['verified_outcome_ms']}),flush=True)
    return row


def preflight():
    if (HERE.parent/'SAFETY_HALT.json').exists():
        raise RuntimeError('Live trials halted: verified headless Sway required')
    source_sha=git('rev-parse','HEAD')
    assert source_sha==audit.SOURCE, 'source head changed'
    assert not git('status','--porcelain','--','libs/cua-driver/examples/jev-use'), 'source dirty'
    build=json.loads(BUILD.read_text()); rust=git('rev-parse',source_sha+':libs/cua-driver/rust')
    assert rust==build['source_rust_tree']; assert digest(DRIVER)==build['sha256']==audit.DRIVER
    private=bool(os.environ.get('DISPLAY')) and os.environ.get('XDG_SESSION_TYPE')=='x11' and not os.environ.get('WAYLAND_DISPLAY') and not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and '/cua-4316-x11.' in os.environ.get('XDG_RUNTIME_DIR','')
    assert private, 'private X11 session required'
    files=['fixture_server.py']+[f'{lang}/{name}.{ext}' for lang,ext,names in [('python','py',['run','guarded_completion','tasks','sources','core','jev_adapter','driver_env']),('typescript','ts',['run','guarded_completion','tasks','sources','core','jev_adapter','driver_env'])] for name in names]
    return {'source_sha':source_sha,'source_worktree':str(SOURCE),'source_hashes':{f:digest(EXAMPLES/f) for f in files},
            'harness_hashes':{p.name:digest(p) for p in HERE.iterdir() if p.suffix in ('.py','.mjs')},
            'driver_sha256':digest(DRIVER),'driver_build_receipt':build,'source_rust_tree':rust,
            'launcher_sha256':digest(LAUNCHER),'private_session':private,'private_display':os.environ['DISPLAY'],
            'node_version':subprocess.check_output([str(NODE),'--version'],text=True).strip(),
            'upstream_expected':'fe9b0c6d3c0307537bccbfd69f4f801ec219adc0','upstream_fetched_at_design':'db5d0f4caf3a66eb31c8d6e24394cec962899257',
            'harness_git_head_at_execution':subprocess.check_output(['git','-C',str(HERE),'rev-parse','HEAD'],text=True).strip(),
            'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'seed':SEED}


def plan(phase):
    rng=random.Random(SEED); specs=[]
    if phase=='pilot': designs=[(0,0,1,['baseline','guarded'])]
    elif phase=='fallback': designs=[(0,0,1,['fallback'])]
    elif phase=='repeat': designs=[(0,0,3,['baseline','guarded'])]
    else: designs=[(250,0,1,['baseline','guarded']),(250,250,1,['baseline','guarded'])]
    for p,o,blocks,arms in designs:
        for block in range(1,blocks+1):
            langs=['python','typescript']; rng.shuffle(langs)
            for lang in langs:
                ordered=arms[:]; rng.shuffle(ordered)
                pair=f'{phase}-{lang}-p{p}-o{o}-b{block}'
                for position,arm in enumerate(ordered):
                    specs.append({'trial_id':pair+'-'+arm,'scientific_cell':f'{lang}-{arm}-p{p}-o{o}',
                                  'pair_id':pair,'phase':phase,'language':lang,'arm':arm,'block':block,
                                  'position':position,'provider_ms':p,'observe_ms':o})
    return specs


def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True); p.add_argument('--phase',choices=['pilot','fallback','repeat','grid'],required=True); a=p.parse_args()
    assert a.out.is_absolute(); a.out.mkdir(parents=True,exist_ok=False)
    lock=Path('/home/kvn/.hermes/profiles/clean/cache/scratch/cua-quantitative-desktop.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifest=preflight(); specs=plan(a.phase); save(a.out/'manifest.json',manifest); save(a.out/'plan.json',specs)
    import shutil
    snapshot=a.out/'harness-source'; snapshot.mkdir()
    for name in manifest['harness_hashes']: shutil.copy2(HERE/name,snapshot/name)
    for spec in specs:
        row=run_cell(spec,a.out,manifest)
        if not row['qualifies']: return 2  # Never continue a route failure or contamination.
    return 0

if __name__=='__main__': raise SystemExit(main())

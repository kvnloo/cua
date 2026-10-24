"""Actually route each live semantic decision in an explicitly handed-off owned Sway guest."""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import time
import joblib
import collect
import corpus
import experiment
import jev_bridge
import remote

class RoutedRuntime:
    def __init__(self, args, policy, manifest, bundle):
        self.args,self.policy,self.manifest,self.bundle=args,policy,manifest,bundle
        self.models={m['id']:m for m in manifest['models']}
        self.engine=None
        self.current=None
        self.depth=0
        self.events=[]
        self.seed=1729
        self.remote=None

    def begin(self, task):
        self.depth=0
        self.task=task

    def choose(self, node):
        if self.policy.startswith('always:'):
            return self.policy.split(':',1)[1]
        candidates=self.bundle['candidates']
        if self.policy=='R1':
            state=experiment.decision_state(node,candidates,self.bundle['profiles'],self.bundle['devices'],self.args.device)
            state['live_request_nonce']=str(time.time_ns())
            selected,self.route_evidence=jev_bridge.request_choice(self.args.jev_bridge,state,candidates)
            return selected
        if self.policy=='R0':
            return max(candidates,key=lambda m:experiment.rank(self.bundle['profiles'],experiment.context_key(node),m,
                         self.bundle['devices'].get(self.args.device,{}).get(m)))
        name={'R2':'tree','R3':'mlp','R4':'tree' if self.bundle['meta']=='R2' else 'mlp',
              'cost-tree':'cost_tree','cost-MLP':'cost_mlp'}[self.policy]
        x=self.bundle['vectorizer'].transform([experiment.vector(node,candidates,self.bundle['profiles'],self.bundle['devices'],self.args.device)])
        return str(self.bundle[name].predict(x)[0])

    def complete(self, system, user, max_new=64):
        started=time.perf_counter()
        node={'system':system,'user':user,'request':self.task['request'],'depth':self.depth}
        router_started=time.perf_counter()
        selected=self.choose(node)
        routing_s=time.perf_counter()-router_started
        if selected not in self.bundle['candidates']:
            raise ValueError('policy selected an unavailable model')
        if self.args.remote_command:
            if self.remote is None:
                command=[part.replace('{policy}',self.policy.replace(':','-'))
                         for part in json.loads(self.args.remote_command.read_text())]
                self.remote=remote.Client(command,
                                          self.args.out/(self.policy.replace(':','-')+'-remote-worker.log'))
            response=self.remote.complete(selected,node)
            reply=response['reply']
            switch_s=response['switch_load_s']
            command=response['command']
            evidence=response['backend_evidence']
            if response['model_sha256']!=self.models[selected]['sha256']:
                raise ValueError('remote inference model SHA256 does not match frozen manifest')
        else:
            switch_s=0.
            if self.current!=selected:
                load_started=time.perf_counter()
                self.close()
                self.engine=collect.Engine(self.manifest['server'],self.models[selected],self.args.gpu_layers,self.args.threads,
                                           log=self.args.out/(f'{self.policy.replace(":","-")}-{selected}.log'))
                self.engine.start()
                self.current=selected
                switch_s=time.perf_counter()-load_started
            reply=self.engine.complete(node)
            command=self.engine.command
            evidence=dict(self.engine.backend_evidence)
        elapsed=time.perf_counter()-started
        event={'task':self.task['id'],'depth':self.depth,'policy':self.policy,'selected_model':selected,
               'router_s':routing_s,'switch_load_s':switch_s,'generation_s':reply['latency_s'],
               'total_complete_s':elapsed,'raw':reply['output'],'command':command,
               'backend_evidence':evidence,
               'model_sha256':self.models[selected].get('sha256'),'decoding_seed':self.seed,
               'jev':self.route_evidence if self.policy=='R1' else None,
               'user_sha256':hashlib.sha256(user.encode()).hexdigest()}
        if self.args.remote_command:
            event['remote_memory']={key:response[key] for key in ('memory_before','memory_after')}
            event['remote_admission']=self.remote.ready
        self.events.append(event)
        with (self.args.out/'routing-events.jsonl').open('a') as stream:
            stream.write(json.dumps(event)+'\n')
        self.depth+=1
        timings=reply['timings']
        return {'raw':reply['output'],'seconds':elapsed,'prompt_tokens':timings.get('prompt_n',0),
                'output_tokens':timings.get('predicted_n',0)}

    def close(self):
        if self.remote is not None:
            self.remote.close()
            self.remote=None
        if self.engine is not None:
            self.engine.close()
        self.engine=None
        self.current=None

async def run(args):
    from cua_sandbox import Sandbox
    if 'R1' in args.policy and args.jev_bridge is None:
        raise ValueError('R1 live policy requires the explicitly started native OMP IPC bridge')
    args.out.mkdir(parents=True,exist_ok=False)
    bundle=joblib.load(args.bundle)  # only locally generated/trusted policy artifact
    manifest=json.loads(args.manifest.read_text())
    if args.server:
        manifest['server']=args.server
    frozen=json.loads(args.corpus.read_text())
    heldout=set(frozen['test_tasks'])
    suite,task_digest=corpus.HARNESS.load_tasks()
    tasks=[(i,t) for i,t in enumerate(suite['tasks']) if t['id'] in heldout]
    if len(tasks)<10:
        raise ValueError('dynamic evaluation requires at least ten held-out tasks')
    sandbox=await Sandbox.connect(url=corpus.HARNESS.validate_endpoint(args.endpoint),
                                  token=os.environ.get(args.token_env),telemetry_enabled=False)
    backend=corpus.HARNESS.OwnedLinuxBackend(sandbox,args.ownership_id)
    runtime=None
    def stop(signum,frame):
        if runtime is not None:runtime.close()
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,stop)
    rows=[]
    all_events=[]
    try:
        fingerprint=await backend.guest(mode='fingerprint')
        if not fingerprint.get('outputs') or any(not o['name'].startswith('HEADLESS-') for o in fingerprint['outputs']):
            raise ValueError('non-headless guest rejected')
        for policy in args.policy:
            runtime=RoutedRuntime(args,policy,manifest,bundle)
            try:
                for index,task in tasks:
                    random.seed(suite['seed']+index)
                    runtime.begin(task)
                    row=await corpus.HARNESS.run_task(backend,runtime,task,args.out/policy.replace(':','-')/task['id'],6,64,seed=suite['seed']+index)
                    rows.append(dict(row,policy=policy))
                    with (args.out/'task-results.jsonl').open('a') as stream:
                        stream.write(json.dumps(dict(row,policy=policy))+'\n')
                    print(json.dumps({'policy':policy,'task':task['id'],'status':row['status']}),flush=True)
            finally:
                runtime.close()
                if policy=='R1':
                    jev_bridge.stop_native(args.jev_bridge)
                all_events.extend(runtime.events)
    finally:
        if runtime is not None:runtime.close()
        await sandbox.disconnect()
    summary={'scope':'live closed-loop native GUI, independent final-state oracles; not frozen replay',
             'corpus_sha256':hashlib.sha256(args.corpus.read_bytes()).hexdigest(),'tasks_sha256':task_digest,
             'heldout_tasks':sorted(heldout),'guest_fingerprint':fingerprint,'device':args.device,
             'routing_events':all_events,'policies':{}}
    summary['execution_server']=manifest['server']
    summary['gpu_layers']=args.gpu_layers
    summary['training_latency_caveat']='Static training profiles retain their original device/runtime regime; live CPU execution and switch/load costs are measured separately.'
    for policy in args.policy:
        subset=[r for r in rows if r['policy']==policy]
        events=[e for e in all_events if e['policy']==policy]
        summary['policies'][policy]={'tasks':len(subset),'passed':sum(r['status']=='passed' for r in subset),
             'total_task_wall_s':sum(r['wall_seconds'] for r in subset),
             'total_complete_s':sum(e['total_complete_s'] for e in events),
             'total_router_s':sum(e['router_s'] for e in events),
             'total_switch_load_s':sum(e['switch_load_s'] for e in events),
             'decisions':len(events),'choices':dict(Counter(e['selected_model'] for e in events)),
             'task_status':{r['task']:r['status'] for r in subset}}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary['policies']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--endpoint',required=True)
    p.add_argument('--ownership-id',required=True)
    p.add_argument('--token-env',default='CUA_SANDBOX_TOKEN')
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--server')
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--policy',action='append',required=True)
    p.add_argument('--jev-bridge',type=Path)
    p.add_argument('--remote-command',type=Path,help='JSON argv for a finite stdin/stdout worker, including fleet admission and quiet locks')
    p.add_argument('--device',default='groot')
    p.add_argument('--gpu-layers',type=int,default=0)
    p.add_argument('--threads',type=int,default=2)
    asyncio.run(run(p.parse_args()))

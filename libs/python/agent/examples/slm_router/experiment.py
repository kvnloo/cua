"""Task-grouped static router experiments. No held-out labels enter selection/fitting."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import joblib
import corpus

ROOT = Path(__file__).resolve().parent

def pct(values, p):
    return float(np.percentile(values, p)) if values else None

def read_data(corpus_path, matrix):
    raw = Path(corpus_path).read_bytes()
    data = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(x) for x in Path(matrix).read_text().splitlines()]
    rows = [r for r in rows if r['status'] == 'ok' and r['corpus_sha256'] == digest]
    nodes = {n['id']: n for n in data['nodes']}
    table = {}
    for row in rows:
        if row['node_id'] not in nodes:
            raise ValueError('matrix contains unknown node')
        row['correct'] = corpus.correct(nodes[row['node_id']], row['output'])
        table[row['model'], row['node_id']] = row
    models = sorted({r['model'] for r in rows})
    complete = [m for m in models if all((m, n) in table for n in nodes)]
    return data, nodes, table, complete, digest

def context_key(node):
    f = corpus.features(node)
    return f['family'] + '|' + f['last_action']

def profile(nodes, table, models):
    train = [n for n in nodes.values() if n['split'] == 'train']
    result = {}
    for model in models:
        groups = {}
        keys = {corpus.family(n['request']) for n in train} | {context_key(n) for n in train} | {'all'}
        for family in sorted(keys):
            subset = [n for n in train if family in {'all', corpus.family(n['request']), context_key(n)}]
            groups[family] = {'n': len(subset), 'accuracy': statistics.mean(table[model,n['id']]['correct'] for n in subset),
                              'latency_s': statistics.median(table[model,n['id']]['latency_s'] for n in subset),
                              'devices': sorted({table[model,n['id']]['device'] for n in subset})}
        result[model] = groups
    return result

def rank(profiles, family, model, latency=None):
    p = profiles[model].get(family, profiles[model]['all'])
    return (p['accuracy'], -(latency if latency is not None else p['latency_s']), model)

def device_profiles(paths, profiles, training_ids):
    result = {}
    for model,groups in profiles.items():
        for device in groups['all']['devices']:
            result.setdefault(device,{})[model]=groups['all']['latency_s']
    aliases = {'qwen25': 'qwen25-05', 'Qwen2.5-0.5B-Instruct': 'qwen25-05', 'qwen3': 'qwen3-06', 'Qwen3-0.6B': 'qwen3-06', 'hobbylm': 'hobby1b', 'HobbyLM-1B-CUA-merged': 'hobby1b'}
    provenance = []
    matrix_samples = defaultdict(list)
    for path in paths:
        if not Path(path).exists():
            continue
        for line in Path(path).read_text().splitlines():
            row = json.loads(line)
            if row.get('status') not in {'complete','ok'}:
                continue
            raw_model = str(row.get('model',''))
            model = aliases.get(raw_model,aliases.get(raw_model.partition(':')[0],raw_model))
            if model not in profiles:
                continue
            if 'node_id' in row:
                if row['node_id'] in training_ids:
                    matrix_samples[(str(path),row['device'],model)].append(row['latency_s'])
                continue
            quality = row.get('quality') or {}
            if isinstance(quality,list):
                if any(q.get('reference_exact_match') is False for q in quality):
                    continue
            elif quality.get('passed') is False or quality.get('matches_fp16') is False:
                continue
            metrics = row.get('metrics') or row
            latency = metrics.get('latency_p50_s', row.get('latency_p50_s'))
            if latency is None and row.get('latency_p50_ms') is not None:
                latency = row['latency_p50_ms'] / 1000
            if latency is None:
                continue
            device = row['device']
            current = result.setdefault(device, {}).get(model)
            if current is None or latency < current:
                result[device][model] = latency
                provenance.append({'path': str(path), 'row_id': row.get('id'), 'device':device, 'model':model, 'latency_s':latency,
                                   'scope':'external fixed-prompt tuning latency, not this corpus latency'})
    for (path,device,model),samples in matrix_samples.items():
        result.setdefault(device,{})[model] = statistics.median(samples)
        provenance.append({'path':path,'device':device,'model':model,'samples':len(samples),
                           'latency_s':statistics.median(samples),'scope':'routing corpus TRAINING nodes only; takes precedence over fixed-prompt microbenchmarks'})
    return result, provenance

def vector(node, models, profiles, devices, device='groot'):
    result = corpus.features(node, len(models), device)
    for model in models:
        p = profiles[model].get(context_key(node), profiles[model].get(result['family'], profiles[model]['all']))
        result['train_quality:' + model] = p['accuracy']
        for name, latencies in devices.items():
            result['latency:' + name + ':' + model] = latencies.get(model, 999.)
        result['active_latency:' + model] = devices.get(device, {}).get(model, 999.)
    return result

def decision_state(node, candidates, profiles, devices, device='groot'):
    return {'features':vector(node,candidates,profiles,devices,device),
            'available_models':candidates,
            'training_only_quality_latency_profiles':{
                m:{'current_context':profiles[m].get(context_key(node),profiles[m]['all']),
                   'overall':profiles[m]['all']} for m in candidates},
            'device_latency_profiles':devices}


def prepare(args):
    data,nodes,table,models,digest = read_data(args.corpus,args.matrix)
    if len(models) < 3:
        raise ValueError('at least three complete candidate columns required')
    profiles = profile(nodes,table,models)
    devices,provenance = device_profiles(args.profile,profiles,{n['id'] for n in nodes.values() if n['split']=='train'})
    if args.pools:
        pools = json.loads(Path(args.pools).read_text())['pools']
        missing = set(m for candidates in pools.values() for m in candidates) - set(models)
        if missing:
            raise ValueError('configured pool columns are incomplete: ' + ', '.join(sorted(missing)))
    else:
        ordered = sorted(models,key=lambda m:profiles[m]['all']['latency_s'])
        pools = {'3':ordered[:3], 'all':ordered}
        if len(models)>=5:
            pools['5']=ordered[:5]
    states = {}
    heldout_states = {}
    for pool, candidates in pools.items():
        for node in nodes.values():
            target = states if node['split'] == 'train' else heldout_states
            target[pool + ':' + node['id']] = decision_state(node,candidates,profiles,devices,args.device)
    out = {'corpus_sha256':digest,'complete_models':models,'pools':pools,'profiles':profiles,
           'training_device':args.device,
           'device_profiles':devices,'device_profile_provenance':provenance,'states':states,'heldout_states':heldout_states,
           'split':{k:data[k] for k in ['train_tasks','test_tasks']}}
    Path(args.out).mkdir(parents=True,exist_ok=True)
    (Path(args.out)/'r1-inputs.json').write_text(json.dumps(out,indent=2))
    print(json.dumps({'nodes':len(nodes),'models':models,'pools':pools,'jev_states':len(states),'devices':devices}))

def benchmark(function, nodes, repeats=30):
    times=[]
    predictions=[]
    for node in nodes:
        start=time.perf_counter_ns()
        pred=function(node)
        times.append((time.perf_counter_ns()-start)/1e9)
        predictions.append(pred)
    for _ in range(repeats-1):
        for node in nodes:
            start=time.perf_counter_ns();function(node);times.append((time.perf_counter_ns()-start)/1e9)
    return predictions,{'p50_s':pct(times,50),'p95_s':pct(times,95),'mean_s':statistics.mean(times),'calls':len(times)}

def evaluate(args):
    data,nodes,table,models,digest=read_data(args.corpus,args.matrix)
    inputs=json.loads((Path(args.out)/'r1-inputs.json').read_text())
    judgments=json.loads(Path(args.judgments).read_text())
    if inputs['corpus_sha256']!=digest or judgments['corpus_sha256']!=digest:
        raise ValueError('mismatched corpus')
    if hashlib.sha256((Path(args.out)/'r1-inputs.json').read_bytes()).hexdigest()!=judgments['inputs_sha256']:
        raise ValueError('teacher inputs changed after labeling')
    if not judgments['backend'].startswith('typesafe/'):
        raise ValueError('R1 requires observed native TypeSafe backend, no silent fallback')
    inline=json.loads(Path(args.inline).read_text()) if args.inline else None
    if inline is not None and (inline['corpus_sha256']!=digest or inline['inputs_sha256']!=judgments['inputs_sha256']):
        raise ValueError('inline routing inputs do not match frozen training profiles')
    train=[n for n in nodes.values() if n['split']=='train']
    test=[n for n in nodes.values() if n['split']=='test']
    profiles=inputs['profiles'];devices=inputs['device_profiles']
    output={'corpus_sha256':digest,'train_tasks':data['train_tasks'],'test_tasks':data['test_tasks'],
            'train_nodes':len(train),'test_nodes':len(test),'models':models,'results':[],
            'scope':'static frozen-node accuracy and strict all-node task proxy; not native GUI success',
            'device_profiles':devices,'device_profile_provenance':inputs['device_profile_provenance']}
    out=Path(args.out)
    for pool,candidates in inputs['pools'].items():
        fit_profiles=profile(nodes,table,candidates)
        def hand(node):
            f=context_key(node)
            return max(candidates,key=lambda m:rank(fit_profiles,f,m,devices.get(args.device,{}).get(m)))
        train_best=max(candidates,key=lambda m:rank(fit_profiles,'all',m))
        cheapest=min(candidates,key=lambda m:fit_profiles[m]['all']['latency_s'])
        vectorizer=DictVectorizer(sparse=False)
        xtrain=vectorizer.fit_transform([vector(n,candidates,profiles,devices,args.device) for n in train])
        yjev=[judgments['choices'][pool+':'+n['id']] for n in train]
        if any(y not in candidates for y in yjev):
            raise ValueError('Jev selected outside pool')
        tree=DecisionTreeClassifier(max_depth=4,min_samples_leaf=5,random_state=1729).fit(xtrain,yjev)
        mlp=make_pipeline(StandardScaler(),MLPClassifier(hidden_layer_sizes=(12,),max_iter=500,random_state=1729,solver='lbfgs',alpha=.1)).fit(xtrain,yjev)
        predict=lambda estimator,node: str(estimator.predict(vectorizer.transform([vector(node,candidates,profiles,devices,args.device)]))[0])
        # Parent-requested refinement: exact fastest-correct training labels,
        # with no-correct rows explicitly falling back to fastest (not called correct).
        fastest_labels=[max(candidates,key=lambda m:(table[m,n['id']]['correct'],-table[m,n['id']]['latency_s'])) for n in train]
        cost_tree=DecisionTreeClassifier(max_depth=4,min_samples_leaf=5,random_state=1729).fit(xtrain,fastest_labels)
        cost_mlp=make_pipeline(StandardScaler(),MLPClassifier(hidden_layer_sizes=(12,),max_iter=500,random_state=1729,solver='lbfgs',alpha=.1)).fit(xtrain,fastest_labels)
        (out/('fastest-correct-labels-'+pool+'.json')).write_text(json.dumps([
            {'node_id':n['id'],'selected':m,'any_correct':any(table[c,n['id']]['correct'] for c in candidates),
             'candidate_outcomes':{c:{'correct':table[c,n['id']]['correct'],'latency_s':table[c,n['id']]['latency_s']} for c in candidates}}
            for n,m in zip(train,fastest_labels)],indent=2))
        # Meta selection uses a nested task-group validation, never held-out outcomes.
        val_tasks=set(sorted(data['train_tasks'],key=lambda t:hashlib.sha256(('meta:'+t).encode()).hexdigest())[:5])
        mask=np.array([n['task'] not in val_tasks for n in train]);validation=[n for n in train if n['task'] in val_tasks]
        tsmall=DecisionTreeClassifier(max_depth=4,min_samples_leaf=5,random_state=1729).fit(xtrain[mask],np.array(yjev)[mask])
        msmall=make_pipeline(StandardScaler(),MLPClassifier(hidden_layer_sizes=(12,),max_iter=500,random_state=1729,solver='lbfgs',alpha=.1)).fit(xtrain[mask],np.array(yjev)[mask])
        score=lambda estimator: statistics.mean(10*table[predict(estimator,n),n['id']]['correct']-table[predict(estimator,n),n['id']]['latency_s'] for n in validation)
        meta_name='R2' if score(tsmall)>=score(msmall) else 'R3'
        meta=tree if meta_name=='R2' else mlp
        joblib.dump({'vectorizer':vectorizer,'tree':tree,'mlp':mlp,'cost_tree':cost_tree,'cost_mlp':cost_mlp,'profiles':profiles,'devices':devices,'candidates':candidates,'meta':meta_name,'training_device':args.device},out/('policy-'+pool+'.joblib'))
        (out/('tree-'+pool+'.txt')).write_text(export_text(tree,feature_names=list(vectorizer.get_feature_names_out())))
        policies={**{'always:'+m:(lambda n,m=m:m) for m in candidates},
                  'training-best':lambda n:train_best,'R0':hand,
                  'R2':lambda n:predict(tree,n),'R3':lambda n:predict(mlp,n),'R4':lambda n:predict(meta,n),
                  'oracle':lambda n:max(candidates,key=lambda m:(table[m,n['id']]['correct'],-table[m,n['id']]['latency_s']))}
        if inline is not None:
            policies['R1']=lambda n:inline['choices'][pool+':'+n['id']]
        policies['cost-tree']=lambda n:predict(cost_tree,n)
        policies['cost-MLP']=lambda n:predict(cost_mlp,n)
        # Prespecified reward penalties sweep quality versus measured time.
        # Test results are reported as a curve, not used to select a deployable arm.
        for penalty in [0,.1,.25,.5,1.,2.,5.,10.]:
            labels=[max(candidates,key=lambda m:penalty*table[m,n['id']]['correct']-table[m,n['id']]['latency_s']) for n in train]
            estimator=DecisionTreeClassifier(max_depth=4,min_samples_leaf=5,random_state=1729).fit(xtrain,labels)
            policies['cost-curve:'+str(penalty)]=lambda n,estimator=estimator:predict(estimator,n)
        for seed in range(30):
            rng=random.Random(1729+seed)
            sequence={n['id']:rng.choice(candidates) for n in test}
            policies['random:'+str(seed)]=lambda n,sequence=sequence:sequence[n['id']]
        # Calibration of cheap output-confidence proxy on training tasks only.
        bins=defaultdict(list)
        def output_bin(node):
            raw=table[cheapest,node['id']]['output']
            try: label=corpus.ACTIONS.parse_action(raw).name
            except ValueError: label='invalid'
            return corpus.family(node['request']),label
        for n in train:bins[output_bin(n)].append(table[cheapest,n['id']]['correct'])
        confidence=lambda n:statistics.mean(bins[output_bin(n)]) if bins[output_bin(n)] else 0.
        def cascade(n,threshold=.8):
            return cheapest if confidence(n)>=threshold else train_best
        # Threshold selected using training-set utility, never test labels.
        thresholds=[0,.5,.8,1.01]
        threshold=max(thresholds,key=lambda t:statistics.mean(10*table[cascade(n,t),n['id']]['correct']-table[cheapest,n['id']]['latency_s']-(table[train_best,n['id']]['latency_s'] if cascade(n,t)!=cheapest else 0) for n in train))
        policies['cascade']=lambda n:cascade(n,threshold)
        all_predictions={}
        for name,policy in policies.items():
            predictions,overhead=benchmark(policy,test,repeats=30 if name in {'R0','R2','R3','R4','cost-tree','cost-MLP'} else 1)
            if name=='R1':
                overhead=inline['overhead'][pool]
            if name=='oracle' or name.startswith(('always:','random:')) or name=='training-best':
                overhead={'p50_s':0.,'p95_s':0.,'mean_s':0.,'calls':len(test)}
            all_predictions[name]=predictions
            task_pass=defaultdict(list);task_latency=defaultdict(float);calls=0
            for n,m in zip(test,predictions):
                row=table[m,n['id']]
                task_pass[n['task']].append(row['correct'])
                task_latency[n['task']]+=row['latency_s']+overhead['mean_s']
                calls+=1
                if name=='cascade' and m!=cheapest:
                    task_latency[n['task']]+=table[cheapest,n['id']]['latency_s'];calls+=1
            passed=sum(all(v) for v in task_pass.values())
            output['results'].append({'pool':pool,'policy':name,'node_correct':sum(table[m,n['id']]['correct'] for n,m in zip(test,predictions)),
                 'nodes':len(test),'strict_replay_tasks_passed':passed,'tasks':len(task_pass),
                 'mean_total_latency_per_task_s':statistics.mean(task_latency.values()),
                 'total_latency_s':sum(task_latency.values()),'router_overhead':overhead,'model_calls':calls,
                 'mean_decisions_per_task':len(test)/len(task_pass),'choices':dict(Counter(predictions)),
                 'cascade_threshold':threshold if name=='cascade' else None,'meta_selected':meta_name if name=='R4' else None,
                 'local_api_dollars':0,
                 'task_passes':{k:all(v) for k,v in task_pass.items()},'task_latency_s':dict(task_latency)})
        # Share-matched permutation defeats gains from simply choosing a better global mixture.
        permuted=list(all_predictions['R0']);random.Random(1729).shuffle(permuted)
        proxy=sum(table[m,n['id']]['correct'] for n,m in zip(test,permuted))
        output.setdefault('share_matched_random',{})[pool]={'reference':'R0','node_correct':proxy,'nodes':len(test),'choices':dict(Counter(permuted))}
        # Paired task bootstrap of R2 minus strongest training-selected fixed model.
        keyed={r['policy']:r for r in output['results'] if r['pool']==pool}
        differences=[int(keyed['R2']['task_passes'][t])-int(keyed['training-best']['task_passes'][t]) for t in data['test_tasks']]
        rng=np.random.default_rng(1729)
        boot=[float(np.mean(rng.choice(differences,size=len(differences),replace=True))) for _ in range(2000)]
        output.setdefault('paired_bootstrap',{})[pool]={'comparison':'R2 - training-best strict replay task rate','difference':statistics.mean(differences),'ci95':[pct(boot,2.5),pct(boot,97.5)],'resamples':2000}
    (out/'results.json').write_text(json.dumps(output,indent=2,allow_nan=False))
    print(json.dumps({'results':str(out/'results.json'),'holdout_tasks':len(data['test_tasks']),'holdout_nodes':len(test),'rows':len(output['results'])}))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['prepare','evaluate'])
    p.add_argument('--corpus',default=str(ROOT/'data/corpus.json'))
    p.add_argument('--matrix',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--profile',action='append',default=[])
    p.add_argument('--pools',help='Manifest with explicit nested model-ID pools; membership is frozen independently of test outcomes')
    p.add_argument('--judgments')
    p.add_argument('--inline')
    p.add_argument('--device',default='groot',help='Device whose latency profile is active for this experiment')
    args=p.parse_args()
    (prepare if args.mode=='prepare' else evaluate)(args)

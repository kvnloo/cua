"""Counterfactual device-availability ablation over actually collected per-device rows.

Models/devices are separate candidates. Availability scenarios are explicit inputs,
not a claimed live fleet scheduler. Training and testing remain split by task.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
import corpus
import experiment


def run(args):
    raw=Path(args.corpus).read_bytes();frozen=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
    nodes={n['id']:n for n in frozen['nodes']}
    table={};sources={}
    for path in args.matrix:
        payload=Path(path).read_bytes();sources[str(path)]=hashlib.sha256(payload).hexdigest()
        for line in payload.splitlines():
            row=json.loads(line)
            if row['corpus_sha256']!=digest:raise ValueError('mixed corpus identities')
            if row['status']=='ok':
                row['correct']=corpus.correct(nodes[row['node_id']],row['output'])
                table[(row['model']+'@'+row['device'],row['node_id'])]=row
    pairs=sorted({p for p,n in table if all((p,k) in table for k in nodes)})
    devices=sorted({p.rsplit('@',1)[1] for p in pairs})
    if len(devices)<2:raise ValueError('availability ablation requires two measured devices')
    scenarios={d:[p for p in pairs if p.endswith('@'+d)] for d in devices}
    scenarios['all-free']=pairs
    train=[n for n in nodes.values() if n['split']=='train'];test=[n for n in nodes.values() if n['split']=='test']
    profiles={}
    for pair in pairs:
        groups={}
        for key in {experiment.context_key(n) for n in train}|{'all'}:
            subset=[n for n in train if key=='all' or experiment.context_key(n)==key]
            groups[key]={'accuracy':statistics.mean(table[pair,n['id']]['correct'] for n in subset),
                         'latency_s':statistics.median(table[pair,n['id']]['latency_s'] for n in subset),'n':len(subset)}
        profiles[pair]=groups
    def vector(node,available):
        values=corpus.features(node,len(available),device='availability-scenario')
        for device in devices:values['available:'+device]=int(any(p.endswith('@'+device) for p in available))
        for pair in pairs:
            p=profiles[pair].get(experiment.context_key(node),profiles[pair]['all'])
            values['train_quality:'+pair]=p['accuracy'];values['train_latency:'+pair]=p['latency_s']
        return values
    training=[(n,available) for available in scenarios.values() for n in train]
    vectorizer=DictVectorizer(sparse=False)
    x=vectorizer.fit_transform([vector(n,a) for n,a in training])
    y=[max(a,key=lambda p:(table[p,n['id']]['correct'],-table[p,n['id']]['latency_s'])) for n,a in training]
    tree=DecisionTreeClassifier(max_depth=4,min_samples_leaf=8,random_state=1729).fit(x,y)
    mlp=make_pipeline(StandardScaler(),MLPClassifier(hidden_layer_sizes=(12,),solver='lbfgs',max_iter=500,alpha=.1,random_state=1729)).fit(x,y)
    def masked(estimator,node,available):
        probabilities=estimator.predict_proba(vectorizer.transform([vector(node,available)]))[0]
        classes=estimator.classes_
        return str(max(((p,c) for p,c in zip(probabilities,classes) if c in available),key=lambda z:z[0])[1])
    results=[];choices={}
    for scenario,available in scenarios.items():
        fixed=max(available,key=lambda p:(profiles[p]['all']['accuracy'],-profiles[p]['all']['latency_s']))
        def hand(node):
            key=experiment.context_key(node)
            return max(available,key=lambda p:(profiles[p].get(key,profiles[p]['all'])['accuracy'],-profiles[p].get(key,profiles[p]['all'])['latency_s']))
        policies={'training-best-available':lambda n:fixed,'R0-device':hand,
                  'cost-tree-device':lambda n:masked(tree,n,available),
                  'cost-MLP-device':lambda n:masked(mlp,n,available),
                  'oracle':lambda n:max(available,key=lambda p:(table[p,n['id']]['correct'],-table[p,n['id']]['latency_s']))}
        for seed in range(30):
            rng=random.Random(1729+seed);sequence={n['id']:rng.choice(available) for n in test}
            policies['random:'+str(seed)]=lambda n,sequence=sequence:sequence[n['id']]
        for name,policy in policies.items():
            selected=[];overheads=[]
            for node in test:
                started=time.perf_counter();selected.append(policy(node));overheads.append(time.perf_counter()-started)
            if name=='oracle' or name=='training-best-available' or name.startswith('random:'):overheads=[0.]*len(test)
            task_correct=defaultdict(list)
            for n,p in zip(test,selected):task_correct[n['task']].append(table[p,n['id']]['correct'])
            choices[scenario,name]=selected
            results.append({'scenario':scenario,'policy':name,'available_candidates':available,
                            'correct':sum(table[p,n['id']]['correct'] for n,p in zip(test,selected)),'nodes':len(test),
                            'strict_replay_task_proxy':sum(all(v) for v in task_correct.values()),'tasks':len(task_correct),
                            'total_generation_plus_router_s':sum(table[p,n['id']]['latency_s'] for n,p in zip(test,selected))+sum(overheads),
                            'router_p50_s':experiment.pct(overheads,50),'router_p95_s':experiment.pct(overheads,95),
                            'choices':dict(Counter(selected))})
    switches={}
    if 'groot' in scenarios and 'mbp' in scenarios:
        for policy in ['R0-device','cost-tree-device','cost-MLP-device']:
            switches[policy]={'groot_free_vs_mbp_only_changed_selections':sum(a!=b for a,b in zip(choices['groot',policy],choices['mbp',policy])),
                              'all_free_vs_mbp_only_changed_selections':sum(a!=b for a,b in zip(choices['all-free',policy],choices['mbp',policy]))}
    result={'corpus_sha256':digest,'source_ledgers':sources,'scope':'static replay over actual device/model outcomes; availability scenarios are inputs, not live dispatch',
            'train_tasks':frozen['train_tasks'],'test_tasks':frozen['test_tasks'],'candidate_pairs':pairs,'profiles_training_only':profiles,
            'results':results,'availability_switches':switches,
            'limits':'No model-load, network dispatch, queueing or fleet-availability probe is simulated as measured time. Device/model configurations retain their actual precision/runtime identities in the source rows.'}
    Path(args.out).write_text(json.dumps(result,indent=2))
    print(json.dumps({'device_results':args.out,'pairs':pairs,'availability_switches':switches}))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--corpus',required=True)
    p.add_argument('--matrix',action='append',required=True)
    p.add_argument('--out',required=True)
    run(p.parse_args())

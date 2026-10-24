"""Explain small-model sufficiency and matched-latency frontiers without fitting on test labels."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.tree import DecisionTreeClassifier,export_text
from sklearn.metrics import accuracy_score,balanced_accuracy_score,roc_auc_score
import corpus
import experiment


def analyze(args):
    data,nodes,table,models,digest=experiment.read_data(args.corpus,args.matrix)
    train=[n for n in nodes.values() if n['split']=='train'];test=[n for n in nodes.values() if n['split']=='test']
    smallest='qwen25-05' if 'qwen25-05' in models else models[0]
    grouped={}
    for split,subset in [('train',train),('test',test)]:
        bins=defaultdict(list)
        for n in subset:
            f=corpus.features(n,len(models))
            for key in ['family','decision_type','option_count','dag_depth','prior_failures','last_action']:
                bins[key+'='+str(f[key])].append(bool(table[smallest,n['id']]['correct']))
            bins['observation_chars_bin='+str(int(f['observation_chars'])//200*200)].append(bool(table[smallest,n['id']]['correct']))
        grouped[split]={k:{'nodes':len(v),'small_correct':sum(v),'rate':statistics.mean(v)} for k,v in sorted(bins.items())}
    # Diagnostic learner receives only decision-time features, no empirical quality estimates.
    base=lambda n:{k:v for k,v in corpus.features(n,len(models)).items() if k not in {'device','pool_size','latency_budget_s'}}
    vectorizer=DictVectorizer(sparse=False)
    x=vectorizer.fit_transform([base(n) for n in train]);xt=vectorizer.transform([base(n) for n in test])
    y=np.array([int(table[smallest,n['id']]['correct']) for n in train]);yt=np.array([int(table[smallest,n['id']]['correct']) for n in test])
    tree=DecisionTreeClassifier(max_depth=3,min_samples_leaf=8,random_state=1729).fit(x,y)
    predictions=tree.predict(xt)
    diagnostic={'small_model':smallest,'accuracy':float(accuracy_score(yt,predictions)),
        'balanced_accuracy':float(balanced_accuracy_score(yt,predictions)),
        'always_training_majority_accuracy':float(np.mean(yt==int(np.mean(y)>=.5))),
        'feature_importance':{name:float(v) for name,v in zip(vectorizer.get_feature_names_out(),tree.feature_importances_) if v>0},
        'tree':export_text(tree,feature_names=list(vectorizer.get_feature_names_out())),
        'option_count_caveat':'All nodes expose the same ten action categories. Option count has zero variation; its predictive value cannot be tested here.'}
    if len(set(yt))==2 and len(tree.classes_)==2:
        diagnostic['auc']=float(roc_auc_score(yt,tree.predict_proba(xt)[:,1]))
    results=json.loads(Path(args.results).read_text())
    frontiers={}
    for pool in sorted({r['pool'] for r in results['results']}):
        rows=[r for r in results['results'] if r['pool']==pool and not r['policy'].startswith('random:')]
        points=[]
        for r in sorted(rows,key=lambda r:r['total_latency_s']):
            dominated=any(other['total_latency_s']<=r['total_latency_s'] and other['node_correct']>=r['node_correct']
                          and (other['total_latency_s']<r['total_latency_s'] or other['node_correct']>r['node_correct'])
                          for other in rows if other['policy']!='oracle')
            points.append({'policy':r['policy'],'node_accuracy':r['node_correct']/r['nodes'],
                           'mean_node_latency_s':r['total_latency_s']/r['nodes'],
                           'strict_replay_task_proxy':r['strict_replay_tasks_passed']/r['tasks'],
                           'nondominated_among_implementable_policies':not dominated if r['policy']!='oracle' else None})
        # At fixed baseline time budgets, compare best observed curve value to the baseline.
        # This is descriptive curve reporting, NOT post-hoc selection of a live policy.
        budgets=[]
        curve=[r for r in rows if r['policy'].startswith(('cost-curve:','cost-tree','cost-MLP','R'))]
        for fixed in (r for r in rows if r['policy'].startswith('always:')):
            affordable=[r for r in curve if r['total_latency_s']<=fixed['total_latency_s']]
            budgets.append({'fixed_baseline':fixed['policy'],'latency_budget_s':fixed['total_latency_s'],
                            'fixed_node_correct':fixed['node_correct'],
                            'curve_max_node_correct':max((r['node_correct'] for r in affordable),default=None),
                            'curve_policies_at_budget':[r['policy'] for r in affordable]})
        frontiers[pool]={'points':points,'matched_baseline_latency':budgets}
    result={'corpus_sha256':digest,'scope':'descriptive static held-out analysis; no native GUI claim',
            'small_model_sufficiency':diagnostic,'conditional_rates':grouped,'success_latency_frontiers':frontiers,
            'uncertainty':'Single generation pass/model/node; task bootstrap does not measure run-to-run latency variance. Correlated frozen states and repeated failure loops can make strict replay task proxy much harsher than native task success.'}
    Path(args.out).write_text(json.dumps(result,indent=2))
    print(json.dumps({'analysis':args.out,'small_model_sufficiency':diagnostic}))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--corpus',default=str(Path(__file__).with_name('data')/'corpus.json'))
    p.add_argument('--matrix',required=True)
    p.add_argument('--results',required=True)
    p.add_argument('--out',required=True)
    analyze(p.parse_args())

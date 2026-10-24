"""Load in OMP eval, then await label_training(judge_batch, inputs_path, output_path).

Uses the native TypeSafe judgment adapter; never reads/exports credentials. Training
nodes only. Batch throughput is NOT claimed to be inline per-request latency.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time

async def label_training(judge_batch, inputs_path, output_path, concurrency=8):
    inputs=json.loads(Path(inputs_path).read_text())
    states={}
    aliases={}
    for key,state in inputs['states'].items():
        canonical=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
        states.setdefault(canonical,state)
        aliases[key]=canonical
    grouped={}
    for key,state in states.items():
        grouped.setdefault(tuple(state['available_models']),{})[key]=state
    started=time.perf_counter()
    answers={}
    statuses=[]
    for candidates,subset in grouped.items():
        questions={'model':{'type':'choice',
            'instructions':'Choose exactly one AVAILABLE model BEFORE generating its action. Use only the provided TRAINING profiles, current decision context and measured device latencies. Maximize empirical current-context correctness first; for equal correctness choose the smallest measured active-device latency. Prefer current-context estimates when supported; overall estimates are fallback. This is an offline teacher; do not answer the GUI task.',
            'criteria':{m:f'Choose {m} if it has the highest training current-context action correctness; break correctness ties with lower active-device latency.' for m in candidates}}}
        batch=judge_batch(subset,questions,concurrency=concurrency,retries=0,min_ok=len(subset),intent='SLM router offline training labels')
        async for key,item in batch.drain_iter():
            if not item.ok or not item.model.startswith('typesafe/'):
                raise RuntimeError(f'Jev training label failed or fell back: {key}: {item.error}')
            choice=item.answers['model']['choice']
            if choice not in candidates:
                raise ValueError('teacher selected outside available pool')
            answers[key]={'choice':choice,'answers':item.answers,'backend':item.model}
        statuses.append(batch.status())
    elapsed=time.perf_counter()-started
    backends={a['backend'] for a in answers.values()}
    if len(answers)!=len(states) or len(backends)!=1:
        raise RuntimeError('incomplete or mixed-backend teacher result; no fallback accepted')
    status={'model':next(iter(backends)),'batches':statuses,'cost':sum(s['cost'] for s in statuses)}
    result={'corpus_sha256':inputs['corpus_sha256'],'inputs_sha256':hashlib.sha256(Path(inputs_path).read_bytes()).hexdigest(),
        'backend':status['model'],'unique_training_calls':len(states),'training_node_aliases':len(aliases),
        'choices':{key:answers[canonical]['choice'] for key,canonical in aliases.items()},
        'answers':answers,'status':status,'cost':status['cost'],
        'teacher_batch_elapsed_s':elapsed,'teacher_throughput_s_per_label':elapsed/len(states),
        'timing_caveat':'Concurrent offline teacher throughput, NOT live inline per-call latency; no held-out nodes labeled.'}
    Path(output_path).write_text(json.dumps(result,indent=2))
    return {k:result[k] for k in ['backend','unique_training_calls','training_node_aliases','cost','teacher_batch_elapsed_s','teacher_throughput_s_per_label']}

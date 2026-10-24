"""Native OMP eval adapter: await evaluate_inline(judge_batch, inputs, output).

Held-out ROUTING choices are evaluation only; never supplied to tree/MLP fitting.
A serial native batch proves backend identity and measures full choice-call time.
"""
import hashlib
import json
from pathlib import Path
import time

async def evaluate_inline(judge_batch,inputs_path,output_path):
    inputs=json.loads(Path(inputs_path).read_text())
    groups={}
    aliases={}
    for key,state in inputs['heldout_states'].items():
        available=tuple(state['available_models'])
        state={**state,'evaluation_node_id':key.split(':',1)[1]}
        canonical=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
        groups.setdefault(available,{})[canonical]=state
        aliases[key]=(available,canonical)
    answers={}
    runs=[]
    for available,states in groups.items():
        questions={'model':{'type':'choice',
            'instructions':'Choose exactly one AVAILABLE model before generating its GUI action. Maximize provided training current-context correctness; break quality ties with lower measured active-device latency. Current-context estimates are preferred; overall training estimates are fallback. Do not answer the task. No held-out outcomes are provided.',
            'criteria':{m:'Select this candidate if it has the highest training current-context correctness among available models, with lower active-device latency breaking ties.' for m in available}}}
        started=time.perf_counter()
        batch=judge_batch(states,questions,concurrency=1,retries=0,min_ok=len(states),intent='SLM router held-out serial R1 choices')
        async for key,item in batch.drain_iter():
            if not item.ok:raise RuntimeError('held-out native routing failed: '+str(item.error))
            if not item.model.startswith('typesafe/'):
                raise RuntimeError('non-TypeSafe fallback is not R1 evidence')
            choice=item.answers['model']['choice']
            if choice not in available:raise ValueError('selection outside model pool')
            answers[available,key]={'choice':choice,'answer':item.answers,'backend':item.model}
        elapsed=time.perf_counter()-started
        runs.append({'available':list(available),'unique_nodes':len(states),'client_serial_batch_wall_s':elapsed,
                     'native_worker_status':batch.status(),'mean_client_s_per_choice':elapsed/len(states)})
    choices={key:answers[alias]['choice'] for key,alias in aliases.items()}
    overhead={}
    for pool in inputs['pools']:
        available=tuple(inputs['pools'][pool])
        run=next(r for r in runs if tuple(r['available'])==available)
        overhead[pool]={'p50_s':None,'p95_s':None,'mean_s':run['mean_client_s_per_choice'],
                        'calls':run['unique_nodes'],
                        'timing_definition':'full sequential native batch client wall divided by decisions; includes adapter setup, not a per-call percentile'}
    result={'corpus_sha256':inputs['corpus_sha256'],'inputs_sha256':hashlib.sha256(Path(inputs_path).read_bytes()).hexdigest(),
            'scope':'actual held-out R1 choices against frozen outcomes; not live closed-loop GUI',
            'choices':choices,'answers':{'|'.join(available)+':'+key:value for (available,key),value in answers.items()},
            'runs':runs,'overhead':overhead,'backends':sorted({v['backend'] for v in answers.values()}),
            'cost':sum(r['native_worker_status']['cost'] for r in runs)}
    Path(output_path).write_text(json.dumps(result,indent=2))
    return {'choices':len(choices),'cost':result['cost'],'runs':runs}

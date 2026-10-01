"""Existing caller guard as a non-mutating prepare/commit contract probe.
No native speed result; no speculative mutation or additional authority store.
"""
import sys,pathlib,json,time
from dataclasses import replace
ROOT=pathlib.Path(__file__).resolve().parent;BASE=ROOT/'cua/libs/cua-driver/examples/jev-use';sys.path.insert(0,str(BASE/'python'))
from tasks import FixtureFormTask,fixture_sources
from guarded_completion import plan_guarded_completion,resolve_guarded_completion

def snap(value,refs):return fixture_sources({'target_id':'target','tab_id':'tab','refs':[{'role':'textbox','name':'verification value','ref':'p1:0','value':value}]+[{'role':'button','name':'Submit','ref':r} for r in refs]})
task=FixtureFormTask('proof');initial=snap('',['p1:1']);rows=[]
for case in ['cold','correct_prediction','wrong_prediction','invalidated_prediction','stale_preparation']:
 start=time.perf_counter_ns();p=plan_guarded_completion(task,initial,task.candidates(initial)[0],session='s1');prepare_ns=time.perf_counter_ns()-start
 assert p
 if case=='wrong_prediction':p=replace(p,completion_candidate_id='wrong-control')
 fresh=snap('proof',[] if case=='invalidated_prediction' else ['p2:1'])
 start=time.perf_counter_ns();r=resolve_guarded_completion(p,task,fresh,task.candidates(fresh),session='s2' if case=='stale_preparation' else 's1');commit_check_ns=time.perf_counter_ns()-start
 expected={'cold':'accepted','correct_prediction':'accepted','wrong_prediction':'candidate_not_unique','invalidated_prediction':'submit_not_unique','stale_preparation':'session_mismatch'}[case]
 actual=r.telemetry.get('reason',r.telemetry['status']);assert actual==expected
 rows.append({'case':case,'prepare_ns':prepare_ns,'fresh_commit_check_ns':commit_check_ns,'mutation_count':0,'telemetry':r.telemetry,'fresh_ref':r.candidate.arguments['ref'] if r.candidate else None,'latency_claim':'none: pure contract projection, no action overlap tested'})
(ROOT/'prepare-contract-results.json').write_text(json.dumps(rows,indent=2));print('5 existing-guard prepare/commit contracts passed; no mutation or native speed claim')

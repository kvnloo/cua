import sys,json,pathlib,subprocess,itertools
ROOT=pathlib.Path(__file__).resolve().parent;BASE=ROOT/'cua/libs/cua-driver/examples/jev-use';sys.path.insert(0,str(BASE/'python'))
from guarded_completion import plan_guarded_completion,resolve_guarded_completion
from tasks import FixtureFormTask,fixture_sources
cases=[]
for session,value,refs in itertools.product(['session-a','foreign',''],['proof','other',''],[['p2:1'],['p1:1'],[],['p2:1','p2:2']]):cases.append(dict(session=session,value=value,refs=refs))
def snapshot(value,refs):return {'target_id':'target','tab_id':'tab','refs':[{'role':'textbox','name':'verification value','ref':'p1:0','value':value}]+[{'role':'button','name':'Submit','ref':r} for r in refs]}
rows=[]
for c in cases:
 task=FixtureFormTask('proof');initial=fixture_sources(snapshot('',['p1:1']));plan=plan_guarded_completion(task,initial,task.candidates(initial)[0],session='session-a');fresh=fixture_sources(snapshot(c['value'],c['refs']));r=resolve_guarded_completion(plan,task,fresh,task.candidates(fresh),session=c['session']);rows.append({'telemetry':r.telemetry,'candidate_ref':r.candidate.arguments.get('ref') if r.candidate else None})
(ROOT/'parity-cases.json').write_text(json.dumps(cases));(ROOT/'parity-python.json').write_text(json.dumps(rows,indent=2))
subprocess.run(['node','--import',str(BASE/'node_modules/tsx/dist/loader.mjs'),str(ROOT/'run_parity.mts')],check=True)
other=json.loads((ROOT/'parity-typescript.json').read_text());assert rows==other
(ROOT/'parity-summary.json').write_text(json.dumps({'cases':len(cases),'exact_match':True,'scope':'shared same-input guard corpus; not native Driver'},indent=2));print('Exact Python/TypeScript telemetry/candidate parity:',len(cases))

import json,pathlib,re
R=pathlib.Path(__file__).resolve().parent
load=lambda p:json.loads((R/p).read_text())
p=load('provenance.json');assert re.fullmatch('[0-9a-f]{40}',p['tested_candidate_sha'])
r=load('p0-trials.json');assert len(r)==64
for mode,n in [('baseline',2),('guarded',1)]:
 rows=[x for x in r if x['mode']==mode];assert len(rows)==30 and all(x['verified'] and x['provider_calls']==n and x['actions']==2 and x['observations']==3 for x in rows)
control={x['mode']:x for x in r[60:]}
assert control['ambiguous']['steps'][1]['guarded_completion']['reason']=='submit_not_unique' and control['ambiguous']['provider_calls']==2
assert not control['no-effect']['verified'] and control['no-effect']['outcome']=='budget_exhausted'
assert load('parity-python.json')==load('parity-typescript.json');assert len(load('parity-python.json'))==36
assert len(load('event-wait-trials.json'))==48
assert len(load('prepare-contract-results.json'))==5
assert all(x['mutation_count']==0 for x in load('prepare-contract-results.json'))
n=load('native-trials.json');assert len(n['trials'])==12 and all(x['verified'] for x in n['trials'])
assert len(load('next-25-experiments.json')['experiments'])==25
assert 'BLOCKED' in load('capability-census.json')['browser_live_census_status']
assert 'simulated Driver' in (R/'README.md').read_text()
print('Evidence consistency checks passed; blocked/unexecuted stages remain explicit')

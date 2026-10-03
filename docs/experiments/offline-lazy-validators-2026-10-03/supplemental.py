"""Post-benchmark supplemental correctness; never modifies original timing."""
import json
from run import P, Session, SCHEMAS, CORPUS, outcome, mutants
rows=[]
for i,item in enumerate(CORPUS):
 for wrong in sorted(SCHEMAS):
  if wrong==item['tool']:continue
  # Fresh session each substitution exercises first use and repeated use.
  sessions={a:Session(a,SCHEMAS) for a in ['standard','eager','lazy']}
  for use in range(2):
   ref=outcome(lambda:sessions['standard'].check(wrong,item['structuredContent']))
   for arm in ['eager','lazy']:
    o=outcome(lambda:sessions[arm].check(wrong,item['structuredContent']))
    rows.append({'record':i,'tool':wrong,'use':use,'arm':arm,'reference':ref,'candidate':o,'agree':o['accept']==ref['accept']})
# Reject a reference-invalid mutant on first and repeated use of a fresh cache for each tool.
for tool in sorted(SCHEMAS):
 item=next(x for x in CORPUS if x['tool']==tool)
 ref=Session('standard',SCHEMAS)
 name,bad=next((n,v) for n,v in mutants(item['structuredContent'],SCHEMAS[tool]) if not outcome(lambda:ref.check(tool,v))['accept'])
 for arm in ['eager','lazy']:
  s=Session(arm,SCHEMAS)
  for use in range(2):
   o=outcome(lambda:s.check(tool,bad));rows.append({'case':'first_invalid_mutant','tool':tool,'mutation':name,'arm':arm,'use':use,'candidate':o,'agree':not o['accept']})
r={'scope':'post-benchmark first/repeated cross-tool and invalid-first-use supplement','total':len(rows),'disagreements':sum(not x['agree'] for x in rows),'rows':rows}
(P/'supplemental.json').write_text(json.dumps(r,indent=2));print({k:v for k,v in r.items() if k!='rows'});assert not r['disagreements']

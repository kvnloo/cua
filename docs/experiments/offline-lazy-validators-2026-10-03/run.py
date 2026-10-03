"""Offline prototype. Eager mechanism: Kevin Rajan N-02 / B-01 H_C.
No drivers, transport or user interface are invoked.
"""
import asyncio, copy, gc, hashlib, json, os, random, statistics, sys, time
from pathlib import Path
from jsonschema import validate
from jsonschema.validators import validator_for
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from mcp import ClientSession, types
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P/'inputs'))
from hc_equivalence import mutants
SCHEMAS=json.loads((P/'inputs/output-schemas.json').read_text())
CORPUS=[json.loads(x) for x in (P/'inputs/hc-corpus.jsonl').read_text().splitlines()]
ARMS=['standard','eager','lazy']
def key(s): return json.dumps(s,sort_keys=True,separators=(',',':'))
class Session:
    def __init__(self,arm,schemas,registry=None):
        self.arm=arm; self.schemas=copy.deepcopy(schemas)
        self.registry=registry if registry is not None else Registry()
        self.cache={};self.builds=0
        if arm=='eager':
            for s in self.schemas.values():
                if s is not None: self.compile(s)
    def compile(self,s):
        k=key(s)
        if k not in self.cache:
            cls=validator_for(s);cls.check_schema(s)
            self.cache[k]=cls(s,registry=self.registry);self.builds+=1
        return self.cache[k]
    def check(self,tool,value):
        s=self.schemas[tool]  # unknown tool fails closed, unlike MCP's refresh path
        if s is None: return
        if value is None: raise ValueError('missing structured content')
        if self.arm=='standard': validate(value,s,registry=self.registry)
        else:
            v=self.compile(s)
            err=best_match(v.iter_errors(value))
            if err is not None: raise err

def outcome(fn):
    try: fn();return {'accept':True,'error':None}
    except Exception as e:return {'accept':False,'error':type(e).__name__}
def correctness():
    sessions={a:Session(a,SCHEMAS) for a in ARMS};rows=[]
    for i,item in enumerate(CORPUS):
        tool,v=item['tool'],item['structuredContent']
        cases=[('recorded',v)]+mutants(v,SCHEMAS[tool])
        for name,x in cases:
            ref=outcome(lambda:sessions['standard'].check(tool,x))
            for arm in ['eager','lazy']:
                for use in range(2):
                    o=outcome(lambda:sessions[arm].check(tool,x))
                    rows.append({'record':i,'tool':tool,'case':name,'arm':arm,'use':use,'reference':ref,'candidate':o,'agree':ref['accept']==o['accept']})
        for wrong in sorted(SCHEMAS):
            if wrong==tool:continue
            ref=outcome(lambda:sessions['standard'].check(wrong,v))
            for arm in ['eager','lazy']:
                o=outcome(lambda:sessions[arm].check(wrong,v));rows.append({'record':i,'tool':wrong,'case':'cross_tool','arm':arm,'reference':ref,'candidate':o,'agree':ref['accept']==o['accept']})
    # Actual installed MCP implementation for every recorded result and each mutant.
    async def check_mcp():
        m=object.__new__(ClientSession);m._tool_output_schemas=copy.deepcopy(SCHEMAS)
        for i,item in enumerate(CORPUS):
            t,v=item['tool'],item['structuredContent']
            for name,x in [('recorded',v)]+mutants(v,SCHEMAS[t]):
                try: await ClientSession._validate_tool_result(m,t,types.CallToolResult(content=[],structuredContent=x));ok=True
                except Exception:ok=False
                ref=outcome(lambda:sessions['standard'].check(t,x))
                rows.append({'record':i,'tool':t,'case':name,'arm':'actual_mcp','agree':ok==ref['accept'],'accept':ok})
    asyncio.run(check_mcp())
    refschema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'https://offline.invalid/root','$defs':{'node':{'type':'object','properties':{'n':{'type':'integer'},'child':{'$ref':'#/$defs/node'}},'required':['n'],'additionalProperties':False}},'$ref':'#/$defs/node'}
    remote={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'https://offline.invalid/base/leaf','type':'integer','minimum':1}
    registry=Registry().with_resource(remote['$id'],Resource.from_contents(remote))
    external={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'https://offline.invalid/base/root','type':'object','properties':{'x':{'$ref':'leaf'}},'required':['x']}
    extras=[('local_ref_valid',refschema,{'n':1,'child':{'n':2}},True,None),('local_ref_invalid',refschema,{'n':1,'child':{'n':'bad'}},False,None),('relative_ref_valid',external,{'x':2},True,registry),('relative_ref_invalid',external,{'x':0},False,registry),('missing_ref',external,{'x':2},False,None),('invalid_schema',{'type':42},{},False,None),('refusal_branch',SCHEMAS['get_window_state'],{'refusal':'declined'},True,None)]
    v=copy.deepcopy(next(x['structuredContent'] for x in CORPUS if x['tool']=='get_window_state'))
    v['elements']=[{'element_index':0,'role':'button','depth':0,'frame':{'x':0,'y':0,'w':1,'h':'bad'}}]
    extras.append(('nested_frame_type',SCHEMAS['get_window_state'],v,False,None))
    for name,s,v,expected,r in extras:
        for arm in ARMS:
            holder={}
            for use in range(2):
                def f():
                    if 's' not in holder:holder['s']=Session(arm,{'t':s},r)
                    holder['s'].check('t',v)
                o=outcome(f);rows.append({'case':name,'arm':arm,'use':use,'outcome':o,'agree':o['accept']==expected})
    for arm in ARMS:
        orig={'t':{'type':'object','properties':{'x':{'type':'integer'}},'required':['x']}}
        old=Session(arm,orig);old.check('t',{'x':1});orig['t']['properties']['x']['type']='string';new=Session(arm,orig)
        assertions=[outcome(lambda:old.check('t',{'x':'bad'}))['accept']==False,outcome(lambda:new.check('t',{'x':'ok'}))['accept']==True]
        rows.append({'case':'schema_revision_snapshot','arm':arm,'agree':all(assertions)})
    report={'rows':rows,'total':len(rows),'disagreements':sum(not r['agree'] for r in rows),'record_count':len(CORPUS),'schema_count':len(SCHEMAS),'distinct_schemas':len({key(s) for s in SCHEMAS.values()})}
    (P/'correctness.json').write_text(json.dumps(report,indent=2));print({k:v for k,v in report.items() if k!='rows'},flush=True)
    assert not report['disagreements']

def timed(arm,sequence):
    gc.collect();w=time.perf_counter_ns();c=time.process_time_ns();sess=Session(arm,SCHEMAS);setup=(time.perf_counter_ns()-w)/1e6
    first=[]
    for item in sequence:
        t=time.perf_counter_ns();sess.check(item['tool'],item['structuredContent']);first.append((time.perf_counter_ns()-t)/1e6)
    return {'wall_ms':(time.perf_counter_ns()-w)/1e6,'cpu_ms':(time.process_time_ns()-c)/1e6,'setup_ms':setup,'calls_ms':first,'builds':sess.builds}
def bench():
    first=[x for x in CORPUS if x['trial']==CORPUS[0]['trial']];six=[x for x in CORPUS if x['trial']=='e01-005']
    workloads={'single_result':CORPUS[:1],'first_trial_5':first,'trial_6':six,'corpus_88':CORPUS,'ten_trials_50':first*10}
    rng=random.Random(20261003);rows=[];start={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'load':os.getloadavg()}
    for block in range(12):
        for name,seq in workloads.items():
            arms=ARMS.copy();rng.shuffle(arms)
            for arm in arms: rows.append({'block':block,'workload':name,'arm':arm,**timed(arm,seq)})
        for tool in sorted(SCHEMAS):
            item=next(x for x in CORPUS if x['tool']==tool);arms=ARMS.copy();rng.shuffle(arms)
            for arm in arms:rows.append({'block':block,'workload':'first_repeat:'+tool,'arm':arm,**timed(arm,[item,item])})
    summary={}
    for name in sorted({r['workload'] for r in rows}):
        summary[name]={}
        for arm in ARMS:
            rr=[r for r in rows if r['workload']==name and r['arm']==arm];d={}
            for metric in ['wall_ms','cpu_ms','setup_ms']:
                vals=sorted(r[metric] for r in rr);d[metric]={'p50':statistics.median(vals),'p95_nearest_rank':vals[-1],'min':vals[0],'max':vals[-1]}
            d['first_call_p50']=statistics.median(r['calls_ms'][0] for r in rr)
            if len(rr[0]['calls_ms'])>1:d['second_call_p50']=statistics.median(r['calls_ms'][1] for r in rr)
            d['builds']=rr[0]['builds'];summary[name][arm]=d
    decision='GO' if summary['first_trial_5']['lazy']['wall_ms']['p50']<=min(summary['first_trial_5'][a]['wall_ms']['p50'] for a in ['eager','standard']) and summary['ten_trials_50']['lazy']['wall_ms']['p50']<=1.1*summary['ten_trials_50']['eager']['wall_ms']['p50'] else 'MODIFY'
    result={'start':start,'end':{'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'load':os.getloadavg()},'verdict_offline_only':decision,'rows':rows,'summary':summary}
    (P/'timing.json').write_text(json.dumps(result,indent=2));print('verdict',decision)
    for name in workloads:print(name,{a:round(summary[name][a]['wall_ms']['p50'],3) for a in ARMS})
if __name__=='__main__':
    correctness()
    if '--correctness-only' not in sys.argv:bench()

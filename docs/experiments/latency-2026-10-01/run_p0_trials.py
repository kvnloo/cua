"""Independent instrumented run of the unmodified PR loop using a contract transport.
The actual HTTP fixture owns the outcome; transport is simulated, not native Driver.
"""
import argparse, asyncio, contextlib, hashlib, io, json, pathlib, resource, sys, time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.parse import urlencode
ROOT=pathlib.Path(__file__).resolve().parent
BASE=ROOT/'cua/libs/cua-driver/examples/jev-use'
sys.path[:0]=[str(BASE/'python'),str(BASE)]
import run
from verify_setup import fixture
from tasks import fixture_state

@asynccontextmanager
async def transport(_): yield None,None
class ContractTransport:
 def __init__(self,url,mode): self.url=url;self.mode=mode;self.value='';self.calls=[];self.generation=0
 async def __aenter__(self): return self
 async def __aexit__(self,*a): pass
 async def initialize(self): pass
 async def list_tools(self): return SimpleNamespace(tools=[])
 async def call_tool(self,name,args):
  safe={k:v for k,v in args.items() if k not in ('text','url')};self.calls.append({'tool':name,'args':safe})
  if name=='browser_prepare': data={'prepared_pid':1}
  elif name=='list_windows': data={'windows':[{'window_id':1,'is_on_screen':True,'bounds':{'width':100,'height':100}}]}
  elif name=='get_browser_state':
   self.generation+=1
   ref=f'p{self.generation}:1'
   if self.mode=='stale' and self.value:ref='p2:1'
   refs=[{'role':'textbox','name':'verification value','ref':f'p{self.generation}:0','value':self.value},{'role':'button','name':'Submit','ref':ref}]
   if self.mode=='ambiguous' and self.value:refs.append({'role':'button','name':'Submit','ref':f'p{self.generation}:2'})
   data={'target_id':'target','tab_id':'tab','tabs':[{'tab_id':'tab'}],'refs':refs}
  elif name=='browser_type': self.value=args['text'];data={}
  elif name=='browser_click':
   if self.mode=='no-effect': data={}
   else:
    with urlopen(Request(self.url+'submit',data=urlencode({'value':self.value}).encode()),timeout=2):pass
    data={}
  elif name=='browser_navigate':data={}
  else:raise AssertionError(name)
  return SimpleNamespace(isError=False,structuredContent=data)

async def trial(url,mode,index):
 token='local-fixture-value';session=ContractTransport(url,mode);log=ROOT/'raw'/f'{index:03d}-{mode}.jsonl'
 args=argparse.Namespace(token=token,fixture_url=url,max_steps=4,log=str(log),provider='mock',guarded_completion=mode!='baseline',visual_observation='off',dry_run=False)
 original_plan=run.plan_guarded_completion
 def plan(*a,**kw):
  p=original_plan(*a,**kw)
  if mode=='foreign' and p:
   from dataclasses import replace
   return replace(p,session='different-session')
  return p
 with patch.object(run,'stdio_client',transport),patch.object(run,'ClientSession',return_value=session),patch.object(run,'plan_guarded_completion',side_effect=plan),patch.object(run,'choose_mock_for_task',wraps=run.choose_mock_for_task) as choose,contextlib.redirect_stdout(io.StringIO()):
  cpu=time.process_time();start=time.perf_counter();result=await run.run(args);oracle=fixture_state(url);elapsed=(time.perf_counter()-start)*1000;cpu=(time.process_time()-cpu)*1000
 events=[json.loads(x) for x in log.read_text().splitlines()];steps=[x for x in events if x['event']=='step']
 for c in session.calls:
  if 'session' in c['args']:c['args']['session']='trial-local'
 record={'trial':index,'mode':mode,'evidence_level':'real runner + simulated Driver transport + real fixture HTTP oracle','verified':oracle.get('submitted')==token,'outcome':result,'time_to_verified_or_final_outcome_ms':elapsed,'cpu_ms':cpu,'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'provider_calls':choose.call_count,'observations':sum(c['tool']=='get_browser_state' for c in session.calls),'semantic_step_observations':len(steps),'screenshots':0,'visual_parses':0,'actions':sum(c['tool'] in ('browser_type','browser_click') for c in session.calls),'steps':steps,'tool_calls':session.calls,'oracle':{'submission_matches':oracle.get('submitted')==token},'manifest_sha256':hashlib.sha256((ROOT/'machine-manifest.json').read_bytes()).hexdigest()}
 if mode in ('baseline','guarded','foreign','stale'):assert record['verified'],record
 if mode=='baseline':assert choose.call_count==2
 if mode=='guarded':assert choose.call_count==1 and steps[1]['guarded_completion']['status']=='accepted'
 if mode in ('foreign','stale'):assert choose.call_count==2 and steps[1]['guarded_completion']['reason']=={'foreign':'session_mismatch','stale':'ref_reused'}[mode]
 if mode=='no-effect':assert not record['verified']
 return record

def main():
 (ROOT/'raw').mkdir(exist_ok=True);rows=[]
 with fixture() as url:
  for pair in range(30):
   modes=['baseline','guarded'] if pair%2==0 else ['guarded','baseline']
   for mode in modes:rows.append(asyncio.run(trial(url,mode,len(rows))))
  for mode in ['foreign','stale','ambiguous','no-effect']:rows.append(asyncio.run(trial(url,mode,len(rows))))
 (ROOT/'p0-trials.json').write_text(json.dumps(rows,indent=2));print('Trials passed',len(rows))
if __name__=='__main__':main()

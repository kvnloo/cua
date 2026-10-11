"""Fixture-only event wake A/B around the current run.py completion-poll seam.
Uses actual FixtureState and HTTP /state. Events wake fresh reads, never prove success.
No production Driver modification or generic verifier.
"""
import hashlib,json,pathlib,threading,time,statistics,math,sys
ROOT=pathlib.Path(__file__).resolve().parent
BASE=ROOT/'cua/libs/cua-driver/examples/jev-use'
sys.path[:0]=[str(BASE/'python'),str(BASE)]
from fixture_server import FixtureServer
from tasks import fixture_state,reset_fixture,classify
TOKEN='event-local-fixture';DEADLINE=.30
server=FixtureServer(('127.0.0.1',0));url=f'http://127.0.0.1:{server.server_address[1]}/'
threading.Thread(target=server.serve_forever,daemon=True).start()

def one(route,mode,n):
 reset_fixture(url);event=threading.Event();timeline={};reads=0;sleeps=0;wakes=0;spurious=0
 # Subscribe before dispatch; fixture owner publishes notification after state mutation.
 def dispatch():
  time.sleep(.015)
  if mode=='spurious':event.set();time.sleep(.025)
  if mode!='timeout':
   server.state.submit('wrong-value' if mode=='refuted' else TOKEN);timeline['target_committed_ns']=time.perf_counter_ns()
   if mode!='lost-event':timeline['event_ns']=time.perf_counter_ns();event.set()
 t=threading.Thread(target=dispatch);start=time.perf_counter_ns();cpu=time.process_time_ns();t.start();outcome='unknown';first_wake=None
 while True:
  reads+=1;outcome=classify(fixture_state(url)['submitted'],TOKEN,steps=0,max_steps=1)
  if outcome in ('verified','refuted'):break
  remaining=DEADLINE-(time.perf_counter_ns()-start)/1e9
  if remaining<=0:outcome='timeout';break
  if route=='poll':time.sleep(min(.1,remaining));sleeps+=1
  else:
   woke=event.wait(remaining)
   if woke:
    wakes+=1;event.clear();first_wake=first_wake or time.perf_counter_ns()
    if server.state.snapshot()['submitted'] is None:spurious+=1
   # Both wake and deadline trigger a fresh HTTP read; missing event never means fresh authority.
 end=time.perf_counter_ns();cpu_ms=(time.process_time_ns()-cpu)/1e6;t.join()
 expected={'normal':'verified','spurious':'verified','lost-event':'verified','timeout':'timeout','refuted':'refuted'}[mode]
 assert outcome==expected,(route,mode,outcome)
 return {'index':n,'route':route,'mode':mode,'outcome':outcome,'whole_task_ms':(end-start)/1e6,'cpu_ms':cpu_ms,'observations':reads,'poll_iterations':reads if route=='poll' else 0,'fixed_sleeps':sleeps,'wakes':wakes,'spurious_wakes':spurious,'action_to_event_ms':(timeline['event_ns']-start)/1e6 if 'event_ns' in timeline else None,'event_to_verified_or_final_ms':(end-timeline['event_ns'])/1e6 if 'event_ns' in timeline else None,'verified_after_missing_event':mode=='lost-event' and outcome=='verified','manifest_sha256':hashlib.sha256((ROOT/'machine-manifest.json').read_bytes()).hexdigest(),'evidence_level':'fixture-owned Python event + actual HTTP oracle; not CDP/AT-SPI event'}
rows=[]
try:
 for pair in range(20):
  for route in (['poll','event'] if pair%2==0 else ['event','poll']):rows.append(one(route,'normal',len(rows)))
 for mode in ['spurious','lost-event','timeout','refuted']:
  for route in ['poll','event']:rows.append(one(route,mode,len(rows)))
finally:server.shutdown();server.server_close()
(ROOT/'event-wait-trials.json').write_text(json.dumps(rows,indent=2))
summary={}
for route in ['poll','event']:
 rs=[r for r in rows if r['route']==route and r['mode']=='normal'];xs=sorted(r['whole_task_ms'] for r in rs)
 summary[route]={'n':len(rs),'p50_ms':statistics.median(xs),'p95_ms':xs[math.ceil(.95*len(xs))-1],'cpu_p50_ms':statistics.median(r['cpu_ms'] for r in rs),'observations':sorted(set(r['observations'] for r in rs)),'fixed_sleeps':sorted(set(r['fixed_sleeps'] for r in rs))}
(ROOT/'event-wait-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));print('all controls passed')

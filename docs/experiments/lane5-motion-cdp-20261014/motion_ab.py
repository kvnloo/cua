#!/usr/bin/env python3
"""Bounded real-Chromium CDP motion-policy experiment; NOT a CUA Driver E2E.

Pre-registered controls: 30 AB/BA matched pairs, isolated context/page per attempt,
fixed frame size, same click, independent page-owned mutation journal, no CUA model.
Arms differ only in Emulation.setEmulatedMedia prefers-reduced-motion setting.
Full attempts retained. No win claimed from statistical hints or missing outcomes.
"""
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

N=30
OUT=Path(__file__).resolve().parent
HTML='''<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:sans-serif;background:white;color:black;font-size:17px}
#decor{display:block;width:120px;height:45px;background:#154;animation:shuttle .28s linear infinite alternate}
@keyframes shuttle{0%{transform:translateX(0px)}100%{transform:translateX(170px)}}
@media (prefers-reduced-motion:reduce){#decor{animation:none!important;transform:translateX(0px)}}
#out{margin-top:12px}
</style></head><body><div id="decor"></div><button id="submit">Submit</button><span id="out">count=0</span>
<script>window.journal=[];document.querySelector('#submit').addEventListener('click',()=>{
window.journal.push({kind:'submitted',n:window.journal.length+1});
document.querySelector('#out').textContent='count='+window.journal.length;
});</script></body></html>'''


def med(a):return statistics.median(a)
def pct(a,p):
 a=sorted(a); q=(len(a)-1)*p/100; k=int(q); t=q-k
 return a[k]*(1-t)+a[min(k+1,len(a)-1)]*t

def main():
 rows=[];rng=random.Random(5015)
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
  for pair in range(N):
   order=['default','reduce'] if pair%2==0 else ['reduce','default']
   for arm in order:
    context=browser.new_context(viewport={'width':520,'height':260},device_scale_factor=1,color_scheme='light',reduced_motion='no-preference')
    page=context.new_page();page.goto('about:blank')
    page.set_content(HTML,wait_until='load')
    cdp=context.new_cdp_session(page)
    features=[{'name':'prefers-reduced-motion','value':'reduce'}] if arm=='reduce' else []
    cdp.send('Emulation.setEmulatedMedia',{'media':'','features':features})
    effective=page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches')
    assert effective == (arm=='reduce'),(arm,effective)
    assert page.locator('#submit').count()==1
    # Start on a stable clock after initial load; compare render churn without changing app state.
    page.wait_for_timeout(35)
    hashes=[]; screencap_ms=[]
    for i in range(5):
     begin=time.perf_counter_ns();png=page.screenshot(animations='allow',timeout=8000);screencap_ms.append((time.perf_counter_ns()-begin)/1e6)
     hashes.append(hashlib.sha256(png).hexdigest())
     if i<4:page.wait_for_timeout(33)
    visual_churn=sum(a!=b for a,b in zip(hashes,hashes[1:]))
    t0=time.perf_counter_ns()
    page.locator('#submit').click(timeout=8000)
    page.wait_for_function('window.journal.length === 1 && document.querySelector("#out").textContent === "count=1"',timeout=8000)
    action_to_oracle_ms=(time.perf_counter_ns()-t0)/1e6
    oracle=page.evaluate('({entries:window.journal.length,marker:document.querySelector("#out").textContent,animated:matchMedia("(prefers-reduced-motion: reduce)").matches})')
    result={ 'pair':pair,'arm':arm,'order':order,'status':'verified' if (oracle['entries']==1 and oracle['marker']=='count=1') else 'refuted', 'oracle':oracle,
      'screenshot_unique_hashes':len(set(hashes)),'visual_hash_changes':visual_churn,'screenshot_hashes':hashes,'screenshot_ms':screencap_ms,
      'action_to_oracle_ms':action_to_oracle_ms,'action_count':1,'fresh_oracle_reads':1,'backend':'Chromium CDP + Playwright (not CUA Driver)' }
    rows.append(result)
    cdp.detach();context.close()
  browser.close()
 chromium=subprocess.check_output(['/usr/bin/chromium','--version'],text=True).strip()
 assert len(rows)==2*N
 assert all(r['status']=='verified' and r['action_count']==1 for r in rows)
 default=[r for r in rows if r['arm']=='default']; reduce=[r for r in rows if r['arm']=='reduce']
 pairs={i:{r['arm']:r for r in rows if r['pair']==i} for i in range(N)}
 delta=[pairs[i]['reduce']['action_to_oracle_ms']-pairs[i]['default']['action_to_oracle_ms'] for i in range(N)]
 # Seeded pair bootstrap, descriptive 95% percentile interval of paired median.
 boot=random.Random(50152026)
 samples=[med([delta[boot.randrange(N)] for _ in range(N)]) for _ in range(4000)]
 summary={'status':'VERIFIED_CDP_PREFLIGHT_ONLY','n_pairs':N,'n_attempts':len(rows), 'source_candidate':'kvnloo/cua#110@7694da458342198dbce7f97eaa623450dcb022eb', 'chromium':chromium,'python':platform.python_version(),
 'collected_at_utc':datetime.now(timezone.utc).isoformat(), 'browser':'isolated local headless Chromium','independent_oracle':'page-owned journal length exactly 1 and DOM count=1',
 'paired_order':'AB/BA alternating','controls':{'exactly_one_mutation':True,'same_page_html':True,'same_action':True,'same_viewport':True,'policy_changed_only':True,'real_CUA_Driver_used':False},
 'verified':{'default':sum(r['status']=='verified' for r in default),'reduce':sum(r['status']=='verified' for r in reduce)},
 'median_screenshot_hash_changes':{'default':med([r['visual_hash_changes'] for r in default]),'reduce':med([r['visual_hash_changes'] for r in reduce])},
 'median_screenshot_duration_ms':{'default':med([med(r['screenshot_ms']) for r in default]),'reduce':med([med(r['screenshot_ms']) for r in reduce])},
 'action_to_oracle_p50_ms':{'default':med([r['action_to_oracle_ms'] for r in default]),'reduce':med([r['action_to_oracle_ms'] for r in reduce])},
 'action_to_oracle_p95_ms':{'default':pct([r['action_to_oracle_ms'] for r in default],95),'reduce':pct([r['action_to_oracle_ms'] for r in reduce],95)},
 'paired_action_to_oracle_delta_reduce_minus_default_p50_ms':med(delta), 'paired_median_delta_bootstrap_95pct_ms':[pct(samples,2.5),pct(samples,97.5)],
 'limits':['No CUA Driver or MCP transport; not an upstream performance result','Playwright applies CDP directly; no CUA policy/permissions verified','Decorative animation fixture is designed to honor prefers-reduced-motion; general sites may not','Latency includes Playwright caller overhead; frame-hash churn is not wall-clock improvement','No assertions about production screenshots/model latency or native Wayland.']}
 (OUT/'motion_ab_trials.json').write_text(json.dumps(rows,indent=2)+'\n')
 (OUT/'motion_ab_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
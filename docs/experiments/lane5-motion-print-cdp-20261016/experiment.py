#!/usr/bin/env python3
"""Direct-CDP print-media experiment. NOT a CUA Driver test."""
import datetime
import json
import platform
from pathlib import Path
from playwright.sync_api import sync_playwright

N=24
HTML='''<!doctype html><meta charset="utf-8"><style>
#probe{width:123px;color:rgb(1,2,3)}
@media print {#probe{width:333px;color:rgb(4,5,6)}}
@media (prefers-reduced-motion: reduce) {#probe{height:17px}}
</style><div id="probe">media-print-oracle</div>'''
HERE=Path(__file__).resolve().parent
def oracle(page):
    return page.evaluate("""() => ({print:matchMedia('print').matches,screen:matchMedia('screen').matches,
      reduce:matchMedia('(prefers-reduced-motion: reduce)').matches,
      width:getComputedStyle(document.getElementById('probe')).width,
      height:getComputedStyle(document.getElementById('probe')).height})""")

def trial(browser,idx):
    context=browser.new_context()
    page=context.new_page();page.set_content(HTML)
    cdp=context.new_cdp_session(page)
    assert oracle(page)['print'] is False
    def send(v):cdp.send('Emulation.setEmulatedMedia',v)
    order=['A_exact','B_omit_media','C_carried_print']
    if idx%2:order.reverse()
    arms={}
    for arm in order:
        send({'media':'print','features':[]})
        preset=oracle(page)
        assert preset['print'] and preset['width']=='333px'
        if arm=='A_exact':
            payload={'media':'','features':[{'name':'prefers-reduced-motion','value':'reduce'}]}
        elif arm=='B_omit_media':
            payload={'features':[{'name':'prefers-reduced-motion','value':'reduce'}]}
        else:
            payload={'media':'print','features':[{'name':'prefers-reduced-motion','value':'reduce'}]}
        send(payload)
        action=oracle(page)
        send({'media':'','features':[]})
        reset=oracle(page)
        arms[arm]={'payload':payload,'preset':preset,'action':action,'reset':reset,
            'print_preserved':action['print'] and action['width']=='333px',
            'motion_reduced':action['reduce'],
            'reset_screen':not reset['print'] and reset['width']=='123px'}
    context.close()
    return {'trial':idx,'order':order,'arms':arms}

with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    version=browser.version
    trials=[trial(browser,i) for i in range(N)]
    browser.close()
summary={a:{k:sum(int(t['arms'][a][k]) for t in trials) for k in ['print_preserved','motion_reduced','reset_screen']} for a in ['A_exact','B_omit_media','C_carried_print']}
out={'meta':{'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_ref':'kvnloo/cua@25634766580fe4db2ecc333058cf199e9b4f4ea2',
    'source_path':'libs/cua-driver/rust/crates/cua-driver-core/src/browser/motion_policy.rs',
    'platform':platform.platform(),'python':platform.python_version(),
    'chromium_version':version,'transport':'direct Chromium CDP via Playwright (NOT CUA Driver)',
    'n_trials':N,'matched_order':'AB/BA alternating with independent context per paired trial',
    'latency':'NOT_MEASURED','effect_oracle':'independent matchMedia(print), computed CSS width and matchMedia(reduced-motion)'},
    'summary':summary,'trials':trials}
(HERE/'raw.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps(summary,indent=2))
assert summary['A_exact']['print_preserved']==0
assert summary['B_omit_media']['print_preserved']==0
assert summary['C_carried_print']['print_preserved']==N

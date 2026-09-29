#!/usr/bin/env python3
"""Exact-count deterministic accounting replay; NOT simulated Driver output.
Inputs are audited real c78/MCP receipts. Holding non-injected work fixed, project
additional provider/semantic costs. This is not an exact-runner hermetic replay.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
from audit import audit_directory


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    verified=audit_directory(a.run)
    assert verified['passed'] and verified['count']==12
    rows=[json.loads(p.read_text()) for p in a.run.glob('cells/*/receipt.json')]
    by_language={lang:[r for r in rows if r['language']==lang] for lang in ('python','typescript')}
    surfaces=[]
    for lang,selected in by_language.items():
        profiles={}
        for arm in ('baseline','guarded'):
            counts={(r['provider_entries'],sum(c['name']=='get_browser_state' and c['request']['semantic'] for c in r['mcp']),sum(c['name'] in ('browser_type','browser_click') for c in r['mcp'])) for r in selected if r['arm']==arm}
            assert len(counts)==1
            profiles[arm]=list(counts)[0]
        db,dg=profiles['baseline'],profiles['guarded']
        assert db[1]==dg[1], 'premise changed: do not impose zero observation coefficient'
        grid=[]
        for provider,observe in itertools.product((0,25,100,250,1000),(0,25,250,1000)):
            baseline=db[0]*provider+db[1]*observe; guarded=dg[0]*provider+dg[1]*observe
            grid.append({'provider_ms':provider,'semantic_ms':observe,'baseline_added_ms':baseline,'guarded_added_ms':guarded,'baseline_minus_guarded_added_ms':baseline-guarded})
        surfaces.append({'language':lang,'counts_provider_semantic_action':profiles,
                         'marginal_saved_counts':[b-g for b,g in zip(db,dg)],
                         'observation_dependent_boundary_falsified':True,'grid':grid})
    result={'kind':'deterministic-count-accounting-replay-NOT-driver-or-runner-output',
            'input_live_focus_qualified':False if (a.run.parent.parent/'SAFETY_HALT.json').exists() else None,
            'qualification_note':'Offline accounting of preserved traces only; no focus-isolation-qualified live result.',
            'source_sha':rows[0]['source_sha'],
            'inputs':{str(p.relative_to(a.run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(a.run.glob('cells/*/receipt.json'))},
            'held_fixed':'all non-injected source/driver/fixture/instrumentation/startup/cleanup work',
            'equation':'T_baseline-T_guarded = P - H + (R_baseline-R_guarded); coefficient(O)=0',
            'boundary':'P > H + R_guarded-R_baseline; H and stable residual difference not identifiable from small noisy wall-time samples',
            'surfaces':surfaces}
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'languages':len(surfaces),'grid_points_per_language':len(surfaces[0]['grid']),'marginal_saved_counts':[s['marginal_saved_counts'] for s in surfaces]}))

if __name__=='__main__':main()

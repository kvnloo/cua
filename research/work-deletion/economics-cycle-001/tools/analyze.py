#!/usr/bin/env python3
"""Offline analysis only. Every live receipt is focus-isolation-unqualified.
Do not interpret descriptive wall times as an accepted benchmark or speedup.
"""
import argparse
import collections
import hashlib
import json
import math
import statistics as st
import subprocess
from pathlib import Path
from audit import audit_directory


def stat(values):
    return {'n':len(values),'mean':st.mean(values),'median':st.median(values),'min':min(values),'max':max(values)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent);a=p.parse_args();root=a.root
    rows=[]; audits={}; bindings=[]
    for run in sorted((root/'runs').iterdir()):
        if not (run/'manifest.json').exists(): continue
        audit=audit_directory(run);audits[run.name]=audit
        assert audit['passed'] and audit['live_focus_qualified'] is False
        manifest=json.loads((run/'manifest.json').read_text())
        for name,digest in manifest['harness_hashes'].items():
            assert hashlib.sha256((run/'harness-source'/name).read_bytes()).hexdigest()==digest
        for path in sorted(run.glob('cells/*/receipt.json')):
            row=json.loads(path.read_text());row['run_id']=run.name;row['qualified_trial_key']=run.name+'/'+row['trial_id'];rows.append(row)
            bindings.append({'trial_key':row['qualified_trial_key'],'receipt_path':str(path.relative_to(root)),
                             'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'live_focus_qualified':False,
                             'path_checker_passed':True,'checker_negative_controls':row['checker_corruption_test']})
    assert len(rows)==30 and len({r['qualified_trial_key'] for r in rows})==30
    repeated=[r for r in rows if r['phase']=='repeat']
    assert len(repeated)==12
    results={}
    for lang in ('python','typescript'):
        selected=[r for r in repeated if r['language']==lang]
        pairs=[]
        for pair in sorted({r['pair_id'] for r in selected}):
            members={r['arm']:r for r in selected if r['pair_id']==pair};assert set(members)=={'baseline','guarded'}
            b,g=members['baseline'],members['guarded']
            pairs.append({'pair_id':pair,'baseline_minus_guarded_verified_ms':b['times']['verified_outcome_ms']-g['times']['verified_outcome_ms'],
                          'baseline_minus_guarded_lifetime_ms':b['times']['runner_lifetime_ms']-g['times']['runner_lifetime_ms'],
                          'first_arm':'baseline' if b['position']<g['position'] else 'guarded'})
        delta=[p['baseline_minus_guarded_verified_ms'] for p in pairs]
        mean=st.mean(delta);margin=4.302652729911275*st.stdev(delta)/math.sqrt(len(delta))
        arms={}
        for arm in ('baseline','guarded'):
            chosen=[r for r in selected if r['arm']==arm]
            summary={k:stat([r['times'][k] for r in chosen]) for k in ['verified_outcome_ms','runner_lifetime_ms','startup_to_first_semantic_ms','external_cleanup_ms','runner_post_verified_ms','critical_path_union_ms','residual_runner_ms']}
            by_span=collections.defaultdict(list)
            for r in chosen:
                totals=collections.defaultdict(float)
                for s in r['named_spans']: totals[s['name']]+=(s['end_ns']-s['start_ns'])/1e6
                for name,t in totals.items():by_span[name].append(t)
            summary['named_span_mean_ms']=dict(sorted(((name,st.mean(v)) for name,v in by_span.items()),key=lambda x:-x[1]))
            summary['counts']={
                'actual_provider_entries':sorted({r['provider_entries'] for r in chosen}),
                'mcp_total_calls':sorted({len(r['mcp']) for r in chosen}),
                'fresh_semantic_observations':sorted({sum(c['name']=='get_browser_state' and c['request']['semantic'] for c in r['mcp']) for r in chosen}),
                'binding_observations':sorted({sum(c['name']=='get_browser_state' and not c['request']['semantic'] for c in r['mcp']) for r in chosen}),
                'mcp_actions':sorted({sum(c['name'] in ('browser_click','browser_type','click') for c in r['mcp']) for r in chosen}),
                'mcp_wait_tools':sorted({sum(c['name'].startswith('wait') for c in r['mcp']) for r in chosen}),
                'window_readiness_polls':sorted({sum(c['name']=='list_windows' for c in r['mcp']) for r in chosen}),
                'runner_http_verification_reads':sorted({r['oracle']['http_runner_state_reads'] for r in chosen}),
            }
            arms[arm]=summary
        results[lang]={'paired_blocks':len(pairs),'pairs':pairs,'arms':arms,
                       'paired_verified_delta_ms':{**stat(delta),'student_t_95_ci':[mean-margin,mean+margin],'baseline_slower_pairs':sum(x>0 for x in delta)},
                       'uncertainty':'Descriptive n=3 Student-t interval, df=2; assumes independent approximately normal pair differences. Not a performance claim; no multiple-comparison adjustment; all live focus isolation unqualified.'}
    grid=[]
    for pair in sorted({r['pair_id'] for r in rows if r['phase']=='grid'}):
        m={r['arm']:r for r in rows if r['pair_id']==pair and r['phase']=='grid'};b,g=m['baseline'],m['guarded']
        grid.append({'pair_id':pair,'language':b['language'],'provider_ms':b['provider_ms'],'semantic_ms':b['observe_ms'],
                     'baseline_verified_ms':b['times']['verified_outcome_ms'],'guarded_verified_ms':g['times']['verified_outcome_ms'],
                     'delta_ms':b['times']['verified_outcome_ms']-g['times']['verified_outcome_ms'],
                     'predicted_added_cost_delta_ms':(b['provider_entries']-g['provider_entries'])*b['provider_ms'],
                     'baseline_startup_ms':b['times']['startup_to_first_semantic_ms'],'guarded_startup_ms':g['times']['startup_to_first_semantic_ms']})
    report={'qualification':'ALL LIVE RESULTS FOCUS-ISOLATION-UNQUALIFIED. GUI work halted by user steering.',
            'total_receipts':len(rows),'scientific_cells':len({r['scientific_cell'] for r in rows}),
            'trial_key_contract':'run_id/trial_id; trial_id is local to an immutable run directory; scientific_cell excludes block/trial number',
            'source_sha':rows[0]['source_sha'],'source_runner_worktree':'/mnt/zer0models/github/cua-lanes/c4316',
            'provider_scope':'Exact original deterministic mock chooser, recipe-local entry counters; no paid/network model calls measured.',
            'model_deletion':'One chooser invocation removed on accepted guard; fallback removes zero.',
            'observation_deletion':'Zero: both arms execute two fresh semantic observations plus one browser binding observation.',
            'batching':'Zero: both arms dispatch separate browser_type and browser_click calls.',
            'surface':'T_baseline-T_guarded = P-H+(R_baseline-R_guarded). Added semantic latency coefficient is zero.',
            'boundary_identifiability':'Only the unit coefficient on incremental provider delay and zero observation coefficient are identified from counts. H (incremental proof/planning overhead) and a stable wall-time residual are not isolated; no empirical universal P threshold, no observation-dependent boundary.',
            'limitations':['All live cells used Xvfb; env isolation did not prove actual input backend and user reported physical mouse movement.',
                           'Stop gate blocks live launch until parent provides verified headless Sway; no owned marked live PIDs remained at stop.',
                           'All cells are traced; MCP projection/provider-entry journaling adds overhead.',
                           'First pilot Python stdout was buffered; not included in repeated-trial summaries. Later cells use PYTHONUNBUFFERED.',
                           'HTTP observer polls every 10 ms; first verified receipt includes polling/scheduling delay. Mutation time separately recorded.',
                           'Named span union excludes overlapped time; residual includes interpreter/setup gaps, local candidate/proof work, serialization and uninstrumented client HTTP time.',
                           'Browser startup is browser_prepare RPC plus window readiness/binding, not an internal Chromium launch timeline.',
                           'No exact-runner hermetic timing replay was constructed. Deterministic surface is explicitly count-accounting replay, not Driver output.',
                           'Same-author source-independent checker is not independent-person certification.'],
            'repeated_trials':results,'latency_confirmations_unqualified':grid,'receipt_bindings':bindings}
    (root/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    (root/'source-independent-audit.json').write_text(json.dumps({'qualification':report['qualification'],'all_path_checks_passed':all(x['passed'] for x in audits.values()),'total':len(rows),'runs':audits},indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['qualification','total_receipts','scientific_cells']},indent=2))
    for lang,r in results.items():
        print(json.dumps({'language':lang,'delta':r['paired_verified_delta_ms'],'span_means_guarded':r['arms']['guarded']['named_span_mean_ms'],'guarded_times':{k:v['mean'] for k,v in r['arms']['guarded'].items() if isinstance(v,dict) and 'mean' in v}},indent=2))
    print(json.dumps(grid,indent=2))

if __name__=='__main__':main()

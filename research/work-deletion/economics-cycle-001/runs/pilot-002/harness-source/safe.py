"""Positive allowlist at the persistence boundary; unknown content is discarded."""
import math
import re

REF = re.compile(r'p[0-9]+:[0-9]+\Z')
SESSION = re.compile(r'jev-(?:python|typescript)-[a-f0-9]{8}\Z')
TARGET = re.compile(r'(?:bt|tab)-[a-f0-9-]{36}\Z')
TOOLS = {'browser_prepare','list_windows','get_browser_state','browser_navigate','browser_type','browser_click','click','get_window_state','parse_visual_regions','wait','wait_for_element','end_session'}
ENUMS = {
    'event': {'step','outcome'},
    'outcome': {'verified','refuted','unknown','abstained','budget_exhausted'},
    'decision_route': {'provider','guarded-completion'},
    'candidate': {'type-verification-value','submit-form','submit-form-foreground','reobserve','abstain'},
    'tool': TOOLS,
    'phase': {'action','provider'},
    'delivery_mode': {'background','foreground'},
}
TIMINGS = {'semantic_observe_ms','visual_observe_ms','candidate_build_ms','provider_decision_ms','decision_ms','action_ms','total_step_ms'}
REASONS = {'session_mismatch','task_mismatch','page_missing','field_not_proven','submit_not_unique','ref_reused','candidate_not_unique','candidate_mismatch'}


def opaque(value, regex):
    return value if isinstance(value,str) and regex.fullmatch(value) else None


def event(raw):
    out = {}
    for key, allowed in ENUMS.items():
        value = raw.get(key)
        if isinstance(value,str) and value in allowed: out[key] = value
    for key in TIMINGS | {'step'}:
        value = raw.get(key)
        if type(value) in (int,float) and math.isfinite(value) and value >= 0: out[key] = value
    if type(raw.get('dry_run')) is bool: out['dry_run'] = raw['dry_run']
    if 'confidence' in raw: out['model_score_present'] = raw['confidence'] is not None
    gc=raw.get('guarded_completion')
    if isinstance(gc,dict):
        proof={}
        if gc.get('status') in ('accepted','declined'): proof['status']=gc['status']
        if gc.get('reason') in REASONS: proof['reason']=gc['reason']
        for key in ('prior_ref','fresh_ref'):
            if opaque(gc.get(key),REF): proof[key]=gc[key]
        if opaque(gc.get('session'),SESSION): proof['session']=gc['session']
        if type(gc.get('submit_matches')) is int: proof['submit_matches']=gc['submit_matches']
        if gc.get('verification_field')=='contains_required_token': proof['verification_field']='contains_required_token'
        out['guarded_completion']=proof
    visual=raw.get('visual')
    if isinstance(visual,dict) and visual.get('status') in ('ok','not_installed','error','unavailable','skipped'):
        out['visual_status']=visual['status']
    if raw.get('action_error'): out['action_error_present']=True
    return out


def request(raw):
    out={'semantic':raw.get('snapshot_format')=='semantic_v2'}
    for key, regex in [('ref',REF),('session',SESSION),('target_id',TARGET),('tab_id',TARGET)]:
        value=opaque(raw.get(key),regex)
        if value: out[key]=value
    if 'text' in raw: out['text_present']=True
    if raw.get('profile',{}).get('mode')=='isolated_new': out['isolated_new']=True
    return out


def result(message, name, last_typed):
    raw=message.get('result') or {}; data=raw.get('structuredContent') or {}
    out={'error':bool(message.get('error') or raw.get('isError') or data.get('refusal') or data.get('status')=='refused' or data.get('effect')=='refused')}
    if name=='get_browser_state':
        refs=data.get('refs') or []
        buttons=[r for r in refs if r.get('role')=='button' and r.get('name')=='Submit']
        fields=[r for r in refs if r.get('role')=='textbox' and r.get('name')=='verification value']
        out.update(ref_count=len(refs), submit_refs=[r['ref'] for r in buttons if opaque(r.get('ref'),REF)],
                   field_count=len(fields),field_empty=bool(fields) and not fields[0].get('value'),
                   field_matches=bool(fields) and last_typed is not None and fields[0].get('value')==last_typed)
        for key in ('target_id','tab_id'):
            if opaque(data.get(key),TARGET): out[key]=data[key]
    if name=='list_windows': out['window_count']=len(data.get('windows') or [])
    if name=='browser_prepare': out['prepared_pid_present']=type(data.get('prepared_pid')) is int
    if name=='tools/list': out['tool_count']=len(raw.get('tools') or [])
    return out

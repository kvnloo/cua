"""Evidence-only invariant checks, not an imitation resolver."""
PIN = 'c78f50efed1ee7b289ab8947ec997904ea18fd72'

def proof_errors(proof):
    errors=[]
    if proof.get('status') == 'accepted':
        if proof.get('prior_ref') == proof.get('fresh_ref'): errors.append('fresh_ref_reused')
        if proof.get('submit_matches') != 1: errors.append('proof_not_unique')
        if proof.get('verification_field') != 'contains_required_token': errors.append('field_not_proven')
    return errors

def check(rows):
    errors = []
    seen=set()
    for row in rows:
        if row['trial_key'] in seen: errors.append('duplicate_trial_key')
        seen.add(row['trial_key'])
        if row.get('pin') != PIN: errors.append('pin_mismatch')
        if row.get('kind') == 'runner':
            t=row['transport'];o=row['oracle'];events=row['events']
            if not t['closed']: errors.append('no_driver_cleanup')
            if not t['token_absent']: errors.append('field_leak_reported')
            if not all(r['session_matches'] for r in t['requests']): errors.append('cross_session')
            if o['wrong_submissions']: errors.append('wrong_mutation')
            if t['outcome']=='verified' and not o['submitted_correct']: errors.append('verified_without_oracle')
            if not row['guarded'] and row['proof']: errors.append('default_off_guard')
            if (row['scenario']=='first-response-lost' and o['submit_count']) or (row['scenario']=='second-response-lost' and o['submit_count']!=1): errors.append('lost_response_retried')
            for event in events:
                proof=event.get('guarded_completion') or {}
                errors.extend(proof_errors(proof))
                if event.get('decision_route')=='guarded-completion':
                    if proof.get('status')!='accepted': errors.append('route_without_proof')
                    if event.get('confidence') is not None or event.get('probabilities') is not None: errors.append('guarded_model_scores')
                    if event.get('provider_decision_ms',0)!=0: errors.append('guarded_provider_work')
            continue
        if row.get('kind') != 'resolver': continue
        if row.get('branch') != row.get('expected_branch'): errors.append('unexpected_branch')
        proof = row.get('proof') or {}
        errors.extend(proof_errors(proof))
        if proof.get('status') == 'accepted':
            if not row.get('plan_produced'): errors.append('accepted_without_plan')
            candidate=row.get('candidate') or {}
            if candidate.get('ref') != proof.get('fresh_ref'): errors.append('proof_candidate_mismatch')
            if candidate.get('tool') != 'browser_click' or candidate.get('source') != 'page': errors.append('non_page_acceptance')
    return errors

if __name__ == '__main__':
    import json, sys
    from pathlib import Path
    rows=[json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines()]
    errors=check(rows)
    print(json.dumps({'receipt_count':len(rows),'errors':errors,'ok':not errors},sort_keys=True))
    raise SystemExit(1 if errors else 0)

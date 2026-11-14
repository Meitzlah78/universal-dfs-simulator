"""Offline shadow-capture contract. Never imported by production builds.

Receipts prove observation time, not source semantics or roster completeness.
Those need explicit verifier evidence. A saved capture is never backdated.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import uuid
import pandas as pd


def _time(value):
    t=pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return t


def cold_start_policy(prior):
    """No inferred zero, league-mean fill, or unvalidated contract-tier minute boost."""
    if prior and prior.get('supported') is True:
        m=prior.get('minutes')
        if isinstance(m,(float,int)) and math.isfinite(m) and 0<=m<=48:
            return {'status':'supported','minutes':float(m)}
    return {'status':'uncertified_pool','reason':'No validated point-in-time role prior'}


def assess_shadow(snapshot, *, actual_tipoff=None):
    """Input gate only. Bound infeasibility and forecast accuracy are later stages."""
    errors=[]
    capture=_time(snapshot['captured_at']); scheduled=_time(snapshot['scheduled_tipoff'])
    if capture>=scheduled:
        errors.append('capture_not_before_scheduled_tipoff')
    receipts={}
    for r in snapshot.get('receipts',[]):
        if not r.get('source') or not r.get('sha256') or len(r['sha256'])!=64:
            errors.append('invalid_source_receipt');continue
        if _time(r['observed_at'])>capture:
            errors.append('source_observed_after_capture');continue
        if r['source_id'] in receipts:
            errors.append('duplicate_source_receipt');continue
        receipts[r['source_id']]=r
    pool=snapshot.get('pool_evidence',{})
    if (pool.get('scope')!='full_team_game_roster' or pool.get('membership_verified') is not True
        or pool.get('eligibility_semantics_verified') is not True or not pool.get('verifier_reference')
        or pool.get('source_id') not in receipts or pool.get('game_id')!=snapshot['game_id']
        or pool.get('team')!=snapshot['team']):
        errors.append('uncertified_roster_scope_or_semantics')
    players=snapshot.get('players',[]);ids=[p.get('player_id') for p in players]
    if not players or None in ids or '' in ids or len(set(ids))!=len(ids):
        errors.append('incomplete_or_duplicate_player_identity')
    manifest=pool.get('member_player_ids',[])
    if len(manifest)!=len(set(manifest)) or set(manifest)!=set(ids):
        errors.append('roster_membership_manifest_mismatch')
    eligible=0;unknown_priors=0
    for p in players:
        if p.get('source_id') not in receipts or p.get('eligibility') not in {'eligible','ineligible'}:
            errors.append('unverified_player_status');continue
        if p['eligibility']=='ineligible':
            continue
        eligible+=1
        prior=p.get('role_prior',{})
        if cold_start_policy(prior)['status']!='supported':
            unknown_priors+=1;errors.append('unsupported_role_prior');continue
        if not prior.get('source') or not prior.get('as_of') or not prior.get('latest_training_completion'):
            errors.append('unverified_role_provenance');continue
        if _time(prior['as_of'])>capture or _time(prior['latest_training_completion'])>=capture:
            errors.append('role_evidence_after_capture')
    if eligible<5:
        errors.append('fewer_than_five_verified_eligible_players')
    inputs_verified=not errors
    if actual_tipoff is None:
        evaluation='pending_actual_tipoff'
    elif capture>=_time(actual_tipoff):
        evaluation='capture_not_before_actual_tipoff'
    else:
        evaluation='evaluable' if inputs_verified else 'input_blocked'
    return {'pregame_inputs_verified':inputs_verified,'evaluation_status':evaluation,
            'eligible_n':eligible,'unknown_prior_n':unknown_priors,'errors':sorted(set(errors)),
            'allocation_conflict':None,'allocation_conflict_note':'Not an allocation test; run certified inputs through the frozen candidate separately'}


def write_shadow_capture(directory, snapshot, source_payloads):
    """Append-only local record with raw payload hashes; no live state writes.

    Caller supplies receipt observation times from its actual fetch boundary.
    Recording bytes does not certify an unsupported source or complete a roster.
    This hook is inert until explicitly called by an approved collector.
    """
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    record=json.loads(json.dumps(snapshot,allow_nan=False))
    now=datetime.now(timezone.utc).isoformat()
    # A caller cannot stamp an old capture time onto a newly created record.
    record['captured_at']=now
    record['schema_version']=1;record['mode']='shadow';record['capture_id']=uuid.uuid4().hex
    record['experimental_outputs_only']=True
    byid={r['source_id']:r for r in record.get('receipts',[])}
    if len(byid)!=len(record.get('receipts',[])) or set(byid)!=set(source_payloads):
        raise ValueError('Exactly one raw payload required per unique receipt')
    blobs={}
    for sid,payload in source_payloads.items():
        raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        digest=hashlib.sha256(raw).hexdigest();byid[sid]['sha256']=digest
        byid[sid]['raw_file']=digest+'.json';blobs[digest]=raw
    record['input_gate']=assess_shadow(record)
    # Validate everything before persisting; exclusive creation never overwrites.
    for digest,raw in blobs.items():
        path=root/(digest+'.json')
        try:
            with path.open('xb') as f:f.write(raw)
        except FileExistsError:
            if path.read_bytes()!=raw:raise ValueError('Raw receipt hash collision/corruption')
    path=root/(record['capture_id']+'.shadow.json')
    with path.open('x') as f:json.dump(record,f,indent=2,allow_nan=False)
    return path

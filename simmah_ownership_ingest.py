"""Offline, ID-only single-game ownership ingestion. No live imports.

Unknown role targets stay None; no normalization, name matching, role splitting,
feed fetching or solver execution occurs here. Probabilities are canonical.
"""
import csv
import hashlib
import io
import json
from datetime import datetime,timezone
import numpy as np


class OwnershipIngestionError(ValueError):pass


def _identifier(value,label):
    if not isinstance(value,str) or not value.strip() or value!=value.strip():
        raise OwnershipIngestionError(f'Nonempty exact string required: {label}')
    return value


def _utc(value,label,nullable=True):
    if value is None and nullable:return None
    if not isinstance(value,str):raise OwnershipIngestionError(f'UTC timestamp required: {label}')
    try:parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:raise OwnershipIngestionError(f'Invalid timestamp: {label}') from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds()!=0:raise OwnershipIngestionError(f'Explicit UTC required: {label}')
    return parsed


def _games(value):
    if not isinstance(value,list) or not value or any(not isinstance(v,str) or not v.strip() or v!=v.strip() for v in value) or len(set(value))!=len(value):
        raise OwnershipIngestionError('Unique explicit nonempty game IDs required')
    return sorted(value)


def _number(value,unit):
    if value is None or value=='':return None
    if isinstance(value,bool):raise OwnershipIngestionError('Boolean is not ownership')
    try:n=float(value)
    except (TypeError,ValueError) as exc:raise OwnershipIngestionError('Role ownership must be numeric or explicitly null/blank') from exc
    if not np.isfinite(n):raise OwnershipIngestionError('NaN/Infinity tokens rejected; use JSON null or a blank CSV cell for unknown')
    if not 0<=n<=(100 if unit=='percent' else 1):raise OwnershipIngestionError('Ownership outside declared unit bounds')
    return n/100 if unit=='percent' else n


TIMESTAMPS=('request_started_utc','request_completed_utc','last_successful_received_utc','provider_updated_utc','lock_time_utc')
META_KEYS={'site_id','slate_id','game_set_id','observed_game_set','source_url_or_id','feed_name','unit','request_status','target_kind','source_slate_key','matching_logic_version',*TIMESTAMPS}
ROW_KEYS={'site_id','slate_id','game_set_id','player_id','target_ownership_cpt','target_ownership_flex'}


def ingest_ownership(raw,format,metadata,slate,*,ingested_utc=None,tolerance=1e-6,expected_raw_sha256=None):
    """Return normalized records plus audit report, even for incomplete targets.

    Malformed records, ambiguous units, bad IDs, or mismatched slate/game sets
    raise. Legitimate unknowns and skewed totals are retained but not eligible
    for calibration. The complete site player list stays separate from candidate
    filters; zero point projections are not a support exclusion.
    """
    if not isinstance(raw,bytes):raise OwnershipIngestionError('Exact raw bytes required')
    raw_digest=hashlib.sha256(raw).hexdigest()
    if expected_raw_sha256 is not None and expected_raw_sha256!=raw_digest:raise OwnershipIngestionError('Raw checksum does not match expected SHA-256')
    if not np.isfinite(tolerance) or tolerance<=0:raise OwnershipIngestionError('Positive target tolerance required')
    if set(metadata)!=META_KEYS:raise OwnershipIngestionError(f'Metadata fields differ: missing={sorted(META_KEYS-set(metadata))}, unexpected={sorted(set(metadata)-META_KEYS)}')
    if metadata['site_id'] not in {'dk','fd'}:raise OwnershipIngestionError('site_id must be dk or fd')
    for key in ('site_id','slate_id','game_set_id','source_url_or_id','feed_name','source_slate_key','matching_logic_version'):_identifier(metadata[key],key)
    for key in ('site_id','slate_id','game_set_id'):
        if metadata[key]!=slate[key]:raise OwnershipIngestionError(f'Slate identity mismatch: {key}')
    if _games(metadata['observed_game_set'])!=_games(slate['expected_game_set']):raise OwnershipIngestionError('Feed game set does not exactly match site slate')
    if metadata['unit'] not in {'percent','probability'}:raise OwnershipIngestionError('Explicit percent/probability unit required')
    if metadata['request_status'] not in {'success','error','unknown'}:raise OwnershipIngestionError('Invalid request_status')
    if metadata['target_kind'] not in {'projected','actual'}:raise OwnershipIngestionError('Explicit projected/actual classification required')
    times={key:_utc(metadata[key],key) for key in TIMESTAMPS}
    if times['request_started_utc'] and times['request_completed_utc'] and times['request_started_utc']>times['request_completed_utc']:raise OwnershipIngestionError('Request completion precedes start')
    if metadata['request_status']=='success' and times['last_successful_received_utc'] and times['request_completed_utc'] and times['last_successful_received_utc']>times['request_completed_utc']:raise OwnershipIngestionError('Retained data timestamp is after completed request')
    timestamp=ingested_utc or datetime.now(timezone.utc).isoformat()
    ingested=_utc(timestamp,'ingested_utc',nullable=False)
    ids=slate['player_ids']
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):raise OwnershipIngestionError('Unique ordered site player IDs required')
    for player in ids:_identifier(player,'site player_id')
    excluded=set(slate.get('candidate_excluded_ids',[]))
    if not excluded<=set(ids):raise OwnershipIngestionError('Candidate exclusion references an unknown site player')
    try:
        if format=='json':rows=json.loads(raw.decode('utf-8-sig'))
        elif format=='csv':
            reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
            if reader.fieldnames is None or len(reader.fieldnames)!=len(set(reader.fieldnames)) or set(reader.fieldnames)!=ROW_KEYS:raise OwnershipIngestionError('Canonical role CSV columns required; combined-only ownership is unsupported')
            rows=list(reader)
        else:raise OwnershipIngestionError('Format must be json or csv')
    except (UnicodeError,json.JSONDecodeError) as exc:raise OwnershipIngestionError('Invalid feed encoding/JSON') from exc
    if not isinstance(rows,list):raise OwnershipIngestionError('JSON feed must be a record array')
    byid={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!=ROW_KEYS:raise OwnershipIngestionError('Canonical separate role-target fields required; combined-only ownership is unsupported')
        for key in ('site_id','slate_id','game_set_id'):
            if row[key]!=metadata[key]:raise OwnershipIngestionError(f'Cross-slate record: {key}')
        player=_identifier(row['player_id'],'feed player_id')
        if player not in ids:raise OwnershipIngestionError(f'Feed player absent from site slate: {player}')
        if player in byid:raise OwnershipIngestionError(f'Duplicate feed player: {player}')
        byid[player]=(_number(row['target_ownership_cpt'],metadata['unit']),_number(row['target_ownership_flex'],metadata['unit']))
    normalized=[];candidate_exceptions=[]
    for player in ids:
        special,flex=byid.get(player,(None,None))
        normalized.append({'player_id':player,'target_ownership_cpt':special,'target_ownership_flex':flex,'source_record_present':player in byid})
        if player in excluded and any(v is not None and v>0 for v in (special,flex)):
            candidate_exceptions.append({'player_id':player,'special_target':special,'flex_target':flex,'reason':'Excluded from candidates, retained in complete opponent support'})
    c=[r['target_ownership_cpt'] for r in normalized];f=[r['target_ownership_flex'] for r in normalized]
    unknown_c=sum(v is None for v in c);unknown_f=sum(v is None for v in f)
    sum_c=sum(v for v in c if v is not None);sum_f=sum(v for v in f if v is not None)
    errors=[]
    if sum_c>1+tolerance or (not unknown_c and abs(sum_c-1)>tolerance):errors.append('special_role_sum')
    if sum_f>5+tolerance or (not unknown_f and abs(sum_f-5)>tolerance):errors.append('flex_role_sum')
    for r in normalized:
        a,b=r['target_ownership_cpt'],r['target_ownership_flex']
        if a is not None and b is not None and a+b>1+tolerance:errors.append('role_exclusion:'+r['player_id'])
    received=times['last_successful_received_utc'];lock=times['lock_time_utc'];provider=times['provider_updated_utc']
    prelock='unknown' if received is None or lock is None else ('recorded_prelock' if received<lock else 'not_prelock')
    time_anomalies=[key for key in ('request_started_utc','request_completed_utc','last_successful_received_utc','provider_updated_utc') if times[key] is not None and times[key]>ingested]
    ready=not unknown_c and not unknown_f and not errors
    report={'calibration_ready':ready,'predictive_eligible':ready and metadata['target_kind']=='projected' and prelock=='recorded_prelock' and not time_anomalies,
        'unknown_special_count':unknown_c,'unknown_flex_count':unknown_f,'known_special_sum':sum_c,'known_flex_sum':sum_f,
        'special_sum_residual':None if unknown_c else sum_c-1,'flex_sum_residual':None if unknown_f else sum_f-5,
        'integrity_errors':errors,'future_timestamp_fields':time_anomalies,'candidate_exclusion_exceptions':candidate_exceptions,'prelock_evidence':prelock,
        'retrieval_age_minutes':None if received is None else (ingested-received).total_seconds()/60,
        'provider_data_age_minutes':None if provider is None else (ingested-provider).total_seconds()/60,
        'minutes_before_lock_at_receipt':None if received is None or lock is None else (lock-received).total_seconds()/60,
        'unit_conversion':{'from':metadata['unit'],'to':'probability','multiplier':.01 if metadata['unit']=='percent' else 1.},
        'target_tolerance':tolerance,'feasibility':'not_run','support_policy':'complete_site_list','source_authenticity':'caller-supplied provenance, not independently authenticated'}
    return {'schema_version':'1.0','artifact_type':'offline_ownership_ingestion','ingested_utc':timestamp,
        'identity':{key:metadata[key] for key in ('site_id','slate_id','game_set_id')},'metadata':dict(metadata),
        'raw_sha256':raw_digest,'canonical_unit':'probability','special_role':'CPT' if metadata['site_id']=='dk' else 'MVP',
        'player_ids':list(ids),'records':normalized,'report':report,'offline_only':True}


def require_calibratable(payload,*,predictive=True):
    """Block incomplete/skewed inputs before LP; never normalize or fill values."""
    report=payload['report']
    if not report['calibration_ready']:raise OwnershipIngestionError('Incomplete or inconsistent role targets; see ingestion report')
    if predictive and not report['predictive_eligible']:raise OwnershipIngestionError('Missing recorded prelock projected-feed evidence')
    return (np.asarray([r['target_ownership_cpt'] for r in payload['records']],float),
            np.asarray([r['target_ownership_flex'] for r in payload['records']],float))

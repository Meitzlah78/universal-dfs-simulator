"""Stable-ID, point-in-time adapter contract and experimental minutes allocator.

Only fixture sources are approved here. Real source semantics/full membership
still require a reviewed adapter; raw NBA/ESPN receipts are never auto-approved.
"""
from datetime import datetime
import math
import statistics

VERSION='stable-id-minutes-v1'
# This is trusted code/configuration, never a caller-supplied approval boolean.
PROFILES={
    'fixture://nba-roster/v1':{'kind':'team_game_roster_v1','provenance':'synthetic'},
    'fixture://nba-history/v1':{'kind':'regulation_history_v1','provenance':'synthetic'},
}


class Unsupported(ValueError):
    def __init__(self,code,**details):
        self.code=code;self.details=details;super().__init__(code)


def stamp(value):
    try:
        if not isinstance(value,str):raise ValueError()
        t=datetime.fromisoformat(value.replace('Z','+00:00'))
        if t.tzinfo is None:raise ValueError()
        return t
    except (ValueError,TypeError):raise Unsupported('INVALID_OR_NAIVE_TIMESTAMP')


def stable(value,kind):
    if not isinstance(value,str) or not value.isascii() or not value.isdigit() or (kind in {'game','team'} and len(value)!=10):
        raise Unsupported('INVALID_STABLE_ID',kind=kind)
    return value


def finite(value):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        raise Unsupported('INVALID_NUMERIC_EVIDENCE')
    return float(value)


def evidence(receipt,payload,kind,capture):
    if not isinstance(payload,dict):raise Unsupported('MALFORMED_ADAPTER_INPUT')
    profile=PROFILES.get(receipt.get('source'))
    if not profile or profile['kind']!=kind:
        raise Unsupported('UNAPPROVED_SOURCE_PROFILE')
    if not stamp(receipt['observed_at'])<capture:
        raise Unsupported('SOURCE_NOT_OBSERVED_BEFORE_CAPTURE')
    if payload.get('kind')!=kind or payload.get('id_namespace')!='nba':
        raise Unsupported('SOURCE_CONTRACT_OR_NAMESPACE_MISMATCH')
    return profile


def roster_adapter(payload,receipt,request,capture):
    profile=evidence(receipt,payload,'team_game_roster_v1',capture)
    gid=stable(request['game_id'],'game');tid=stable(request['team_id'],'team')
    if payload.get('game_id')!=gid or payload.get('team_id')!=tid:
        raise Unsupported('GAME_OR_TEAM_ID_MISMATCH')
    if not capture<stamp(payload['scheduled_tipoff']):
        raise Unsupported('CAPTURE_NOT_BEFORE_SCHEDULED_TIPOFF')
    if payload.get('complete_roster') is not True:
        raise Unsupported('INCOMPLETE_ROSTER_MEMBERSHIP')
    members=payload.get('member_player_ids',[]);players=payload.get('players',[])
    if not isinstance(members,list) or not isinstance(players,list) or any(not isinstance(p,dict) for p in players):
        raise Unsupported('MALFORMED_ADAPTER_INPUT')
    for pid in members:stable(pid,'person')
    if not members or len(set(members))!=len(members):raise Unsupported('INVALID_ROSTER_MANIFEST')
    ids=[stable(p.get('player_id'),'person') for p in players]
    if len(set(ids))!=len(ids) or set(ids)!=set(members):
        raise Unsupported('ROSTER_MANIFEST_MISMATCH')
    for p in players:
        if p.get('team_id')!=tid or p.get('game_id')!=gid:raise Unsupported('PLAYER_TEAM_OR_GAME_MISMATCH')
        if not stamp(p['status_observed_at'])<=stamp(receipt['observed_at'])<capture:
            raise Unsupported('STATUS_NOT_OBSERVED_BEFORE_CAPTURE',player_id=p['player_id'])
        if p.get('eligibility') not in {'eligible','ineligible'}:
            raise Unsupported('UNRESOLVED_ELIGIBILITY',player_id=p['player_id'])
        if p['eligibility']=='eligible':
            if p.get('role_context') not in {'normal','injury_promoted'}:
                raise Unsupported('UNRESOLVED_ROLE_CONTEXT',player_id=p['player_id'])
            if not stamp(p['role_context_observed_at'])<=stamp(receipt['observed_at'])<capture:
                raise Unsupported('ROLE_CONTEXT_NOT_OBSERVED_BEFORE_CAPTURE',player_id=p['player_id'])
    return players,profile


def history_adapter(payload,receipt,capture,request,season):
    profile=evidence(receipt,payload,'regulation_history_v1',capture)
    rows=[];rejected={};seen=set()
    records=payload.get('records',[])
    if not isinstance(records,list) or any(not isinstance(r,dict) for r in records):
        raise Unsupported('MALFORMED_ADAPTER_INPUT')
    for raw in records:
        row=dict(raw);pid=stable(row.get('player_id'),'person');tid=stable(row.get('team_id'),'team');gid=stable(row.get('game_id'),'game')
        key=(gid,tid,pid)
        if key in seen:raise Unsupported('DUPLICATE_HISTORY_OBSERVATION')
        seen.add(key)
        def reject(reason):rejected[reason]=rejected.get(reason,0)+1
        end=stamp(row['game_end_time']);start=stamp(row['game_start_time'])
        if gid==request['game_id'] or not end<capture:
            reject('not_completed_before_capture');continue
        if end>stamp(receipt['observed_at']):
            reject('game_not_completed_at_source_observation');continue
        if not start<end:raise Unsupported('INVALID_HISTORICAL_GAME_TIMES')
        if row.get('season_type')!='regular' or row.get('season_id')!=season:
            reject('other_season_or_type');continue
        if row.get('regulation_only') is not True:
            reject('no_verified_regulation_minutes');continue
        if row.get('participation') not in {'played','confirmed_dnp'}:
            reject('unknown_participation');continue
        m=finite(row.get('minutes'))
        if not 0<=m<=48 or (row['participation']=='played' and m<=0) or (row['participation']=='confirmed_dnp' and m!=0):
            raise Unsupported('CONTRADICTORY_PARTICIPATION')
        if type(row.get('started')) is not bool:reject('unknown_start_flag');continue
        if row.get('role_context') not in {'normal','injury_promoted'}:
            reject('unknown_historical_role_context');continue
        if not stamp(row['role_context_observed_at'])<start:
            reject('historical_role_context_not_pregame');continue
        rows.append(row)
    return rows,rejected,profile


def _prior_rows(rows,pid,tid,before):
    # Same player + same team: a trade does not inherit an unverified new role.
    return sorted([r for r in rows if r['player_id']==pid and r['team_id']==tid and stamp(r['game_end_time'])<before],key=lambda r:stamp(r['game_end_time']))


def _role(own):
    if len(own)<3:return None
    return 'historical_starter' if sum(r['started'] for r in own[-5:])/len(own[-5:])>=.5 else 'historical_reserve'


def _examples(rows):
    result=[]
    for r in rows:
        own=_prior_rows(rows,r['player_id'],r['team_id'],stamp(r['game_start_time']))
        role=_role(own)
        if role:result.append(dict(r,role=role))
    return result


def quantile(values,q):
    v=sorted(values);index=(len(v)-1)*q;lo=math.floor(index);hi=math.ceil(index)
    return v[lo]+(v[hi]-v[lo])*(index-lo)


def role_and_bounds(players,rows,capture):
    examples=_examples(rows);forecasts=[]
    for p in players:
        if p['eligibility']=='ineligible':continue
        own=_prior_rows(rows,p['player_id'],p['team_id'],capture);role=_role(own)
        if role is None:raise Unsupported('COLD_START_ROLE_HISTORY',player_id=p['player_id'],history_n=len(own))
        group=[r for r in examples if r['role']==role and r['role_context']==p['role_context']]
        games={r['game_id'] for r in group}
        if len(group)<20 or len(games)<5:
            raise Unsupported('INSUFFICIENT_CONTEXT_TRAINING',player_id=p['player_id'],context=p['role_context'],samples=len(group),games=len(games))
        values=[finite(r['minutes']) for r in group];mu=statistics.mean(values)
        mass=[2**(-(capture-stamp(r['game_end_time'])).total_seconds()/86400/14) for r in own]
        total=sum(mass);raw=(sum(w*r['minutes'] for w,r in zip(mass,own))+3*mu)/(total+3)
        forecasts.append({'player_id':p['player_id'],'team_id':p['team_id'],'game_id':p['game_id'],
            'role':role,'role_context':p['role_context'],'role_prior_minutes':mu,
            'raw_minutes':raw,'history_weight':total/(total+3),'history_n':len(own),
            'lower':quantile(values,.05),'upper':quantile(values,.95),
            'uncertainty':max(1.,statistics.pstdev(values)),
            'training_n':len(group),'training_games':len(games),
            'latest_training_end':max(group,key=lambda r:stamp(r['game_end_time']))['game_end_time'],
            'latest_own_end':own[-1]['game_end_time']})
    return forecasts


def allocate(forecasts):
    low=sum(p['lower'] for p in forecasts);high=sum(p['upper'] for p in forecasts)
    if len(forecasts)<5 or low>240+1e-8 or high<240-1e-8:
        return None,{'target_minutes':240.,'eligible_n':len(forecasts),'lower_sum':low,'upper_sum':high,
            'upper_minute_deficit':max(0.,240-high),'lower_minute_excess':max(0.,low-240),
            'physical_minute_deficit':max(0.,240-48*len(forecasts)),
            'reason':'physical_or_learned_bounds_infeasible','bounds_relaxed':False}
    a=min((p['lower']-p['raw_minutes'])/p['uncertainty']**2 for p in forecasts)-1
    b=max((p['upper']-p['raw_minutes'])/p['uncertainty']**2 for p in forecasts)+1
    def project(x):return [min(p['upper'],max(p['lower'],p['raw_minutes']+x*p['uncertainty']**2)) for p in forecasts]
    for _ in range(100):
        mid=(a+b)/2
        if sum(project(mid))<240:a=mid
        else:b=mid
    values=project((a+b)/2)
    if abs(sum(values)-240)>1e-7:raise Unsupported('ALLOCATION_NUMERICAL_FAILURE')
    return [dict(p,predicted_minutes=v) for p,v in zip(forecasts,values)],None


def run_team(capture,request,receipts,payloads):
    """One team-game: input rejection precedes the two allocation terminal states."""
    base={'capture_id':capture['capture_id'],'adapter_version':VERSION,'id_namespace':'nba',
        'actual_tipoff_verified':False,'actuals_attached':False,'game_id':request.get('game_id'),
        'team_id':request.get('team_id'),'frozen_at':capture['frozen_at'],'predictions':None,
        'allocation_conflict':None,'production_modified':False,'qualified_for_evaluation':False}
    try:
        cutoff=stamp(capture['frozen_at'])
        roster_hash=request['roster_sha256'];history_hash=request['history_sha256']
        roster=payloads[roster_hash];history=payloads[history_hash]
        players,rprofile=roster_adapter(roster,receipts[roster_hash],request,cutoff)
        season=roster.get('season_id')
        if not isinstance(season,str) or not season:raise Unsupported('MISSING_SEASON_ID')
        rows,rejected,hprofile=history_adapter(history,receipts[history_hash],cutoff,request,season)
        forecasts=role_and_bounds(players,rows,cutoff)
        predictions,conflict=allocate(forecasts)
        provenance='synthetic' if 'synthetic' in {rprofile['provenance'],hprofile['provenance']} else 'observed'
        return dict(base,status='allocation_conflict' if conflict else 'forecasts',input_gate_passed=True,
            predictions=predictions,allocation_conflict=conflict,frozen_player_parameters=forecasts,history_rejections=rejected,
            eligible_player_ids=[p['player_id'] for p in players if p['eligibility']=='eligible'],
            ineligible_player_ids=[p['player_id'] for p in players if p['eligibility']=='ineligible'],
            provenance=provenance,
            qualification_blockers=(['synthetic_fixture'] if provenance=='synthetic' else [])+['actual_tipoff_and_actuals_not_reconciled'],
            source_hashes={'roster':roster_hash,'history':history_hash},
            scheduled_tipoff=roster['scheduled_tipoff'],season_id=season)
    except Unsupported as exc:
        return dict(base,status='uncertified_pool',reason=exc.code,details=exc.details)
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError):
        return dict(base,status='uncertified_pool',reason='MALFORMED_ADAPTER_INPUT',details={})

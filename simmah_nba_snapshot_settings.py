"""Offline initial-build configuration contract for the pinned NBA baseline.

No defaults are injected and the live pipeline does not import this module.
The emitted dictionary is JSON Schema 2020-12. The dependency-free validator
implements exactly its small vocabulary, plus payload alignment checks.
"""
from datetime import date
import math
import numpy as np

BASELINE='a3e1ec4ddb56d69fc4614eac4e36367cd21f4d06'

class SnapshotContractError(ValueError):pass


def obj(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def integer(minimum=0):return dict(type='integer',minimum=minimum)
def number(minimum=0,maximum=None):
    result=dict(type='number',minimum=minimum)
    if maximum is not None:result['maximum']=maximum
    return result

def const(value):return {'const':value}

FIXED={
 'candidate_search':dict(max_attempts=200000,batch_size=512,gumbel_multiplier=.15,correlation_cutoff=.05,correlation_multiplier=.5,fixed_slots={}),
 'opponent_search':dict(salary_min=0,correlation=0,excluded_indices=[],max_attempts=200000,batch_size=512,scenario_target_rule='max(1, target // 2)',ownership_target_rule='max(1, target - scenario_target)',proposal_rows=1024,popularity_floor=.1,proposal_gumbel_multiplier=2),
 'ownership_fit':dict(method='L-BFGS-B',max_iterations=100,regularization=1e-6,ftol=1e-12,gtol=1e-7,sum_tolerance_pp=.5),
 'fallback':dict(strength=.5,popularity_floor=.1,policy='relative_popularity_after_failed_fit'),
 'support_diagnostic':dict(method='highs',time_limit_seconds=5,feasibility_epsilon_pp=1e-6),
 'evaluation':dict(batch_size=128,histogram_max_span=65536,histogram_max_entries=2**53,field_weighting='integer_copies',payout_mode='marginal_candidate_exact_tie_split',top_one_percent_rule='max(1, ceil(contest_entries * .01))'),
 'selection':dict(metric='Top 1%',controls=None,stable_sort=True,canonical_dedup=True,strength_rule='diversity / 100',cap_rule='100 - 40 * strength',overlap_multiplier=.7,urgency_multiplier=2,repair_seconds=5,repair_relative_gap=.05,repair_cap_step=5,repair_start_rule='int(default_max)',repair_tiebreak=1e-10),
 'engine':dict(max_overtimes=10,require_markets=False,parallel=True,game_index_offset=0,output_dtype='float32',rotation_minutes=48,overtime_minutes=5,minutes_tolerance=1e-6,rotation_remainder_noise=1e-10,rotation_capacity_noise=.01,event_gamma_shape=4,action_limit_per_period_budget=5000),
 'parallel':dict(max_workers=2,start_method='spawn',minimum_games=2,minimum_scenarios=512,fallback_exceptions=['OSError','BrokenProcessPool']),
 'calibration':dict(pilot_limit=1024,market_iterations=4,market_factor_clip=[.8,1.2],make_two_clip=[.15,.85],make_three_clip=[.1,.75],team_score_tolerance=4,anchor_iterations=5,anchor_floor=.1,anchor_ratio_clip=[.5,2],anchor_exponent=.7,assist_clip=[.05,.95]),
 'cache':dict(enabled=True,identity_version=1,max_slates=2,construction_seed=83,draw_order=['construction','field','evaluation']),
 'seed_offsets':dict(candidate=1,field_draw=1009,support=1010,sampling=1011,evaluation=2017,ownership_proposal=37,ownership_search=38,game_stride=97,game_events=3,overtime_rotation=10000,overtime_stride=11,calibration_base=71333,anchor=17,final_market=31,market_pilot=104729,anchor_validation=65537),
}

# Position sets are serialized in sorted order for stable identities.
ALL=['C','PF','PG','SF','SG']
SITE_RULES={
 'dk':dict(platform='DraftKings',slots=['PG','SG','SF','PF','C','G','F','UTIL'],eligibility=[['PG'],['SG'],['SF'],['PF'],['C'],['PG','SG'],['PF','SF'],ALL],salary_cap=50000,max_from_team=8,min_teams=2,min_games=2,score_ticks=4),
 'fd':dict(platform='FanDuel',slots=['PG','SG','SF','PF','C','GF','FC','UTIL1','UTIL2'],eligibility=[['PG'],['SG'],['SF'],['PF'],['C'],['PF','PG','SF','SG'],['C','PF','SF'],ALL,ALL],salary_cap=60000,max_from_team=4,min_teams=3,min_games=1,score_ticks=10),
}

SCHEMA={'$schema':'https://json-schema.org/draft/2020-12/schema',**obj({
 'schema_version':const('1.0'),'artifact_type':const('initial_build'),'baseline_commit':const(BASELINE),
 'site':{'enum':['dk','fd']},'slate_id':dict(type='string',minLength=1),'slate_date':dict(type='string',minLength=10),
 'pipeline':obj({'simulations':integer(1),'candidate_target':integer(1),'field_support_target':integer(1),'seed':integer(),
   'diversity':number(0,100),'salary_min':number(),'max_ownership_error':number(),
   'ownership_mode':{'enum':['projected','relative popularity']},'correlation':number(0,100),
   'portfolio_count':integer(1),'ownership_source':dict(type='string',minLength=1),
   'excluded_indices':dict(type='array',items=integer()),
   'excluded_player_ids':dict(type='array',items=dict(type='string',minLength=1))}),
 'contest':obj({'id':dict(type='string',minLength=1),'entry_fee':dict(type='number',exclusiveMinimum=0),
   'contest_entries':integer(2),'represented_opponent_entries':integer(1)}),
 'site_rules':dict(type='object'),
 'implementation':obj({key:const(value) for key,value in FIXED.items()}),
})}


def _json(value,path='$'):
    if type(value) is dict:
        for key,child in value.items():
            if type(key) is not str:raise SnapshotContractError(path+': string keys required')
            _json(child,path+'.'+key)
    elif type(value) is list:
        for child in value:_json(child,path+'[]')
    elif type(value) is float:
        if not math.isfinite(value):raise SnapshotContractError(path+': finite numbers required')
    elif value is not None and type(value) not in (str,int,bool):raise SnapshotContractError(path+': JSON value required')


def _validate(value,schema,path='$'):
    if 'const' in schema:
        # JSON equality must not treat True as 1.
        import json
        if json.dumps(value,sort_keys=True)!=json.dumps(schema['const'],sort_keys=True):
            raise SnapshotContractError(path+': pinned constant mismatch')
    if 'enum' in schema and value not in schema['enum']:raise SnapshotContractError(path+': invalid choice')
    kind=schema.get('type')
    types={'object':dict,'array':list,'string':str,'integer':int}
    if kind in types and type(value) is not types[kind]:raise SnapshotContractError(path+': '+kind+' required')
    if kind=='number' and type(value) not in (int,float):raise SnapshotContractError(path+': number required')
    if kind=='object' and 'properties' in schema:
        if set(value)!=set(schema['required']):raise SnapshotContractError(path+': missing or unexpected settings keys')
        for key,child in value.items():_validate(child,schema['properties'][key],path+'.'+key)
    if kind=='array':
        for child in value:_validate(child,schema['items'],path+'[]')
    if 'minLength' in schema and len(value)<schema['minLength']:raise SnapshotContractError(path+': value too short')
    for key,invalid in [('minimum',lambda a,b:a<b),('maximum',lambda a,b:a>b),('exclusiveMinimum',lambda a,b:a<=b)]:
        if key in schema and invalid(value,schema[key]):raise SnapshotContractError(path+': outside allowed range')


def validate_settings(settings,*,player_ids,ownership,payouts,pool_platform):
    _json(settings);_validate(settings,SCHEMA)
    p=settings['pipeline'];c=settings['contest'];rules=SITE_RULES[settings['site']]
    _validate(settings['site_rules'],const(rules),'$.site_rules')
    if pool_platform!=rules['platform']:raise SnapshotContractError('Pool platform mismatch')
    try:day=date.fromisoformat(settings['slate_date'])
    except (ValueError,TypeError) as exc:raise SnapshotContractError('Invalid slate date') from exc
    if day.isoformat()!=settings['slate_date']:raise SnapshotContractError('Canonical ISO slate date required')
    if not player_ids or any(type(pid) is not str or not pid for pid in player_ids) or len(set(player_ids))!=len(player_ids):raise SnapshotContractError('Ordered unique player IDs required')
    if any(i>=len(player_ids) for i in p['excluded_indices']):raise SnapshotContractError('Excluded index outside pool')
    if [player_ids[i] for i in p['excluded_indices']]!=p['excluded_player_ids']:raise SnapshotContractError('Excluded IDs/index order mismatch')
    if p['salary_min']>rules['salary_cap'] or p['portfolio_count']>p['candidate_target']:raise SnapshotContractError('Invalid salary or portfolio bound')
    if c['represented_opponent_entries']!=c['contest_entries']-1:raise SnapshotContractError('Opponent count mismatch')
    own=np.asarray(ownership,float);prize=np.asarray(payouts,float)
    if own.shape!=(len(player_ids),) or not np.isfinite(own).all() or (own<0).any():raise SnapshotContractError('Invalid ownership/popularity vector')
    if p['ownership_mode']=='projected':
        if (own>100).any() or abs(own.sum()-100*len(rules['slots']))>.5:raise SnapshotContractError('Invalid projected ownership totals')
    elif not (own>0).any():raise SnapshotContractError('Positive relative popularity required')
    if prize.shape!=(c['contest_entries'],) or not np.isfinite(prize).all() or (prize<0).any() or (np.diff(prize)>0).any():raise SnapshotContractError('Invalid full contest payout vector')

SCHEMA['allOf']=[{'if':{'properties':{'site':const(site)},'required':['site']},
                  'then':{'properties':{'site_rules':const(rules)}}}
                 for site,rules in SITE_RULES.items()]

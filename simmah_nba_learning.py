"""Versioned historical role learning; validation uses observed minutes, not ROI."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unicodedata
import numpy as np
from simmah_nba_roles import observations, fit_roles, ROLES

MODEL_ROOT=Path(__file__).parent/'data'/'nba_models'
ROLE_COLUMNS=['Historical Shot Rate','Historical Assist Rate','Historical Rebound Rate','Historical Steal Rate','Historical Block Rate']


def name_key(name):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(name)).casefold() if c.isalnum())


def load_approved(slate_day, root=None):
    """Never apply a model before its validation/activation date."""
    root=Path(root or MODEL_ROOT)
    registry=root/'learned_roles_index.json'
    if not registry.exists():return None
    index=json.loads(registry.read_text())
    options=[r for r in index['versions'] if r['activation_date']<=str(slate_day)]
    for record in sorted(options,key=lambda r:(r['activation_date'],r['version']),reverse=True):
        target=root/record['file']
        if target.parent!=root/'learned_roles':raise ValueError('Invalid learned-model path')
        data=target.read_bytes()
        if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Learned-model checksum mismatch')
        model=json.loads(data)
        if (model['version']!=record['version'] or model['activation_date']!=record['activation_date']
                or not model.get('approved') or model['activation_date']>str(slate_day)
                or model['validation_through']>=model['activation_date']
                or model['latest_game']>=model['before']
                or model['before']>model['validation_start']
                or ('selection_through' in model and not model['before']<=model['selection_through']<model['validation_start'])):
            raise ValueError('Learned-model temporal validation failed')
        return model
    return None



def learning_status(slate_day,root=None):
    root=Path(root or MODEL_ROOT)
    reports=sorted(p for p in (root/'learning_reports').glob('*.json') if p.stem<=str(slate_day))
    if not reports:return {'status':'No evaluation yet'}
    report=json.loads(reports[-1].read_text())
    return {k:report.get(k) for k in ('status','as_of','training_games','validation_games','reason','accepted_roles','preserved_roles')}


def apply_learned_roles(pool, slate_day, root=None):
    model=load_approved(slate_day,root)
    if model is None:
        out=pool.copy();out.attrs.pop('nba_learning',None)
        return out
    out=pool.copy()
    matched=0
    for idx,row in out.iterrows():
        source=str(row.get('Role Rate Source',''))
        if not source.startswith(('Position prior (','Learned historical roles ')):continue
        player=model['players_by_name'].get(name_key(row.get('Name','')))
        if player is None or player['minutes']<60:continue
        rates=np.asarray(player['rates'],float)
        if rates.shape!=(5,) or not np.isfinite(rates).all() or (rates<0).any() or rates.sum()<=0:
            raise ValueError('Invalid learned player rates')
        # Source projections, availability, ownership and minutes are preserved.
        mask=role_mask(player)
        columns=[c for c,enabled in zip(ROLE_COLUMNS,mask) if enabled]
        if not columns:continue
        out.loc[idx,columns]=rates[mask]
        out.at[idx,'Role Rate Source']='Learned historical roles '+model['version']
        matched+=1
    out.attrs['nba_learning']={'version':model['version'],'matched_players':matched,
        'training_before':model['before'],'validation_through':model['validation_through'],
        'accepted_roles':model.get('validation',{}).get('accepted_roles',list(ROLES)),
        'scope':'historical role priors; held-out actual-minute validation, not ROI'}
    return out


def identities(games):
    names={};positions={};collisions=set()
    for g in games:
        for team in g['boxscore']['players']:
            for group in team['statistics']:
                for row in group['athletes']:
                    athlete=row['athlete'];pid=str(athlete['id'])
                    name=athlete.get('displayName') or athlete.get('fullName')
                    if not name:continue
                    key=name_key(name)
                    if key in names and names[key]!=pid:collisions.add(key)
                    names[key]=pid
                    positions[pid]=athlete.get('position',{}).get('abbreviation','')
    return {k:v for k,v in names.items() if k not in collisions},positions


def role_mask(player):
    """Legacy approved models replaced all roles; new models retain per-player masks."""
    enabled=player.get('enabled_roles',list(ROLES))
    if not isinstance(enabled,list) or not set(enabled)<=set(ROLES):
        raise ValueError('Invalid enabled learned roles')
    return np.asarray([r in enabled for r in ROLES],dtype=bool)


def baseline_rates(pid, names_by_id, positions, incumbent, baseline):
    from simmah_nba_role_priors import position_groups
    groups=position_groups(positions[pid])
    rates=np.mean([baseline['positions'][g]['rates'] for g in groups],axis=0)
    key=names_by_id.get(pid)
    if incumbent and key in incumbent['players_by_name']:
        player=incumbent['players_by_name'][key]
        if player['minutes']>=60:
            mask=role_mask(player)
            rates[mask]=np.asarray(player['rates'],float)[mask]
    return rates


def evaluate_candidate(fitted, names, games, today, incumbent, baseline):
    # Resolve identities as live loading does: collisions or unknown names keep priors.
    _,positions=identities(games)
    test_names,_=identities(games)
    names_by_id={pid:key for key,pid in test_names.items()}
    eligible={pid for key,pid in names.items() if test_names.get(key)==pid}
    candidate_errors=[];old_errors=[]
    for pid,minutes,actual in observations(games,today):
        try:old=baseline_rates(pid,names_by_id,positions,incumbent,baseline)
        except (KeyError,ValueError):continue
        player=fitted['players'].get(pid) if pid in eligible else None
        new=np.asarray(player['rates'],float) if player and player['minutes']>=60 else old
        candidate_errors.append(abs(new*minutes-actual));old_errors.append(abs(old*minutes-actual))
    return np.asarray(candidate_errors),np.asarray(old_errors)


def train_and_validate(games,today,baseline,incumbent=None,minimum_training=30,minimum_validation=10):
    """Fit, select roles, then confirm them on strictly later games without refitting."""
    today=str(today);seen=set()
    for g in games:
        if g['date']>=today:raise ValueError('Training corpus includes target-day/future game')
        if g['event_id'] in seen:raise ValueError('Duplicate archived game')
        seen.add(g['event_id'])
    games=sorted(games,key=lambda g:(g['date'],g['event_id']))
    dates=sorted({g['date'] for g in games})
    fresh=[d for d in dates if not incumbent or d>incumbent['validation_through']]
    evaluation_dates=fresh if incumbent else fresh[-3:]
    if len(evaluation_dates)<3:
        return {'status':'pending','reason':'Need one fresh selection date and two fresh confirmation dates'}
    boundary=evaluation_dates[0]
    # Last two dates are reserved for confirmation; preceding fresh dates select roles.
    confirmation_start=evaluation_dates[-2]
    training=[g for g in games if g['date']<boundary]
    selection=[g for g in games if boundary<=g['date']<confirmation_start]
    testing=[g for g in games if g['date']>=confirmation_start]
    report={'status':'pending','training_games':len(training),'selection_games':len(selection),
            'validation_games':len(testing),'training_before':boundary,
            'selection_through':selection[-1]['date'],'validation_start':confirmation_start,
            'validation_through':dates[-1],
            'scope':'Player stat-rate accuracy conditional on observed minutes; not fantasy-point or ROI validation'}
    if len(training)<minimum_training or len(testing)<minimum_validation:
        return dict(report,reason='Insufficient independent training/validation games')
    if incumbent and incumbent['latest_game']>=boundary:raise ValueError('Incumbent overlaps validation training boundary')
    if baseline['before']>boundary:raise ValueError('Baseline follows validation dates')
    fitted=fit_roles(training,boundary)
    names,_=identities(training)
    select_new,select_old=evaluate_candidate(fitted,names,selection,today,incumbent,baseline)
    test_new,test_old=evaluate_candidate(fitted,names,testing,today,incumbent,baseline)
    if len(select_old)<100 or len(test_old)<100:
        return dict(report,reason='Need 100 comparable player observations in both selection and confirmation')
    selected_ratio=1+(select_new.mean(axis=0)-select_old.mean(axis=0))/np.maximum(select_old.mean(axis=0),.01)
    new=test_new.mean(axis=0);old=test_old.mean(axis=0)
    ratios=1+(new-old)/np.maximum(old,.01)
    # Fixed per-role rule: at least 1% better on BOTH disjoint evaluation periods.
    # Unsuccessful roles keep their incumbent parameters, including previous gains.
    keep=(selected_ratio<=.99)&(ratios<=.99)&np.isfinite(selected_ratio)&np.isfinite(ratios)
    approved=bool(keep.any())
    retained=np.where(keep,new,old)
    retained_ratios=1+(retained-old)/np.maximum(old,.01)
    accepted=[r for r,k in zip(ROLES,keep) if k]
    report.update(status='approved' if approved else 'rejected',observations=len(test_old),
        selection_observations=len(select_old),
        selection_error_ratio=dict(zip(ROLES,selected_ratio.tolist())),
        candidate_mae=dict(zip(ROLES,new.tolist())),incumbent_mae=dict(zip(ROLES,old.tolist())),
        retained_mae=dict(zip(ROLES,retained.tolist())),accepted_roles=accepted,
        preserved_roles=[r for r,k in zip(ROLES,keep) if not k],
        candidate_mean_error_ratio=float(ratios.mean()),
        mean_error_ratio=float(retained_ratios.mean()),max_role_error_ratio=float(retained_ratios.max()),
        acceptance='Each role needs at least 1% improvement on selection AND later confirmation; other roles retain incumbent',
        training_ids=[g['event_id'] for g in training],selection_ids=[g['event_id'] for g in selection],
        validation_ids=[g['event_id'] for g in testing])
    if approved:
        players=deepcopy(incumbent['players_by_name']) if incumbent else {}
        for key,pid in names.items():
            player=fitted['players'].get(pid)
            if not player or player['minutes']<60:continue
            previous=players.get(key)
            rates=np.asarray(previous['rates'],float).copy() if previous else np.zeros(5)
            mask=role_mask(previous) if previous else np.zeros(5,dtype=bool)
            rates[keep]=np.asarray(player['rates'],float)[keep]
            mask|=keep
            players[key]={'minutes':player['minutes'],'espn_id':pid,'rates':rates.tolist(),
                          'enabled_roles':[r for r,k in zip(ROLES,mask) if k]}
        version=today+'-'+hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()[:12]
        report['model']={'approved':True,'version':version,'before':boundary,
            'latest_game':max(g['date'] for g in training),'activation_date':today,
            'selection_through':selection[-1]['date'],
            'validation_start':confirmation_start,'validation_through':dates[-1],
            'players_by_name':players,
            'validation':{k:v for k,v in report.items() if k!='model'}}
    return report

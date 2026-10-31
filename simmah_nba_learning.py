"""Versioned historical role learning; validation uses observed minutes, not ROI."""
from datetime import date
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
                or model['before']>model['validation_start']):
            raise ValueError('Learned-model temporal validation failed')
        return model
    return None



def learning_status(slate_day,root=None):
    root=Path(root or MODEL_ROOT)
    reports=sorted(p for p in (root/'learning_reports').glob('*.json') if p.stem<=str(slate_day))
    if not reports:return {'status':'No evaluation yet'}
    report=json.loads(reports[-1].read_text())
    return {k:report.get(k) for k in ('status','as_of','training_games','validation_games','reason')}


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
        out.loc[idx,ROLE_COLUMNS]=rates
        out.at[idx,'Role Rate Source']='Learned historical roles '+model['version']
        matched+=1
    out.attrs['nba_learning']={'version':model['version'],'matched_players':matched,
        'training_before':model['before'],'validation_through':model['validation_through'],
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


def baseline_rates(pid, names_by_id, positions, incumbent, baseline):
    from simmah_nba_role_priors import position_groups
    key=names_by_id.get(pid)
    if incumbent and key in incumbent['players_by_name']:
        player=incumbent['players_by_name'][key]
        if player['minutes']>=60:return np.asarray(player['rates'],float)
    groups=position_groups(positions[pid])
    return np.mean([baseline['positions'][g]['rates'] for g in groups],axis=0)


def train_and_validate(games,today,baseline,incumbent=None,minimum_training=30,minimum_validation=10):
    """Fit on earlier dates; only use fresh later dates to accept/reject updates."""
    today=str(today);seen=set()
    for g in games:
        if g['date']>=today:raise ValueError('Training corpus includes target-day/future game')
        if g['event_id'] in seen:raise ValueError('Duplicate archived game')
        seen.add(g['event_id'])
    games=sorted(games,key=lambda g:(g['date'],g['event_id']))
    dates=sorted({g['date'] for g in games})
    fresh=[d for d in dates if not incumbent or d>incumbent['validation_through']]
    validation_dates=fresh if incumbent else fresh[-3:]
    if len(validation_dates)<2:return {'status':'pending','reason':'Need at least two fresh validation dates'}
    boundary=validation_dates[0]
    training=[g for g in games if g['date']<boundary]
    testing=[g for g in games if g['date']>=boundary]
    report={'status':'pending','training_games':len(training),'validation_games':len(testing),
            'training_before':boundary,'validation_through':dates[-1],
            'scope':'Player stat-rate accuracy conditional on observed minutes; not fantasy-point or ROI validation'}
    if len(training)<minimum_training or len(testing)<minimum_validation:
        return dict(report,reason='Insufficient independent training/validation games')
    if incumbent and incumbent['latest_game']>=boundary:raise ValueError('Incumbent overlaps validation training boundary')
    if baseline['before']>boundary:raise ValueError('Baseline follows validation dates')
    fitted=fit_roles(training,boundary)
    names,_=identities(training)
    _,positions=identities(testing)
    test_names,_=identities(testing)
    names_by_id={pid:key for key,pid in test_names.items()}
    candidate_errors=[];old_errors=[]
    for pid,minutes,actual in observations(testing,today):
        try:old=baseline_rates(pid,names_by_id,positions,incumbent,baseline)
        except (KeyError,ValueError):continue
        player=fitted['players'].get(pid)
        new=np.asarray(player['rates'],float) if player and player['minutes']>=60 else old
        candidate_errors.append(abs(new*minutes-actual));old_errors.append(abs(old*minutes-actual))
    if len(old_errors)<100:return dict(report,reason='Need 100 comparable held-out player observations')
    new=np.mean(candidate_errors,axis=0);old=np.mean(old_errors,axis=0)
    # Normalize roles so shots do not drown out steals and blocks.
    ratios=1+(new-old)/np.maximum(old,.01)
    approved=bool(ratios.mean()<=.99 and (ratios<=1.02).all())
    report.update(status='approved' if approved else 'rejected',observations=len(old_errors),
        candidate_mae=dict(zip(ROLES,new.tolist())),incumbent_mae=dict(zip(ROLES,old.tolist())),
        mean_error_ratio=float(ratios.mean()),max_role_error_ratio=float(ratios.max()),
        acceptance='At least 1% average normalized improvement; no role more than 2% worse',
        training_ids=[g['event_id'] for g in training],validation_ids=[g['event_id'] for g in testing])
    if approved:
        version=today+'-'+hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()[:12]
        report['model']={'approved':True,'version':version,'before':boundary,
            'latest_game':max(g['date'] for g in training),'activation_date':today,
            'validation_start':boundary,'validation_through':dates[-1],
            'players_by_name':{key:{**fitted['players'][pid],'espn_id':pid} for key,pid in names.items() if pid in fitted['players']},
            'validation':{k:v for k,v in report.items() if k!='model'}}
    return report

"""Explicit historical position priors for players without individual NBA history."""
from datetime import date
import numpy as np
from simmah_nba_roles import observations
from simmah_nba_pregame import ROLE_COLUMNS


def position_groups(position):
    groups=set()
    for p in str(position).upper().split('/'):
        if p in {'PG','SG','G'}:groups.add('G')
        elif p in {'SF','PF','F'}:groups.add('F')
        elif p=='C':groups.add('C')
        else:raise ValueError('Unsupported NBA position for role prior: '+p)
    return sorted(groups)


def fit_position_priors(games,before,minimum_minutes=1000):
    games=list(games)
    if minimum_minutes<=0 or not np.isfinite(minimum_minutes):raise ValueError('Positive prior sample floor required')
    # Validate the whole corpus before aggregating one game at a time.
    list(observations(games,before))
    totals={g:[0.,np.zeros(5)] for g in ('G','F','C')}
    for game in games:
        positions={str(r['athlete']['id']):r['athlete'].get('position',{}).get('abbreviation','')
                   for t in game['boxscore']['players'] for s in t['statistics'] for r in s['athletes']}
        for pid,minutes,values in observations([game],before):
            groups=position_groups(positions[pid])
            for group in groups:
                totals[group][0]+=minutes/len(groups)
                totals[group][1]+=values/len(groups)
    priors={g:{'minutes':m,'rates':(v/m).tolist()} for g,(m,v) in totals.items() if m>=minimum_minutes}
    if not priors:raise ValueError('Insufficient historical position observations')
    return {'before':str(before),'latest_game':max(g['date'] for g in games),
            'games':len(games),'event_ids':[g['event_id'] for g in games],
            'positions':priors,'source':'Completed ESPN NBA box scores; pooled per-minute position roles',
            'status':'experimental position prior, not an individual player forecast'}


def apply_position_priors(pool,model,slate_day):
    if date.fromisoformat(model['before'])>date.fromisoformat(slate_day) or date.fromisoformat(model['latest_game'])>=date.fromisoformat(model['before']):
        raise ValueError('Position prior would use future results')
    result=pool.copy()
    # Projection feeds can succeed while the minutes provider is unavailable.
    # Keep unknown minutes explicit; never manufacture a playable rotation.
    if 'Projected Minutes' not in result:result['Projected Minutes']=np.nan
    if 'Minutes Source' not in result:result['Minutes Source']='Missing'
    for c in ROLE_COLUMNS:
        if c not in result:result[c]=np.nan
    result['Role Rate Source']='Missing'
    for i,row in result.iterrows():
        existing=np.asarray([row[c] for c in ROLE_COLUMNS],float)
        if np.isfinite(existing).all() and (existing>=0).all():
            result.at[i,'Role Rate Source']='Individual historical rates'
            continue
        try:
            projection=float(row.get('Projection',np.nan))
            minutes=float(row.get('Projected Minutes',np.nan))
            eligible=np.isfinite([projection,minutes]).all() and projection>0 and 0<minutes<=48
        except (ValueError,TypeError):eligible=False
        if not eligible or str(row['Injury Status']).upper() in {'O','OUT','IR','SUSPENDED'}:continue
        groups=position_groups(row['Position'])
        if any(g not in model['positions'] for g in groups):raise ValueError('Position prior is unavailable for '+str(row.get('Name',row['Player ID'])))
        rates=np.mean([model['positions'][g]['rates'] for g in groups],axis=0)
        if rates.shape!=(5,) or not np.isfinite(rates).all() or (rates<0).any():raise ValueError('Invalid historical position prior')
        for c,value in zip(ROLE_COLUMNS,rates):result.at[i,c]=value
        result.at[i,'Role Rate Source']='Position prior ('+'/'.join(groups)+'); '+model['before']
    return result


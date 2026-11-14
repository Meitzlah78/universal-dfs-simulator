"""Explicit participation streaks and independent tiered minutes; offline only."""
import numpy as np
import pandas as pd
from simmah_nba_independent_minutes_offline import forecast_team


def absence_state(key,calendar,participation,game_date,captured_at):
    capture=pd.Timestamp(captured_at)
    if capture.tzinfo is None:raise ValueError('Timezone-aware cutoff required')
    eligible=[g for g in calendar if g['team']==key[1] and g['date']<game_date and pd.Timestamp(g['completed_at'])<capture]
    eligible=sorted(eligible,key=lambda g:(g['date'],g['completed_at'],g['game_id']),reverse=True)
    if len({g['game_id'] for g in eligible})!=len(eligible):raise ValueError('Duplicate team game')
    states=[participation.get((g['game_id'],key[0],key[1]),'unknown') for g in eligible]
    if any(s not in ['played','dnp','unknown'] for s in states):raise ValueError('Unsupported participation label')
    streak=0
    for state in states:
        if state!='dnp':break
        streak+=1
    if states and states[0]=='played':label='fresh'
    elif len(states)>=2 and states[:2]==['dnp','played']:label='fresh'
    elif streak>=3:label='ongoing_3plus'
    elif len(states)>=3 and states[:3]==['dnp','dnp','played']:label='two_missed_transition'
    else:label='unknown'
    return {'state':label,'consecutive_verified_dnp':streak,'streak_exact':streak<len(states) and states[streak]=='played','last3_games':[g['game_id'] for g in eligible[:3]],'last3_states':states[:3]}


def tiered_team(roster,history,game_date,captured_at):
    base=forecast_team(roster,history,game_date,captured_at)
    long=forecast_team(roster,history,game_date,captured_at,window=10,half_life=5.)
    fast=forecast_team(roster,history,game_date,captured_at,window=3,half_life=1.)
    # Tier is determined before evaluating outcomes and before new team allocation.
    weights=[];tiers=[]
    for b,l,f in zip(base,long,fast):
        if b['key']!=l['key'] or b['key']!=f['key']:raise AssertionError('Roster mismatch')
        role='core' if b['raw_minutes']>=28 else 'bench' if b['raw_minutes']<18 else 'rotation'
        weights.append(l['raw_minutes'] if role=='core' else f['raw_minutes'] if role=='bench' else b['raw_minutes']);tiers.append(role)
    from simmah_nba_minutes import allocate_minutes
    predicted=allocate_minutes(np.asarray(weights)[None,:])[0]
    return base,predicted,tiers


def transfer_proposal(minutes,recipient_weights):
    v=np.asarray(minutes,float).copy();weights=np.asarray(recipient_weights,float)
    if v.shape!=weights.shape or not np.isfinite(v).all() or not np.isfinite(weights).all() or np.any(weights<0) or np.any(v<0) or np.any(v>48) or abs(v.sum()-240)>1e-6:raise ValueError('Bounded240-minute vector and nonnegative routing weights required')
    recipients=np.flatnonzero(weights>0);donors=np.flatnonzero(weights==0)
    amount=min(float(weights.sum()),float(v[donors].sum()),float((48-v[recipients]).sum()))
    if amount>0:
        v[donors]-=amount*v[donors]/v[donors].sum();remaining=amount
        for _ in range(len(recipients)+1):
            ids=recipients[v[recipients]<48-1e-12]
            if not len(ids) or remaining<1e-10:break
            change=np.minimum(48-v[ids],remaining*weights[ids]/weights[ids].sum());v[ids]+=change;remaining-=change.sum()
        if remaining>1e-8:raise AssertionError('Unallocated vacancy transfer')
    if abs(v.sum()-240)>1e-6 or np.any(v< -1e-8) or np.any(v>48+1e-8):raise AssertionError('Transfer budget failure')
    return np.clip(v,0,48)

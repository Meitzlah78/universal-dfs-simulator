"""Historical game-margin discounts for isolated offline point-forecast tests."""
import numpy as np
import pandas as pd

SCHEMES=['none','final_hard20','final_hard25','final_linear','q4_hard20','q4_hard25','q4_linear']

def clock_seconds(clock):
    parts=str(clock).split(':');return float(parts[0])*60+float(parts[1]) if len(parts)==2 else float(parts[0])

def margin_profile(events,home_score,away_score):
    scores=np.asarray([home_score,away_score],float)
    if not np.isfinite(scores).all() or np.any(scores<0):raise ValueError('Finite nonnegative final score required')
    final=float(abs(scores[0]-scores[1]))
    quarters={};q4=[];previous=721.;issue=None
    for e in events:
        period=e.get('period',{}).get('number',0)
        if period not in [1,2,3,4]:continue
        try:s=clock_seconds(e['clock']['displayValue']);h=float(e['homeScore']);a=float(e['awayScore'])
        except (KeyError,ValueError,TypeError):
            if period==4:issue='missing_q4_clock_or_score'
            continue
        if not np.isfinite([s,h,a]).all() or s<0 or s>720:
            if period==4:issue='invalid_q4_clock_or_score'
            continue
        if s==0:quarters[str(period)]=h-a
        if period==4:
            if s>previous+1e-6:issue='nonmonotonic_q4_source_order'
            previous=s;q4.append((s,abs(h-a)))
    before=[m for s,m in q4 if s>=360];after=[(s,m) for s,m in q4 if s<360]
    if not before or not after or after[-1][0]!=0:issue=issue or 'missing_last6_boundary_coverage'
    mean=None;seconds20=None
    if issue is None:
        previous=360.;state=before[-1];integral=0.;above=0.
        for s,m in after:
            elapsed=previous-s;integral+=elapsed*state;above+=elapsed*(state>=20);previous=s;state=m
        mean=integral/360.;seconds20=above
    return {'final_abs_margin':final,'quarter_end_home_minus_away':quarters,'q4_last6_mean_abs_margin':mean,'q4_last6_seconds_margin20plus':seconds20,'q4_issue':issue}

def discount_weight(profile,scheme):
    if scheme not in SCHEMES:raise ValueError('Unknown frozen discount scheme')
    if scheme=='none':return 1.
    value=profile.get('final_abs_margin') if scheme.startswith('final_') else profile.get('q4_last6_mean_abs_margin')
    if value is None:return 1.
    if not np.isfinite(value) or value<0:raise ValueError('Invalid historical margin')
    if scheme.endswith('hard20'):return .5 if value>=20 else 1.
    if scheme.endswith('hard25'):return .5 if value>=25 else 1.
    return float(np.clip(1.-.75*(value-10.)/20.,.25,1.))

def discounted_recent_mean(rows,game_date,captured_at,window,half_life,profiles,scheme,fallback):
    capture=pd.Timestamp(captured_at)
    if capture.tzinfo is None or not isinstance(window,int) or window<1 or not np.isfinite(half_life) or half_life<=0:raise ValueError('Valid cutoff and window required')
    prior=[r for r in rows if r['date']<game_date and pd.Timestamp(r['completed_at'])<capture]
    prior=sorted(prior,key=lambda r:(r['date'],r['completed_at'],r['game_id']))[-window:]
    if any(not np.isfinite(r['minutes']) or not 0<=r['minutes']<=48 for r in prior):raise ValueError('Bounded historical minutes required')
    if not prior:return float(fallback),{'n':0,'discounted':0,'missing_profile':0}
    weights=2.**(-np.arange(len(prior)-1,-1,-1)/half_life);discounted=missing=0
    for i,r in enumerate(prior):
        if r['minutes']==0 or scheme=='none':continue
        profile=profiles.get(str(r['game_id']));valid=profile is not None and profile.get('date',r['date'])<game_date and pd.Timestamp(profile['completed_at'])<capture
        field='final_abs_margin' if scheme.startswith('final_') else 'q4_last6_mean_abs_margin'
        if not valid or profile.get(field) is None:missing+=1;continue
        w=discount_weight(profile,scheme);weights[i]*=w;discounted+=w<1
    return float(np.average([r['minutes'] for r in prior],weights=weights)),{'n':len(prior),'discounted':int(discounted),'missing_profile':missing}

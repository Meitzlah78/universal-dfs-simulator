"""Hard limits on selected NBA entries, independently checked before CSV export."""
import math
import pandas as pd
from simmah_nba_ownership import field_ownership_inputs, COLUMN


def portfolio_limits(pool, controls=None):
    ownership=field_ownership_inputs(pool)
    trusted=ownership['mode']=='projected'
    limits={}
    for _,row in pool.iterrows():
        pid=str(row['Player ID']);cap=60.
        if trusted:
            own=pd.to_numeric(row.get(COLUMN),errors='coerce')
            if pd.notna(own):cap=min(cap,float(own)+5.)
        if 'Projected Minutes' in pool:
            minutes=pd.to_numeric(row.get('Projected Minutes'),errors='coerce')
            if pd.isna(minutes) or minutes<=0:cap=0.
            elif minutes<16:cap=min(cap,15.)
        cfg=dict((controls or {}).get(pid,{}))
        manual=pd.to_numeric(cfg.get('Max Exposure %',100),errors='coerce')
        cfg['Max Exposure %']=min(cap,float(manual) if pd.notna(manual) else cap)
        if cfg.get('Lock') or float(cfg.get('Min Exposure %',0))>cfg['Max Exposure %']:
            raise ValueError('NBA hard exposure cap conflicts with lock/minimum for '+str(row['Name']))
        limits[pid]=cfg
    return limits


def validate_portfolio_limits(portfolio, slots, limits):
    if portfolio.empty:raise ValueError('NBA portfolio is empty')
    counts=portfolio[list(slots)].astype(str).stack().value_counts()
    for pid,used in counts.items():
        if pid not in limits:raise ValueError('NBA exposure validation: unknown player '+pid)
        cap=float(limits[pid]['Max Exposure %'])
        maximum=0 if cap<=0 else max(1,math.floor(len(portfolio)*cap/100+1e-9))
        if used>maximum:
            raise ValueError(f'NBA exposure cap exceeded for {pid}: {used} entries; maximum {maximum}. Rebuild the portfolio.')

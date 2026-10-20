"""Offline empirical team-minutes challenger. Not enabled in live builds.

Requires archived pregame inputs and verified regulation-only actuals. Exact
roster matching deliberately avoids inventing injury/replacement uncertainty.
"""
import numpy as np
import pandas as pd


def fit_team_residuals(rows,before,minimum_games=3):
    required={'Game ID','Team','Player ID','GameStart','CapturedAt','Final',
              'Overtime','Projected Minutes','Actual Minutes'}
    if not required<=set(rows):raise ValueError('Complete frozen minutes training records required')
    cutoff=pd.Timestamp(before)
    if cutoff.tzinfo is None:raise ValueError('Timezone-aware training cutoff required')
    if minimum_games<3:raise ValueError('At least three training games required')
    corpus={}
    for (_,team),group in rows.groupby(['Game ID','Team'],sort=True):
        group=group.copy();group['Player ID']=group['Player ID'].astype(str)
        if group['Player ID'].duplicated().any():raise ValueError('Duplicate team-game player')
        starts=pd.to_datetime(group['GameStart'],utc=True,errors='raise')
        captured=pd.to_datetime(group['CapturedAt'],utc=True,errors='raise')
        if starts.nunique()!=1 or (starts>=cutoff).any() or (captured>=starts).any():
            raise ValueError('Training must precede cutoff and snapshots must precede tipoff')
        if not group['Final'].eq(True).all():raise ValueError('Verified final games required')
        if not group['Overtime'].eq(False).all():raise ValueError('Overtime cannot train regulation minutes')
        group=group.sort_values('Player ID')
        predicted=group['Projected Minutes'].to_numpy(float);actual=group['Actual Minutes'].to_numpy(float)
        for values in (predicted,actual):
            if not np.isfinite(values).all() or (values<0).any() or (values>48).any() or abs(values.sum()-240)>1e-6:
                raise ValueError('Complete 240-minute regulation team ledgers required')
        key=(str(team),tuple(group['Player ID']))
        corpus.setdefault(key,[]).append(actual-predicted)
    return {'before':cutoff.isoformat(),'minimum_games':minimum_games,
            'residuals':{key:np.array(value) for key,value in corpus.items()},
            'status':'offline exact-roster residual challenger; no validated predictive improvement'}


def sample_team_minutes(model,team,player_ids,means,n,seed):
    ids=list(map(str,player_ids));means=np.asarray(means,float)
    if len(ids)!=len(set(ids)) or len(ids)<5 or means.shape!=(len(ids),):raise ValueError('Unique complete team roster required')
    if not np.isfinite(means).all() or (means<0).any() or (means>48).any() or abs(means.sum()-240)>1e-6:
        raise ValueError('Complete legal baseline minutes required')
    if not isinstance(n,int) or n<1:raise ValueError('Positive scenario count required')
    order=np.argsort(ids);key=(str(team),tuple(np.array(ids)[order]))
    residuals=model['residuals'].get(key)
    if residuals is None or len(residuals)<model['minimum_games']:
        raise ValueError('Insufficient pregame residual history for this exact team roster')
    rng=np.random.default_rng(seed)
    sampled=means[order]+residuals[rng.integers(len(residuals),size=n)]
    # Capped-simplex Euclidean projection, vectorized across scenarios. Unlike
    # proportional scaling, this preserves both team budget and individual caps.
    lower=sampled.min(axis=1)-48;upper=sampled.max(axis=1)
    for _ in range(60):
        mid=(lower+upper)/2
        budget=np.clip(sampled-mid[:,None],0,48).sum(axis=1)
        lower=np.where(budget>240,mid,lower);upper=np.where(budget>240,upper,mid)
    result=np.clip(sampled-((lower+upper)/2)[:,None],0,48)
    return result[:,np.argsort(order)]


def evaluate_team_minutes(model,holdout,n=1000,seed=83):
    """Grade later regulation games; never update the fitted model on holdout."""
    cutoff=pd.Timestamp(model['before']);reports=[];uncovered=[]
    for (game,team),group in holdout.groupby(['Game ID','Team'],sort=True):
        starts=pd.to_datetime(group['GameStart'],utc=True,errors='raise')
        if (starts<cutoff).any():raise ValueError('Holdout overlaps training dates')
        # Reuse strict snapshot, final, unique-ID and full-ledger checks.
        fit_team_residuals(group,(starts.max()+pd.Timedelta(days=1)).isoformat())
        try:
            sampled=sample_team_minutes(model,team,group['Player ID'].tolist(),
                group['Projected Minutes'].to_numpy(float),n,seed)
        except ValueError as exc:
            uncovered.append({'Game ID':str(game),'Team':str(team),'reason':str(exc)})
            continue
        actual=group['Actual Minutes'].to_numpy(float)
        lower,upper=np.quantile(sampled,[.1,.9],axis=0)
        for i,(_,row) in enumerate(group.iterrows()):
            reports.append({'Game ID':str(game),'Player ID':str(row['Player ID']),
                'baseline_abs_error':abs(float(row['Projected Minutes'])-actual[i]),
                'challenger_abs_error':abs(sampled[:,i].mean()-actual[i]),
                'covered_80':bool(lower[i]<=actual[i]<=upper[i]),
                'interval_width':float(upper[i]-lower[i])})
    frame=pd.DataFrame(reports)
    return {'rows':reports,'uncovered_team_games':uncovered,'matched_player_games':len(reports),
        'baseline_mae':float(frame.baseline_abs_error.mean()) if len(frame) else None,
        'challenger_mae':float(frame.challenger_abs_error.mean()) if len(frame) else None,
        'coverage_80':float(frame.covered_80.mean()) if len(frame) else None,
        'status':'offline holdout diagnostic; no automatic promotion to live builds'}

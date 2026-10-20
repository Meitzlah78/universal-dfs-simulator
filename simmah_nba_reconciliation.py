"""Offline reconciliation of frozen forecasts and verified final NBA minutes.

Inputs must already use explicit game IDs and official NBA player IDs. No name,
jersey-number, missing-to-zero or proportional-overtime inference is performed.
"""
import numpy as np
import pandas as pd

KEYS=['Game ID','NBA Player ID']


def _ids(frame,required):
    if not set(required)<=set(frame):raise ValueError('Missing columns: '+', '.join(sorted(set(required)-set(frame))))
    result=frame.copy()
    for key in KEYS:
        if result[key].isna().any():raise ValueError('Missing official game/player IDs')
        result[key]=result[key].astype(str).str.strip()
        if not result[key].str.fullmatch(r'\d+').all():raise ValueError('Numeric official game/player IDs required')
    if result.duplicated(KEYS).any():raise ValueError('Duplicate game/player rows; choose one pregame snapshot explicitly')
    return result


def reconcile_minutes(pregame,actuals):
    pre=_ids(pregame,KEYS+['Team','GameStart','CapturedAt','Projected Minutes'])
    actual=_ids(actuals,KEYS+['Team','Actual Minutes','Status','Final','Overtimes'])
    for column in ('GameStart','CapturedAt'):
        if any(pd.Timestamp(value).tzinfo is None for value in pre[column]):
            raise ValueError('Explicit timezone offsets required for frozen timestamps')
    starts=pd.to_datetime(pre['GameStart'],utc=True,errors='raise')
    captured=pd.to_datetime(pre['CapturedAt'],utc=True,errors='raise')
    if starts.isna().any() or captured.isna().any() or (captured>=starts).any():
        raise ValueError('Every frozen input must be observed before tipoff')
    pre['Projected Minutes']=pd.to_numeric(pre['Projected Minutes'],errors='raise')
    if pre['Projected Minutes'].isna().any() or not np.isfinite(pre['Projected Minutes']).all() or not pre['Projected Minutes'].between(0,48).all():
        raise ValueError('Finite regulation pregame minutes between 0 and 48 required')
    if not actual['Final'].eq(True).all():raise ValueError('Actuals must come from verified final games')
    ot=pd.to_numeric(actual['Overtimes'],errors='raise')
    if ot.isna().any() or not np.isfinite(ot).all() or (ot<0).any() or (ot%1!=0).any():
        raise ValueError('Verified integer overtime counts required')
    actual['Overtimes']=ot.astype(int)
    if (actual.groupby('Game ID')['Overtimes'].nunique()>1).any():raise ValueError('Conflicting overtime counts')
    status=actual['Status'].astype(str).str.lower()
    if not status.isin(['played','dnp','unresolved']).all():raise ValueError('Status must be played, dnp or unresolved')
    actual['Status']=status
    actual['Actual Minutes']=pd.to_numeric(actual['Actual Minutes'],errors='raise')
    known=actual['Actual Minutes'].notna()
    if not np.isfinite(actual.loc[known,'Actual Minutes']).all() or (actual.loc[known,'Actual Minutes']<0).any():
        raise ValueError('Nonnegative finite actual minutes required')
    if (actual.loc[known,'Actual Minutes'] > 48+5*actual.loc[known,'Overtimes']).any():raise ValueError('Actual minutes exceed game length')
    if ((status=='played') & (~known | actual['Actual Minutes'].le(0))).any():raise ValueError('Played status needs positive verified minutes')
    if ((status=='dnp') & known & actual['Actual Minutes'].ne(0)).any():raise ValueError('Verified DNP conflicts with positive minutes')
    if ((status=='unresolved') & known).any():raise ValueError('Unresolved actuals must remain missing')
    # Only a verified DNP designation authorizes conversion of blank minutes to 0.
    actual.loc[status=='dnp','Actual Minutes']=0.
    if pre['Team'].isna().any() or actual['Team'].isna().any():raise ValueError('Explicit team identity required')
    merged=pre.merge(actual,on=KEYS,how='outer',suffixes=('_pregame','_actual'),indicator=True,validate='one_to_one')
    matched=merged['_merge'].eq('both')
    if (merged.loc[matched,'Team_pregame']!=merged.loc[matched,'Team_actual']).any():raise ValueError('Team mismatch; audit ID mapping')
    merged['Reconciliation']='matched'
    merged.loc[merged['_merge'].eq('left_only'),'Reconciliation']='missing_actual'
    merged.loc[merged['_merge'].eq('right_only'),'Reconciliation']='missing_pregame'
    merged.loc[matched & merged['Status'].eq('unresolved'),'Reconciliation']='unresolved_actual'
    valid=matched & merged['Actual Minutes'].notna()
    merged['Minutes Error']=np.where(valid,merged['Projected Minutes']-merged['Actual Minutes'],np.nan)
    metrics={}
    for label,mask in [('regulation',valid & merged['Overtimes'].eq(0)),('overtime_full_game',valid & merged['Overtimes'].gt(0))]:
        errors=merged.loc[mask,'Minutes Error']
        metrics[label]={'players':len(errors),'mae':float(errors.abs().mean()) if len(errors) else None,
                        'bias':float(errors.mean()) if len(errors) else None}
    audit=[]
    for (game,team),group in actual.groupby(['Game ID','Team']):
        expected=240+25*int(group['Overtimes'].iloc[0]);total=float(group['Actual Minutes'].sum())
        complete=bool(group['Actual Minutes'].notna().all() and abs(total-expected)<=1.)
        audit.append({'Game ID':game,'Team':team,'minutes_sum':total,'expected':expected,
                      'ledger_reconciled':complete})
    return {'rows':merged.drop(columns='_merge'),'metrics':metrics,
        'coverage':{str(k):int(v) for k,v in merged['Reconciliation'].value_counts().items()},
        'team_ledgers':audit,'verified_dnp':int(actual['Status'].eq('dnp').sum()),
        'caveat':'Overtime full-game errors are separate diagnostics, not recovered regulation minutes. Audit incomplete team ledgers before training.'}

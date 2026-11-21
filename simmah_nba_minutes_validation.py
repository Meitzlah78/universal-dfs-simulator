from simmah_slate_workspaces import workspace_download_button
"""Pregame minutes snapshots and explicit-ID grading, independent of live models."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import numpy as np
import pandas as pd


def freeze_minutes(pool, platform, now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:raise ValueError('Timezone-aware snapshot time required')
    column='Game Start' if 'Game Start' in pool else 'GameStart'
    if column not in pool:return None
    def kickoff(value):
        try:
            if isinstance(value,str) and ':' not in value:return pd.NaT
            stamp=pd.Timestamp(value)
            if pd.isna(stamp):return pd.NaT
            if stamp.tzinfo is None:stamp=stamp.tz_localize('America/New_York')
            return stamp.tz_convert('UTC')
        except (ValueError,TypeError):return pd.NaT
    starts=pd.to_datetime(pool[column].map(kickoff),utc=True)
    minutes=pd.to_numeric(pool.get('Projected Minutes',pd.Series(np.nan,index=pool.index)),errors='coerce')
    keep=starts.notna() & (starts>now) & minutes.notna() & np.isfinite(minutes) & minutes.between(0,48)
    columns=[c for c in ['Player ID','Name','Team','Opponent','Injury Status','Starter Confirmed',
        'Projected Minutes','Minutes Source','Projection','Projection Source',
        'RotoWire Projected Own %','RotoWire RST % (unverified)',
        'FantasyLabs Projected Own %','DraftDashboard Projected Own %',
        'DraftDashboard Reference Minutes','Eligible','Minutes Source'] if c in pool]
    columns=list(dict.fromkeys(columns))
    frame=pool.loc[keep,columns].copy()
    if frame.empty:return None
    frame['GameStart']=starts[keep].map(lambda x:x.isoformat())
    if frame['Player ID'].astype(str).duplicated().any():raise ValueError('Duplicate snapshot player IDs')
    # Missing numeric fields are null, never silently represented as zero.
    records=json.loads(frame.to_json(orient='records'))
    signature=sha256(json.dumps([platform,records],sort_keys=True).encode()).hexdigest()
    return {'schema':1,'platform':platform,'captured_at':now.isoformat(),
            'signature':signature,'players':records,
            'caveat':'Observed provider inputs, not independently verified forecasts. Only unstarted games included.'}


def grade_minutes(snapshot,actuals):
    """Actuals must explicitly supply Minutes including verified DNP=0.

    IDs must already be mapped to the snapshot's site IDs. Missing joins remain
    unmatched. Never infer a DNP from absence in a box score.
    """
    expected=pd.DataFrame(snapshot['players'])
    if not {'Player ID','Minutes'}<=set(actuals):raise ValueError('Actual Player ID and Minutes required')
    actual=actuals[['Player ID','Minutes']].copy();actual['Player ID']=actual['Player ID'].astype(str)
    expected['Player ID']=expected['Player ID'].astype(str)
    if actual['Player ID'].duplicated().any():raise ValueError('Duplicate actual player IDs')
    actual['Minutes']=pd.to_numeric(actual['Minutes'],errors='coerce')
    if actual['Minutes'].isna().any() or (~np.isfinite(actual['Minutes'])).any() or (actual['Minutes']<0).any():
        raise ValueError('Actual minutes must be verified nonnegative numbers')
    report=expected.merge(actual,on='Player ID',how='left',validate='one_to_one',indicator=True)
    report['Actual status']=np.where(report['_merge']=='both','matched','unmatched')
    report['Error']=report['Projected Minutes']-report['Minutes']
    matched=report['Actual status'].eq('matched')
    error=report.loc[matched,'Error']
    return {'report':report.drop(columns='_merge'),'matched':int(matched.sum()),
            'unmatched':int((~matched).sum()),'verified_zero_minutes':int(report['Minutes'].eq(0).sum()),
            'mae':float(error.abs().mean()) if len(error) else None,
            'bias':float(error.mean()) if len(error) else None,
            'caveat':'Actuals require verified final games and explicit site-ID mapping. Includes overtime minutes; not regulation-only validation.'}


def render_minutes_snapshots(st,pool,platform,show_controls=True):
    record_pregame_snapshot(st,pool,platform,'Applied inputs')
    history=st.session_state.setdefault('nba_minutes_snapshots',[])
    if not show_controls:return
    with st.expander('Advanced — pregame minutes validation',expanded=False):
        st.caption('Automatically records available minutes before each game starts. Saved with this browser’s slate workspace; download an archive for a separate backup. No simulation parameters are changed.')
        st.caption(f'{len(history)} saved snapshots. Missing actual players will stay unmatched, not become zeros.')
        workspace_download_button(st,'DOWNLOAD MINUTES SNAPSHOTS',json.dumps(history,indent=2).encode(),
            'Simmah_NBA_Minutes_Snapshots.json','application/json',key='nba_minutes_snapshot_download',on_click='ignore')



def record_pregame_snapshot(st,pool,platform,layer):
    """Capture observed unstarted inputs independently of diagnostics visibility.

    This records available inputs only; it does not manufacture native forecasts.
    Captured time is observation time, not the provider's publication time.
    """
    frozen=freeze_minutes(pool,platform)
    if frozen is None:return
    frozen['provenance']='Saved Pregame'
    frozen['layer']=layer
    frozen['source_metadata']={k:pool.attrs[k] for k in (
        'slate_date','rotowire_provider_evidence','draftdashboard_text',
        'fantasylabs_nba_ownership','saved_minutes_restored') if k in pool.attrs}
    frozen['signature']=sha256((frozen['signature']+layer+json.dumps(
        frozen['source_metadata'],sort_keys=True,default=str)).encode()).hexdigest()
    history=st.session_state.setdefault('nba_minutes_snapshots',[])
    if not any(x['signature']==frozen['signature'] for x in history):history.append(frozen)

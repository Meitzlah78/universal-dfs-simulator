"""Recover dated provider minutes lost during a feed outage; never estimate."""
import math
import pandas as pd
from simmah_nba_projections import team_key
from simmah_nba_game_strip import game_start


def restore_saved_minutes(pool,previous,day):
    required={'Player ID','Team','Opponent','Game Start','Projected Minutes','Minutes Source','Projection'}
    if not isinstance(previous,pd.DataFrame) or not required<=set(previous):return pool
    ids=previous['Player ID'].astype(str)
    if ids.duplicated().any() or set(ids)!=set(pool['Player ID'].astype(str)):return pool
    source=previous.set_index(ids);view=pool.copy()
    minutes=pd.to_numeric(view.get('Projected Minutes',pd.Series(index=view.index,dtype=float)),errors='coerce')
    candidates=pd.to_numeric(view['Projection'],errors='coerce').gt(0)&~minutes.eq(0)&~minutes.between(0,48,inclusive='right')
    if not candidates.any():return pool
    view['Projected Minutes']=minutes.astype(float)
    view['Minutes Source']=view['Minutes Source'].astype(object) if 'Minutes Source' in view else pd.Series(None,index=view.index,dtype=object)
    restored=[]
    for index in view.index[candidates]:
        row=view.loc[index];old=source.loc[str(row['Player ID'])]
        if (team_key(row['Team']),team_key(row['Opponent']))!=(team_key(old['Team']),team_key(old['Opponent'])):continue
        start=game_start([old['Game Start']])
        if start is None or start.date().isoformat()!=day:continue
        provenance=str(old['Minutes Source']).removeprefix('Last saved · ')
        if not provenance.startswith(('RotoWire','Uploaded')):continue
        try:
            value=float(old['Projected Minutes']);old_projection=float(old['Projection'])
            if not math.isfinite(value) or not 0<value<=48 or not math.isfinite(old_projection) or old_projection<=0:continue
        except (ValueError,TypeError):continue
        view.at[index,'Projected Minutes']=value
        view.at[index,'Minutes Source']='Last saved · '+provenance
        restored.append(str(row.get('Name',row['Player ID'])))
    if restored:view.attrs['saved_minutes_restored']=restored
    return view

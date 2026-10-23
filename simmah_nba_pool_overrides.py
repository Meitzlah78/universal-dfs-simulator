"""Explicit dated lineup exclusions, separate from the simulated rotation."""
import json
import math
from pathlib import Path
import pandas as pd
from simmah_nba_projections import player_key


def requested_pool_exclusions(pool, day, platform, *, restore_rotation=True):
    # Requested by the user for this slate; never infer inactivity from a
    # missing provider record and never carry this decision to another date.
    excluded={('sergio de larrea','DAL')} if (day,platform)==('2026-10-23','FanDuel') else set()
    mask=pool.apply(lambda row:player_key(row['Name'],row['Team']) in excluded,axis=1)
    names=pool.loc[mask,'Name'].astype(str).tolist()
    result=pool.copy()
    if not names:return result,names
    if 'User Excluded' not in result:result['User Excluded']=False
    result.loc[mask,'User Excluded']=True
    if 'Eligible' in result:result.loc[mask,'Eligible']=False
    if not restore_rotation:return result,names
    # A lineup fade does not mean the player is out of the real game. Keep
    # verified minutes in the rotation; do not redistribute them to teammates.
    snapshot=Path(__file__).parent/'data'/'nba_minutes_snapshots'/(day+'-reserve.json')
    try:
        saved=json.loads(snapshot.read_text())
        if saved.get('date')!=day or saved.get('source')!='RotoWire':return result,names
        records={player_key(r['name'],r['team']):r for r in saved['records']}
    except (OSError,ValueError,KeyError,TypeError):return result,names
    minutes=pd.to_numeric(result.get('Projected Minutes',pd.Series(index=result.index,dtype=float)),errors='coerce')
    for index in result.index[mask]:
        if pd.notna(minutes.loc[index]) and 0<=minutes.loc[index]<=48:continue
        row=result.loc[index];record=records.get(player_key(row['Name'],row['Team']))
        if not record or str(row.get('Opponent','')).upper()!=record['opponent']:continue
        if str(record.get('game_start',''))[:10]!=day:continue
        try:
            value=float(record['projected_minutes'])
            if not math.isfinite(value) or not 0<=value<=48:continue
        except (ValueError,TypeError,KeyError):continue
        result.at[index,'Projected Minutes']=value
        result.at[index,'Minutes Source']='RotoWire same-game minutes (saved DraftKings snapshot, '+day+')'
        result.attrs.setdefault('saved_minutes_restored',[]).append(str(row['Name']))
    return result,names

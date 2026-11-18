"""Reusable numerical slate inputs, separated from provider payloads and UI tables."""
from hashlib import sha256
import json
import numpy as np
import pandas as pd
from simmah_nba_frame import data_view

ROLE_COLUMNS=['Historical Shot Rate','Historical Assist Rate','Historical Rebound Rate',
              'Historical Steal Rate','Historical Block Rate']
INPUT_COLUMNS=['Player ID','Name','Position','Salary','Team','Opponent','Projection',
               'Projected Minutes','Injury Status','Eligible','Rotation Only',*ROLE_COLUMNS]
VERSION=1


def prepare_player_arrays(pool, cache=None):
    """Hash small input columns; reuse read-only arrays for unchanged DK/FD slates.

    The cache is an ordinary dict so workspace checkpoint/restore can preserve
    it losslessly. No provider payload or pandas object is stored in it.
    """
    values=data_view(pool)
    columns=[c for c in INPUT_COLUMNS if c in values]
    signature=sha256()
    signature.update(json.dumps([VERSION,pool.attrs.get('platform'),pool.attrs.get('slate_date'),
                                 columns,list(map(str,values[columns].dtypes))]).encode())
    signature.update(pd.util.hash_pandas_object(values[columns],index=False).to_numpy().tobytes())
    key=signature.hexdigest()
    if cache is not None and key in cache:
        result=cache[key]
        for array in result.values():
            if isinstance(array,np.ndarray):array.flags.writeable=False
        return result
    size=len(values)
    def numeric(column):
        if column not in values:return np.full(size,np.nan)
        return pd.to_numeric(values[column],errors='coerce').to_numpy(dtype=float,na_value=np.nan,copy=True)
    def text(column):
        return values[column].astype(str).to_numpy(copy=True) if column in values else np.full(size,'',dtype=object)
    from simmah_nba_projections import team_key
    result={'identity':key,'ids':text('Player ID'),'names':text('Name'),
            'position':text('Position'),'salary':numeric('Salary'),
            'team':np.array([team_key(v) for v in text('Team')]),
            'opponent':np.array([team_key(v) for v in text('Opponent')]),
            'projection':numeric('Projection'),'minutes':numeric('Projected Minutes'),
            'roles':np.column_stack([numeric(c) for c in ROLE_COLUMNS]),
            'injured':np.isin(np.char.upper(text('Injury Status').astype(str)),['O','OUT','IR','SUSPENDED']),
            'rotation_only':values['Rotation Only'].eq(True).fillna(False).to_numpy(dtype=bool,copy=True) if 'Rotation Only' in values else np.zeros(size,bool)}
    active=np.isfinite(result['projection'])&(result['projection']>0)&~result['injured']
    if 'Eligible' in values:
        active &= np.isin(np.char.lower(text('Eligible').astype(str)),['true','1'])
    if 'Projected Minutes' in values:
        minutes=result['minutes'];active &= np.isfinite(minutes)&(minutes>0)&(minutes<=48)
    result['active']=active
    for array in result.values():
        if isinstance(array,np.ndarray):array.flags.writeable=False
    if cache is not None:
        # Retain several recent versions without retaining obsolete slate data forever.
        if len(cache)>=4:cache.pop(next(iter(cache)))
        cache[key]=result
    return result

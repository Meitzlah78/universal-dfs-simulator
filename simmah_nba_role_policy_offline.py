"""Explicit offline archive/provider policy. Never auto-enables learned blending."""
from collections import Counter
import pandas as pd
import numpy as np
from simmah_nba_learning import load_approved,name_key,role_mask,ROLE_COLUMNS


def blend_stale_provider_roles(pool,slate_day,*,root=None,max_age_days=7,archive_weight=.25):
    """Keep fresh/unknown-age provider data; blend only dated stale provider rows.

    Approved archive roles must also have >=60 training minutes. Only accepted
    role components can change. Source projections and minute targets persist.
    Unknown freshness is reported, never treated as permission to overwrite.
    """
    if max_age_days<0 or not 0<archive_weight<=1:raise ValueError('Valid freshness threshold and blend weight required')
    model=load_approved(slate_day,root);out=pool.copy();reasons=Counter()
    for idx,row in out.iterrows():
        if not str(row.get('Role Rate Source','')).startswith('Individual historical rates'):
            reasons['not_provider_row']+=1;continue
        stamp=row.get('Role Rates As Of')
        try:asof=pd.Timestamp(stamp)
        except (TypeError,ValueError):asof=pd.NaT
        if pd.isna(asof):reasons['provider_freshness_unknown_kept']+=1;continue
        if asof.date()>pd.Timestamp(slate_day).date():raise ValueError('Provider role timestamp follows target slate')
        if (pd.Timestamp(slate_day).date()-asof.date()).days<=max_age_days:
            reasons['fresh_provider_kept']+=1;continue
        if model is None:reasons['no_approved_archive_kept']+=1;continue
        archive=model['players_by_name'].get(name_key(row.get('Name','')))
        if archive is None or archive.get('minutes',0)<60:reasons['insufficient_archive_history_kept']+=1;continue
        mask=role_mask(archive);prior=np.asarray(archive['rates'],float);provider=row[ROLE_COLUMNS].to_numpy(float)
        if prior.shape!=(5,) or not np.isfinite(prior).all() or not np.isfinite(provider).all() or (prior<0).any() or (provider<0).any():raise ValueError('Invalid role rate vector')
        if not mask.any():reasons['no_approved_components_kept']+=1;continue
        combined=provider*(1-archive_weight)+prior*archive_weight
        columns=[c for c,enabled in zip(ROLE_COLUMNS,mask) if enabled]
        out.loc[idx,columns]=combined[mask];out.at[idx,'Role Rate Source']='Offline stale-provider/archive blend '+model['version']
        reasons['stale_provider_blended']+=1
    out.attrs['offline_role_policy']={'live_enabled':False,'reasons':dict(reasons),'archive_weight':archive_weight,'maximum_provider_age_days':max_age_days,'status':'research policy; temporal component validation required'}
    return out

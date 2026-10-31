"""Offline Captain/MVP shortlist from historical all-slot ownership ranks."""
from datetime import date
import numpy as np
from simmah_single_exhaustive import prepare


def likely_special_players(pool,site,history,*,slate_date,ownership_column='Ownership',coverage=.99):
    if not np.isfinite(coverage) or not 0<coverage<=1:raise ValueError('Coverage must be in (0,1]')
    target_date=date.fromisoformat(slate_date)
    profiles=[p for p in history['profiles'] if p['site']==site]
    if not profiles:raise ValueError('No historical profile for this site')
    if any(date.fromisoformat(p['available_date'])>=target_date for p in profiles):
        raise ValueError('History must precede the current slate')
    eligible=prepare(pool,site)['indices']
    values=pool[ownership_column].to_numpy(dtype=float)
    if not np.isfinite(values[eligible]).all() or (values[eligible]<0).any() or values[eligible].sum()<=0:
        raise ValueError('Finite nonnegative projected all-slot ownership required')
    width=max(len(p['special_mass_by_rank']) for p in profiles)
    mass=np.zeros(width)
    for p in profiles:
        weights=np.asarray(p['special_mass_by_rank'],float)
        if not np.isfinite(weights).all() or (weights<0).any() or not np.isclose(weights.sum(),1):
            raise ValueError('Invalid historical role probabilities')
        # Each contest receives equal influence; big fields do not dominate.
        mass[:len(weights)]+=weights/len(profiles)
    rank_count=min(int(np.searchsorted(np.cumsum(mass),coverage))+1,len(eligible))
    if not rank_count:raise ValueError('No eligible players')
    order=eligible[np.argsort(-values[eligible],kind='stable')]
    threshold=values[order[rank_count-1]]
    chosen=order[values[order]>=threshold]  # preserve ties at cutoff
    return {'player_ids':pool['Player ID'].astype(str).iloc[chosen].tolist(),
        'coverage_requested':coverage,'historical_mass_within_selected_ranks':float(mass[:len(chosen)].sum()),
        'ownership_column':ownership_column,'rank_cutoff_including_ties':len(chosen),
        'history_sources':[{'sha256':p['source_sha256'],'entries':p['entries']} for p in profiles],
        'method':'historical special-role mass by all-slot ownership rank',
        'offline_only':True}

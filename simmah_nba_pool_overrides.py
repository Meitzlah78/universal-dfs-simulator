"""Explicit, dated user exclusions; uploaded salary bytes stay unchanged."""
from simmah_nba_projections import player_key


def requested_pool_exclusions(pool, day, platform):
    # Requested by the user for this slate; never infer inactivity from a
    # missing provider record and never carry this decision to another date.
    excluded={('sergio de larrea','DAL')} if (day,platform)==('2026-10-23','FanDuel') else set()
    mask=pool.apply(lambda row:player_key(row['Name'],row['Team']) in excluded,axis=1)
    names=pool.loc[mask,'Name'].astype(str).tolist()
    return pool.loc[~mask].reset_index(drop=True).copy(),names

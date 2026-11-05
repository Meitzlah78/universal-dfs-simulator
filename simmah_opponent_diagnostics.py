"""Optional projection diagnostics for roster-only opponent fields."""
import numpy as np
import pandas as pd


def numeric_column(frame, column):
    """Missing diagnostics stay unknown, with a Series on every path."""
    values=frame[column] if column in frame else pd.Series(np.nan,index=frame.index,dtype=float)
    return pd.to_numeric(values,errors='coerce').replace([np.inf,-np.inf],np.nan)


def with_roster_projections(field,pool,slots,multipliers=None):
    """Add diagnostic totals without modifying rosters or imputing unknowns."""
    result=field.copy()
    existing=numeric_column(result,'ProjectedPoints')
    if existing.notna().all():return result
    totals=pd.Series(np.nan,index=result.index,dtype=float)
    if (all(c in result for c in slots) and 'Name' in pool and 'Projection' in pool
            and not pool.Name.astype(str).duplicated().any()):
        lookup=pd.Series(numeric_column(pool,'Projection').to_numpy(),index=pool.Name.astype(str))
        values=result[slots].apply(lambda col:col.astype(str).map(lookup))
        weights=np.ones(len(slots)) if multipliers is None else np.asarray(multipliers,float)
        if weights.shape!=(len(slots),) or not np.isfinite(weights).all():
            raise ValueError('Projection multipliers must match roster slots')
        totals=values.mul(weights,axis=1).sum(axis=1,min_count=len(slots))
    result['ProjectedPoints']=existing.fillna(totals)
    return result

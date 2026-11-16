"""Validate external NBA ownership before using marginal field targets."""
import numpy as np
import pandas as pd
from simmah_nba_rules import rules_for

COLUMN='RotoWire Projected Own %'


def ownership_column(pool):
    from simmah_nba_ownership_upload import IMPORTED_COLUMN
    if 'DraftDashboard Projected Own %' in pool:
        return 'DraftDashboard Projected Own %'
    return IMPORTED_COLUMN if IMPORTED_COLUMN in pool else COLUMN


def active_players(pool):
    projection=pd.to_numeric(pool['Projection'],errors='coerce').to_numpy(float)
    active=np.isfinite(projection)&(projection>0)&~pool['Injury Status'].astype(str).str.upper().isin(['O','OUT','IR','SUSPENDED']).to_numpy()
    if 'Eligible' in pool:active &= pool['Eligible'].astype(str).str.casefold().isin(['true','1']).to_numpy()
    if 'Projected Minutes' in pool:
        minutes=pd.to_numeric(pool['Projected Minutes'],errors='coerce').to_numpy(float)
        active &= np.isfinite(minutes)&(minutes>0)&(minutes<=48)
    return active


def ownership_values(pool):
    """Preserve reported values; estimate only the small unreported residual."""
    column=ownership_column(pool)
    raw=pd.to_numeric(pool.get(column,pd.Series(np.nan,index=pool.index)),errors='coerce')
    meta=pool.attrs.get('fantasylabs_nba_ownership',{})
    if column!=COLUMN and meta.get('missing_ownership_policy')=='share unreported residual equally':
        missing=active_players(pool)&raw.isna().to_numpy()
        if missing.any():
            expected=100*len(rules_for(pool)['slots'])
            residual=max(0.,expected-float(meta['raw_total']))
            raw=raw.copy()
            raw.loc[missing]=residual/int(missing.sum())
    return raw


def validated_import(pool):
    """The original snapshot validation survives later player exclusions."""
    meta=pool.attrs.get('fantasylabs_nba_ownership',{})
    expected=100*len(rules_for(pool)['slots'])
    total=meta.get('raw_total')
    return (ownership_column(pool)!=COLUMN and meta.get('source') in {'FantasyLabs SimLabs','DraftDashboard'}
            and isinstance(total,(int,float)) and np.isfinite(total)
            and (abs(total-expected)<=expected*.01 or (meta.get('normalize_field_targets') and total>0)))


def field_ownership_inputs(pool):
    expected=100*len(rules_for(pool)['slots'])
    active=active_players(pool)
    column=ownership_column(pool)
    source='FantasyLabs imported slate ownership' if column!=COLUMN else 'RotoWire dedicated slate ownership'
    if column=='DraftDashboard Projected Own %':
        source='DraftDashboard imported slate ownership'
    raw=ownership_values(pool).to_numpy(float)
    if column!=COLUMN and pool.attrs.get('fantasylabs_nba_ownership',{}).get('missing_eligible_players'):
        source+=' with estimated residual ownership for unreported players'
    meta=pool.attrs.get('fantasylabs_nba_ownership',{})
    current_total=float(np.where(active,raw,0.).sum())
    baseline=meta.get('normalization_total',meta.get('raw_total',expected))
    reason=None
    if column!=COLUMN and meta.get('normalize_field_targets') and current_total>=baseline*.9:
        from simmah_nba_uploaded_ownership import normalize_targets
        try:
            target,total=normalize_targets(raw,active,expected)
        except ValueError as exc:
            reason=str(exc)
        else:
            return {'weights':target,'mode':'projected','source':source+f'; normalized estimate {total:.2f}% to {expected}%',
                    'raw_total':total,'expected_total':expected,'adjustment_factor':expected/total,
                    'conditional_estimate':True,'warnings':meta.get('warnings',[]),
                    'status':'Uploaded ownership normalized for field modeling; source values retained. Field fit still requires residual checks.'}
    if not active.any():reason='no eligible players'
    elif not np.isfinite(raw[active]).all():reason='missing dedicated ownership values'
    elif ((raw[active]<0)|(raw[active]>100)).any():reason='ownership outside 0–100%'
    target=np.where(active,raw,0.)
    total=float(target.sum()) if np.isfinite(target).all() else None
    coverage_complete=abs(float(np.nansum(raw))-expected)<=expected*.01
    conditional=(reason is None and validated_import(pool) and coverage_complete
                 and expected*.9<=total<expected*.99)
    if reason is None and abs(total-expected)>expected*.01 and not conditional:
        reason=f'eligible ownership total {total:.1f}% differs from {expected}% for this roster'
    if reason is None:
        target=target*(expected/total)
        if (target>100).any():reason='rounding adjustment would exceed 100%'
    if reason is None:
        adjustment=(f'conditional estimate after exclusions: {total:.1f}% scaled to {expected}%' if conditional
                    else f'total {total:.1f}% rounded to {expected}%')
        return {'weights':target,'mode':'projected','source':source+'; '+adjustment,
                'conditional_estimate':conditional,'adjustment_factor':expected/total,
                'raw_total':total,'expected_total':expected,'status':('Ownership targets proportionally redistributed after exclusions; estimated, not a new provider forecast. Field fit still requires residual checks.' if conditional else 'External ownership targets; field fit still requires residual checks.')}
    # A failed percentage-total check does not erase complete, bounded
    # popularity inputs. Keep their relative values without calling them
    # calibrated ownership percentages or scaling them into apparent validity.
    if active.any() and np.isfinite(raw[active]).all() and ((raw[active]>=0)&(raw[active]<=100)).all() and (raw[active]>0).any():
        return {'weights':np.where(active,raw,0.),'mode':'relative popularity',
            'source':source+' used only as relative popularity: '+reason,
            'raw_total':total,'expected_total':expected,
            'status':f'{source} totals {total:.1f}% versus {expected}% required. Field uses relative popularity; not calibrated projected ownership.'}
    return {'weights':np.ones(len(pool)), 'mode':'relative popularity',
        'source':'Scenario-derived estimate; external ownership not used: '+reason,
        'raw_total':total,'expected_total':expected,
        'status':'External ownership unavailable or inconsistent. Field uses equal weights on independent scenario-built legal rosters; not calibrated contest ownership.'}

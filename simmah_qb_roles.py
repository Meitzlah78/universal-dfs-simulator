"""Resolve projected same-team quarterbacks without inferring a starter from points."""
import pandas as pd


def quarterback_conflicts(pool):
    position=pool['Position'].astype(str).str.upper().str.strip().str.split('/').str[0]
    projection=pd.to_numeric(pool['Projection'],errors='coerce')
    qbs=pool.loc[position.eq('QB') & projection.gt(0)].copy()
    qbs['Team']=qbs['Team'].astype(str).str.strip().str.upper().replace({'LA':'LAR','JAC':'JAX','WSH':'WAS'})
    return {team:sorted(group['Name'].astype(str).unique().tolist()) for team,group in qbs.groupby('Team')
            if group['Name'].nunique()>1}


def resolve_quarterbacks(pool,starters):
    conflicts=quarterback_conflicts(pool)
    position=pool['Position'].astype(str).str.upper().str.strip().str.split('/').str[0]
    team=pool['Team'].astype(str).str.strip().str.upper().replace({'LA':'LAR','JAC':'JAX','WSH':'WAS'})
    keep=pd.Series(True,index=pool.index)
    for club,names in conflicts.items():
        starter=starters.get(club)
        if starter not in names:
            raise ValueError('Confirm starting QB for '+club+': '+', '.join(names))
        keep &= ~(position.eq('QB') & team.eq(club) & ~pool['Name'].astype(str).eq(starter))
    return pool.loc[keep].copy()

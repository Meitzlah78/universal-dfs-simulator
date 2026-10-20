"""Experimental pregame adapter from complete provider rotations and historical roles."""
import numpy as np
from simmah_nba_projections import team_key
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_markets import simulate_market_game

ROLE_COLUMNS=['Historical '+r+' Rate' for r in ('Shot','Assist','Rebound','Steal','Block')]


class PregameEngine:
    def __init__(self,pool,markets,rates,max_overtimes=4):
        if not isinstance(max_overtimes,int) or not 1<=max_overtimes<=10:raise ValueError("Explicit bounded overtime count required")
        self.max_overtimes=max_overtimes
        self.pool=pool.reset_index(drop=True).copy();self.rates=rates
        rates.validate()
        if self.pool['Player ID'].duplicated().any():raise ValueError('Duplicate player IDs')
        required={'Projected Minutes',*ROLE_COLUMNS}
        if not required<=set(pool.columns):raise ValueError('Missing NBA projected minutes or historical role rates')
        self.games=[];covered=set()
        for market in markets:
            pair=tuple(map(team_key,market['teams']))
            if len(pair)!=2 or pair[0]==pair[1] or covered&set(pair):raise ValueError('Duplicate NBA market teams')
            groups=[]
            for team,opp in (pair,pair[::-1]):
                group=self.pool[self.pool['Team'].map(team_key)==team]
                if group.empty or set(group['Opponent'].map(team_key))!={opp}:
                    raise ValueError('Market does not match uploaded game')
                injured=group['Injury Status'].astype(str).str.upper().isin(['OUT','O','IR','SUSPENDED'])
                projection=np.asarray(group['Projection'],float)
                active=group[np.isfinite(projection)&(projection>0)&~injured]
                minutes=np.asarray(active['Projected Minutes'],float)
                roles=active[ROLE_COLUMNS].to_numpy(float)
                if len(active)<5 or not np.isfinite(minutes).all() or (minutes<=0).any() or (minutes>48).any():
                    raise ValueError('Complete positive projected rotation required for '+team)
                if abs(minutes.sum()-240)>1e-6:
                    raise ValueError(f'{team} projected rotation totals {minutes.sum():.1f} minutes; 240 required')
                missing=~np.isfinite(roles).all(axis=1)|(roles<0).any(axis=1)
                if missing.any():
                    names=active.loc[missing,'Name'] if 'Name' in active else active.loc[missing,'Player ID']
                    raise ValueError('Missing historical player roles for '+team+': '+', '.join(names.astype(str)))
                if (roles.sum(axis=0)<=0).any():
                    raise ValueError('Unsupported historical role totals for '+team)
                groups.append((active.index.to_numpy(),minutes,roles))
            covered.update(pair);self.games.append((market,groups))
        if covered!=set(self.pool['Team'].map(team_key)):
            raise ValueError('Every uploaded NBA game needs complete market lines')
        self.last_report=[]

    def __call__(self,n,seed):
        if not isinstance(n,int) or n<1:raise ValueError('Positive simulation count required')
        output=np.zeros((n,len(self.pool)),np.float32);reports=[]
        for game_index,(market,groups) in enumerate(self.games):
            size=max(len(g[0]) for g in groups);profiles=np.zeros((2,size,5));rotations=[];overtime=[]
            for team,(ids,minutes,roles) in enumerate(groups):
                padded=np.zeros(size);padded[:len(ids)]=minutes
                profiles[team,:len(ids)]=roles
                overtime.append(np.stack([build_rotation(np.tile(padded*5/48,(n,1)),seed+game_index*97+team+10000+ot*11,team*size,period_minutes=5) for ot in range(self.max_overtimes)],axis=1))
                rotations.append(build_rotation(np.tile(padded,(n,1)),seed+game_index*97+team,team*size))
            result=simulate_market_game(np.stack(rotations,axis=1),profiles,[self.rates]*2,
                                         market['implied_points'],seed+game_index*97+3,overtime_rotations=np.stack(overtime,axis=1))
            for team,(ids,_,_) in enumerate(groups):
                output[:,ids]=result['scores'][:,team*size:team*size+len(ids)]
            reports.append({'teams':market['teams'],'calibration':result['market_calibration'],
                            'overtime_fraction':float((result['overtime_periods']>0).mean()),
                            'max_overtimes_supplied':self.max_overtimes,
                            'unresolved_tie_fraction':float(result['requires_overtime'].mean())})
        self.last_report=reports
        return output
